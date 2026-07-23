"""CLI entry point: guided interactive mode (no flags) or full argparse flags.

Ported from the original single-script `main()` (~900 lines). Behavior is
preserved; the main structural change is factoring the four run modes
(backtest/replay/live/demo) into separate functions and de-duplicating the
periodic-metrics logging block that was previously copy-pasted three times.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..core.order_book import OrderBook
from ..core.matching_engine import MatchingEngine
from ..portfolio.portfolio import PortfolioDispatcher
from ..risk.risk_manager import RiskManager
from ..persistence.csv_logger import CsvLogger
from ..strategies import AlgorithmicTrader, MomentumTrader, EMABasedTrader, SwingTrader, SentimentAnalysisTrader
from ..strategies.registry import load_custom_trader, StrategyLoadError
from ..marketmaker.market_maker import MarketMaker
from ..marketdata.feed import MarketDataFeed
from ..marketdata.history import load_historical_data, load_multi_historical_data
from ..marketdata.liquidity import SyntheticLiquidityProvider
from ..connectivity.fix_app import FixApplication, SIMPLEFIX_AVAILABLE
from ..connectivity.order_cli import OrderCliServer
from ..backtest.runner import run_backtest, run_multi_backtest
from ..backtest.metrics import load_equity_curve, compute_performance_metrics, export_html_report
from .args import build_parser
from .guided import run_guided_cli

logger = logging.getLogger(__name__)


def _set_seed(seed: Optional[int]) -> None:
    if seed is None:
        return
    import random
    random.seed(seed)
    np.random.seed(seed & 0xFFFFFFFF)


def _log_periodic_metrics(csv_logger: CsvLogger) -> None:
    metrics = csv_logger.compute_periodic_metrics(lookback=100)
    if not metrics:
        return
    logger.info(
        "Metrics: net_liq=%.2f cash=%.2f realized=%.2f sharpe=%.3f sortino=%.3f vol=%.3f%% "
        "dd_cur=%.2f%% dd_max=%.2f%% trades=%.0f",
        metrics.get("net_liquidation", float("nan")), metrics.get("cash", float("nan")),
        metrics.get("realized_pnl", float("nan")), metrics.get("sharpe_ann", float("nan")),
        metrics.get("sortino_ann", float("nan")), metrics.get("vol_ann", 0.0) * 100.0,
        metrics.get("drawdown_cur", 0.0) * 100.0, metrics.get("drawdown_max", 0.0) * 100.0,
        metrics.get("trades", 0.0),
    )


def _build_market_maker(symbol: str, engine, args) -> MarketMaker:
    return MarketMaker(
        symbol=symbol, matching_engine=engine, gamma=args.mm_gamma, k=args.mm_k,
        horizon_seconds=args.mm_horizon_seconds, max_inventory=args.mm_max_inventory,
        base_order_size=args.mm_base_order_size, min_spread=args.mm_min_spread,
        num_levels=args.mm_num_levels, level_spacing_bps=args.mm_level_spacing_bps,
        size_decay=args.mm_size_decay, momentum_window=args.mm_momentum_window,
        alpha_skew=args.mm_alpha_skew, vol_widen_z=args.mm_vol_widen_z, drawdown_limit=args.mm_drawdown_limit,
        capital_base=args.mm_capital_base,
    )


def _build_traders(symbol: str, engine, args, portfolio=None, live_intervals: bool = False) -> List[AlgorithmicTrader]:
    if not args.enable_traders:
        return []
    momentum_interval = 10 if live_intervals else 0.0
    ema_interval = 30 if live_intervals else 0.0
    swing_interval = 15 if live_intervals else 0.0
    return [
        MomentumTrader(symbol=symbol, matching_engine=engine, interval=momentum_interval, lookback=int(args.momentum_lookback)),
        EMABasedTrader(symbol=symbol, matching_engine=engine, interval=ema_interval, short_window=int(args.ema_short_window), long_window=int(args.ema_long_window)),
        SwingTrader(symbol=symbol, matching_engine=engine, interval=swing_interval, support_level=float(args.swing_support), resistance_level=float(args.swing_resistance)),
    ]


def _load_custom_traders(args, symbol: str, engine) -> List[AlgorithmicTrader]:
    traders: List[AlgorithmicTrader] = []
    specs = args.custom_trader or []
    params_list = args.custom_trader_params or []
    for idx, spec in enumerate(specs):
        params_json = params_list[idx] if idx < len(params_list) else "{}"
        try:
            traders.append(load_custom_trader(spec, params_json, symbol, engine))
        except StrategyLoadError as exc:
            logger.warning("Failed to load custom trader %r: %s", spec, exc)
    return traders


def _build_common(args) -> Dict:
    order_book = OrderBook()
    engine = MatchingEngine(order_book)
    engine.slippage_bps_per_100_shares = max(0.0, args.slippage_bps_per_100)
    engine.latency_ms = max(0, int(args.latency_ms))
    engine.price_band_bps = max(0.0, args.price_band_bps)
    engine.band_reference = args.band_reference
    engine.taker_fee_bps = max(0.0, args.taker_fee_bps)
    engine.maker_rebate_bps = max(0.0, args.maker_rebate_bps)
    engine.use_queue = bool(args.use_queue)
    engine.queue_max = max(1, int(args.queue_max))
    if args.snapshot_interval_sec and args.snapshot_dir:
        engine.start_snapshotting(int(args.snapshot_interval_sec), args.snapshot_dir)

    dispatcher = PortfolioDispatcher(fee_bps=args.fee_bps)
    portfolio = dispatcher.ensure("default", initial_cash=args.initial_cash)
    engine.subscribe_trades(dispatcher.on_execution)

    csv_logger = CsvLogger(args.log_dir)
    engine.subscribe_trades(csv_logger.log_execution)
    engine.tca_logger = csv_logger

    engine.risk_manager = RiskManager(
        portfolio=portfolio, max_order_qty=args.risk_max_order_qty,
        max_symbol_position=args.risk_max_symbol_position, max_gross_notional=args.risk_max_gross_notional,
        min_order_qty=max(1, args.risk_min_order_qty), lot_size=max(1, args.risk_lot_size),
        round_lot_required=bool(args.risk_round_lot_required), order_rate_limit_per_sec=args.risk_order_rate_limit,
        owner_drawdown_limit=args.risk_owner_drawdown_limit, owner_portfolios=dispatcher,
        price_provider=engine.get_last_trade_price, volatility_window=max(5, args.risk_volatility_window),
        volatility_halt_z=args.risk_volatility_halt_z, max_leverage=args.risk_max_leverage,
        max_symbol_gross_exposure=args.risk_max_symbol_gross_exposure,
    )
    return {"order_book": order_book, "engine": engine, "dispatcher": dispatcher, "portfolio": portfolio, "csv_logger": csv_logger}


def _run_backtest_mode(args, common: Dict) -> None:
    engine, portfolio, csv_logger = common["engine"], common["portfolio"], common["csv_logger"]
    if args.symbols:
        symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
        data_map = load_multi_historical_data(symbols, args.start_date, args.end_date)
        engines, makers, traders_map = {}, {}, {}
        for sym in symbols:
            ob = OrderBook()
            eng = MatchingEngine(ob)
            eng.slippage_bps_per_100_shares = engine.slippage_bps_per_100_shares
            eng.latency_ms = engine.latency_ms
            eng.subscribe_trades(portfolio.on_execution)
            eng.subscribe_trades(csv_logger.log_execution)
            eng.risk_manager = engine.risk_manager
            engines[sym] = eng
            makers[sym] = _build_market_maker(sym, eng, args)
            eng.subscribe_trades(makers[sym].on_execution)
            traders_map[sym] = _build_traders(sym, eng, args)
        run_multi_backtest(data_map, engines, makers, traders_map or None, portfolio, csv_logger)
    else:
        historical_data = load_historical_data(args.symbol, args.start_date, args.end_date)
        market_maker = _build_market_maker(args.symbol, engine, args)
        traders = _build_traders(args.symbol, engine, args) + _load_custom_traders(args, args.symbol, engine)
        run_backtest(historical_data, market_maker, engine, traders=traders or None, portfolio=portfolio, csv_logger=csv_logger)
        _log_periodic_metrics(csv_logger)

    if args.export_report:
        try:
            eq_df = load_equity_curve(os.path.join(args.log_dir, "equity_curve.csv"))
            export_html_report(eq_df, compute_performance_metrics(eq_df), args.report_out)
            logger.info("Report exported to %s", args.report_out)
        except (FileNotFoundError, RuntimeError) as exc:
            logger.warning("Report export failed: %s", exc)

    if args.optuna_trials and args.optuna_trials > 0:
        _run_optuna(args)

    snap = portfolio.snapshot()
    logger.info("Portfolio after backtest: cash=%.2f realized_pnl=%.2f positions=%s", snap["cash"], snap["realized_pnl"], snap["positions"])


def _run_optuna(args) -> None:
    try:
        import optuna
    except ImportError:
        logger.warning("Optuna not installed. `pip install optuna` to use --optuna-trials.")
        return
    from ..backtest.optuna_opt import objective_optuna, MLFLOW_AVAILABLE

    mlflow = None
    if MLFLOW_AVAILABLE and args.mlflow_uri:
        import mlflow as _mlflow
        mlflow = _mlflow
        mlflow.set_tracking_uri(args.mlflow_uri)
        mlflow.set_experiment(args.mlflow_experiment)

    base_params = {"initial_cash": args.initial_cash, "fee_bps": args.fee_bps,
                   "risk_max_order_qty": args.risk_max_order_qty,
                   "risk_max_symbol_position": args.risk_max_symbol_position,
                   "risk_max_gross_notional": args.risk_max_gross_notional}

    def _obj(trial):
        if mlflow is not None:
            with mlflow.start_run(nested=True):
                return objective_optuna(trial, args.symbol, args.start_date, args.end_date, base_params, args.log_dir)
        return objective_optuna(trial, args.symbol, args.start_date, args.end_date, base_params, args.log_dir)

    study = optuna.create_study(direction="maximize")
    study.optimize(_obj, n_trials=int(args.optuna_trials))
    logger.info("Optuna best value=%.6f params=%s", study.best_value, study.best_params)
    if mlflow is not None:
        with mlflow.start_run(run_name="optuna-summary"):
            mlflow.log_params(study.best_params)
            mlflow.log_metric("best_value", float(study.best_value))


def _run_replay_mode(args, common: Dict) -> None:
    engine, portfolio, csv_logger = common["engine"], common["portfolio"], common["csv_logger"]
    historical_data = load_historical_data(args.symbol, args.start_date, args.end_date)
    market_maker = _build_market_maker(args.symbol, engine, args)
    engine.subscribe_trades(market_maker.on_execution)
    traders = _build_traders(args.symbol, engine, args) + _load_custom_traders(args, args.symbol, engine)

    for _, row in historical_data.iterrows():
        ts = row["Date"] if isinstance(row["Date"], pd.Timestamp) else pd.to_datetime(row["Date"], utc=True)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        engine.set_time(ts)
        engine.process_delayed_orders(ts)
        md = {"symbol": args.symbol, "price": float(row["Close"]), "timestamp": ts}
        market_maker.on_market_data(md)
        for t in traders:
            try:
                t.on_market_data(md)
                t.trade()
            except Exception:
                logger.warning("Replay trader %s raised", type(t).__name__, exc_info=True)
        net_liq = portfolio.equity({args.symbol: float(row["Close"])}) + portfolio.realized_pnl
        csv_logger.log_equity(ts, net_liq, portfolio.realized_pnl, portfolio.cash)
        sleep_s = args.replay_interval_seconds if args.replay_interval_seconds is not None else 1.0 / max(0.1, args.replay_speed)
        time.sleep(max(0.0, sleep_s))

    logger.info("Replay completed.")
    _log_periodic_metrics(csv_logger)
    snap = portfolio.snapshot()
    logger.info("Portfolio after replay: cash=%.2f realized_pnl=%.2f positions=%s", snap["cash"], snap["realized_pnl"], snap["positions"])


def _start_order_cli(engine, args) -> OrderCliServer:
    order_cli = OrderCliServer(engine, host=args.order_cli_host, port=args.order_cli_port, default_owner=args.order_cli_owner)
    order_cli.start()
    # Log the *actual* bound port, not the requested one: --order-cli-port 0
    # asks the OS for an ephemeral port, and order_cli.port is populated with
    # the real assignment only after start() returns. Logging args.order_cli_port
    # here used to print "0" verbatim, leaving the user with no way to discover
    # which port to actually connect to.
    logger.info("Order CLI enabled: send JSON to %s:%d", args.order_cli_host, order_cli.port)
    return order_cli


def _run_live_mode(args, common: Dict) -> None:
    engine, portfolio, csv_logger = common["engine"], common["portfolio"], common["csv_logger"]
    symbol = args.symbol

    fix_app: Optional[FixApplication] = FixApplication(
        engine, sender_comp_id=args.fix_sender_comp_id, target_comp_id=args.fix_target_comp_id,
        heartbeat_interval=args.fix_heartbeat_interval,
    ) if SIMPLEFIX_AVAILABLE else None
    feed = MarketDataFeed(symbol=symbol)
    market_maker = _build_market_maker(symbol, engine, args)
    engine.subscribe_trades(market_maker.on_execution)

    if fix_app is not None:
        threading.Thread(target=fix_app.start, kwargs={"host": args.fix_host, "port": args.fix_port}, daemon=True).start()
        logger.info("FIX server enabled: %s:%d (SenderCompID=%s TargetCompID=%s HeartBtInt=%ds)",
                     args.fix_host, args.fix_port, args.fix_sender_comp_id, args.fix_target_comp_id, args.fix_heartbeat_interval)
    else:
        logger.warning("FIX server disabled: simplefix is not installed (`pip install simplefix` to enable it)")
    threading.Thread(target=feed.start, kwargs={"interval_seconds": args.md_interval}, daemon=True).start()
    market_maker.start(feed)

    traders = _build_traders(symbol, engine, args, live_intervals=True) + _load_custom_traders(args, symbol, engine)
    if args.news_api_key:
        try:
            traders.append(SentimentAnalysisTrader(symbol=symbol, matching_engine=engine, model_file=args.sentiment_model_path,
                                                    news_api_key=args.news_api_key, interval=60, vocab_path=args.sentiment_vocab_path))
        except Exception as exc:
            logger.warning("Sentiment trader disabled: %s", exc)

    trader_threads = [threading.Thread(target=t.start, args=(feed,), daemon=True) for t in traders]
    for t in trader_threads:
        t.start()

    order_cli = _start_order_cli(engine, args) if args.order_cli_enable else None

    if args.inject_liquidity > 0:
        provider = SyntheticLiquidityProvider(symbol=symbol, matching_engine=engine, num_orders=10)

        def _inject_loop():
            while True:
                try:
                    provider.generate_liquidity()
                except Exception:
                    logger.exception("Liquidity injection error")
                time.sleep(max(1, int(args.inject_liquidity)))

        threading.Thread(target=_inject_loop, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        market_maker.stop()
        feed.stop()
        if fix_app is not None:
            fix_app.stop()
        for t in traders:
            t.stop()
        for th in trader_threads:
            th.join(timeout=5)
        if order_cli is not None:
            order_cli.stop()

        snap = portfolio.snapshot()
        last_price = feed.last_price()
        if last_price is not None:
            net_liq = portfolio.equity({symbol: last_price}) + portfolio.realized_pnl
            csv_logger.log_equity(pd.Timestamp.now(tz="UTC"), net_liq, portfolio.realized_pnl, portfolio.cash)
        _log_periodic_metrics(csv_logger)
        logger.info("Final portfolio: cash=%.2f realized_pnl=%.2f positions=%s", snap["cash"], snap["realized_pnl"], snap["positions"])


def _run_demo_mode(common: Dict) -> None:
    import uuid
    from ..core.order import Order
    order_book = common["order_book"]
    order_book.add_order(Order(id=uuid.uuid4().hex, price=415.0, quantity=100, side="sell", type="limit", symbol="MSFT"))
    order_book.display_order_book()


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if argv is None and len(sys.argv) == 1:
        guided_args = run_guided_cli()
        if guided_args is None:
            return
        argv = guided_args

    parser = build_parser()
    args = parser.parse_args(argv)
    _set_seed(args.seed)

    try:
        common = _build_common(args)
        if args.mode == "backtest":
            _run_backtest_mode(args, common)
        elif args.mode == "demo":
            _run_demo_mode(common)
        elif args.mode == "replay":
            _run_replay_mode(args, common)
        else:
            _run_live_mode(args, common)
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        raise SystemExit(130)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        # Expected, actionable failures (bad symbol, no market data provider
        # installed, malformed custom-trader spec, etc.) get a clean one-line
        # message instead of a raw traceback -- pass --debug to see the full
        # traceback when actually debugging the library itself.
        if args.debug:
            raise
        logger.error("%s", exc)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
