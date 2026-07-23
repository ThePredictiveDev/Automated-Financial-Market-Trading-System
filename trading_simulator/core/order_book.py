"""In-memory limit order book for a single symbol.

Fix vs. the original script: every mutating/reading method now takes an
internal RLock. The original OrderBook had *no* locking of its own -- only
MatchingEngine wrapped its calls in a lock, so any strategy or market maker
that read `matching_engine.order_book` directly (a pattern the project's own
README recommends for custom traders) was unsynchronized in live/threaded
mode. MatchingEngine still owns a coarser lock for multi-step operations that
must be atomic across several book calls, but the book is now safe to poke at
directly too.
"""
from __future__ import annotations

import bisect
import logging
import threading
from collections import deque
from typing import Deque, Dict, List, Optional

import pandas as pd

from .instruments import InstrumentRegistry, DEFAULT_REGISTRY
from .order import Order

logger = logging.getLogger(__name__)


class OrderBook:
    def __init__(self, instruments: Optional[InstrumentRegistry] = None) -> None:
        self.instruments = instruments or DEFAULT_REGISTRY
        self.bids: Dict[float, Deque[Order]] = {}
        self.asks: Dict[float, Deque[Order]] = {}
        self.order_map: Dict[str, Order] = {}
        self._bid_prices: List[float] = []   # descending
        self._ask_prices: List[float] = []   # ascending
        self._lock = threading.RLock()

    # -- mutation -----------------------------------------------------
    def add_order(self, order: Order) -> None:
        with self._lock:
            order.price = self.instruments.normalize_price(order.price, order.symbol)
            if order.side == "buy":
                if order.price not in self.bids:
                    self.bids[order.price] = deque()
                    pos = bisect.bisect_left([-p for p in self._bid_prices], -order.price)
                    self._bid_prices.insert(pos, order.price)
                self.bids[order.price].append(order)
            else:
                if order.price not in self.asks:
                    self.asks[order.price] = deque()
                    pos = bisect.bisect_left(self._ask_prices, order.price)
                    self._ask_prices.insert(pos, order.price)
                self.asks[order.price].append(order)
            self.order_map[order.id] = order

    def remove_order(self, order_id: str) -> None:
        with self._lock:
            order = self.order_map.get(order_id)
            if order is None:
                return
            book = self.bids if order.side == "buy" else self.asks
            prices = self._bid_prices if order.side == "buy" else self._ask_prices
            queue = book.get(order.price)
            if queue is not None and order in queue:
                queue.remove(order)
                if not queue:
                    del book[order.price]
                    try:
                        prices.remove(order.price)
                    except ValueError:
                        pass
            del self.order_map[order_id]

    def cancel_order(self, order_id: str) -> None:
        with self._lock:
            if order_id in self.order_map:
                self.remove_order(order_id)
                logger.info("Order %s cancelled.", order_id)
            else:
                # Not necessarily a bug: a resting order routinely disappears
                # from the book on its own after a full fill (e.g. a market
                # maker's own quote crossing immediately), so a subsequent
                # cancel of that same id is an expected no-op, not a fault.
                # Logged at INFO rather than WARNING to avoid alarm fatigue
                # from a benign, common race between "fill" and "cancel".
                logger.info("Order %s not found for cancellation (already filled or cancelled).", order_id)

    def cancel_orders_by_owner(self, owner_id: str) -> int:
        with self._lock:
            to_cancel = [oid for oid, o in self.order_map.items() if getattr(o, "owner_id", None) == owner_id]
            for oid in to_cancel:
                self.cancel_order(oid)
            return len(to_cancel)

    def modify_order(self, order_id: str, new_quantity: Optional[int] = None, new_price: Optional[float] = None) -> None:
        with self._lock:
            order = self.order_map.get(order_id)
            if order is None:
                logger.warning("Order %s not found for modification.", order_id)
                return
            self.remove_order(order_id)
            if new_quantity is not None:
                order.quantity = int(new_quantity)
            if new_price is not None:
                order.price = float(new_price)
            self.add_order(order)
            logger.info("Order %s modified.", order_id)

    # -- reads ----------------------------------------------------------
    def get_best_bid(self) -> Optional[float]:
        with self._lock:
            while self._bid_prices:
                top = self._bid_prices[0]
                if self.bids.get(top):
                    return top
                self._bid_prices.pop(0)
            return None

    def get_best_ask(self) -> Optional[float]:
        with self._lock:
            while self._ask_prices:
                top = self._ask_prices[0]
                if self.asks.get(top):
                    return top
                self._ask_prices.pop(0)
            return None

    def depth_at(self, side: str, price: float) -> int:
        with self._lock:
            book = self.bids if side == "buy" else self.asks
            q = book.get(price)
            return sum(o.quantity for o in q) if q else 0

    def bids_to_dataframe(self) -> pd.DataFrame:
        with self._lock:
            rows = [
                {"Order ID": o.id, "Price": o.price, "Quantity": o.quantity}
                for price in sorted(self.bids.keys(), reverse=True)
                for o in self.bids[price]
            ]
        return pd.DataFrame(rows)

    def asks_to_dataframe(self) -> pd.DataFrame:
        with self._lock:
            rows = [
                {"Order ID": o.id, "Price": o.price, "Quantity": o.quantity}
                for price in sorted(self.asks.keys())
                for o in self.asks[price]
            ]
        return pd.DataFrame(rows)

    def display_order_book(self) -> None:
        bids_df = self.bids_to_dataframe()
        asks_df = self.asks_to_dataframe()
        logger.info("Bid Side:\n%s", bids_df.to_string(index=False) if not bids_df.empty else "<empty>")
        logger.info("Ask Side:\n%s", asks_df.to_string(index=False) if not asks_df.empty else "<empty>")
