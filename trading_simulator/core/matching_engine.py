"""Price-time-priority matching engine for a single symbol's OrderBook.

Two correctness fixes relative to the original monolithic script:

1. Self-trade prevention no longer corrupts price-time priority. The
   original used `queue.rotate(-1)` to skip a same-owner resting order,
   which permanently moved that order to the back of the queue -- so every
   self-trade skip silently stole priority from someone else's order at that
   price level. Here, skipped same-owner orders are buffered and restored to
   the *front* of the queue in their original relative order once we're done,
   so nobody's priority is disturbed.

2. Fill-or-Kill pre-checks now exclude the incoming order's own resting
   liquidity from the "available depth" calculation. Previously a FOK order
   could count its own resting orders as available depth, pass the pre-check,
   and then fail to actually fill against them (self-trade prevention blocks
   that), producing an accept/execute mismatch.

Known limitation (documented, not silently papered over): finding "does this
price level have a non-self-owner order" is an O(depth) scan per level. For
book depths seen in backtests/paper trading this is fine; a true low-latency
venue would maintain a per-price-level owner-count instead. Left as a
documented follow-up rather than added speculative complexity.

Locked/crossed book guard: self-trade prevention can leave a residual whose
limit would rest at (or through) the opposite best quote when that level is
entirely own orders. Resting that residual creates best_bid == best_ask
(spread 0). Continuous trading forbids a locked book, so residuals that
would lock or cross are discarded instead of rested. See
`_would_lock_or_cross`.
"""
from __future__ import annotations

import logging
import math
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

import pandas as pd

from .execution import Execution
from .instruments import InstrumentRegistry, DEFAULT_REGISTRY
from .order import Order

logger = logging.getLogger(__name__)


class MatchingEngine:
    def __init__(self, order_book, instruments: Optional[InstrumentRegistry] = None) -> None:
        self.order_book = order_book
        self.instruments = instruments or order_book.instruments or DEFAULT_REGISTRY
        self._lock = threading.RLock()
        self._trade_subscribers: List[Callable[[Execution], None]] = []
        self.risk_manager = None  # type: ignore[var-annotated]

        # Latency/slippage modeling (used by backtests)
        self.latency_ms: int = 0
        self.slippage_bps_per_100_shares: float = 0.0
        self._current_time: Optional[pd.Timestamp] = None
        self._delayed_orders: List[Tuple[pd.Timestamp, Order]] = []
        # Reject orders above this size (protects the L2 book from corrupt/runaway qty).
        self.max_order_qty: int = 100_000

        # Price band protection
        self.price_band_bps: float = 0.0
        self.band_reference: str = "mid"  # 'mid' or 'last'
        self._last_trade_price_by_symbol: Dict[str, float] = {}

        # Auction state
        self.auction_mode: Optional[str] = None
        self._auction_orders: List[Order] = []

        # Fees/rebates (bps)
        self.taker_fee_bps: float = 0.0
        self.maker_rebate_bps: float = 0.0

        # Optional loggers (duck-typed: must expose log_new_order/log_cancel/log_execution)
        self.event_logger = None
        self.audit_logger = None
        self.tca_logger = None

        self._halted: set = set()

        # Optional submission queue for a producer/consumer concurrency model
        self.use_queue: bool = False
        self.queue_max: int = 10000
        self._order_queue: Deque[Order] = deque()
        self._queue_cond = threading.Condition(self._lock)
        self._loop_running: bool = False
        self._loop_thread: Optional[threading.Thread] = None

        # Snapshotting
        self.snapshot_interval_sec: int = 0
        self.snapshot_dir: Optional[str] = None
        self._snapshot_thread: Optional[threading.Thread] = None
        self._snapshot_running: bool = False

        self._last_exec_by_symbol: Dict[str, Execution] = {}

    # -- subscriptions ----------------------------------------------------
    def subscribe_trades(self, callback: Callable[[Execution], None]) -> None:
        self._trade_subscribers.append(callback)

    def _emit_trade(self, execution: Execution) -> None:
        self._last_trade_price_by_symbol[execution.symbol] = float(execution.price)
        try:
            if self.event_logger is not None:
                bb = self.order_book.get_best_bid()
                ba = self.order_book.get_best_ask()
                self.event_logger.log_execution(execution, best_bid=bb, best_ask=ba)
            if self.audit_logger is not None:
                self.audit_logger.log_execution(execution)
        except Exception:
            logger.warning("Execution logging failed for trade %s", execution.trade_id, exc_info=True)

        for cb in list(self._trade_subscribers):
            try:
                cb(execution)
            except Exception:
                logger.exception("Trade subscriber raised for trade %s", execution.trade_id)

        self._log_tca(execution)

    def _log_tca(self, execution: Execution) -> None:
        if self.tca_logger is None:
            return
        try:
            mid = self._mid_price()
            last = self.get_last_trade_price(execution.symbol)
            slip_mid = None
            if mid is not None:
                slip_mid = (execution.price - mid) / mid * 10000.0 if execution.side == "buy" else (mid - execution.price) / mid * 10000.0
            slip_last = None
            if last:
                slip_last = (execution.price - last) / last * 10000.0 if execution.side == "buy" else (last - execution.price) / last * 10000.0
            self.tca_logger.log_tca(execution.timestamp, execution.symbol, execution.side, float(execution.price), mid, last, slip_mid, slip_last)
            prev = self._last_exec_by_symbol.get(execution.symbol)
            if prev is not None:
                next_price = float(execution.price)
                adverse = (prev.side == "buy" and next_price < float(prev.price)) or (prev.side == "sell" and next_price > float(prev.price))
                self.tca_logger.log_tca_adv(prev.timestamp, prev.symbol, prev.side, float(prev.price), next_price, bool(adverse))
            self._last_exec_by_symbol[execution.symbol] = execution
        except Exception:
            logger.warning("TCA logging failed for trade %s", execution.trade_id, exc_info=True)

    # -- pricing helpers ----------------------------------------------------
    def _reference_price(self, symbol: str) -> Optional[float]:
        if self.band_reference == "last":
            return self._last_trade_price_by_symbol.get(symbol)
        bb = self.order_book.get_best_bid()
        ba = self.order_book.get_best_ask()
        if bb is not None and ba is not None:
            return float((bb + ba) / 2.0)
        return self._last_trade_price_by_symbol.get(symbol)

    def _mid_price(self) -> Optional[float]:
        bb = self.order_book.get_best_bid()
        ba = self.order_book.get_best_ask()
        if bb is None or ba is None:
            return None
        return float((bb + ba) / 2.0)

    def _within_price_band(self, order: Order) -> bool:
        if self.price_band_bps <= 0 or order.type != "limit":
            return True
        ref = self._reference_price(order.symbol)
        if not ref or ref <= 0:
            return True
        dev_bps = abs(order.price - ref) / ref * 10000.0
        return dev_bps <= self.price_band_bps

    def get_last_trade_price(self, symbol: str) -> Optional[float]:
        return self._last_trade_price_by_symbol.get(symbol)

    def _available_depth(self, side: str, limit_price: float, exclude_owner_id: Optional[str] = None) -> int:
        """Opposing quantity available up to limit_price, excluding any
        resting quantity owned by exclude_owner_id (used for FOK pre-checks
        so we don't count liquidity self-trade prevention will skip over)."""
        total = 0
        if side == "buy":
            prices, book = self.order_book._ask_prices, self.order_book.asks
            in_range = lambda px: px <= limit_price
        else:
            prices, book = self.order_book._bid_prices, self.order_book.bids
            in_range = lambda px: px >= limit_price
        for px in list(prices):
            if not in_range(px):
                break
            q = book.get(px)
            if not q:
                continue
            for o in q:
                if exclude_owner_id is not None and getattr(o, "owner_id", None) == exclude_owner_id:
                    continue
                total += int(getattr(o, "quantity", 0))
        return total

    # -- time / latency -----------------------------------------------------
    def set_time(self, current_time: pd.Timestamp) -> None:
        self._current_time = current_time

    def process_delayed_orders(self, upto_time: pd.Timestamp) -> None:
        with self._lock:
            if not self._delayed_orders:
                return
            self._delayed_orders.sort(key=lambda x: x[0])
            ready = []
            while self._delayed_orders and self._delayed_orders[0][0] <= upto_time:
                ready.append(self._delayed_orders.pop(0))
        for _, order in ready:
            self._direct_match(order)

    # -- halts ----------------------------------------------------------
    def halt(self, symbol: str) -> None:
        with self._lock:
            self._halted.add(symbol)

    def resume(self, symbol: str) -> None:
        with self._lock:
            self._halted.discard(symbol)

    # -- order entry ----------------------------------------------------
    def match_order(self, incoming_order: Order) -> None:
        incoming_order.validate()
        
        # Safety clamp: reject astronomical quantities that could be caused by numerical instability
        # or divergent feedback loops in bot order sizing.
        if incoming_order.quantity > 1_000_000:
            logger.warning("Order %s rejected: quantity %d exceeds absolute safety limit", incoming_order.id, incoming_order.quantity)
            return
            
        with self._lock:
            if incoming_order.symbol in self._halted and self.auction_mode is None:
                logger.warning("Order %s rejected: trading halted for %s", incoming_order.id, incoming_order.symbol)
                return
            if self.risk_manager is not None and not self.risk_manager.allow_order(incoming_order):
                logger.warning("Order %s rejected by risk manager", incoming_order.id)
                return
            if not self.instruments.is_market_open(incoming_order.symbol, self._current_time or pd.Timestamp.now(tz="UTC")):
                logger.warning("Order %s rejected: market closed for %s", incoming_order.id, incoming_order.symbol)
                return

            if self.auction_mode is not None:
                if incoming_order.auction_only and incoming_order.auction_phase in (None, self.auction_mode):
                    self._auction_orders.append(incoming_order)
                    return
                if not incoming_order.auction_only:
                    if incoming_order.type == "limit":
                        self.order_book.add_order(incoming_order)
                    else:
                        incoming_order.auction_only = True
                        incoming_order.auction_phase = self.auction_mode
                        self._auction_orders.append(incoming_order)
                    return

            try:
                if self.event_logger is not None:
                    self.event_logger.log_new_order(incoming_order)
                if self.audit_logger is not None:
                    self.audit_logger.log_new_order(incoming_order)
            except Exception:
                logger.warning("Order-accept logging failed for %s", incoming_order.id, exc_info=True)

            if self.latency_ms > 0 and self._current_time is not None:
                available_at = self._current_time + pd.Timedelta(milliseconds=int(self.latency_ms))
                self._delayed_orders.append((available_at, incoming_order))
                return
            self._direct_match(incoming_order)

    def submit_order(self, incoming_order: Order) -> None:
        if not self.use_queue:
            self.match_order(incoming_order)
            return
        with self._lock:
            if len(self._order_queue) >= self.queue_max:
                logger.warning("Order queue full; rejecting order %s", incoming_order.id)
                return
            self._order_queue.append(incoming_order)
            self._queue_cond.notify()

    def start_loop(self) -> None:
        if not self.use_queue:
            return
        with self._lock:
            if self._loop_running:
                return
            self._loop_running = True
            self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._loop_thread.start()

    def stop_loop(self) -> None:
        with self._lock:
            self._loop_running = False
            self._queue_cond.notify_all()
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=3)
            self._loop_thread = None

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if not self._loop_running:
                    break
                while self._loop_running and not self._order_queue:
                    self._queue_cond.wait(timeout=0.5)
                    if not self._loop_running:
                        return
                if not self._order_queue:
                    continue
                order = self._order_queue.popleft()
            try:
                self.match_order(order)
            except Exception:
                logger.exception("Engine loop error processing order %s", getattr(order, "id", "?"))

    def cancel_order(self, order_id: str) -> None:
        with self._lock:
            self.order_book.cancel_order(order_id)
            try:
                if self.event_logger is not None:
                    self.event_logger.log_cancel(order_id)
                if self.audit_logger is not None:
                    self.audit_logger.log_cancel(order_id)
            except Exception:
                logger.warning("Cancel logging failed for %s", order_id, exc_info=True)

    def cancel_orders_by_owner(self, owner_id: str) -> int:
        with self._lock:
            return self.order_book.cancel_orders_by_owner(owner_id)

    # -- matching core ----------------------------------------------------
    def _direct_match(self, order: Order) -> None:
        if order.type == "limit":
            order.price = self.instruments.normalize_price(order.price, order.symbol)
        order.quantity = self.instruments.normalize_quantity(order.quantity, order.symbol)
        if order.quantity <= 0:
            logger.warning("Order %s rejected after lot normalization (qty<=0)", order.id)
            return
        # Guard against runaway strategy sizing / corrupt inputs poisoning the book.
        # Demo bots and the user risk gate stay well below this; anything larger is
        # treated as invalid rather than rested as multi-trillion "depth".
        max_qty = getattr(self, "max_order_qty", 100_000)
        if max_qty and order.quantity > max_qty:
            logger.warning(
                "Order %s rejected: quantity %s exceeds engine max_order_qty %s",
                order.id, order.quantity, max_qty,
            )
            return
        if order.type == "limit" and not self._within_price_band(order):
            logger.warning("Order %s rejected by price band: price=%s symbol=%s", order.id, order.price, order.symbol)
            return

        if order.tif == "FOK":
            if order.side == "buy":
                eff = order.price if order.type == "limit" else math.inf
                avail = self._available_depth("buy", eff, exclude_owner_id=order.owner_id)
            else:
                eff = order.price if order.type == "limit" else 0.0
                avail = self._available_depth("sell", eff, exclude_owner_id=order.owner_id)
            if avail < order.quantity:
                logger.info("FOK order %s cancelled: insufficient depth (need %s, have %s)", order.id, order.quantity, avail)
                return

        if order.side == "buy":
            self._match_buy_order(order)
        else:
            self._match_sell_order(order)

    def _has_contra_owner(self, queue: Deque[Order], owner_id: Optional[str]) -> bool:
        return any(getattr(o, "owner_id", None) != owner_id and getattr(o, "quantity", 0) > 0 for o in queue)

    def _would_lock_or_cross(self, order: Order) -> bool:
        """True if resting this limit would create best_bid >= best_ask."""
        if order.side == "buy":
            best_ask = self.order_book.get_best_ask()
            return best_ask is not None and order.price >= best_ask
        best_bid = self.order_book.get_best_bid()
        return best_bid is not None and order.price <= best_bid

    def unlock_self_locked_book(self) -> int:
        """Clear an already-locked book caused by same-owner bids and asks.

        Cancels ask-side orders at the touch whose owner also rests on the
        bid touch (and vice-versa on the next pass). Safe no-op when the
        book is not locked. Returns the number of cancelled orders.
        """
        cancelled = 0
        with self._lock:
            for _ in range(1000):
                bb = self.order_book.get_best_bid()
                ba = self.order_book.get_best_ask()
                if bb is None or ba is None or bb < ba:
                    break
                bid_q = list(self.order_book.bids.get(bb, ()))
                ask_q = list(self.order_book.asks.get(ba, ()))
                bid_owners = {getattr(o, "owner_id", None) for o in bid_q}
                ask_owners = {getattr(o, "owner_id", None) for o in ask_q}
                conflict = bid_owners & ask_owners
                to_cancel = [
                    o.id for o in ask_q
                    if getattr(o, "owner_id", None) in conflict
                ]
                if not to_cancel:
                    to_cancel = [
                        o.id for o in bid_q
                        if getattr(o, "owner_id", None) in conflict
                    ]
                if not to_cancel:
                    # Different owners at a locked touch should have matched;
                    # cancel one ask lot so the book can make progress.
                    if ask_q:
                        to_cancel = [ask_q[0].id]
                    elif bid_q:
                        to_cancel = [bid_q[0].id]
                    else:
                        break
                for oid in to_cancel:
                    self.order_book.cancel_order(oid)
                    cancelled += 1
        return cancelled

    def _match_buy_order(self, order: Order) -> None:
        effective_limit = order.price if order.type == "limit" else math.inf
        iters = 0
        while order.quantity > 0:
            iters += 1
            if iters > 100_000:
                logger.warning("Buy match loop cap reached for %s; aborting to avoid runaway.", order.id)
                break
            best_ask_price = None
            for px in list(self.order_book._ask_prices):
                q = self.order_book.asks.get(px)
                if q and self._has_contra_owner(q, order.owner_id):
                    best_ask_price = px
                    break
            if best_ask_price is None or effective_limit < best_ask_price:
                break
            order = self._execute_order(order, best_ask_price, "sell")

        if order.quantity > 0 and order.type == "limit":
            if order.tif in ("FOK", "IOC"):
                return
            best_ask = self.order_book.get_best_ask()
            if order.post_only and best_ask is not None and order.price >= best_ask:
                return
            # Do not rest a residual that would lock/cross (common after STP
            # skips same-owner asks at the touch). Continuous books require
            # best_bid < best_ask.
            if self._would_lock_or_cross(order):
                logger.info(
                    "Discarding residual buy %s @ %s: would lock/cross book (best ask %s)",
                    order.id, order.price, best_ask,
                )
                return
            self.order_book.add_order(order)

    def _match_sell_order(self, order: Order) -> None:
        effective_limit = order.price if order.type == "limit" else 0.0
        iters = 0
        while order.quantity > 0:
            iters += 1
            if iters > 100_000:
                logger.warning("Sell match loop cap reached for %s; aborting to avoid runaway.", order.id)
                break
            best_bid_price = None
            for px in list(self.order_book._bid_prices):
                q = self.order_book.bids.get(px)
                if q and self._has_contra_owner(q, order.owner_id):
                    best_bid_price = px
                    break
            if best_bid_price is None or effective_limit > best_bid_price:
                break
            order = self._execute_order(order, best_bid_price, "buy")

        if order.quantity > 0 and order.type == "limit":
            if order.tif in ("FOK", "IOC"):
                return
            best_bid = self.order_book.get_best_bid()
            if order.post_only and best_bid is not None and order.price <= best_bid:
                return
            if self._would_lock_or_cross(order):
                logger.info(
                    "Discarding residual sell %s @ %s: would lock/cross book (best bid %s)",
                    order.id, order.price, best_bid,
                )
                return
            self.order_book.add_order(order)

    def _apply_slippage(self, side: str, base_price: float, quantity: int) -> float:
        if self.slippage_bps_per_100_shares <= 0:
            return base_price
        units = max(1.0, quantity / 100.0)
        bps = self.slippage_bps_per_100_shares * units
        sign = 1.0 if side == "buy" else -1.0
        
        # Ensure price never drops below one tick size even with extreme slippage
        min_price = self.instruments.tick_size("") # Registry will return default 0.01
        slippage_price = float(base_price * (1.0 + sign * (bps / 10000.0)))
        return max(min_price, slippage_price)

    def _execute_order(self, order: Order, price: float, counter_side: str) -> Order:
        """Execute the incoming order against resting liquidity at `price`.

        Self-trade prevention: same-owner resting orders are skipped without
        being consumed, buffered in `skipped`, and restored to the *front* of
        the queue (in original relative order) before we return -- so their
        priority relative to each other and to orders behind them is
        unchanged. This replaces the original `queue.rotate(-1)` approach,
        which permanently reordered the queue on every skip.
        """
        counter_orders = self.order_book.asks if counter_side == "sell" else self.order_book.bids
        queue = counter_orders.get(price)
        if queue is None:
            return order

        skipped: List[Order] = []
        while order.quantity > 0 and queue:
            resting = queue[0]

            if getattr(resting, "owner_id", None) == getattr(order, "owner_id", None):
                skipped.append(queue.popleft())
                continue

            if getattr(resting, "expires_at", None) is not None and pd.Timestamp.now(tz="UTC") >= pd.to_datetime(resting.expires_at):
                queue.popleft()
                self.order_book.order_map.pop(resting.id, None)
                continue

            if resting.quantity > order.quantity:
                resting.quantity -= order.quantity
                trade_qty = order.quantity
                self.order_book.order_map[resting.id] = resting
                trade_price = self._apply_slippage(order.side, price, trade_qty)
                self._emit_trade(Execution(
                    trade_id=uuid.uuid4().hex, price=trade_price, quantity=trade_qty,
                    taker_order_id=order.id, maker_order_id=resting.id, symbol=resting.symbol,
                    side=order.side, timestamp=pd.Timestamp.now(tz="UTC"),
                    taker_owner_id=getattr(order, "owner_id", None), maker_owner_id=getattr(resting, "owner_id", None),
                ))
                order.quantity = 0
            else:
                consumed = resting.quantity
                queue.popleft()
                self.order_book.order_map.pop(resting.id, None)
                trade_price = self._apply_slippage(order.side, price, consumed)
                self._emit_trade(Execution(
                    trade_id=uuid.uuid4().hex, price=trade_price, quantity=consumed,
                    taker_order_id=order.id, maker_order_id=resting.id, symbol=resting.symbol,
                    side=order.side, timestamp=pd.Timestamp.now(tz="UTC"),
                    taker_owner_id=getattr(order, "owner_id", None), maker_owner_id=getattr(resting, "owner_id", None),
                ))
                order.quantity -= consumed

        # Restore skipped same-owner orders to the front, in original order,
        # so their relative priority is exactly as it was before this call.
        for o in reversed(skipped):
            queue.appendleft(o)

        if not queue:
            counter_orders.pop(price, None)
            prices = self.order_book._ask_prices if counter_side == "sell" else self.order_book._bid_prices
            try:
                prices.remove(price)
            except ValueError:
                pass
        return order

    # -- snapshotting -----------------------------------------------------
    def depth_snapshot(self, top_n: int = 5) -> Dict[str, List[Tuple[float, int]]]:
        with self._lock:
            bids = [(px, sum(o.quantity for o in self.order_book.bids[px])) for px in list(self.order_book._bid_prices)[:top_n] if self.order_book.bids.get(px)]
            asks = [(px, sum(o.quantity for o in self.order_book.asks[px])) for px in list(self.order_book._ask_prices)[:top_n] if self.order_book.asks.get(px)]
            return {"bids": bids, "asks": asks}

    def _snapshot_once(self) -> None:
        if not self.snapshot_dir:
            return
        import json
        import os
        os.makedirs(self.snapshot_dir, exist_ok=True)
        snap = {"bids": [], "asks": []}
        with self._lock:
            for px in self.order_book._bid_prices:
                q = self.order_book.bids.get(px)
                if q:
                    snap["bids"].append({"price": px, "orders": [{"id": o.id, "qty": o.quantity, "owner": o.owner_id, "symbol": o.symbol, "side": "buy"} for o in q]})
            for px in self.order_book._ask_prices:
                q = self.order_book.asks.get(px)
                if q:
                    snap["asks"].append({"price": px, "orders": [{"id": o.id, "qty": o.quantity, "owner": o.owner_id, "symbol": o.symbol, "side": "sell"} for o in q]})
        path = os.path.join(self.snapshot_dir, f"snapshot_{int(time.time())}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(snap, f)
        except OSError:
            logger.warning("Failed to write snapshot to %s", path, exc_info=True)

    def snapshot_now(self) -> None:
        self._snapshot_once()

    def _snapshot_loop(self) -> None:
        while True:
            with self._lock:
                if not self._snapshot_running or self.snapshot_interval_sec <= 0:
                    break
                interval = self.snapshot_interval_sec
            self._snapshot_once()
            time.sleep(max(1, int(interval)))

    def start_snapshotting(self, interval_sec: int, out_dir: str) -> None:
        with self._lock:
            self.snapshot_interval_sec = max(0, int(interval_sec))
            self.snapshot_dir = out_dir
            if self.snapshot_interval_sec <= 0 or self._snapshot_running:
                return
            self._snapshot_running = True
            self._snapshot_thread = threading.Thread(target=self._snapshot_loop, daemon=True)
            self._snapshot_thread.start()

    def stop_snapshotting(self) -> None:
        with self._lock:
            self._snapshot_running = False
        if self._snapshot_thread is not None:
            self._snapshot_thread.join(timeout=3)
            self._snapshot_thread = None

    # -- auctions ---------------------------------------------------------
    def start_auction(self, phase: str) -> None:
        with self._lock:
            self.auction_mode = phase
            self._auction_orders.clear()

    def uncross_auction(self) -> None:
        with self._lock:
            if self.auction_mode is None:
                return
            temp_bids: Dict[float, int] = {}
            temp_asks: Dict[float, int] = {}

            def add_side(dst, px, qty):
                dst[px] = dst.get(px, 0) + qty

            for px, q in self.order_book.bids.items():
                size = sum(o.quantity for o in q if o.type == "limit")
                if size > 0:
                    add_side(temp_bids, px, size)
            for px, q in self.order_book.asks.items():
                size = sum(o.quantity for o in q if o.type == "limit")
                if size > 0:
                    add_side(temp_asks, px, size)
            for ao in self._auction_orders:
                if ao.side == "buy":
                    add_side(temp_bids, math.inf if ao.type == "market" else ao.price, ao.quantity)
                else:
                    add_side(temp_asks, 0.0 if ao.type == "market" else ao.price, ao.quantity)

            prices = sorted({p for p in temp_bids if p != math.inf} | {p for p in temp_asks if p != 0.0})
            if not prices and temp_bids and temp_asks:
                bb = max((p for p in temp_bids if p != math.inf), default=None)
                ba = min((p for p in temp_asks if p != 0.0), default=None)
                if bb is not None and ba is not None:
                    prices = [float((bb + ba) / 2.0)]

            best_price, best_volume = None, -1
            for px in prices:
                buy_qty = sum(q for p, q in temp_bids.items() if p >= px)
                sell_qty = sum(q for p, q in temp_asks.items() if p <= px)
                matched = min(buy_qty, sell_qty)
                if matched > best_volume:
                    best_volume, best_price = matched, px

            if best_price is None or best_volume <= 0:
                if self._auction_orders:
                    # These orders only ever lived in the auction pool (never
                    # rested in the book), so if there's no cross they are
                    # simply gone -- previously silent. Logged now so a user
                    # isn't left wondering why their auction order vanished.
                    logger.warning(
                        "Auction uncross for phase %r found no cross; discarding %d auction-only order(s): %s",
                        self.auction_mode, len(self._auction_orders), [o.id for o in self._auction_orders],
                    )
                self.auction_mode = None
                self._auction_orders.clear()
                return

            pool = list(self._auction_orders)
            self._auction_orders.clear()
            self.auction_mode = None

        for ao in pool:
            ao.type = "limit"
            ao.price = best_price
            self._direct_match(ao)

    # -- snapshot load/replay ----------------------------------------------
    def load_snapshot_file(self, path: str) -> None:
        import json
        with open(path, "r", encoding="utf-8") as f:
            snap = json.load(f)
        with self._lock:
            self.order_book.bids.clear()
            self.order_book.asks.clear()
            self.order_book.order_map.clear()
            self.order_book._bid_prices.clear()
            self.order_book._ask_prices.clear()
            for side_key in ("bids", "asks"):
                for lvl in snap.get(side_key, []) or []:
                    for od in lvl.get("orders") or []:
                        try:
                            o = Order(
                                id=str(od.get("id") or uuid.uuid4().hex),
                                price=float(lvl.get("price")),
                                quantity=int(od.get("qty") or 0),
                                side=str(od.get("side") or ("buy" if side_key == "bids" else "sell")),
                                type="limit",
                                symbol=str(od.get("symbol") or ""),
                                owner_id=str(od.get("owner") or ""),
                            )
                            if o.quantity > 0:
                                self.order_book.add_order(o)
                        except (ValueError, TypeError, KeyError):
                            logger.warning("Skipping malformed snapshot order entry: %r", od, exc_info=True)
