from __future__ import annotations

import uuid
from typing import Any, Dict

from ..core.order import Order
from .base import AlgorithmicTrader


class CustomTrader(AlgorithmicTrader):
    """Minimal example: buys a small fixed clip whenever price is below a
    threshold. Intended as a template to copy, not a real strategy -- it has
    no cooldown or sell logic on purpose, so it's obvious at a glance it
    needs customization before use."""

    def __init__(self, symbol: str, matching_engine, interval: float = 0.1, threshold: float = 0.0,
                 owner_id: str = "custom") -> None:
        super().__init__(symbol, matching_engine, interval)
        self.threshold = float(threshold)
        self.owner_id = owner_id

    def trade(self) -> None:
        if self.current_price is None:
            return
        if self.current_price < self.threshold:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=10, side="buy",
                          type="market", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
