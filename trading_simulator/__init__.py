"""trading_simulator: institutional-grade algorithmic trading simulator.

This top-level package re-exports the most commonly used names so the
README's documented usage pattern actually works:

    from trading_simulator import MomentumTrader, MatchingEngine, OrderBook

(Previously the whole project lived in one script,
`trading_simulator_with_algorithmic_traders.py`, and the README's own
Quick Start examples imported from a `trading_simulator` module that did not
exist anywhere in the repository -- a new user following the README got
`ModuleNotFoundError` on the very first example. This package IS that
module now.)
"""
from .core import Order, OrderValidationError, OrderBook, Execution, MatchingEngine, InstrumentRegistry, InstrumentConfig, DEFAULT_REGISTRY
from .portfolio import Portfolio, PortfolioDispatcher
from .risk import RiskManager
from .strategies import (
    AlgorithmicTrader, MomentumTrader, EMABasedTrader, SwingTrader, CustomTrader,
    SentimentAnalysisTrader, NewsFetcher, StrategySpec, register_strategy, list_strategies,
    resolve_trader_class, load_custom_trader, StrategyLoadError, fixed_fraction_size,
)
from .marketmaker import MarketMaker
from .marketdata import MarketDataFeed, load_historical_data, load_multi_historical_data, SyntheticLiquidityProvider
from .connectivity import FixApplication, FixClient, FixSessionState, FixSessionError, OrderCliServer, Venue, MarketRouter
from .persistence import CsvLogger, AuditLogger, EventLogger, DbLogger, SQLA_AVAILABLE
from .backtest import run_backtest, run_multi_backtest, ReplayRunner, compute_performance_metrics, export_html_report, load_equity_curve
from .execution_algos import ChildOrderPlan, twap_schedule, vwap_schedule
from .streaming import EventBus, make_redis_publisher, make_kafka_publisher, REDIS_AVAILABLE, KAFKA_AVAILABLE

__version__ = "2.2.0"

__all__ = [
    "Order", "OrderValidationError", "OrderBook", "Execution", "MatchingEngine",
    "InstrumentRegistry", "InstrumentConfig", "DEFAULT_REGISTRY",
    "Portfolio", "PortfolioDispatcher", "RiskManager",
    "AlgorithmicTrader", "MomentumTrader", "EMABasedTrader", "SwingTrader", "CustomTrader",
    "SentimentAnalysisTrader", "NewsFetcher", "StrategySpec", "register_strategy", "list_strategies",
    "resolve_trader_class", "load_custom_trader", "StrategyLoadError", "fixed_fraction_size",
    "MarketMaker", "MarketDataFeed", "load_historical_data", "load_multi_historical_data",
    "SyntheticLiquidityProvider", "FixApplication", "FixClient", "FixSessionState", "FixSessionError",
    "OrderCliServer", "Venue", "MarketRouter",
    "CsvLogger", "AuditLogger", "EventLogger", "DbLogger", "SQLA_AVAILABLE",
    "run_backtest", "run_multi_backtest", "ReplayRunner", "compute_performance_metrics",
    "export_html_report", "load_equity_curve", "ChildOrderPlan", "twap_schedule", "vwap_schedule",
    "EventBus", "make_redis_publisher", "make_kafka_publisher", "REDIS_AVAILABLE", "KAFKA_AVAILABLE",
]
