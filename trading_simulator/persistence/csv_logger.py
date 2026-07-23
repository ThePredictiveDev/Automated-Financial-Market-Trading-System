"""Append-only CSV logging for executions, equity curve, and TCA (transaction
cost analysis)."""
from __future__ import annotations

import logging
import os
from math import isfinite
from typing import Any, Dict, Optional

import pandas as pd

from ..core.execution import Execution

logger = logging.getLogger(__name__)


class CsvLogger:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self.exec_path = os.path.join(self.base_dir, "executions.csv")
        self.equity_path = os.path.join(self.base_dir, "equity_curve.csv")
        self.tca_path = os.path.join(self.base_dir, "tca.csv")
        self.tca_adv_path = os.path.join(self.base_dir, "tca_adv.csv")
        self._init_file(self.exec_path, "timestamp,symbol,price,quantity,side,taker_order_id,maker_order_id,trade_id\n")
        self._init_file(self.equity_path, "timestamp,net_liquidation,realized_pnl,cash\n")
        self._init_file(self.tca_path, "timestamp,symbol,side,price,mid,last_trade,slippage_mid_bps,slippage_last_bps\n")
        self._init_file(self.tca_adv_path, "timestamp,symbol,side,entry_price,next_price,adverse\n")

    @staticmethod
    def _init_file(path: str, header: str) -> None:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(header)

    def log_execution(self, execu: Execution) -> None:
        try:
            with open(self.exec_path, "a", encoding="utf-8") as f:
                f.write(f"{execu.timestamp.isoformat()},{execu.symbol},{execu.price},{execu.quantity},"
                        f"{execu.side},{execu.taker_order_id},{execu.maker_order_id},{execu.trade_id}\n")
        except OSError:
            logger.warning("Failed to write execution log", exc_info=True)

    def log_equity(self, timestamp: pd.Timestamp, net_liq: float, realized: float, cash: float) -> None:
        if not (isfinite(float(net_liq)) and isfinite(float(realized)) and isfinite(float(cash))):
            logger.warning("Skipping non-finite equity point at %s", timestamp)
            return
        ts = timestamp
        if isinstance(ts, pd.Timestamp) and ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        try:
            with open(self.equity_path, "a", encoding="utf-8") as f:
                f.write(f"{ts.isoformat()},{float(net_liq)},{float(realized)},{float(cash)}\n")
        except OSError:
            logger.warning("Failed to write equity log", exc_info=True)

    def log_tca(self, timestamp, symbol: str, side: str, price: float, mid: Optional[float],
                last_trade: Optional[float], slip_mid_bps: Optional[float], slip_last_bps: Optional[float]) -> None:
        try:
            with open(self.tca_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp.isoformat()},{symbol},{side},{price},"
                        f"{'' if mid is None else mid},{'' if last_trade is None else last_trade},"
                        f"{'' if slip_mid_bps is None else slip_mid_bps},{'' if slip_last_bps is None else slip_last_bps}\n")
        except OSError:
            logger.warning("Failed to write TCA log", exc_info=True)

    def log_tca_adv(self, timestamp, symbol: str, side: str, entry: float, next_price: float, adverse: bool) -> None:
        try:
            with open(self.tca_adv_path, "a", encoding="utf-8") as f:
                f.write(f"{timestamp.isoformat()},{symbol},{side},{entry},{next_price},{int(adverse)}\n")
        except OSError:
            logger.warning("Failed to write TCA-adverse log", exc_info=True)

    def compute_periodic_metrics(self, lookback: int = 50) -> Optional[Dict[str, float]]:
        if not os.path.exists(self.equity_path):
            return None
        df = pd.read_csv(self.equity_path)
        if df.empty or "net_liquidation" not in df.columns:
            return None
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
        series = df["net_liquidation"].astype(float)
        if len(series) < 2:
            return None
        tail = series.tail(max(2, lookback))
        rets = tail.pct_change().dropna()
        mean = float(rets.mean()) if not rets.empty else 0.0
        std = float(rets.std(ddof=0)) if not rets.empty else 0.0
        downside = rets[rets < 0]
        downside_std = float(downside.std(ddof=0)) if not downside.empty else 0.0
        sharpe = (mean / std) * (252 ** 0.5) if std > 0 else float("nan")
        sortino = (mean / downside_std) * (252 ** 0.5) if downside_std > 0 else float("nan")
        roll_max = series.cummax()
        dd = series / roll_max - 1.0
        return {
            "net_liquidation": float(series.iloc[-1]),
            "realized_pnl": float(df["realized_pnl"].astype(float).iloc[-1]) if "realized_pnl" in df.columns else 0.0,
            "cash": float(df["cash"].astype(float).iloc[-1]) if "cash" in df.columns else 0.0,
            "sharpe_ann": sharpe,
            "sortino_ann": sortino,
            "vol_ann": float(std * (252 ** 0.5)) if std > 0 else 0.0,
            "drawdown_cur": float(dd.iloc[-1]),
            "drawdown_max": float(dd.min()),
        }
