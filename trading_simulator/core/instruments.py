"""Per-instrument configuration (tick size, lot size, precision, trading hours).

The original script kept this as module-level global dicts (TICK_SIZE,
LOT_SIZE, DECIMAL_PRECISION, INSTRUMENTS), shared mutable state across every
MatchingEngine/OrderBook in the process. That breaks isolation between
parallel backtests, Optuna trials, and unit tests (one test's tick-size
override leaks into the next). InstrumentRegistry is a plain object instead:
each MatchingEngine gets its own registry by default, and callers who *want*
shared config across engines can explicitly pass the same registry instance
around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import pandas as pd


@dataclass
class InstrumentConfig:
    tick_size: float = 0.01
    lot_size: int = 1
    decimal_precision: int = 0
    tz: str = "America/New_York"
    open: str = "09:30"
    close: str = "16:00"
    holidays: frozenset = field(default_factory=frozenset)


class InstrumentRegistry:
    """Holds per-symbol trading rules. Unknown symbols fall back to sane
    equity-market defaults (1 cent tick, lot size 1, always-open session)."""

    def __init__(self, defaults: Optional[InstrumentConfig] = None) -> None:
        self._defaults = defaults or InstrumentConfig()
        self._by_symbol: Dict[str, InstrumentConfig] = {}

    def configure(self, symbol: str, **kwargs: Any) -> None:
        base = self._by_symbol.get(symbol, self._defaults)
        merged = InstrumentConfig(**{**base.__dict__, **kwargs})
        self._by_symbol[symbol] = merged

    def get(self, symbol: str) -> InstrumentConfig:
        return self._by_symbol.get(symbol, self._defaults)

    def tick_size(self, symbol: str) -> float:
        return float(self.get(symbol).tick_size)

    def lot_size(self, symbol: str) -> int:
        return int(self.get(symbol).lot_size)

    def normalize_price(self, price: float, symbol: str) -> float:
        cfg = self.get(symbol)
        tick = cfg.tick_size
        res = float(price) if tick <= 0 else float(round(float(price) / tick) * tick)
        if cfg.decimal_precision > 0:
            return round(res, cfg.decimal_precision)
        return res

    def normalize_quantity(self, quantity: int, symbol: str) -> int:
        lot = self.lot_size(symbol)
        if lot <= 1:
            return int(quantity)
        return int(quantity // lot * lot)

    def is_market_open(self, symbol: str, now_utc: Optional[pd.Timestamp] = None) -> bool:
        # Matches the original script's semantics: a symbol with no explicit
        # session-hours configuration is always considered open. Only
        # symbols explicitly registered via `configure(...)` are subject to
        # trading-hours enforcement. (Falling back to the *default* hours
        # here, as an earlier draft of this registry did, silently blocked
        # every unconfigured symbol outside 09:30-16:00 America/New_York --
        # a behavior regression caught by the matching-engine test suite.)
        cfg = self._by_symbol.get(symbol)
        if cfg is None:
            return True
        try:
            now_utc = now_utc or pd.Timestamp.now(tz="UTC")
            local = now_utc.tz_convert(cfg.tz)
            date_key = local.strftime("%Y-%m-%d")
            if date_key in cfg.holidays:
                return False
            t_open = pd.to_datetime(f"{date_key} {cfg.open}").tz_localize(cfg.tz)
            t_close = pd.to_datetime(f"{date_key} {cfg.close}").tz_localize(cfg.tz)
            return bool(t_open <= local <= t_close)
        except Exception:
            # A misconfigured session shouldn't block trading; fail open like
            # the original implementation did, but this is the one place we
            # intentionally swallow broadly (session-hours math on odd
            # timestamps), so it's a single documented exception rather than
            # thirty silent ones scattered through the engine.
            return True


# Process-wide default registry for callers who don't need isolation
# (matches pre-refactor behavior of "just works" for simple scripts/CLI use).
DEFAULT_REGISTRY = InstrumentRegistry()
