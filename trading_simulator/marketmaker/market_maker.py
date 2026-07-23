"""Avellaneda-Stoikov-inspired market maker with inventory management,
multi-level laddering, volatility widening, and a drawdown kill switch.

Fix vs. the original: `_post_quote` used to call
`matching_engine.order_book.add_order()` directly, bypassing MatchingEngine
entirely -- so market-maker quotes skipped pre-trade risk checks, price-band
protection, halted-symbol checks, tick/lot normalization, and the
audit/event log. Every other order path in the system went through
`match_order()`; the market maker quietly didn't. It now routes through
`match_order()` like any other participant, which also means an MM quote
that crosses the existing book fills immediately instead of just resting.

Because a quote can now fill immediately (as taker) instead of only later
(as maker), `on_execution` tracks inventory for both roles.

Second fix, found by actually running a backtest rather than just reading
the code: the original drawdown kill-switch computed
`equity = inventory * mid` and tracked drawdown as a *fraction of peak
equity*. Since `inventory` is a small signed integer that regularly crosses
zero, "peak equity" is often a tiny number (or even negative territory
shortly after), so `(peak - equity) / peak` blows up to enormous
percentages (98%+) on totally ordinary inventory swings -- the kill switch
fired almost immediately in testing and pinned quotes off for the rest of
the session. `equity` here now means actual realized+unrealized P&L
(`realized_cash + inventory * mid`, where `realized_cash` is the running
cash flow from fills), and drawdown is measured against `capital_base` (a
stable, user-supplied notional -- the capital this book is allowed to risk)
instead of against its own noisy peak.
"""
from __future__ import annotations

import logging
import math
import uuid
from typing import Any, Dict, List, Tuple

import numpy as np

from ..core.execution import Execution
from ..core.order import Order

logger = logging.getLogger(__name__)


class MarketMaker:
    def __init__(self, symbol: str, matching_engine, gamma: float = 0.1, k: float = 1.5,
                 horizon_seconds: float = 60.0, max_inventory: int = 1000, base_order_size: int = 100,
                 min_spread: float = 0.01, num_levels: int = 2, level_spacing_bps: float = 2.0,
                 size_decay: float = 0.7, momentum_window: int = 10, alpha_skew: float = 0.5,
                 vol_widen_z: float = 2.0, drawdown_limit: float = 0.2, capital_base: float = 100_000.0,
                 owner_id: str = "mm") -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.owner_id = owner_id
        self.gamma = max(1e-6, float(gamma))
        self.k = max(1e-6, float(k))
        self.horizon_seconds = max(1.0, float(horizon_seconds))
        self.max_inventory = int(max_inventory)
        self.base_order_size = max(1, int(base_order_size))
        self.min_spread = max(0.0, float(min_spread))
        self.num_levels = max(1, int(num_levels))
        self.level_spacing_bps = max(0.0, float(level_spacing_bps))
        self.size_decay = min(1.0, max(0.1, float(size_decay)))
        self.momentum_window = max(1, int(momentum_window))
        self.alpha_skew = max(0.0, float(alpha_skew))
        self.vol_widen_z = max(0.0, float(vol_widen_z))
        self.drawdown_limit = max(0.0, float(drawdown_limit))
        self.capital_base = max(1e-6, float(capital_base))
        self.price_history: List[float] = []
        self.running = False
        self.inventory = 0
        self.realized_cash = 0.0
        self.current_bid_ids: List[str] = []
        self.current_ask_ids: List[str] = []
        self.order_id_to_side: Dict[str, str] = {}
        self.peak_equity = 0.0
        self.last_mid = None

    def _estimate_sigma(self, window: int = 60) -> float:
        if len(self.price_history) < max(3, window):
            return 0.0
        arr = np.array(self.price_history[-window:], dtype=float)
        return float(np.std(np.diff(np.log(arr + 1e-12))))

    def _compute_quotes(self, mid: float) -> Tuple[float, float, int, int]:
        sigma = self._estimate_sigma()
        T, gamma, k = self.horizon_seconds, self.gamma, self.k
        reservation = mid - self.inventory * gamma * (sigma ** 2) * T
        if len(self.price_history) >= self.momentum_window:
            recent = self.price_history[-self.momentum_window:]
            mom = recent[-1] - recent[0]
            direction = 1.0 if mom > 0 else (-1.0 if mom < 0 else 0.0)
            reservation += direction * self.alpha_skew * self.min_spread
        try:
            half_spread = (gamma * (sigma ** 2) * T) / 2.0 + (1.0 / gamma) * math.log(1.0 + (gamma / k))
        except (ValueError, ZeroDivisionError):
            half_spread = self.min_spread
        half_spread = max(self.min_spread, half_spread)
        if len(self.price_history) >= max(5, self.momentum_window):
            arr = np.array(self.price_history[-self.momentum_window:], dtype=float)
            rets = np.diff(arr)
            if rets.size > 1 and rets.std(ddof=0) > 0:
                z = float((rets[-1] - rets.mean()) / (rets.std(ddof=0) + 1e-12))
                half_spread *= 1.0 + max(0.0, abs(z) - self.vol_widen_z) * 0.25
        bid = max(0.0, reservation - half_spread)
        ask = max(bid + self.min_spread, reservation + half_spread)
        inv_ratio = min(1.0, abs(self.inventory) / max(1, self.max_inventory))
        size_factor = max(0.2, 1.0 - inv_ratio)
        buy_size = max(1, round(self.base_order_size * (size_factor if self.inventory > 0 else 1.0)))
        sell_size = max(1, round(self.base_order_size * (size_factor if self.inventory < 0 else 1.0)))
        return bid, ask, int(buy_size), int(sell_size)

    def _cancel_existing_quotes(self) -> None:
        ob = self.matching_engine.order_book
        for oid in self.current_bid_ids + self.current_ask_ids:
            ob.cancel_order(oid)
            self.order_id_to_side.pop(oid, None)
        self.current_bid_ids, self.current_ask_ids = [], []

    def _post_quote(self, side: str, price: float, qty: int) -> str:
        order_id = uuid.uuid4().hex
        order = Order(id=order_id, price=float(price), quantity=int(qty), side=side, type="limit",
                      symbol=self.symbol, owner_id=self.owner_id, post_only=False)
        self.order_id_to_side[order_id] = side
        # Routed through match_order (not order_book.add_order) so MM quotes
        # get risk checks, price-band protection, halts, and audit logging
        # like every other participant. If it crosses immediately it fills
        # as taker; otherwise it rests and may later fill as maker.
        self.matching_engine.match_order(order)
        return order_id

    def on_market_data(self, data: Dict[str, Any]) -> None:
        if data["symbol"] != self.symbol:
            return
        mid = float(data["price"])
        self.price_history.append(mid)
        self.last_mid = mid

        equity = self.realized_cash + self.inventory * mid
        self.peak_equity = max(self.peak_equity, equity)
        drawdown = (self.peak_equity - equity) / self.capital_base
        if drawdown > self.drawdown_limit:
            self._cancel_existing_quotes()
            logger.warning("MM %s kill-switch active: drawdown=%.2f%% of capital_base=%.2f", self.symbol, drawdown * 100.0, self.capital_base)
            return

        self._cancel_existing_quotes()
        bid, ask, buy_size, sell_size = self._compute_quotes(mid)
        for i in range(self.num_levels):
            decay = self.size_decay ** i
            level_size_bid = max(1, round(buy_size * decay))
            level_size_ask = max(1, round(sell_size * decay))
            step = (self.level_spacing_bps / 10000.0) * i
            bid_i = max(0.0, bid - mid * step)
            ask_i = max(bid_i + self.min_spread, ask + mid * step)
            self.current_bid_ids.append(self._post_quote("buy", bid_i, level_size_bid))
            self.current_ask_ids.append(self._post_quote("sell", ask_i, level_size_ask))
        logger.info("MM %s quotes bid=%.4f ask=%.4f levels=%d inv=%d", self.symbol, bid, ask, self.num_levels, self.inventory)

    def on_execution(self, execu: Execution) -> None:
        if execu.symbol != self.symbol:
            return
        side = None
        # Maker fill: our resting quote was hit.
        if execu.maker_order_id in self.order_id_to_side:
            side = self.order_id_to_side[execu.maker_order_id]
        # Taker fill: our quote crossed the book immediately on entry.
        elif execu.taker_order_id in self.order_id_to_side:
            side = self.order_id_to_side[execu.taker_order_id]
        if side is None:
            return
        signed_qty = execu.quantity if side == "buy" else -execu.quantity
        self.inventory += signed_qty
        # Cash flow: buying spends cash, selling receives cash -- mirrors
        # Portfolio.on_execution's convention so realized_cash + inventory*mid
        # is a genuine mark-to-market equity figure, not just inventory value.
        self.realized_cash -= signed_qty * float(execu.price)

    def start(self, feed) -> None:
        self.running = True
        feed.subscribe(self)

    def stop(self) -> None:
        self.running = False

    def receive(self, data: Dict[str, Any]) -> None:
        self.on_market_data(data)
