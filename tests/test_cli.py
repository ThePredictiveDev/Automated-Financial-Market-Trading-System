import io
import os
import sys

import pandas as pd
import pytest

import importlib
cli_main = importlib.import_module("trading_simulator.cli.main")
from trading_simulator.cli.guided import run_guided_cli


def _synthetic_history(symbol, start_date, end_date):
    dates = pd.date_range("2023-01-01", periods=30, freq="D", tz="UTC")
    prices = [100 + i * 0.2 + (1.0 if i % 5 == 0 else -0.3) for i in range(30)]
    return pd.DataFrame({"Date": dates, "Close": prices})


def _synthetic_multi_history(symbols, start_date, end_date):
    return {sym: _synthetic_history(sym, start_date, end_date) for sym in symbols}


def test_cli_demo_mode_runs_without_error(capsys):
    cli_main.main(["--mode", "demo"])  # must not raise


def test_cli_backtest_mode_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "load_historical_data", _synthetic_history)
    log_dir = str(tmp_path / "logs")
    cli_main.main(["--mode", "backtest", "--symbol", "AAPL", "--enable-traders",
                   "--log-dir", log_dir, "--export-report", "--report-out", str(tmp_path / "report.html")])
    assert os.path.exists(os.path.join(log_dir, "equity_curve.csv"))
    assert os.path.exists(os.path.join(log_dir, "executions.csv"))
    assert os.path.exists(str(tmp_path / "report.html"))


def test_cli_backtest_multi_asset(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "load_multi_historical_data", _synthetic_multi_history)
    log_dir = str(tmp_path / "logs")
    cli_main.main(["--mode", "backtest", "--symbols", "AAPL,MSFT", "--enable-traders", "--log-dir", log_dir])
    assert os.path.exists(os.path.join(log_dir, "equity_curve.csv"))


def test_cli_backtest_with_custom_trader_from_examples(tmp_path, monkeypatch):
    # Exercises the exact README-documented custom trader workflow end-to-end.
    monkeypatch.setattr(cli_main, "load_historical_data", _synthetic_history)
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__))))
    log_dir = str(tmp_path / "logs")
    cli_main.main([
        "--mode", "backtest", "--symbol", "AAPL", "--log-dir", log_dir,
        "--custom-trader", "examples.strats:BreakoutTrader",
        "--custom-trader-params", '{"lookback": 5, "band_bps": 5, "owner_id": "bo"}',
    ])
    assert os.path.exists(os.path.join(log_dir, "equity_curve.csv"))


def test_cli_backtest_bad_custom_trader_spec_gives_clean_error(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(cli_main, "load_historical_data", _synthetic_history)
    log_dir = str(tmp_path / "logs")
    # Should log a warning and continue (not crash the whole backtest) since
    # _load_custom_traders swallows StrategyLoadError per-spec.
    cli_main.main(["--mode", "backtest", "--symbol", "AAPL", "--log-dir", log_dir,
                   "--custom-trader", "not_a_real_module:NotARealClass"])
    assert os.path.exists(os.path.join(log_dir, "equity_curve.csv"))


def test_cli_replay_mode_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(cli_main, "load_historical_data", _synthetic_history)
    log_dir = str(tmp_path / "logs")
    cli_main.main(["--mode", "replay", "--symbol", "AAPL", "--replay-interval-seconds", "0",
                   "--enable-traders", "--log-dir", log_dir])
    assert os.path.exists(os.path.join(log_dir, "equity_curve.csv"))


def test_cli_missing_market_data_provider_exits_cleanly_not_a_traceback():
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--mode", "backtest", "--symbol", "AAPL", "--start-date", "2023-01-01", "--end-date", "2023-01-05"])
    assert exc_info.value.code == 1


def test_cli_debug_flag_reraises_full_exception():
    with pytest.raises(RuntimeError):
        cli_main.main(["--mode", "backtest", "--symbol", "AAPL", "--debug"])


def test_guided_cli_demo_selection(monkeypatch):
    inputs = iter(["4"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    argv = run_guided_cli()
    assert argv == ["--mode", "demo"]


def test_guided_cli_backtest_minimal_answers(monkeypatch):
    # Every guided prompt answered "no"/blank -- the most common path for a
    # first-time user just trying the tool.
    answers = iter([
        "1",       # mode: backtest
        "AAPL",    # symbol
        "",        # multi-asset symbols (blank)
        "",        # start date (default)
        "",        # end date (default)
        "n",       # enable built-in traders
        "",        # log dir (default)
        "",        # seed
        "n",       # customize microstructure
        "n",       # customize matching protections
        "n",       # customize risk manager
        "n",       # add custom traders
        "n",       # export report
        "n",       # optuna
    ])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    argv = run_guided_cli()
    assert argv[:6] == ["--mode", "backtest", "--symbol", "AAPL", "--start-date", "2023-01-01"]
    assert "--enable-traders" not in argv


def test_start_order_cli_logs_actual_bound_port_not_requested_zero(caplog):
    # Regression test: --order-cli-port 0 asks the OS for an ephemeral port.
    # main.py used to log args.order_cli_port (still "0") instead of the real
    # bound port, leaving the user with no way to discover which port to
    # connect to. _start_order_cli must log order_cli.port instead.
    from trading_simulator.core.order_book import OrderBook
    from trading_simulator.core.matching_engine import MatchingEngine

    class _Args:
        order_cli_host = "127.0.0.1"
        order_cli_port = 0
        order_cli_owner = "cli"

    engine = MatchingEngine(OrderBook())
    with caplog.at_level("INFO"):
        order_cli = cli_main._start_order_cli(engine, _Args())
    try:
        assert order_cli.port != 0
        matching = [r.message for r in caplog.records if "Order CLI enabled" in r.message]
        assert matching, "expected an 'Order CLI enabled' log line"
        assert f":{order_cli.port}" in matching[-1]
        assert ":0" not in matching[-1]
    finally:
        order_cli.stop()


def test_guided_cli_advanced_mode_passes_through_raw_flags(monkeypatch):
    inputs = iter(["5", "--mode demo"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    argv = run_guided_cli()
    assert argv == ["--mode", "demo"]


def test_guided_cli_keyboard_interrupt_returns_none(monkeypatch):
    def _raise(*_a, **_kw):
        raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", _raise)
    assert run_guided_cli() is None
