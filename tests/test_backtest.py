import pandas as pd
import pytest

from trading_simulator import (OrderBook, MatchingEngine, PortfolioDispatcher, RiskManager, CsvLogger,
                                MarketMaker, MomentumTrader, EMABasedTrader, SwingTrader, run_backtest,
                                compute_performance_metrics)


@pytest.fixture
def synthetic_data():
    dates = pd.date_range("2023-01-01", periods=40, freq="D", tz="UTC")
    prices = [100 + i * 0.25 + (1.5 if i % 6 == 0 else -0.5) for i in range(40)]
    return pd.DataFrame({"Date": dates, "Close": prices})


def test_run_backtest_end_to_end(tmp_path, synthetic_data):
    ob = OrderBook()
    eng = MatchingEngine(ob)
    dispatcher = PortfolioDispatcher(fee_bps=1.0)
    portfolio = dispatcher.ensure("default", initial_cash=1_000_000.0)
    eng.subscribe_trades(dispatcher.on_execution)

    logger = CsvLogger(str(tmp_path))
    eng.subscribe_trades(logger.log_execution)
    eng.tca_logger = logger
    eng.risk_manager = RiskManager(portfolio=portfolio, max_order_qty=1000, max_symbol_position=100_000,
                                    max_gross_notional=5_000_000.0, owner_portfolios=dispatcher,
                                    price_provider=eng.get_last_trade_price)

    mm = MarketMaker(symbol="TEST", matching_engine=eng, base_order_size=50, capital_base=1_000_000.0)
    traders = [
        MomentumTrader(symbol="TEST", matching_engine=eng, interval=0.0, lookback=3, portfolio=portfolio),
        EMABasedTrader(symbol="TEST", matching_engine=eng, interval=0.0, short_window=3, long_window=8, portfolio=portfolio),
        SwingTrader(symbol="TEST", matching_engine=eng, interval=0.0, support_level=95, resistance_level=115, portfolio=portfolio),
    ]

    run_backtest(synthetic_data, mm, eng, traders=traders, portfolio=portfolio, csv_logger=logger)

    snap = portfolio.snapshot()
    # Some trading activity should have occurred over 40 days of moving prices
    assert snap["cash"] != 1_000_000.0 or snap["positions"]

    eq_df = pd.read_csv(str(tmp_path / "equity_curve.csv"))
    assert len(eq_df) == len(synthetic_data)
    metrics = compute_performance_metrics(pd.read_csv(str(tmp_path / "equity_curve.csv"), parse_dates=["timestamp"]))
    assert "sharpe" in metrics


def test_run_backtest_empty_data_is_a_noop():
    ob = OrderBook()
    eng = MatchingEngine(ob)
    mm = MarketMaker(symbol="TEST", matching_engine=eng)
    run_backtest(pd.DataFrame(columns=["Date", "Close"]), mm, eng)  # must not raise
