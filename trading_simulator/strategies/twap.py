"""TWAP (Time-Weighted Average Price) Execution Strategy.

Slices a large parent order into equal-sized child orders submitted at fixed
time intervals to minimize market impact. Each child order routes through the
normal order lifecycle: risk validation → order book → matching engine → 
execution → portfolio update.
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional, List

from ..core.order import Order
from ..execution_algos import twap_schedule, ChildOrderPlan
from .base import AlgorithmicTrader

logger = logging.getLogger(__name__)


class TWAPTrader(AlgorithmicTrader):
    """Time-Weighted Average Price execution algorithm.
    
    Splits a parent order into multiple child clips of equal size and submits
    them at evenly-spaced time intervals.
    """

    def __init__(
        self,
        symbol: str,
        matching_engine,
        side: str,  # 'buy' or 'sell'
        total_quantity: int,
        num_slices: int = 5,
        duration_seconds: float = 10.0,
        interval: float = 0.1,
        owner_id: str = "twap_bot",
        portfolio=None,
    ) -> None:
        """
        Args:
            symbol: Trading symbol
            matching_engine: MatchingEngine instance
            side: 'buy' or 'sell'
            total_quantity: Total parent order size to slice
            num_slices: Number of equal child orders
            duration_seconds: Total execution window
            interval: Polling interval (seconds) — should be < duration/num_slices
            owner_id: Owner identifier for orders
            portfolio: Optional portfolio for tracking (not currently used)
        """
        super().__init__(symbol, matching_engine, interval)
        
        if side.lower() not in ("buy", "sell"):
            raise ValueError(f"side must be 'buy' or 'sell', got {side}")
        if total_quantity <= 0:
            raise ValueError(f"total_quantity must be > 0, got {total_quantity}")
        if num_slices <= 0:
            raise ValueError(f"num_slices must be > 0, got {num_slices}")
        if duration_seconds <= 0:
            raise ValueError(f"duration_seconds must be > 0, got {duration_seconds}")
            
        self.side = side.lower()
        self.total_quantity = int(total_quantity)
        self.num_slices = int(num_slices)
        self.duration_seconds = float(duration_seconds)
        self.owner_id = owner_id
        self.portfolio = portfolio
        
        # Generate the execution schedule
        self.schedule: List[ChildOrderPlan] = twap_schedule(
            total_quantity=self.total_quantity,
            num_slices=self.num_slices,
            duration_seconds=self.duration_seconds,
        )
        
        # Execution state
        self._start_time: Optional[float] = None
        self._next_slice_idx: int = 0
        self._completed = False
        
        logger.info(
            "TWAPTrader initialized: %s %d shs %s over %.1fs in %d slices",
            self.side.upper(),
            self.total_quantity,
            self.symbol,
            self.duration_seconds,
            self.num_slices,
        )

    def handle_market_data(self, data: Dict[str, Any]) -> None:
        """Receive market data updates."""
        self.current_price = float(data["price"])

    def trade(self) -> None:
        """Check if it's time to submit the next child order."""
        if self._completed:
            return  # All slices submitted
            
        # Initialize start time on first call
        if self._start_time is None:
            self._start_time = time.time()
            logger.info("TWAP execution started for %s at t=0", self.symbol)
        
        elapsed = time.time() - self._start_time
        
        # Check if next slice is due
        while self._next_slice_idx < len(self.schedule):
            plan = self.schedule[self._next_slice_idx]
            
            if elapsed >= plan.offset_seconds:
                self._submit_child_order(plan, elapsed)
                self._next_slice_idx += 1
            else:
                break  # Next slice not yet due
        
        # Mark complete when all slices submitted
        if self._next_slice_idx >= len(self.schedule):
            if not self._completed:
                logger.info(
                    "TWAP execution complete for %s: submitted %d/%d slices over %.2fs",
                    self.symbol,
                    self._next_slice_idx,
                    len(self.schedule),
                    elapsed,
                )
                self._completed = True

    def _submit_child_order(self, plan: ChildOrderPlan, elapsed: float) -> None:
        """Submit a single child order to the matching engine."""
        if self.current_price is None:
            logger.warning("TWAP: no price available, skipping slice %d", self._next_slice_idx)
            return
        
        # Use current best bid/ask as limit price
        if self.side == "buy":
            best_ask = self.matching_engine.order_book.get_best_ask()
            price = best_ask if best_ask is not None else self.current_price
        else:
            best_bid = self.matching_engine.order_book.get_best_bid()
            price = best_bid if best_bid is not None else self.current_price
        
        order = Order(
            id=uuid.uuid4().hex,
            price=float(price),
            quantity=plan.quantity,
            side=self.side,
            type="limit",
            symbol=self.symbol,
            owner_id=self.owner_id,
        )
        
        logger.info(
            "TWAP slice %d/%d: %s %d shs @ $%.2f (t=%.2fs, target_offset=%.2fs)",
            self._next_slice_idx + 1,
            len(self.schedule),
            self.side.upper(),
            plan.quantity,
            price,
            elapsed,
            plan.offset_seconds,
        )
        
        self.matching_engine.match_order(order)

    def reset(self) -> None:
        """Reset execution state (for restarting the strategy)."""
        self._start_time = None
        self._next_slice_idx = 0
        self._completed = False
        logger.info("TWAP execution reset for %s", self.symbol)
