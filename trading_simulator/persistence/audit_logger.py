"""JSON-lines audit trail for orders, cancels, and executions (compliance/replay)."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import pandas as pd

from ..core.execution import Execution
from ..core.order import Order

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.audit_path = os.path.join(self.base_dir, "audit.jsonl")

    def _write(self, payload: Dict[str, Any]) -> None:
        try:
            with open(self.audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, default=str) + "\n")
        except OSError:
            logger.warning("Audit write failed", exc_info=True)

    def log_new_order(self, order: Order) -> None:
        self._write({
            "ts": pd.Timestamp.now(tz="UTC").isoformat(), "event": "order_accepted", "order_id": order.id,
            "symbol": order.symbol, "side": order.side, "type": order.type, "price": order.price,
            "quantity": order.quantity, "owner": order.owner_id, "tif": order.tif,
        })

    def log_cancel(self, order_id: str) -> None:
        self._write({"ts": pd.Timestamp.now(tz="UTC").isoformat(), "event": "order_cancel", "order_id": order_id})

    def log_execution(self, execu: Execution) -> None:
        self._write({
            "ts": execu.timestamp.isoformat(), "event": "execution", "trade_id": execu.trade_id,
            "symbol": execu.symbol, "side": execu.side, "price": float(execu.price), "quantity": int(execu.quantity),
            "taker_order_id": execu.taker_order_id, "maker_order_id": execu.maker_order_id,
            "taker_owner_id": execu.taker_owner_id, "maker_owner_id": execu.maker_owner_id,
        })
