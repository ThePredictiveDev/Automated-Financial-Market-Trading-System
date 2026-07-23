"""Multi-venue router: NBBO aggregation and inter-market sweep across
independent MatchingEngine instances (one per venue)."""
from __future__ import annotations

import logging
import math
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..core.order import Order

logger = logging.getLogger(__name__)


class Venue:
    def __init__(self, name: str, engine, fee_bps: float = 0.0, latency_ms: int = 0) -> None:
        self.name = name
        self.engine = engine
        self.fee_bps = float(fee_bps)
        self.latency_ms = int(latency_ms)

    def top_of_book(self) -> Tuple[Optional[float], Optional[float]]:
        return self.engine.order_book.get_best_bid(), self.engine.order_book.get_best_ask()


class MarketRouter:
    def __init__(self) -> None:
        self.venues: Dict[str, Venue] = {}
        self.retry_attempts = 1
        self.retry_backoff_ms = 50
        self.inter_market_sweep = True
        self.retry_total = 0
        self.retry_failures = 0

    def add_venue(self, venue: Venue) -> None:
        self.venues[venue.name] = venue

    def nbbo(self) -> Dict[str, Any]:
        best_bid = best_ask = None
        venues = []
        for name, v in self.venues.items():
            bb, ba = v.top_of_book()
            venues.append({"name": name, "best_bid": bb, "best_ask": ba, "fee_bps": v.fee_bps, "latency_ms": v.latency_ms})
            if bb is not None:
                best_bid = bb if best_bid is None else max(best_bid, bb)
            if ba is not None:
                best_ask = ba if best_ask is None else min(best_ask, ba)
        return {"best_bid": best_bid, "best_ask": best_ask, "venues": venues}

    def _best_single_venue(self, order: Order, limit: float) -> Optional[Venue]:
        target, target_px = None, None
        for v in self.venues.values():
            bid, ask = v.top_of_book()
            if order.side == "buy":
                px = ask
                if px is None or px > limit:
                    continue
                eff = px * (1.0 + v.fee_bps / 10000.0)
                if target_px is None or eff < target_px:
                    target_px, target = eff, v
            else:
                px = bid
                if px is None or (order.type == "limit" and px < limit):
                    continue
                eff = px * (1.0 - v.fee_bps / 10000.0)
                if target_px is None or eff > target_px:
                    target_px, target = eff, v
        return target

    def _route_child(self, venue: Venue, order: Order, qty: int) -> None:
        child = Order(id=uuid.uuid4().hex, price=(float(order.price) if order.type == "limit" else 0.0),
                      quantity=qty, side=order.side, type=order.type, symbol=order.symbol,
                      tif=order.tif, post_only=False, owner_id=order.owner_id)
        if venue.latency_ms > 0:
            time.sleep(venue.latency_ms / 1000.0)
        attempts = 0
        while attempts < max(1, self.retry_attempts):
            try:
                venue.engine.match_order(child)
                return
            except Exception:
                attempts += 1
                self.retry_total += 1
                if attempts < self.retry_attempts:
                    time.sleep(self.retry_backoff_ms / 1000.0)
                else:
                    self.retry_failures += 1
                    raise

    def route_order(self, order: Order) -> None:
        if not self.venues:
            raise RuntimeError("No venues configured")
        limit = float(order.price) if order.type == "limit" else (math.inf if order.side == "buy" else 0.0)

        if not self.inter_market_sweep:
            target = self._best_single_venue(order, limit) or next(iter(self.venues.values()))
            self._route_child(target, order, int(order.quantity))
            return

        remaining = int(order.quantity)
        visited = 0
        while remaining > 0 and visited < len(self.venues):
            target = self._best_single_venue(order, limit)
            if target is None:
                break
            try:
                eff = limit if order.type == "limit" else (math.inf if order.side == "buy" else 0.0)
                avail = target.engine._available_depth(order.side, eff)
            except Exception:
                avail = remaining
            qty = max(0, min(remaining, int(avail)))
            if qty <= 0:
                break
            try:
                self._route_child(target, order, qty)
                remaining -= qty
            except Exception:
                logger.warning("Venue %s failed to fill %s shares of order %s", target.name, qty, order.id)
            visited += 1
