"""Execution (fill) model."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Execution:
    trade_id: str
    price: float
    quantity: int
    taker_order_id: str
    maker_order_id: str
    symbol: str
    side: str  # side of the taker
    timestamp: pd.Timestamp
    taker_owner_id: Optional[str] = None
    maker_owner_id: Optional[str] = None
