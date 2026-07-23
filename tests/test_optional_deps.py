"""Graceful-degradation tests for optional third-party dependencies.

None of simplefix, tensorflow, sqlalchemy, optuna, mlflow, redis, or kafka
are installed in the test environment, so these exercise the *real*
ImportError-guard code paths (no mocking needed): every optional feature
should fail with a clear, actionable message instead of a confusing
AttributeError/TypeError/NoneType crash.
"""
import importlib

import pytest

from trading_simulator.connectivity.fix_app import FixApplication, FixClient, SIMPLEFIX_AVAILABLE
from trading_simulator.persistence.db_logger import DbLogger, SQLA_AVAILABLE
from trading_simulator.strategies.sentiment import SentimentAnalysisTrader, TF_AVAILABLE
from trading_simulator.core.matching_engine import MatchingEngine
from trading_simulator.core.order_book import OrderBook


def test_simplefix_not_available_in_this_environment():
    assert SIMPLEFIX_AVAILABLE is False


def test_fix_application_raises_clear_error_without_simplefix():
    engine = MatchingEngine(OrderBook())
    with pytest.raises(RuntimeError) as exc_info:
        FixApplication(engine)
    msg = str(exc_info.value)
    assert "simplefix" in msg.lower()
    assert "pip install" in msg.lower()


def test_fix_client_raises_clear_error_without_simplefix():
    with pytest.raises(RuntimeError) as exc_info:
        FixClient()
    msg = str(exc_info.value)
    assert "simplefix" in msg.lower()
    assert "pip install" in msg.lower()


def test_tensorflow_not_available_in_this_environment():
    assert TF_AVAILABLE is False


def test_sentiment_trader_raises_clear_error_without_tensorflow():
    engine = MatchingEngine(OrderBook())
    with pytest.raises(RuntimeError) as exc_info:
        SentimentAnalysisTrader(symbol="AAPL", matching_engine=engine, model_file="does_not_matter.keras",
                                 news_api_key="fake-key")
    msg = str(exc_info.value)
    assert "tensorflow" in msg.lower()
    assert "pip install" in msg.lower()


def test_sqlalchemy_not_available_in_this_environment():
    assert SQLA_AVAILABLE is False


def test_db_logger_raises_clear_error_without_sqlalchemy_instead_of_nonetype_crash():
    # Before the fix, DbLogger was bound to plain `None` when SQLAlchemy was
    # missing, so DbLogger(...) failed with an opaque
    # "TypeError: 'NoneType' object is not callable" -- this asserts the
    # actionable RuntimeError instead.
    with pytest.raises(RuntimeError) as exc_info:
        DbLogger("sqlite:///:memory:")
    msg = str(exc_info.value)
    assert "sqlalchemy" in msg.lower()
    assert "pip install" in msg.lower()


def test_optuna_missing_logs_clean_warning_and_returns_without_crashing(caplog):
    import importlib
    cli_main = importlib.import_module("trading_simulator.cli.main")

    class _Args:
        optuna_trials = 5
        symbol = "AAPL"
        start_date = "2023-01-01"
        end_date = "2023-01-10"
        log_dir = ".logs"
        initial_cash = 1_000_000.0
        fee_bps = 0.0
        risk_max_order_qty = 1000
        risk_max_symbol_position = 10_000
        risk_max_gross_notional = 5_000_000.0
        mlflow_uri = None
        mlflow_experiment = "trading-simulator"

    with caplog.at_level("WARNING"):
        cli_main._run_optuna(_Args())  # must not raise
    assert any("optuna" in r.message.lower() for r in caplog.records)


def test_kafka_and_redis_publishers_raise_clear_errors_without_libraries():
    from trading_simulator.streaming import make_redis_publisher, make_kafka_publisher, REDIS_AVAILABLE, KAFKA_AVAILABLE
    assert REDIS_AVAILABLE is False
    assert KAFKA_AVAILABLE is False
    with pytest.raises(RuntimeError):
        make_redis_publisher("redis://localhost:6379", "trades")
    with pytest.raises(RuntimeError):
        make_kafka_publisher(["localhost:9092"], "trades")
