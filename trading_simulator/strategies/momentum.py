from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ..core.order import Order
from .base import AlgorithmicTrader
from .sizing import fixed_fraction_size

logger = logging.getLogger(__name__)


class MomentumTrader(AlgorithmicTrader):
    """Trades in the direction of short-term price momentum over `lookback` ticks.

    `quantity` keeps the original fixed-size behavior if set explicitly.
    Otherwise, if `portfolio` is provided, order size scales with account
    equity (`risk_fraction` of equity per order) instead of a hardcoded 100
    shares -- pass neither to keep the pre-refactor default of 100 shares.
    """

    def __init__(self, symbol: str, matching_engine, interval: float = 0.1, lookback: int = 5,
                 quantity: Optional[int] = None, portfolio=None, risk_fraction: float = 0.01,
                 owner_id: str = "default") -> None:
        super().__init__(symbol, matching_engine, interval)
        self.lookback = int(lookback)
        self.prices: List[float] = []
        self.quantity = quantity
        self.portfolio = portfolio
        self.risk_fraction = float(risk_fraction)
        self.owner_id = owner_id

    def _order_qty(self, price: float) -> int:
        if self.quantity is not None:
            return int(self.quantity)
        if self.portfolio is not None:
            equity = self.portfolio.equity({self.symbol: price})
            return fixed_fraction_size(equity, price, self.risk_fraction)
        return 100

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        if self.current_price is not None:
            self.prices.append(self.current_price)
            if len(self.prices) > self.lookback:
                self.prices.pop(0)

    def trade(self) -> None:
        if len(self.prices) < self.lookback or self.current_price is None:
            return
        price_change = self.prices[-1] - self.prices[0]
        if price_change > 0:
            best_ask = self.matching_engine.order_book.get_best_ask()
            if best_ask is None:
                return
            qty = self._order_qty(best_ask)
            order = Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=qty, side="buy",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("MomentumTrader buy %s @ %s", qty, best_ask)
        elif price_change < 0:
            best_bid = self.matching_engine.order_book.get_best_bid()
            if best_bid is None:
                return
            qty = self._order_qty(best_bid)
            order = Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=qty, side="sell",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("MomentumTrader sell %s @ %s", qty, best_bid)
