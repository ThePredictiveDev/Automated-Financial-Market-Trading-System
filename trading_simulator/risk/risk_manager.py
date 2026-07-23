"""Pre-trade risk checks: size limits, exposure, rate limiting, drawdown,
volatility halts, leverage, and per-owner/per-symbol kill switches."""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Optional

import numpy as np

from ..core.order import Order
from ..portfolio.portfolio import Portfolio, PortfolioDispatcher

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, portfolio: Portfolio, max_order_qty: int, max_symbol_position: int,
                 max_gross_notional: float, min_order_qty: int = 1, lot_size: int = 1,
                 round_lot_required: bool = False, order_rate_limit_per_sec: Optional[int] = None,
                 owner_drawdown_limit: Optional[float] = None,
                 owner_portfolios: Optional[PortfolioDispatcher] = None,
                 price_provider: Optional[Callable[[str], Optional[float]]] = None,
                 volatility_window: int = 20, volatility_halt_z: Optional[float] = None,
                 max_leverage: Optional[float] = None,
                 max_symbol_gross_exposure: Optional[float] = None,
                 on_reject: Optional[Callable[[Dict], None]] = None) -> None:
        self.portfolio = portfolio
        self.max_order_qty = int(max_order_qty)
        self.max_symbol_position = int(max_symbol_position)
        self.max_gross_notional = float(max_gross_notional)
        self.min_order_qty = max(1, int(min_order_qty))
        self.lot_size = max(1, int(lot_size))
        self.round_lot_required = bool(round_lot_required)

        self.order_rate_limit_per_sec = int(order_rate_limit_per_sec) if order_rate_limit_per_sec else None
        self._owner_to_timestamps: Dict[str, Deque[float]] = {}
        self.owner_drawdown_limit = float(owner_drawdown_limit) if owner_drawdown_limit is not None else None
        self.owner_portfolios = owner_portfolios
        self.price_provider = price_provider
        self._owner_peak_equity: Dict[str, float] = {}

        self.volatility_window = max(5, int(volatility_window))
        self.volatility_halt_z = float(volatility_halt_z) if volatility_halt_z is not None else None
        self._symbol_last_price: Dict[str, float] = {}
        self._symbol_returns: Dict[str, Deque[float]] = {}

        self._disabled_owners: set = set()
        self._disabled_symbols: set = set()
        self.max_leverage = float(max_leverage) if max_leverage is not None else None
        self.max_symbol_gross_exposure = float(max_symbol_gross_exposure) if max_symbol_gross_exposure is not None else None
        self.on_reject = on_reject
        self._lock = threading.RLock()

    def disable_owner(self, owner_id: str) -> None:
        self._disabled_owners.add(owner_id)

    def enable_owner(self, owner_id: str) -> None:
        self._disabled_owners.discard(owner_id)

    def disable_symbol(self, symbol: str) -> None:
        self._disabled_symbols.add(symbol)

    def enable_symbol(self, symbol: str) -> None:
        self._disabled_symbols.discard(symbol)

    def _reject(self, order: Order, reason: str, **extra) -> bool:
        payload = {"event": "risk_reject", "reason": reason, "order_id": order.id,
                   "owner": getattr(order, "owner_id", "default"), **extra}
        logger.info(json.dumps(payload, default=str))
        if self.on_reject is not None:
            try:
                self.on_reject(payload)
            except Exception:
                logger.warning("on_reject callback raised", exc_info=True)
        return False

    def allow_order(self, order: Order) -> bool:
        owner = getattr(order, "owner_id", "default")

        if owner in self._disabled_owners:
            return self._reject(order, "owner_killed")
        if order.symbol in self._disabled_symbols:
            return self._reject(order, "symbol_disabled", symbol=order.symbol)
        if order.quantity <= 0 or order.quantity > self.max_order_qty:
            return self._reject(order, "qty_bounds", qty=order.quantity, max_order_qty=self.max_order_qty)
        if order.quantity < self.min_order_qty:
            return self._reject(order, "min_qty", qty=order.quantity, min_order_qty=self.min_order_qty)
        if self.round_lot_required and order.quantity % self.lot_size != 0:
            return self._reject(order, "round_lot", qty=order.quantity, lot_size=self.lot_size)

        notional = abs(order.quantity * float(order.price))
        if notional > self.max_gross_notional:
            return self._reject(order, "gross_notional", notional=notional, max_gross_notional=self.max_gross_notional)

        pos = self.portfolio.positions.get(order.symbol, 0)
        projected = pos + (order.quantity if order.side == "buy" else -order.quantity)
        if abs(projected) > self.max_symbol_position:
            return self._reject(order, "symbol_exposure", symbol=order.symbol, projected=projected,
                                 max_symbol_position=self.max_symbol_position)

        if self.order_rate_limit_per_sec is not None:
            with self._lock:
                now = time.time()
                dq = self._owner_to_timestamps.setdefault(owner, deque())
                dq.append(now)
                one_sec_ago = now - 1.0
                while dq and dq[0] < one_sec_ago:
                    dq.popleft()
                if len(dq) > self.order_rate_limit_per_sec:
                    return self._reject(order, "rate_limit", rate=len(dq), limit=self.order_rate_limit_per_sec)

        if self.owner_drawdown_limit is not None and self.owner_portfolios is not None and self.price_provider is not None:
            pf = self.owner_portfolios.get_portfolio(owner)
            if pf is not None:
                equity = float(pf.cash)
                for sym, qty in pf.positions.items():
                    px = self.price_provider(sym)
                    if px is not None:
                        equity += float(qty) * float(px)
                peak = max(self._owner_peak_equity.get(owner, equity), equity)
                self._owner_peak_equity[owner] = peak
                dd = 0.0 if peak <= 0 else (peak - equity) / peak
                if dd > self.owner_drawdown_limit:
                    return self._reject(order, "drawdown_limit", drawdown=dd, limit=self.owner_drawdown_limit)

        if self.max_leverage is not None and self.owner_portfolios is not None and self.price_provider is not None:
            pf = self.owner_portfolios.get_portfolio(owner)
            if pf is not None:
                equity = float(pf.cash)
                exposures = 0.0
                for sym, qty in pf.positions.items():
                    px = self.price_provider(sym)
                    if px is not None:
                        exposures += abs(float(qty) * float(px))
                        equity += float(qty) * float(px)
                px_new = self.price_provider(order.symbol) or float(order.price)
                projected_qty = pf.positions.get(order.symbol, 0) + (order.quantity if order.side == "buy" else -order.quantity)
                cur_sym_exposure = abs(pf.positions.get(order.symbol, 0) * (self.price_provider(order.symbol) or 0.0))
                exposures = exposures - cur_sym_exposure + abs(projected_qty * float(px_new))
                if equity <= 0 or (exposures / equity) > self.max_leverage:
                    return self._reject(order, "max_leverage", exposures=exposures, equity=equity, max_leverage=self.max_leverage)

        if self.max_symbol_gross_exposure is not None and self.owner_portfolios is not None and self.price_provider is not None:
            pf = self.owner_portfolios.get_portfolio(owner)
            if pf is not None:
                px = self.price_provider(order.symbol) or float(order.price)
                projected_qty = pf.positions.get(order.symbol, 0) + (order.quantity if order.side == "buy" else -order.quantity)
                gross = abs(float(projected_qty) * float(px))
                if gross > self.max_symbol_gross_exposure:
                    return self._reject(order, "symbol_gross_exposure", symbol=order.symbol, gross=gross,
                                         max_symbol_gross_exposure=self.max_symbol_gross_exposure)

        if self.volatility_halt_z is not None and self.price_provider is not None:
            px = self.price_provider(order.symbol)
            if px and px > 0:
                last_px = self._symbol_last_price.get(order.symbol)
                if last_px and last_px > 0:
                    r = math.log(px / last_px)
                    dq = self._symbol_returns.setdefault(order.symbol, deque(maxlen=self.volatility_window))
                    dq.append(r)
                    if len(dq) >= max(5, self.volatility_window // 2):
                        mean, std = float(np.mean(dq)), float(np.std(dq))
                        z = 0.0 if std == 0.0 else (r - mean) / std
                        if abs(z) > self.volatility_halt_z:
                            return self._reject(order, "volatility_halt", symbol=order.symbol, z=z, threshold=self.volatility_halt_z)
                self._symbol_last_price[order.symbol] = float(px)

        return True
