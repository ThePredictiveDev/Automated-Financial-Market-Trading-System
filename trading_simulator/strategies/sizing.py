"""Risk-based position sizing.

The original built-in traders (Momentum/EMA/Swing) always sent a hardcoded
100-share order regardless of account size or the configured risk limits --
fine for a $1M demo account, silently wrong (or silently rejected) for any
other configuration. `fixed_fraction_size` sizes an order as a fraction of
current equity at the current price, then clamps it to the risk manager's
qty bounds when one is attached, so strategies scale sensibly with account
size instead of hardcoding round numbers.
"""
from __future__ import annotations

from typing import Optional


# Hard ceiling so a bad equity/price input cannot submit exchange-breaking sizes.
# Matches the demo RiskManager max_order_qty used for user orders in web_server.
DEFAULT_MAX_ORDER_QTY = 5_000


def fixed_fraction_size(equity: float, price: float, risk_fraction: float = 0.01,
                         min_qty: int = 1, max_qty: Optional[int] = DEFAULT_MAX_ORDER_QTY) -> int:
    """Return a share quantity worth ~`risk_fraction` of `equity` at `price`."""
    if price <= 0 or equity <= 0 or not (equity < float("inf")):
        return min_qty
    qty = int((equity * risk_fraction) / price)
    qty = max(min_qty, qty)
    if max_qty is not None:
        qty = min(max_qty, qty)
    return qty
