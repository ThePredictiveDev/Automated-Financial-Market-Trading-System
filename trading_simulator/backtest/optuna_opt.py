"""Optuna hyperparameter search objective for the EMA/Momentum strategy pair.

Import-guarded: only usable if `optuna` is installed.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

from ..core.order_book import OrderBook
from ..core.matching_engine import MatchingEngine
from ..portfolio.portfolio import Portfolio
from ..persistence.csv_logger import CsvLogger
from ..risk.risk_manager import RiskManager
from ..strategies.ema import EMABasedTrader
from ..strategies.momentum import MomentumTrader
from ..marketmaker.market_maker import MarketMaker
from ..marketdata.history import load_historical_data
from .runner import run_backtest
from .metrics import load_equity_curve, compute_performance_metrics

logger = logging.getLogger(__name__)

try:
    import mlflow  # type: ignore
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def objective_optuna(trial, symbol: str, start: str, end: str, base_params: Dict[str, Any], log_dir: str) -> float:
    short_window = trial.suggest_int("short_window", 3, 20)
    long_window = trial.suggest_int("long_window", max(short_window + 1, 10), 60)
    lookback = trial.suggest_int("lookback", 3, 20)
    slippage = trial.suggest_float("slippage_bps_per_100", 0.0, 5.0)
    latency = trial.suggest_int("latency_ms", 0, 300)

    order_book = OrderBook()
    engine = MatchingEngine(order_book)
    engine.slippage_bps_per_100_shares = slippage
    engine.latency_ms = latency

    portfolio = Portfolio(initial_cash=float(base_params.get("initial_cash", 1_000_000.0)),
                          fee_bps=float(base_params.get("fee_bps", 0.0)))
    csv_logger = CsvLogger(log_dir)
    engine.subscribe_trades(portfolio.on_execution)
    engine.subscribe_trades(csv_logger.log_execution)

    engine.risk_manager = RiskManager(
        portfolio=portfolio,
        max_order_qty=int(base_params.get("risk_max_order_qty", 1000)),
        max_symbol_position=int(base_params.get("risk_max_symbol_position", 10_000)),
        max_gross_notional=float(base_params.get("risk_max_gross_notional", 5_000_000.0)),
    )

    data = load_historical_data(symbol, start, end)
    maker = MarketMaker(symbol=symbol, matching_engine=engine)
    traders = [
        EMABasedTrader(symbol=symbol, matching_engine=engine, interval=0.0, short_window=short_window, long_window=long_window),
        MomentumTrader(symbol=symbol, matching_engine=engine, interval=0.0, lookback=lookback),
    ]
    run_backtest(data, maker, engine, traders=traders, portfolio=portfolio, csv_logger=csv_logger)

    eq_df = load_equity_curve(os.path.join(log_dir, "equity_curve.csv"))
    metrics = compute_performance_metrics(eq_df)

    if MLFLOW_AVAILABLE:
        try:
            mlflow.log_params({"short_window": short_window, "long_window": long_window, "lookback": lookback,
                                "slippage_bps_per_100": slippage, "latency_ms": latency, "symbol": symbol,
                                "start": start, "end": end})
            for k, v in metrics.items():
                mlflow.log_metric(k, float(v))
        except Exception:
            logger.warning("MLflow logging failed", exc_info=True)

    return float(metrics.get("cagr", 0.0)) - 0.1 * abs(float(metrics.get("max_drawdown", 0.0)))
