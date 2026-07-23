"""Owner-aware portfolio/PnL tracking."""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from ..core.execution import Execution


class Portfolio:
    """Tracks cash, positions, average price, and realized PnL for a single
    owner_id. Applies a taker fee when this portfolio is the taker on an
    execution, and a maker rebate when it's the maker."""

    def __init__(self, initial_cash: float = 1_000_000.0, fee_bps: float = 0.0,
                 maker_rebate_bps: float = 0.0, owner_id: str = "default") -> None:
        self.cash = float(initial_cash)
        self.fee_bps = float(fee_bps)
        self.maker_rebate_bps = float(maker_rebate_bps)
        self.owner_id = str(owner_id)
        self.positions: Dict[str, int] = {}
        self.avg_price: Dict[str, float] = {}
        self.realized_pnl: float = 0.0
        self._lock = threading.RLock()

    def _apply_fee(self, notional: float) -> float:
        return abs(notional) * (self.fee_bps / 10_000.0)

    def on_execution(self, execu: Execution) -> None:
        with self._lock:
            is_taker = execu.taker_owner_id == self.owner_id
            is_maker = execu.maker_owner_id == self.owner_id
            if not is_taker and not is_maker:
                return

            eff_side = execu.side if is_taker else ("sell" if execu.side == "buy" else "buy")
            qty = execu.quantity if eff_side == "buy" else -execu.quantity
            symbol, price = execu.symbol, execu.price

            fees = 0.0
            if is_taker and self.fee_bps:
                fees += self._apply_fee(price * execu.quantity)
            if is_maker and self.maker_rebate_bps:
                fees -= abs(price * execu.quantity) * (self.maker_rebate_bps / 10_000.0)

            prev_pos = self.positions.get(symbol, 0)
            new_pos = prev_pos + qty
            self.cash -= qty * price
            self.cash -= fees

            if prev_pos == 0 or (prev_pos > 0 and qty > 0) or (prev_pos < 0 and qty < 0):
                total_qty = abs(prev_pos) + abs(qty)
                if total_qty == 0:
                    self.avg_price[symbol] = price
                else:
                    prev_avg = self.avg_price.get(symbol, price if prev_pos != 0 else 0.0)
                    self.avg_price[symbol] = (prev_avg * abs(prev_pos) + price * abs(qty)) / total_qty
            else:
                close_qty = min(abs(prev_pos), abs(qty))
                sign = 1 if prev_pos > 0 else -1
                entry = self.avg_price.get(symbol, price)
                self.realized_pnl += (price - entry) * (close_qty * sign)
                if abs(qty) > abs(prev_pos):
                    self.avg_price[symbol] = price

            self.positions[symbol] = new_pos

    def equity(self, prices: Dict[str, float]) -> float:
        """Net liquidation value: cash + mark-to-market of open positions."""
        with self._lock:
            net = self.cash
            for symbol, qty in self.positions.items():
                if symbol in prices:
                    net += qty * float(prices[symbol])
            return float(net)

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "cash": self.cash,
                "positions": dict(self.positions),
                "avg_price": dict(self.avg_price),
                "realized_pnl": self.realized_pnl,
            }


class PortfolioDispatcher:
    """Routes executions to owner-specific Portfolio instances, creating them
    lazily on first sight of a new owner_id."""

    def __init__(self, fee_bps: float = 0.0, maker_rebate_bps: float = 0.0) -> None:
        self._lock = threading.RLock()
        self._portfolios: Dict[str, Portfolio] = {}
        self._default_fee_bps = float(fee_bps)
        self._default_maker_rebate_bps = float(maker_rebate_bps)

    def ensure(self, owner_id: str, initial_cash: float = 0.0, fee_bps: Optional[float] = None,
               maker_rebate_bps: Optional[float] = None) -> Portfolio:
        with self._lock:
            if owner_id in self._portfolios:
                return self._portfolios[owner_id]
            pf = Portfolio(
                initial_cash=float(initial_cash),
                fee_bps=self._default_fee_bps if fee_bps is None else float(fee_bps),
                maker_rebate_bps=self._default_maker_rebate_bps if maker_rebate_bps is None else float(maker_rebate_bps),
                owner_id=owner_id,
            )
            self._portfolios[owner_id] = pf
            return pf

    def get_portfolio(self, owner_id: str) -> Optional[Portfolio]:
        with self._lock:
            return self._portfolios.get(owner_id)

    def on_execution(self, execu: Execution) -> None:
        taker_owner = execu.taker_owner_id or ""
        maker_owner = execu.maker_owner_id or ""
        if taker_owner:
            self.ensure(taker_owner).on_execution(execu)
        if maker_owner and maker_owner != taker_owner:
            self.ensure(maker_owner).on_execution(execu)

    def snapshot_all(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return {oid: pf.snapshot() for oid, pf in self._portfolios.items()}
