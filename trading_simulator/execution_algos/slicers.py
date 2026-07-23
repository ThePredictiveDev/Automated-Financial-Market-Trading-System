"""TWAP/VWAP parent-order slicing.

New feature (not present in the original script): institutional execution
desks rarely send a large order to the book in one clip -- they slice it to
reduce market impact. These slicers take a parent quantity and produce a
schedule of child order sizes; a caller (backtest loop or live scheduler)
submits each child through the normal MatchingEngine at the scheduled time.
Kept intentionally simple (no adaptive participation-rate logic) so it's
easy to audit and extend rather than a black box.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np


@dataclass
class ChildOrderPlan:
    """One slice of a parent order: `quantity` shares to submit at/after
    `offset_seconds` from the algo's start time."""
    offset_seconds: float
    quantity: int


def twap_schedule(total_quantity: int, num_slices: int, duration_seconds: float) -> List[ChildOrderPlan]:
    """Split `total_quantity` into `num_slices` equal-sized clips spread
    evenly across `duration_seconds`."""
    if total_quantity <= 0:
        raise ValueError("total_quantity must be > 0")
    if num_slices <= 0:
        raise ValueError("num_slices must be > 0")
    base = total_quantity // num_slices
    remainder = total_quantity - base * num_slices
    step = duration_seconds / num_slices if num_slices > 1 else 0.0
    plans = []
    for i in range(num_slices):
        qty = base + (1 if i < remainder else 0)  # spread remainder across the first slices
        if qty > 0:
            plans.append(ChildOrderPlan(offset_seconds=round(i * step, 3), quantity=qty))
    return plans


def vwap_schedule(total_quantity: int, volume_profile: Sequence[float], duration_seconds: float) -> List[ChildOrderPlan]:
    """Split `total_quantity` proportionally to a historical intraday volume
    profile (e.g., average traded volume per bucket over the last N days),
    spread across `duration_seconds`. Buckets with zero/negative weight are
    skipped."""
    if total_quantity <= 0:
        raise ValueError("total_quantity must be > 0")
    weights = np.array(volume_profile, dtype=float)
    if weights.size == 0 or weights.sum() <= 0:
        raise ValueError("volume_profile must contain at least one positive weight")
    weights = np.clip(weights, 0.0, None)
    weights = weights / weights.sum()
    n = len(weights)
    step = duration_seconds / n if n > 1 else 0.0

    raw = weights * total_quantity
    qtys = np.floor(raw).astype(int)
    shortfall = int(total_quantity - qtys.sum())
    # Distribute leftover shares (from flooring) to the largest-weight buckets first
    if shortfall > 0:
        order = np.argsort(-raw)
        for i in order[:shortfall]:
            qtys[i] += 1

    plans = []
    for i, qty in enumerate(qtys):
        if qty > 0:
            plans.append(ChildOrderPlan(offset_seconds=round(i * step, 3), quantity=int(qty)))
    return plans
