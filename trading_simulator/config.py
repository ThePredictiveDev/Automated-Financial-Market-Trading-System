"""Environment-variable-backed defaults, loaded once at import time.

Centralizes the handful of settings the original script read ad hoc from
os.environ scattered across the file (or not at all -- some, like DATABASE_URL,
were documented in the README but never actually read anywhere in the code).
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass(frozen=True)
class Settings:
    news_api_key: str = os.environ.get("NEWS_API_KEY", "")
    database_url: str = os.environ.get("DATABASE_URL", "")
    redis_url: str = os.environ.get("REDIS_URL", "")
    kafka_bootstrap_servers: str = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")
    default_initial_cash: float = _env_float("DEFAULT_INITIAL_CASH", 1_000_000.0)
    default_fee_bps: float = _env_float("DEFAULT_FEE_BPS", 1.0)
    default_maker_rebate_bps: float = _env_float("DEFAULT_MAKER_REBATE_BPS", 0.5)
    max_order_qty: int = _env_int("MAX_ORDER_QTY", 1000)
    max_symbol_position: int = _env_int("MAX_SYMBOL_POSITION", 10_000)
    max_gross_notional: float = _env_float("MAX_GROSS_NOTIONAL", 5_000_000.0)


SETTINGS = Settings()
