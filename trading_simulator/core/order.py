"""Order model and validation.

The Order dataclass is intentionally small and mutable (quantity is reduced in
place as fills occur) to avoid churn in hot paths. Validation happens once at
construction time via `Order.validate()`, which callers building orders from
external input (CLI, FIX adapter, order-control server) should invoke.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

VALID_SIDES = {"buy", "sell"}
VALID_TYPES = {"limit", "market"}
VALID_TIF = {"GTC", "IOC", "FOK"}


class OrderValidationError(ValueError):
    """Raised when an Order fails validation. Distinct from generic ValueError
    so callers can catch it specifically instead of accidentally swallowing
    unrelated value errors."""


@dataclass
class Order:
    id: str
    price: float
    quantity: int
    side: str             # 'buy' or 'sell'
    type: str              # 'limit' or 'market'
    symbol: str
    tif: str = "GTC"       # 'GTC', 'IOC', 'FOK'
    post_only: bool = False
    timestamp: float = field(default_factory=lambda: time.time())
    owner_id: str = "default"
    expires_at: Optional[pd.Timestamp] = None
    auction_only: bool = False
    auction_phase: Optional[str] = None  # 'open' or 'close'

    def validate(self) -> None:
        if self.side not in VALID_SIDES:
            raise OrderValidationError(f"invalid side {self.side!r}; expected one of {VALID_SIDES}")
        if self.type not in VALID_TYPES:
            raise OrderValidationError(f"invalid type {self.type!r}; expected one of {VALID_TYPES}")
        if self.tif not in VALID_TIF:
            raise OrderValidationError(f"invalid tif {self.tif!r}; expected one of {VALID_TIF}")
        if self.type == "limit" and self.price <= 0:
            raise OrderValidationError("limit orders require price > 0")
        if self.type == "market" and self.price < 0:
            raise OrderValidationError("market order price hint must be >= 0")
        if self.quantity <= 0:
            raise OrderValidationError("quantity must be > 0")
        if not self.symbol:
            raise OrderValidationError("symbol is required")
        if self.post_only and self.type != "limit":
            raise OrderValidationError("post_only is only valid for limit orders")
        if self.post_only and self.tif in ("IOC", "FOK"):
            raise OrderValidationError("post_only cannot be combined with IOC/FOK")
