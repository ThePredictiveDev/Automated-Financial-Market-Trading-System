from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from ..core.order import Order
from .base import AlgorithmicTrader
from .sizing import fixed_fraction_size

logger = logging.getLogger(__name__)


class EMABasedTrader(AlgorithmicTrader):
    """Trend-following crossover of a short- and long-window EMA."""

    def __init__(self, symbol: str, matching_engine, interval: float = 0.1, short_window: int = 5,
                 long_window: int = 20, quantity: Optional[int] = None, portfolio=None,
                 risk_fraction: float = 0.01, owner_id: str = "default") -> None:
        super().__init__(symbol, matching_engine, interval)
        if short_window >= long_window:
            raise ValueError("short_window must be < long_window")
        self.short_window = int(short_window)
        self.long_window = int(long_window)
        self.prices: List[float] = []
        self.quantity = quantity
        self.portfolio = portfolio
        self.risk_fraction = float(risk_fraction)
        self.owner_id = owner_id

    def _order_qty(self, price: float) -> int:
        if self.quantity is not None:
            return int(self.quantity)
        if self.portfolio is not None:
            prices = dict(getattr(self, "mark_prices", None) or {})
            prices[self.symbol] = price
            return fixed_fraction_size(self.portfolio.equity(prices), price, self.risk_fraction)
        return 100

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        if self.current_price is not None:
            self.prices.append(self.current_price)
            if len(self.prices) > self.long_window:
                self.prices.pop(0)

    def _calculate_ema(self, window: int) -> float:
        weights = np.exp(np.linspace(-1.0, 0.0, window))
        weights /= weights.sum()
        return float(np.convolve(self.prices, weights, mode="valid")[-1])

    def trade(self) -> None:
        if len(self.prices) < self.long_window or self.current_price is None:
            return
        short_ema = self._calculate_ema(self.short_window)
        long_ema = self._calculate_ema(self.long_window)
        if short_ema > long_ema:
            best_ask = self.matching_engine.order_book.get_best_ask()
            if best_ask is None:
                return
            qty = self._order_qty(best_ask)
            order = Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=qty, side="buy",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("EMABasedTrader buy %s @ %s", qty, best_ask)
        elif short_ema < long_ema:
            best_bid = self.matching_engine.order_book.get_best_bid()
            if best_bid is None:
                return
            qty = self._order_qty(best_bid)
            order = Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=qty, side="sell",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("EMABasedTrader sell %s @ %s", qty, best_bid)
