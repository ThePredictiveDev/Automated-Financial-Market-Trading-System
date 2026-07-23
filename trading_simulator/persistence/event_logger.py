"""Append-only CSV event log (NEW/CANCEL/EXEC) used to deterministically
replay a session into a fresh engine via ReplayRunner."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import pandas as pd

from ..core.execution import Execution
from ..core.order import Order

logger = logging.getLogger(__name__)


class EventLogger:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.events_path = os.path.join(self.base_dir, "events.csv")
        self._seq = 0
        if not os.path.exists(self.events_path):
            with open(self.events_path, "w", encoding="utf-8") as f:
                f.write("seq,timestamp,event,order_id,symbol,side,type,price,quantity,extra\n")
        else:
            last = None
            with open(self.events_path, "r", encoding="utf-8") as f:
                for line in f:
                    last = line
            if last and not last.startswith("seq,"):
                parts = last.strip().split(",")
                if parts and parts[0].isdigit():
                    self._seq = int(parts[0])

    def log_new_order(self, order: Order) -> None:
        self._seq += 1
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(f"{self._seq},{pd.Timestamp.now(tz='UTC').isoformat()},NEW,{order.id},{order.symbol},"
                        f"{order.side},{order.type},{order.price},{order.quantity},owner={order.owner_id}\n")
        except OSError:
            logger.warning("Event log (new) failed", exc_info=True)

    def log_cancel(self, order_id: str) -> None:
        self._seq += 1
        try:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(f"{self._seq},{pd.Timestamp.now(tz='UTC').isoformat()},CANCEL,{order_id},,,,,,\n")
        except OSError:
            logger.warning("Event log (cancel) failed", exc_info=True)

    def log_execution(self, execu: Execution, best_bid: Optional[float] = None, best_ask: Optional[float] = None) -> None:
        self._seq += 1
        try:
            extra = []
            if best_bid is not None:
                extra.append(f"bb={best_bid}")
            if best_ask is not None:
                extra.append(f"ba={best_ask}")
            extra.append(f"maker={execu.maker_order_id}")
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(f"{self._seq},{execu.timestamp.isoformat()},EXEC,{execu.taker_order_id},{execu.symbol},"
                        f"{execu.side},,{execu.price},{execu.quantity},{' '.join(extra)}\n")
        except OSError:
            logger.warning("Event log (exec) failed", exc_info=True)

    def replay(self) -> List[Dict[str, Any]]:
        events: List[Dict[str, Any]] = []
        if not os.path.exists(self.events_path):
            return events
        with open(self.events_path, "r", encoding="utf-8") as f:
            next(f, None)  # header
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                idx = 1 if parts[0].isdigit() else 0
                seq = int(parts[0]) if idx == 1 else None
                ts, ev, oid = parts[idx], parts[idx + 1], parts[idx + 2]
                symbol = parts[idx + 3] if len(parts) > idx + 3 else ""
                side = parts[idx + 4] if len(parts) > idx + 4 else ""
                typ = parts[idx + 5] if len(parts) > idx + 5 else ""
                price = float(parts[idx + 6]) if len(parts) > idx + 6 and parts[idx + 6] else None
                qty = int(float(parts[idx + 7])) if len(parts) > idx + 7 and parts[idx + 7] else None
                extra_raw = parts[idx + 8] if len(parts) > idx + 8 else ""
                extras = dict(kv.split("=", 1) for kv in extra_raw.split() if "=" in kv)
                events.append({"seq": seq, "timestamp": ts, "event": ev, "order_id": oid, "symbol": symbol,
                                "side": side, "type": typ, "price": price, "quantity": qty, "extra": extras, "raw": parts})
        return events
