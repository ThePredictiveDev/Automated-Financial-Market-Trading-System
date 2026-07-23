"""Deterministic replay: rebuild an engine/book from a recorded events.csv."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import pandas as pd

from ..core.order import Order
from ..core.order_book import OrderBook
from ..core.matching_engine import MatchingEngine

logger = logging.getLogger(__name__)


class ReplayRunner:
    def __init__(self, events: List[Dict[str, Any]]) -> None:
        self.events = events

    def run(self) -> Dict[str, Any]:
        order_book = OrderBook()
        engine = MatchingEngine(order_book)
        count_new = count_cancel = 0

        for e in self.events:
            ts = pd.to_datetime(e.get("timestamp"), utc=True, errors="coerce")
            if isinstance(ts, pd.Timestamp) and ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            if isinstance(ts, pd.Timestamp):
                engine.set_time(ts)

            ev = e.get("event")
            if ev == "NEW":
                try:
                    order = Order(
                        id=str(e.get("order_id")), symbol=str(e.get("symbol")), side=str(e.get("side")),
                        type=str(e.get("type") or "limit"), price=float(e.get("price") or 0.0),
                        quantity=int(e.get("quantity") or 0), owner_id=e.get("extra", {}).get("owner", "replay"),
                    )
                    engine.match_order(order)
                    count_new += 1
                except (ValueError, KeyError):
                    logger.warning("Skipping malformed NEW event: %r", e, exc_info=True)
            elif ev == "CANCEL":
                try:
                    engine.cancel_order(str(e.get("order_id")))
                    count_cancel += 1
                except (ValueError, KeyError):
                    logger.warning("Skipping malformed CANCEL event: %r", e, exc_info=True)
            # EXEC events are not replayed as input; the engine regenerates its own.

        return {"orders": count_new, "cancels": count_cancel, "engine": engine}
