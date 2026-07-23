from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from ..core.order import Order
from .base import AlgorithmicTrader
from .sizing import fixed_fraction_size

logger = logging.getLogger(__name__)


class SwingTrader(AlgorithmicTrader):
    """Mean-reversion: buys near support, sells near resistance."""

    def __init__(self, symbol: str, matching_engine, interval: float = 0.1, support_level: float = 100.0,
                 resistance_level: float = 200.0, quantity: Optional[int] = None, portfolio=None,
                 risk_fraction: float = 0.01, owner_id: str = "default") -> None:
        super().__init__(symbol, matching_engine, interval)
        if support_level >= resistance_level:
            raise ValueError("support_level must be < resistance_level")
        self.support_level = float(support_level)
        self.resistance_level = float(resistance_level)
        self.quantity = quantity
        self.portfolio = portfolio
        self.risk_fraction = float(risk_fraction)
        self.owner_id = owner_id

    def _order_qty(self, price: float) -> int:
        if self.quantity is not None:
            return int(self.quantity)
        if self.portfolio is not None:
            return fixed_fraction_size(self.portfolio.equity({self.symbol: price}), price, self.risk_fraction)
        return 100

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        self.current_price = float(data["price"])

    def trade(self) -> None:
        if self.current_price is None:
            return
        if self.current_price <= self.support_level:
            best_ask = self.matching_engine.order_book.get_best_ask()
            if best_ask is None:
                return
            qty = self._order_qty(best_ask)
            order = Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=qty, side="buy",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("SwingTrader buy %s @ %s", qty, best_ask)
        elif self.current_price >= self.resistance_level:
            best_bid = self.matching_engine.order_book.get_best_bid()
            if best_bid is None:
                return
            qty = self._order_qty(best_bid)
            order = Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=qty, side="sell",
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
            logger.info("SwingTrader sell %s @ %s", qty, best_bid)
