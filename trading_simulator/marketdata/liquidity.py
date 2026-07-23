"""Synthetic liquidity injection: seeds a symbol's book with random small
buy/sell limit orders at the last traded price, useful for demos/tests where
there's no real counterparty flow."""
from __future__ import annotations

import logging
import random
import uuid

from ..core.order import Order
from .history import fetch_history_with_retry

logger = logging.getLogger(__name__)


class SyntheticLiquidityProvider:
    def __init__(self, symbol: str, matching_engine, num_orders: int = 10, owner_id: str = "synthetic_lp") -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.num_orders = int(num_orders)
        self.owner_id = owner_id

    def generate_liquidity(self) -> None:
        try:
            data = fetch_history_with_retry(self.symbol, period="1d", interval="1m", max_retries=4, base_backoff=1.8)
        except Exception as exc:
            logger.warning("SyntheticLiquidityProvider fetch failed: %s", exc)
            return
        if data is None or data.empty:
            return
        price = float(data.iloc[-1]["Close"])
        for _ in range(self.num_orders):
            side = "buy" if random.random() < 0.5 else "sell"
            order = Order(id=uuid.uuid4().hex, price=price, quantity=random.randint(10, 100), side=side,
                          type="limit", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
        logger.info("Injected %d synthetic liquidity orders for %s @ %.4f", self.num_orders, self.symbol, price)
