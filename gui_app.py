"""
FastAPI GUI for Trading Simulator

Run:
  uvicorn gui_app:app --reload --host 0.0.0.0 --port 8000

This app manages live and backtest sessions, exposes REST endpoints,
and serves a simple single-page UI with controls and charts.
"""

from __future__ import annotations

import threading
import time
import os
import uuid
from typing import Any, Dict, List, Optional
import pandas as pd

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from trading_simulator_with_algorithmic_traders import (
    Order,
    OrderBook,
    MatchingEngine,
    MarketDataFeed,
    MarketMaker,
    MomentumTrader,
    EMABasedTrader,
    SwingTrader,
    SentimentAnalysisTrader,
    CustomTrader,
    Portfolio,
    RiskManager,
    CsvLogger,
    mark_to_market,
    load_historical_data,
    run_backtest,
    FixApplication,
    list_strategies,
    objective_optuna,
    load_multi_historical_data,
    run_multi_backtest,
    export_html_report,
    _load_equity_curve,
    compute_performance_metrics,
    LOT_SIZE,
    DECIMAL_PRECISION,
    INSTRUMENTS,
    PortfolioDispatcher,
)
import asyncio
try:
    import optuna  # type: ignore
    _OPTUNA = True
except Exception:
    _OPTUNA = False
try:
    import mlflow  # type: ignore
    _MLFLOW = True
except Exception:
    _MLFLOW = False
try:
    from trading_simulator_with_algorithmic_traders import DbLogger  # type: ignore
    _DBLOGGER = True
except Exception:
    _DBLOGGER = False


class StartRequest(BaseModel):
    mode: str = Field("backtest", pattern="^(backtest|live)$")
    symbol: str = Field("AAPL")
    symbols: Optional[str] = None
    start_date: Optional[str] = "2023-01-01"
    end_date: Optional[str] = "2023-12-31"
    enable_traders: bool = False
    enable_sentiment: bool = False
    news_api_key: str = ""
    sentiment_model_path: str = "sentiment_classifier_model.keras"
    sentiment_vocab_path: Optional[str] = None
    md_interval: int = 60
    inject_liquidity: int = 0
    fix_host: str = "localhost"
    fix_port: int = 5005
    enable_fix: bool = False
    slippage_bps_per_100: float = 0.0
    latency_ms: int = 0
    price_band_bps: float = 0.0
    band_reference: str = "mid"  # 'mid' or 'last'
    export_report: bool = False
    report_out: str = "report.html"
    seed: Optional[int] = None
    initial_cash: float = 1_000_000.0
    fee_bps: float = 0.0
    maker_rebate_bps: float = 0.0
    sessions: Optional[Dict[str, Dict[str, Any]]] = None
    risk_max_order_qty: int = 1000
    risk_max_symbol_position: int = 10_000
    risk_max_gross_notional: float = 5_000_000.0
    risk_min_order_qty: int = 1
    risk_lot_size: int = 1
    risk_round_lot_required: bool = False
    risk_order_rate_limit_per_sec: Optional[int] = None
    risk_owner_drawdown_limit: Optional[float] = None
    log_dir: str = ".logs"
    db_uri: Optional[str] = None
    custom_threshold: Optional[float] = None
    decimal_precision: Optional[Dict[str, int]] = None
    lot_size: Optional[Dict[str, int]] = None


class TradingController:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.running = False
        self.mode: Optional[str] = None

        # Core components
        self.order_book: Optional[OrderBook] = None
        self.engine: Optional[MatchingEngine] = None
        self.feed: Optional[MarketDataFeed] = None
        self.maker: Optional[MarketMaker] = None
        self.traders: Dict[str, Any] = {}
        self.trader_threads: Dict[str, threading.Thread] = {}
        self.fix_thread: Optional[threading.Thread] = None
        self.fix_app: Optional[FixApplication] = None
        self.feed_thread: Optional[threading.Thread] = None
        self.liquidity_thread: Optional[threading.Thread] = None

        self.portfolio: Optional[Portfolio] = None
        self.portfolios: Optional[PortfolioDispatcher] = None
        self.logger: Optional[CsvLogger] = None
        self.config: Optional[StartRequest] = None

        # State
        self.symbol: str = "AAPL"
        self.last_executions: List[Dict[str, Any]] = []
        self.equity_points: List[Dict[str, Any]] = []
        self.db_logger: Optional[DbLogger] = None
        # Optimization state
        self.optimize_thread: Optional[threading.Thread] = None
        self.optimize_running: bool = False
        self.optimize_trials_done: int = 0
        self.optimize_best_value: Optional[float] = None
        self.optimize_best_params: Dict[str, Any] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _on_execution(self, execu) -> None:  # Execution from engine
        with self.lock:
            self.last_executions.append(
                {
                    "timestamp": execu.timestamp.isoformat(),
                    "symbol": execu.symbol,
                    "price": execu.price,
                    "quantity": execu.quantity,
                    "side": execu.side,
                    "taker_order_id": execu.taker_order_id,
                    "maker_order_id": execu.maker_order_id,
                    "trade_id": execu.trade_id,
                }
            )
            # cap to last 500
            if len(self.last_executions) > 500:
                self.last_executions = self.last_executions[-500:]
        # also log to CSV
        if self.logger is not None:
            self.logger.log_execution(execu)
        # push update to websockets
        try:
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(ws_manager.broadcast({"type": "execution", "data": self.last_executions[-1]}), self._loop)
        except Exception:
            pass

    def _on_market_data_tick(self, data: Dict[str, Any]) -> None:
        # Update equity on every tick
        try:
            if self.portfolio is None:
                return
            price = float(data["price"])
            net_liq = mark_to_market(self.portfolio, {self.symbol: price}) + self.portfolio.realized_pnl
            point = {
                "timestamp": str(data.get("timestamp")),
                "net_liquidation": net_liq,
                "cash": self.portfolio.cash,
                "realized_pnl": self.portfolio.realized_pnl,
            }
            with self.lock:
                self.equity_points.append(point)
                if len(self.equity_points) > 1000:
                    self.equity_points = self.equity_points[-1000:]
            if self.logger is not None:
                from pandas import Timestamp

                ts = data.get("timestamp")
                ts = ts if isinstance(ts, Timestamp) else None
                self.logger.log_equity(ts or Timestamp.utcnow().tz_localize("UTC"), net_liq, self.portfolio.realized_pnl, self.portfolio.cash)
            # push equity snapshot
            try:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(ws_manager.broadcast({"type": "equity", "data": self.equity_points[-1]}), self._loop)
            except Exception:
                pass
        except Exception:
            pass

    def start(self, req: StartRequest) -> None:
        with self.lock:
            if self.running:
                raise RuntimeError("Session already running")

            # Build components
            self.mode = req.mode
            self.symbol = req.symbol
            self.config = req
            self.order_book = OrderBook()
            self.engine = MatchingEngine(self.order_book)
            # Microstructure (used in backtest)
            try:
                self.engine.slippage_bps_per_100_shares = float(req.slippage_bps_per_100)
                self.engine.latency_ms = int(req.latency_ms)
                self.engine.price_band_bps = float(req.price_band_bps)
                self.engine.band_reference = str(req.band_reference or 'mid')
                self.engine.maker_rebate_bps = float(req.maker_rebate_bps)
            except Exception:
                pass
            # Owner-aware portfolio for the GUI's session owner 'web'
            # Multi-portfolio dispatcher (tracks per-owner PnL, including 'web' GUI owner)
            self.portfolios = PortfolioDispatcher(fee_bps=req.fee_bps, maker_rebate_bps=req.maker_rebate_bps)
            self.portfolio = self.portfolios.ensure('web', initial_cash=req.initial_cash)
            self.engine.subscribe_trades(self.portfolios.on_execution)
            self.engine.subscribe_trades(self._on_execution)
            self.logger = CsvLogger(req.log_dir)
            self.engine.subscribe_trades(self.logger.log_execution)
            # Attach TCA logger to engine for slippage metrics
            try:
                self.engine.tca_logger = self.logger  # type: ignore[attr-defined]
            except Exception:
                pass
            # Event logger for replay/snapshots
            try:
                from trading_simulator_with_algorithmic_traders import EventLogger  # type: ignore
                self.event_logger = EventLogger(req.log_dir)
                self.engine.event_logger = self.event_logger
                # also record executions as events
                self.engine.subscribe_trades(self.event_logger.log_execution)
            except Exception:
                self.event_logger = None
            # Instrument precision setup
            try:
                if req.decimal_precision:
                    DECIMAL_PRECISION.update({str(k): int(v) for k, v in req.decimal_precision.items()})
                if req.lot_size:
                    LOT_SIZE.update({str(k): int(v) for k, v in req.lot_size.items()})
                # Sessions config
                if req.sessions:
                    INSTRUMENTS.update(req.sessions)
            except Exception:
                pass
            if req.db_uri and _DBLOGGER:
                try:
                    self.db_logger = DbLogger(req.db_uri)
                    self.engine.subscribe_trades(self.db_logger.log_execution)  # type: ignore
                except Exception:
                    self.db_logger = None
            self.engine.risk_manager = RiskManager(
                portfolio=self.portfolio,
                max_order_qty=req.risk_max_order_qty,
                max_symbol_position=req.risk_max_symbol_position,
                max_gross_notional=req.risk_max_gross_notional,
                min_order_qty=req.risk_min_order_qty,
                lot_size=req.risk_lot_size,
                round_lot_required=bool(req.risk_round_lot_required),
                order_rate_limit_per_sec=req.risk_order_rate_limit_per_sec,
                owner_drawdown_limit=req.risk_owner_drawdown_limit,
                owner_portfolios=self.portfolios,
                price_provider=(lambda sym: (self.engine.get_last_trade_price(sym) or self.engine.order_book.get_best_bid() or self.engine.order_book.get_best_ask())) if self.engine else None,
            )

            if req.mode == "backtest":
                self.maker = MarketMaker(
                    symbol=req.symbol,
                    matching_engine=self.engine,
                    gamma=req.mm_gamma,
                    k=req.mm_k,
                    horizon_seconds=req.mm_horizon_seconds,
                    max_inventory=req.mm_max_inventory,
                    base_order_size=req.mm_base_order_size,
                    min_spread=req.mm_min_spread,
                    num_levels=req.mm_num_levels,
                    level_spacing_bps=req.mm_level_spacing_bps,
                    size_decay=req.mm_size_decay,
                    momentum_window=req.mm_momentum_window,
                    alpha_skew=req.mm_alpha_skew,
                    vol_widen_z=req.mm_vol_widen_z,
                    drawdown_limit=req.mm_drawdown_limit,
                )
                traders: List[Any] = []
                if req.enable_traders:
                    traders.extend(
                        [
                            MomentumTrader(symbol=req.symbol, matching_engine=self.engine, interval=0.0),
                            EMABasedTrader(symbol=req.symbol, matching_engine=self.engine, interval=0.0),
                            SwingTrader(symbol=req.symbol, matching_engine=self.engine, interval=0.0),
                        ]
                    )
                    if req.custom_threshold is not None:
                        traders.append(CustomTrader(symbol=req.symbol, matching_engine=self.engine, interval=0.0, threshold=req.custom_threshold))
                    if req.enable_sentiment and req.news_api_key:
                        try:
                            traders.append(
                                SentimentAnalysisTrader(
                                    symbol=req.symbol,
                                    matching_engine=self.engine,
                                    model_file=req.sentiment_model_path,
                                    news_api_key=req.news_api_key,
                                    interval=0.0,
                                    vocab_path=req.sentiment_vocab_path,
                                )
                            )
                        except Exception:
                            pass

                # Run backtest in a thread to avoid blocking startup
                def _bt():
                    try:
                        if req.symbols:
                            symbols = [s.strip() for s in (req.symbols or '').split(',') if s.strip()]
                            data_map = load_multi_historical_data(symbols, req.start_date or '2023-01-01', req.end_date or '2023-12-31')
                            engines = {}
                            makers = {}
                            traders_map: Dict[str, List[Any]] = {}
                            for sym in symbols:
                                ob = OrderBook()
                                eng = MatchingEngine(ob)
                                try:
                                    eng.slippage_bps_per_100_shares = float(req.slippage_bps_per_100)
                                    eng.latency_ms = int(req.latency_ms)
                                except Exception:
                                    pass
                                eng.subscribe_trades(self.portfolio.on_execution)
                                eng.subscribe_trades(self.logger.log_execution)
                                if self.db_logger:
                                    eng.subscribe_trades(self.db_logger.log_execution)  # type: ignore
                                eng.risk_manager = self.engine.risk_manager
                                engines[sym] = eng
                                makers[sym] = MarketMaker(
                                    symbol=sym,
                                    matching_engine=eng,
                                    gamma=req.mm_gamma,
                                    k=req.mm_k,
                                    horizon_seconds=req.mm_horizon_seconds,
                                    max_inventory=req.mm_max_inventory,
                                    base_order_size=req.mm_base_order_size,
                                    min_spread=req.mm_min_spread,
                                    num_levels=req.mm_num_levels,
                                    level_spacing_bps=req.mm_level_spacing_bps,
                                    size_decay=req.mm_size_decay,
                                    momentum_window=req.mm_momentum_window,
                                    alpha_skew=req.mm_alpha_skew,
                                    vol_widen_z=req.mm_vol_widen_z,
                                    drawdown_limit=req.mm_drawdown_limit,
                                )
                                if req.enable_traders:
                                    traders_map[sym] = [
                                        MomentumTrader(symbol=sym, matching_engine=eng, interval=0.0),
                                        EMABasedTrader(symbol=sym, matching_engine=eng, interval=0.0),
                                        SwingTrader(symbol=sym, matching_engine=eng, interval=0.0),
                                    ]
                            run_multi_backtest(data_map, engines, makers, traders_map if traders_map else None, self.portfolio, self.logger)
                        else:
                            hist = load_historical_data(req.symbol, req.start_date or "2023-01-01", req.end_date or "2023-12-31")
                            run_backtest(hist, self.maker, self.engine, traders=traders, portfolio=self.portfolio, csv_logger=self.logger)
                        # Export report
                        if req.export_report:
                            try:
                                eq_df = _load_equity_curve(os.path.join(self.logger.base_dir, 'equity_curve.csv'))
                                metrics = compute_performance_metrics(eq_df)  # type: ignore
                                export_html_report(eq_df, metrics, req.report_out)
                            except Exception:
                                pass
                        # Persist equity to DB if configured
                        if self.db_logger:
                            try:
                                eq_df = _load_equity_curve(os.path.join(self.logger.base_dir, 'equity_curve.csv'))
                                for _, r in eq_df.iterrows():
                                    ts = r['timestamp']
                                    self.db_logger.log_equity(ts, float(r['net_liquidation']), float(r.get('realized_pnl', 0.0)), float(r.get('cash', 0.0)))
                            except Exception:
                                pass
                    finally:
                        self.running = False
                        self.mode = None

                self.running = True
                threading.Thread(target=_bt, daemon=True).start()
                return

            # Live mode
            self.feed = MarketDataFeed(symbol=req.symbol)
            self.maker = MarketMaker(
                symbol=req.symbol,
                matching_engine=self.engine,
                gamma=req.mm_gamma,
                k=req.mm_k,
                horizon_seconds=req.mm_horizon_seconds,
                max_inventory=req.mm_max_inventory,
                base_order_size=req.mm_base_order_size,
                min_spread=req.mm_min_spread,
                num_levels=req.mm_num_levels,
                level_spacing_bps=req.mm_level_spacing_bps,
                size_decay=req.mm_size_decay,
                momentum_window=req.mm_momentum_window,
                alpha_skew=req.mm_alpha_skew,
                vol_widen_z=req.mm_vol_widen_z,
                drawdown_limit=req.mm_drawdown_limit,
            )
            # Tap market data to update equity
            self.feed.subscribe(self)

            # Optional FIX server
            if req.enable_fix:
                self.fix_app = FixApplication(self.engine)
                def _fix_start():
                    try:
                        self.fix_app.start(host=req.fix_host, port=req.fix_port)
                    finally:
                        pass
                self.fix_thread = threading.Thread(target=_fix_start, daemon=True)
                self.fix_thread.start()

            if req.enable_traders:
                # Add initial traders via runtime API internally
                self.add_trader("MomentumTrader", {"interval": 10, "lookback": 5})
                self.add_trader("EMABasedTrader", {"interval": 30, "short_window": 5, "long_window": 20})
                self.add_trader("SwingTrader", {"interval": 15, "support_level": 100.0, "resistance_level": 200.0})
                if req.custom_threshold is not None:
                    self.add_trader("CustomTrader", {"interval": 5, "threshold": req.custom_threshold})
                if req.enable_sentiment and req.news_api_key:
                    try:
                        self.add_trader("SentimentAnalysisTrader", {
                            "interval": 60,
                            "model_file": req.sentiment_model_path,
                            "news_api_key": req.news_api_key,
                            "vocab_path": req.sentiment_vocab_path,
                        })
                    except Exception:
                        pass

            # Start threads
            def _run_feed():
                self.feed.start(interval_seconds=req.md_interval)  # type: ignore[union-attr]

            def _start_trader(trader, feed):
                trader.start(feed)

            self.running = True
            # Optional engine queue loop (bounded queue)
            try:
                self.engine.use_queue = False
                self.engine.start_loop()
            except Exception:
                pass
            self.feed_thread = threading.Thread(target=_run_feed, daemon=True)
            self.feed_thread.start()
            # market maker subscribes directly
            self.maker.start(self.feed)
            # user traders are started within add_trader

            if req.inject_liquidity > 0:
                from trading_simulator_with_algorithmic_traders import SyntheticLiquidityProvider, auto_inject_liquidity

                provider = SyntheticLiquidityProvider(symbol=req.symbol, matching_engine=self.engine, num_orders=10)
                self.liquidity_thread = threading.Thread(
                    target=auto_inject_liquidity, args=(provider, req.inject_liquidity), daemon=True
                )
                self.liquidity_thread.start()

    # MarketDataFeed will call receive() on subscribers
    def receive(self, data: Dict[str, Any]) -> None:
        self._on_market_data_tick(data)

    def stop(self) -> None:
        with self.lock:
            if not self.running:
                return
            try:
                if self.maker is not None:
                    self.maker.stop()
                if self.feed is not None:
                    self.feed.stop()
                if self.fix_app is not None:
                    try:
                        self.fix_app.stop()
                    except Exception:
                        pass
                # Traders
                for t in list(self.traders.values()):
                    try:
                        t.stop()
                    except Exception:
                        pass
                # Join threads
                for th in list(self.trader_threads.values()):
                    try:
                        th.join(timeout=3)
                    except Exception:
                        pass
                if self.feed_thread is not None:
                    try:
                        self.feed_thread.join(timeout=3)
                    except Exception:
                        pass
                if self.fix_thread is not None:
                    try:
                        self.fix_thread.join(timeout=3)
                    except Exception:
                        pass
            finally:
                self.running = False
                self.mode = None

    def snapshot(self) -> Dict[str, Any]:
        with self.lock:
            orderbook = self.order_book
            best_bid = orderbook.get_best_bid() if orderbook else None  # type: ignore[union-attr]
            best_ask = orderbook.get_best_ask() if orderbook else None  # type: ignore[union-attr]
            pos = self.portfolio.snapshot() if self.portfolio else {}
            owners = self.portfolios.snapshot_all() if self.portfolios else {}
            depth = self.engine.depth_snapshot(5) if self.engine else {"bids":[],"asks":[]}
            last_trade = self.engine.get_last_trade_price(self.symbol) if self.engine else None
            engine_status = {
                "use_queue": bool(self.engine.use_queue) if self.engine else False,
                "halted": self.symbol in (self.engine._halted if self.engine else set()),
            }
            return {
                "running": self.running,
                "mode": self.mode,
                "symbol": self.symbol,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "last_trade": last_trade,
                "portfolio": pos,
                "owners": owners,
                "depth": depth,
                "engine": engine_status,
                "last_executions": list(self.last_executions[-100:]),
                "equity": list(self.equity_points[-500:]),
                "active_traders": [
                    {"id": tid, "name": type(inst).__name__}
                    for tid, inst in self.traders.items()
                ],
                "optimize": {
                    "running": self.optimize_running,
                    "trials_done": self.optimize_trials_done,
                    "best_value": self.optimize_best_value,
                    "best_params": self.optimize_best_params,
                },
            }

    # Optimization
    def start_optimization(self, params: Dict[str, Any]) -> None:
        if not _OPTUNA:
            raise RuntimeError("Optuna not installed on server")
        if self.optimize_running:
            raise RuntimeError("Optimization already running")
        symbol = params.get('symbol') or self.symbol
        start = params.get('start_date') or '2023-01-01'
        end = params.get('end_date') or '2023-12-31'
        trials = int(params.get('trials', 10))
        base_params = {
            'initial_cash': float(params.get('initial_cash', 1_000_000.0)),
            'fee_bps': float(params.get('fee_bps', 0.0)),
            'risk_max_order_qty': int(params.get('risk_max_order_qty', 1000)),
            'risk_max_symbol_position': int(params.get('risk_max_symbol_position', 10_000)),
            'risk_max_gross_notional': float(params.get('risk_max_gross_notional', 5_000_000.0)),
        }
        log_dir = params.get('log_dir') or (self.logger.base_dir if self.logger else '.logs')
        mlflow_uri = params.get('mlflow_uri')
        mlflow_experiment = params.get('mlflow_experiment', 'trading-simulator')

        def _run():
            from math import isfinite
            try:
                if _MLFLOW and mlflow_uri:
                    try:
                        mlflow.set_tracking_uri(mlflow_uri)
                        mlflow.set_experiment(mlflow_experiment)
                    except Exception:
                        pass
                study = optuna.create_study(direction='maximize')

                def _obj(trial):
                    val = objective_optuna(trial, symbol, start, end, base_params, log_dir)
                    # progress update
                    with self.lock:
                        self.optimize_trials_done += 1
                        if self.optimize_best_value is None or val > (self.optimize_best_value or float('-inf')):
                            self.optimize_best_value = float(val)
                            self.optimize_best_params = dict(trial.params)
                    try:
                        import asyncio
                        asyncio.create_task(ws_manager.broadcast({
                            'type': 'optuna-progress',
                            'data': {
                                'trials_done': self.optimize_trials_done,
                                'best_value': self.optimize_best_value,
                                'best_params': self.optimize_best_params,
                            }
                        }))
                    except Exception:
                        pass
                    return val

                with self.lock:
                    self.optimize_running = True
                    self.optimize_trials_done = 0
                    self.optimize_best_value = None
                    self.optimize_best_params = {}
                study.optimize(_obj, n_trials=trials)
            finally:
                with self.lock:
                    self.optimize_running = False

        self.optimize_thread = threading.Thread(target=_run, daemon=True)
        self.optimize_thread.start()

    # Runtime strategy management
    def _make_trader(self, name: str, params: Dict[str, Any]):
        if name == "MomentumTrader":
            return MomentumTrader(symbol=self.symbol, matching_engine=self.engine, interval=float(params.get("interval", 10)), lookback=int(params.get("lookback", 5)))
        if name == "EMABasedTrader":
            return EMABasedTrader(symbol=self.symbol, matching_engine=self.engine, interval=float(params.get("interval", 30)), short_window=int(params.get("short_window", 5)), long_window=int(params.get("long_window", 20)))
        if name == "SwingTrader":
            return SwingTrader(symbol=self.symbol, matching_engine=self.engine, interval=float(params.get("interval", 15)), support_level=float(params.get("support_level", 100.0)), resistance_level=float(params.get("resistance_level", 200.0)))
        if name == "CustomTrader":
            return CustomTrader(symbol=self.symbol, matching_engine=self.engine, interval=float(params.get("interval", 5)), threshold=float(params.get("threshold", 0.0)))
        if name == "SentimentAnalysisTrader":
            cfg = self.config
            return SentimentAnalysisTrader(
                symbol=self.symbol,
                matching_engine=self.engine,
                model_file=str(params.get("model_file", cfg.sentiment_model_path if cfg else "sentiment_classifier_model.keras")),
                news_api_key=str(params.get("news_api_key", cfg.news_api_key if cfg else "")),
                interval=float(params.get("interval", 60)),
                vocab_path=params.get("vocab_path", cfg.sentiment_vocab_path if cfg else None),
            )
        raise ValueError(f"Unknown strategy: {name}")

    def add_trader(self, name: str, params: Dict[str, Any]) -> str:
        if self.feed is None:
            raise RuntimeError("Feed not running")
        inst = self._make_trader(name, params)
        tid = uuid.uuid4().hex
        setattr(inst, "_id", tid)
        th = threading.Thread(target=inst.start, args=(self.feed,), daemon=True)
        th.start()
        self.traders[tid] = inst
        self.trader_threads[tid] = th
        return tid

    def remove_trader(self, trader_id: str) -> None:
        inst = self.traders.get(trader_id)
        if inst is None:
            raise RuntimeError("Trader not found")
        try:
            inst.stop()
        except Exception:
            pass
        th = self.trader_threads.get(trader_id)
        if th is not None:
            try:
                th.join(timeout=3)
            except Exception:
                pass
        self.traders.pop(trader_id, None)
        self.trader_threads.pop(trader_id, None)

    def update_trader(self, trader_id: str, params: Dict[str, Any]) -> None:
        inst = self.traders.get(trader_id)
        if inst is None:
            raise RuntimeError("Trader not found")
        # Basic attribute updates depending on class
        name = type(inst).__name__
        if name == "MomentumTrader":
            if "lookback" in params: inst.lookback = int(params["lookback"])  # type: ignore[attr-defined]
            if "interval" in params: inst.interval = float(params["interval"])  # type: ignore[attr-defined]
        elif name == "EMABasedTrader":
            if "short_window" in params: inst.short_window = int(params["short_window"])  # type: ignore[attr-defined]
            if "long_window" in params: inst.long_window = int(params["long_window"])  # type: ignore[attr-defined]
            if "interval" in params: inst.interval = float(params["interval"])  # type: ignore[attr-defined]
        elif name == "SwingTrader":
            if "support_level" in params: inst.support_level = float(params["support_level"])  # type: ignore[attr-defined]
            if "resistance_level" in params: inst.resistance_level = float(params["resistance_level"])  # type: ignore[attr-defined]
            if "interval" in params: inst.interval = float(params["interval"])  # type: ignore[attr-defined]
        elif name == "CustomTrader":
            if "threshold" in params: inst.threshold = float(params["threshold"])  # type: ignore[attr-defined]
            if "interval" in params: inst.interval = float(params["interval"])  # type: ignore[attr-defined]
        elif name == "SentimentAnalysisTrader":
            if "interval" in params: inst.interval = float(params["interval"])  # type: ignore[attr-defined]
        else:
            raise RuntimeError("Unsupported trader for update")


controller = TradingController()
app = FastAPI()


class WebSocketManager:
    def __init__(self) -> None:
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        dead: List[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Trading Simulator GUI</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; }
    .row { display: flex; gap: 20px; }
    .col { flex: 1; }
    input, select, button { margin: 4px 0; padding: 6px; width: 100%; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 6px; }
    th { background: #f2f2f2; }
    .card { border: 1px solid #ccc; padding: 12px; margin-bottom: 12px; }
  </style>
  </head>
  <body>
    <h2>Trading Simulator GUI</h2>
    <div id="wsStatus">WS: connecting...</div>
    <div class="row">
      <div class="col">
        <div class="card">
          <h3>Start Session</h3>
          <form id="startForm" onsubmit="startSession(event)">
            <label>Mode</label>
            <select name="mode">
              <option value="backtest">Backtest</option>
              <option value="live">Live</option>
            </select>
            <label>Symbol</label><input name="symbol" value="AAPL"/>
            <label>Symbols (multi-asset, comma separated)</label><input name="symbols" placeholder="AAPL,MSFT"/>
            <label>Start Date</label><input name="start_date" value="2023-01-01"/>
            <label>End Date</label><input name="end_date" value="2023-12-31"/>
            <label>Enable Traders</label><select name="enable_traders"><option value="false">False</option><option value="true">True</option></select>
            <label>Enable Sentiment</label><select name="enable_sentiment"><option value="false">False</option><option value="true">True</option></select>
            <label>News API Key</label><input name="news_api_key" value=""/>
            <label>Sentiment Model Path</label><input name="sentiment_model_path" value="sentiment_classifier_model.keras"/>
            <label>Sentiment Vocab Path</label><input name="sentiment_vocab_path"/>
            <label>Custom Trader Threshold</label><input name="custom_threshold"/>
            <label>MD Interval (s)</label><input name="md_interval" value="60"/>
            <label>Inject Liquidity (s)</label><input name="inject_liquidity" value="0"/>
            <label>Enable FIX</label><select name="enable_fix"><option value="false">False</option><option value="true">True</option></select>
            <label>FIX Host</label><input name="fix_host" value="localhost"/>
            <label>FIX Port</label><input name="fix_port" value="5005"/>
            <label>Slippage (bps per 100 shares)</label><input name="slippage_bps_per_100" value="0"/>
            <label>Latency (ms)</label><input name="latency_ms" value="0"/>
            <label>Price Band (bps)</label><input name="price_band_bps" value="0"/>
            <label>Band Reference</label><select name="band_reference"><option value="mid">Mid</option><option value="last">Last Trade</option></select>
            <label>Export HTML Report</label><select name="export_report"><option value="false">False</option><option value="true">True</option></select>
            <label>Report Output</label><input name="report_out" value="report.html"/>
            <h4>Market Maker</h4>
            <label>MM Gamma</label><input name="mm_gamma" value="0.1"/>
            <label>MM k</label><input name="mm_k" value="1.5"/>
            <label>MM Horizon (s)</label><input name="mm_horizon_seconds" value="60"/>
            <label>MM Max Inventory</label><input name="mm_max_inventory" value="1000"/>
            <label>MM Base Order Size</label><input name="mm_base_order_size" value="100"/>
            <label>MM Min Spread</label><input name="mm_min_spread" value="0.01"/>
            <label>MM Num Levels</label><input name="mm_num_levels" value="2"/>
            <label>MM Level Spacing (bps)</label><input name="mm_level_spacing_bps" value="2"/>
            <label>MM Size Decay</label><input name="mm_size_decay" value="0.7"/>
            <label>MM Momentum Window</label><input name="mm_momentum_window" value="10"/>
            <label>MM Alpha Skew</label><input name="mm_alpha_skew" value="0.5"/>
            <label>MM Vol Widen Z</label><input name="mm_vol_widen_z" value="2"/>
            <label>MM Drawdown Limit</label><input name="mm_drawdown_limit" value="0.2"/>
            <label>Initial Cash</label><input name="initial_cash" value="1000000"/>
            <label>Fee (bps)</label><input name="fee_bps" value="0"/>
            <label>Maker Rebate (bps)</label><input name="maker_rebate_bps" value="0"/>
            <label>Sessions (JSON)</label>
            <textarea name="sessions" rows="3" placeholder='{"AAPL": {"tz": "America/New_York", "open": "09:30", "close": "16:00", "holidays": ["2023-12-25"]}}'></textarea>
            <label>Risk Max Order Qty</label><input name="risk_max_order_qty" value="1000"/>
            <label>Risk Max Symbol Position</label><input name="risk_max_symbol_position" value="10000"/>
            <label>Risk Max Gross Notional</label><input name="risk_max_gross_notional" value="5000000"/>
            <label>Risk Min Order Qty</label><input name="risk_min_order_qty" value="1"/>
            <label>Risk Lot Size</label><input name="risk_lot_size" value="1"/>
            <label>Round Lot Required</label><select name="risk_round_lot_required"><option value="false">False</option><option value="true">True</option></select>
            <label>Rate Limit (orders/sec per owner)</label><input name="risk_order_rate_limit_per_sec" placeholder="e.g., 5"/>
            <label>Owner Drawdown Limit (fraction, e.g., 0.2)</label><input name="risk_owner_drawdown_limit" placeholder="0.2"/>
            <label>Log Dir</label><input name="log_dir" value=".logs"/>
            <label>DB URI (optional)</label><input name="db_uri" placeholder="postgresql+psycopg2://user:pass@host/db"/>
            <h4>Instrument Precision</h4>
            <label>Decimal Precision (per symbol JSON)</label>
            <textarea name="decimal_precision" placeholder='{"AAPL":2,"MSFT":4}' style="width:100%;height:60px;"></textarea>
            <label>Lot Size (per symbol JSON)</label>
            <textarea name="lot_size" placeholder='{"AAPL":1,"MSFT":100}' style="width:100%;height:60px;"></textarea>
            <button type="submit">Start</button>
          </form>
          <button onclick="stopSession()">Stop Session</button>
        </div>
        <div class="card">
          <h3>Strategies</h3>
          <form id="addTraderForm" onsubmit="addTrader(event)">
            <label>Name</label>
            <select name="name" id="strategyName"></select>
            <label>Params (JSON)</label>
            <textarea name="params" placeholder='{"interval":10}' style="width:100%;height:80px;"></textarea>
            <button type="submit">Add Trader</button>
          </form>
          <h4>Active Traders</h4>
          <table>
            <thead><tr><th>ID</th><th>Name</th><th>Actions</th></tr></thead>
            <tbody id="activeTraders"></tbody>
          </table>
        </div>
        <div class="card">
          <h3>Manual Order</h3>
          <form id="orderForm" onsubmit="placeOrder(event)">
            <label>Side</label><select name="side"><option value="buy">Buy</option><option value="sell">Sell</option></select>
            <label>Type</label><select name="type"><option value="limit">Limit</option><option value="market">Market</option></select>
            <label>Price</label><input name="price" placeholder="0 for market"/>
            <label>Quantity</label><input name="quantity" value="100"/>
            <label>Symbol</label><input name="symbol" placeholder="leave blank for session symbol"/>
            <label>TIF</label><select name="tif"><option value="GTC">GTC</option><option value="IOC">IOC</option><option value="FOK">FOK</option></select>
            <label>Post Only</label><select name="post_only"><option value="false">False</option><option value="true">True</option></select>
            <label>Owner</label><input name="owner_id" value="web"/>
            <label>Expires At (UTC)</label><input name="expires_at" placeholder="2025-01-01T15:30:00Z"/>
            <label>Auction Only</label><select name="auction_only"><option value="false">False</option><option value="true">True</option></select>
            <label>Auction Phase</label><select name="auction_phase"><option value="">(auto)</option><option value="open">open</option><option value="close">close</option></select>
            <button type="submit">Place</button>
          </form>
          <form id="cancelForm" onsubmit="cancelOrder(event)">
            <label>Cancel Order ID</label><input name="order_id"/>
            <button type="submit">Cancel</button>
          </form>
          <form id="cancelOwnerForm" onsubmit="cancelOwner(event)">
            <label>Cancel by Owner</label><input name="owner_id" placeholder="owner id"/>
            <button type="submit">Cancel Owner Orders</button>
          </form>
        </div>
        <div class="card">
          <h3>Portfolio</h3>
          <div>Cash: <span id="cash">0</span></div>
          <div>Realized PnL: <span id="realized">0</span></div>
          <h4>Positions</h4>
          <table><thead><tr><th>Symbol</th><th>Qty</th><th>Avg Price</th></tr></thead><tbody id="positions"></tbody></table>
        </div>
        <div class="card">
          <h3>Owner Portfolios</h3>
          <table>
            <thead><tr><th>Owner</th><th>Cash</th><th>Realized PnL</th></tr></thead>
            <tbody id="owners"></tbody>
          </table>
        </div>
        <div class="card">
          <h3>Order Book</h3>
          <div>Best Bid: <span id="bestBid">-</span></div>
          <div>Best Ask: <span id="bestAsk">-</span></div>
          <h4>Depth (Top 5)</h4>
          <table>
            <thead><tr><th colspan="2">Bids</th><th colspan="2">Asks</th></tr><tr><th>Px</th><th>Qty</th><th>Px</th><th>Qty</th></tr></thead>
            <tbody id="depth"></tbody>
          </table>
          <div style="margin-top:8px; display:flex; gap:8px;">
            <button onclick="haltSymbol()">Halt</button>
            <button onclick="resumeSymbol()">Resume</button>
            <button onclick="toggleQueue()">Toggle Queue</button>
          </div>
          <div style="margin-top:8px; display:flex; gap:8px;">
            <button onclick="startOpenAuction()">Start Open Auction</button>
            <button onclick="startCloseAuction()">Start Close Auction</button>
            <button onclick="uncrossAuction()">Uncross Auction</button>
          </div>
        </div>
      </div>
      <div class="col">
        <div class="card">
          <h3>Equity Curve</h3>
          <canvas id="equityChart"></canvas>
        </div>
        <div class="card">
          <h3>Recent Executions</h3>
          <table>
            <thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th></tr></thead>
            <tbody id="execs"></tbody>
          </table>
        </div>
        <div class="card">
          <h3>TCA (latest)</h3>
          <div>Last Trade: <span id="lastTrade">-</span></div>
          <div>Engine Queue: <span id="engineQueue">-</span> | Halted: <span id="engineHalted">-</span></div>
        </div>
        <div class="card">
          <h3>Parameter Optimization</h3>
          <form id="optForm" onsubmit="startOpt(event)">
            <label>Trials</label><input name="trials" value="10"/>
            <label>Symbol</label><input name="symbol" placeholder="leave blank for session symbol"/>
            <label>Start Date</label><input name="start_date" placeholder="2023-01-01"/>
            <label>End Date</label><input name="end_date" placeholder="2023-12-31"/>
            <label>MLflow URI</label><input name="mlflow_uri" placeholder="http://localhost:5000"/>
            <label>MLflow Experiment</label><input name="mlflow_experiment" value="trading-simulator"/>
            <button type="submit">Start Optimization</button>
          </form>
          <div>
            <div>Running: <span id="optRunning">false</span></div>
            <div>Trials done: <span id="optTrials">0</span></div>
            <div>Best value: <span id="optBest">-</span></div>
            <div>Best params: <pre id="optParams" style="white-space:pre-wrap"></pre></div>
          </div>
        </div>
        <div class="card">
          <h3>Replay Events</h3>
          <button onclick="replayEvents()">Replay events.csv</button>
        </div>
      </div>
    </div>

    <script>
      async function startSession(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('startForm'));
        const body = {};
        form.forEach((v,k)=>body[k]=v);
        body.enable_traders = body.enable_traders === 'true';
        body.enable_sentiment = body.enable_sentiment === 'true';
        body.enable_fix = body.enable_fix === 'true';
        body.export_report = body.export_report === 'true';
        try { if(body.decimal_precision) body.decimal_precision = JSON.parse(body.decimal_precision); } catch(e) {}
        try { if(body.lot_size) body.lot_size = JSON.parse(body.lot_size); } catch(e) {}
        try { if(body.sessions) body.sessions = JSON.parse(body.sessions); } catch(e) {}
        if(body.risk_order_rate_limit_per_sec==='') delete body.risk_order_rate_limit_per_sec;
        if(body.risk_owner_drawdown_limit==='') delete body.risk_owner_drawdown_limit;
        if(body.custom_threshold === '') delete body.custom_threshold;
        const res = await fetch('/api/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        if(!res.ok){ alert('Failed to start: '+await res.text()); return; }
      }
      async function stopSession(){
        await fetch('/api/stop', {method:'POST'});
      }
      async function loadStrategies(){
        try {
          const res = await fetch('/api/strategies');
          const list = await res.json();
          const sel = document.getElementById('strategyName');
          sel.innerHTML = '';
          list.forEach(s=>{
            const opt = document.createElement('option');
            opt.value = s.name; opt.textContent = `${s.name}`; sel.appendChild(opt);
          });
        } catch(e) {}
      }
      async function startOpenAuction(){ await fetch('/api/auction/start/open', {method:'POST'}); }
      async function startCloseAuction(){ await fetch('/api/auction/start/close', {method:'POST'}); }
      async function uncrossAuction(){ await fetch('/api/auction/uncross', {method:'POST'}); }
      async function haltSymbol(){ await fetch('/api/halt', {method:'POST'}); }
      async function resumeSymbol(){ await fetch('/api/resume', {method:'POST'}); }
      async function toggleQueue(){ await fetch('/api/engine/queue-toggle', {method:'POST'}); }
      async function addTrader(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('addTraderForm'));
        let params = {};
        try { params = JSON.parse(form.get('params')||'{}'); } catch(e){ alert('Params must be valid JSON'); return; }
        const body = { name: form.get('name'), params };
        const res = await fetch('/api/traders', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const j = await res.json(); if(!res.ok){ alert('Add trader failed: '+JSON.stringify(j)); return; }
        refresh();
      }
      async function replayEvents(){ await fetch('/api/replay', {method:'POST'}); }
      async function deleteTrader(id){
        const res = await fetch(`/api/traders/${id}`, {method:'DELETE'});
        if(!res.ok){ alert('Delete failed'); return; }
        refresh();
      }
      async function updateTrader(id){
        const ta = document.getElementById(`params_${id}`);
        let params = {};
        try { params = JSON.parse(ta.value||'{}'); } catch(e){ alert('Params must be valid JSON'); return; }
        const res = await fetch(`/api/traders/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({params})});
        if(!res.ok){ alert('Update failed'); return; }
        refresh();
      }
      async function placeOrder(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('orderForm'));
        const body = {};
        form.forEach((v,k)=>body[k]=v);
        if(body.type === 'market') body.price = null; else body.price = parseFloat(body.price);
        body.quantity = parseInt(body.quantity);
        body.post_only = body.post_only === 'true';
        body.auction_only = body.auction_only === 'true';
        if(!body.auction_phase) delete body.auction_phase;
        const res = await fetch('/api/order', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const j = await res.json(); if(!res.ok){ alert('Order failed: '+JSON.stringify(j)); }
      }
      async function cancelOrder(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('cancelForm'));
        const body = {order_id: form.get('order_id')};
        const res = await fetch('/api/cancel', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const j = await res.json(); if(!res.ok){ alert('Cancel failed: '+JSON.stringify(j)); }
      }
      async function cancelOwner(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('cancelOwnerForm'));
        const body = {owner_id: form.get('owner_id')};
        const res = await fetch('/api/cancel/owner', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const j = await res.json(); if(!res.ok){ alert('Cancel owner failed: '+JSON.stringify(j)); }
      }
      async function startOpt(e){
        e.preventDefault();
        const form = new FormData(document.getElementById('optForm'));
        const body = {};
        form.forEach((v,k)=>body[k]=v);
        body.trials = parseInt(body.trials||'10');
        const res = await fetch('/api/optimize', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
        const j = await res.json(); if(!res.ok){ alert('Optimization start failed: '+JSON.stringify(j)); }
      }
      const ctx = document.getElementById('equityChart').getContext('2d');
      const eqData = {labels: [], datasets:[{label:'Net Liq', data:[], borderColor:'#1976d2', fill:false}]};
      const chart = new Chart(ctx, {type:'line', data:eqData, options:{responsive:true, scales:{x:{display:false}}}});
      // WebSocket real-time updates
      let ws;
      function initWS(){
        try{
          ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
          ws.onopen = ()=>{ document.getElementById('wsStatus').textContent = 'WS: connected'; };
          ws.onclose = ()=>{ document.getElementById('wsStatus').textContent = 'WS: closed'; setTimeout(initWS, 2000); };
          ws.onerror = ()=>{ document.getElementById('wsStatus').textContent = 'WS: error'; };
          ws.onmessage = (ev)=>{
            try{
              const msg = JSON.parse(ev.data);
              if(msg.type === 'equity'){
                const p = msg.data; eqData.labels.push(''); eqData.datasets[0].data.push(p.net_liquidation); chart.update();
              } else if(msg.type === 'execution'){
                // soft refresh of execution table
                refresh();
              } else if(msg.type === 'optuna-progress'){
                const d = msg.data || {};
                document.getElementById('optTrials').textContent = String(d.trials_done||0);
                document.getElementById('optBest').textContent = String(d.best_value??'-');
                document.getElementById('optParams').textContent = JSON.stringify(d.best_params||{}, null, 2);
              }
            } catch(e){}
          };
        }catch(e){ document.getElementById('wsStatus').textContent = 'WS: unsupported'; }
      }
      initWS();
      async function refresh(){
        const res = await fetch('/api/state');
        const s = await res.json();
        document.getElementById('bestBid').textContent = s.best_bid ?? '-';
        document.getElementById('bestAsk').textContent = s.best_ask ?? '-';
        document.getElementById('lastTrade').textContent = s.last_trade ?? '-';
        const eng = s.engine || {}; document.getElementById('engineQueue').textContent = String(!!eng.use_queue);
        document.getElementById('engineHalted').textContent = String(!!eng.halted);
        // Depth
        const d = s.depth || {bids:[], asks:[]};
        const rows = Math.max(d.bids.length||0, d.asks.length||0);
        const dtb = document.getElementById('depth'); dtb.innerHTML='';
        for(let i=0;i<rows;i++){
          const b = d.bids[i] || [null,null]; const a = d.asks[i] || [null,null];
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${b[0]??''}</td><td>${b[1]??''}</td><td>${a[0]??''}</td><td>${a[1]??''}</td>`;
          dtb.appendChild(tr);
        }
        if(s.portfolio){
          document.getElementById('cash').textContent = s.portfolio.cash?.toFixed(2) ?? 0;
          document.getElementById('realized').textContent = s.portfolio.realized_pnl?.toFixed(2) ?? 0;
          const pos = s.portfolio.positions || {}; const avg = s.portfolio.avg_price || {};
          const tbody = document.getElementById('positions'); tbody.innerHTML='';
          Object.keys(pos).forEach(sym=>{
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${sym}</td><td>${pos[sym]}</td><td>${(avg[sym]||0).toFixed(2)}</td>`;
            tbody.appendChild(tr);
          });
        }
        // Owners table
        const owners = s.owners || {}; const otb = document.getElementById('owners'); otb.innerHTML='';
        Object.keys(owners).forEach(id=>{
          const o = owners[id]||{};
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${id}</td><td>${(o.cash||0).toFixed(2)}</td><td>${(o.realized_pnl||0).toFixed(2)}</td>`;
          otb.appendChild(tr);
        });
        const execs = s.last_executions || []; const etb = document.getElementById('execs'); etb.innerHTML='';
        execs.slice(-50).reverse().forEach(x=>{
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${x.timestamp}</td><td>${x.symbol}</td><td>${x.side}</td><td>${x.quantity}</td><td>${x.price}</td>`;
          etb.appendChild(tr);
        })
        const eq = s.equity || []; eqData.labels = eq.map(_=> ''); eqData.datasets[0].data = eq.map(p=> p.net_liquidation);
        chart.update();
        // Active traders table
        const atb = document.getElementById('activeTraders'); atb.innerHTML='';
        (s.active_traders||[]).forEach(t=>{
          const tr = document.createElement('tr');
          tr.innerHTML = `<td>${t.id}</td><td>${t.name}</td><td>
            <button onclick="deleteTrader('${t.id}')">Delete</button><br/>
            <small>Update Params (JSON):</small><br/>
            <textarea id="params_${t.id}" style="width:100%;height:60px;"></textarea>
            <button onclick="updateTrader('${t.id}')">Apply</button>
          </td>`;
          atb.appendChild(tr);
        });
        // Optimization
        const opt = s.optimize || {};
        document.getElementById('optRunning').textContent = String(!!opt.running);
        document.getElementById('optTrials').textContent = String(opt.trials_done||0);
        document.getElementById('optBest').textContent = String(opt.best_value??'-');
        document.getElementById('optParams').textContent = JSON.stringify(opt.best_params||{}, null, 2);
      }
      setInterval(refresh, 1000);
      loadStrategies().then(refresh);
    </script>
  </body>
</html>
"""


@app.post("/api/start")
def api_start(req: StartRequest):
    try:
        # capture event loop for background WS notifications
        controller._loop = asyncio.get_event_loop()
        controller.start(req)
        return JSONResponse({"status": "started"})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/stop")
def api_stop():
    controller.stop()
    return {"status": "stopped"}


@app.get("/api/state")
def api_state():
    return controller.snapshot()
@app.post("/api/auction/start/{phase}")
def api_start_auction(phase: str):
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    if phase not in ("open", "close"):
        raise HTTPException(status_code=400, detail="Invalid phase")
    controller.engine.start_auction(phase)
    return {"status": "started", "phase": phase}


@app.post("/api/auction/uncross")
def api_uncross_auction():
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    controller.engine.uncross_auction()
    return {"status": "uncrossed"}


@app.post("/api/halt")
def api_halt():
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    controller.engine.halt(controller.symbol)
    return {"status": "halted", "symbol": controller.symbol}


@app.post("/api/resume")
def api_resume():
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    controller.engine.resume(controller.symbol)
    return {"status": "resumed", "symbol": controller.symbol}


@app.post("/api/engine/queue-toggle")
def api_queue_toggle():
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        controller.engine.use_queue = not bool(controller.engine.use_queue)
        if controller.engine.use_queue:
            controller.engine.start_loop()
        else:
            controller.engine.stop_loop()
        return {"use_queue": bool(controller.engine.use_queue)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/replay")
def api_replay():
    try:
        # Basic replay surface: parse events for visibility. Full deterministic rebuild can be added later.
        from trading_simulator_with_algorithmic_traders import EventLogger, ReplayRunner  # type: ignore
        logger = EventLogger(controller.config.log_dir if controller.config else '.logs')
        evs = logger.replay()
        # Run deterministic rebuild in a lightweight engine
        runner = ReplayRunner(evs)
        summary = runner.run()
        tca = logger.tca_summary()
        return {"events": evs[:100], "replay": summary, "tca": tca}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))



@app.get("/api/strategies")
def api_strategies():
    specs = list_strategies()
    return [
        {
            "name": s.name,
            "description": s.description,
            "params": s.params,
        }
        for s in specs
    ]


class AddTraderRequest(BaseModel):
    name: str
    params: Dict[str, Any] = {}


@app.post("/api/traders")
def add_trader(req: AddTraderRequest):
    try:
        tid = controller.add_trader(req.name, req.params)
        return {"id": tid}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class UpdateTraderRequest(BaseModel):
    params: Dict[str, Any]


@app.patch("/api/traders/{trader_id}")
def update_trader(trader_id: str, req: UpdateTraderRequest):
    try:
        controller.update_trader(trader_id, req.params)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/api/traders/{trader_id}")
def delete_trader(trader_id: str):
    try:
        controller.remove_trader(trader_id)
        return {"status": "deleted"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep the connection alive; client does not need to send messages
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


class OptimizeRequest(BaseModel):
    trials: int = 10
    symbol: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    mlflow_uri: Optional[str] = None
    mlflow_experiment: Optional[str] = None
    initial_cash: Optional[float] = None
    fee_bps: Optional[float] = None
    risk_max_order_qty: Optional[int] = None
    risk_max_symbol_position: Optional[int] = None
    risk_max_gross_notional: Optional[float] = None
    log_dir: Optional[str] = None


@app.post("/api/optimize")
def api_optimize(req: OptimizeRequest):
    try:
        controller.start_optimization(req.dict(exclude_none=True))
        return {"status": "started"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class OrderRequest(BaseModel):
    side: str
    type: str
    price: Optional[float] = None
    quantity: int
    symbol: Optional[str] = None
    tif: Optional[str] = 'GTC'
    post_only: Optional[bool] = False
    owner_id: Optional[str] = 'web'
    expires_at: Optional[str] = None
    auction_only: Optional[bool] = False
    auction_phase: Optional[str] = None


@app.post("/api/order")
def api_order(req: OrderRequest):
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    sym = req.symbol or controller.symbol
    if req.type not in ("limit", "market"):
        raise HTTPException(status_code=400, detail="Invalid type")
    if req.side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="Invalid side")
    if req.type == "limit" and (req.price is None or req.price <= 0):
        raise HTTPException(status_code=400, detail="Limit orders need positive price")
    try:
        expires = None
        if req.expires_at:
            expires = pd.to_datetime(req.expires_at).tz_localize('UTC')
        order = Order(
            id=uuid.uuid4().hex,
            price=float(req.price or 0.0),
            quantity=int(req.quantity),
            side=req.side,
            type=req.type,
            symbol=sym,
            tif=(req.tif or 'GTC'),
            post_only=bool(req.post_only),
            owner_id=(req.owner_id or 'web'),
            expires_at=expires,
            auction_only=bool(req.auction_only),
            auction_phase=req.auction_phase,
        )
        controller.engine.match_order(order)
        return {"status": "accepted", "order_id": order.id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


class CancelRequest(BaseModel):
    order_id: str
class CancelOwnerRequest(BaseModel):
    owner_id: str



@app.post("/api/cancel")
def api_cancel(req: CancelRequest):
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        controller.engine.cancel_order(req.order_id)
        return {"status": "cancelled", "order_id": req.order_id}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/cancel/owner")
def api_cancel_owner(req: CancelOwnerRequest):
    if controller.engine is None:
        raise HTTPException(status_code=400, detail="Engine not running")
    try:
        count = controller.engine.cancel_orders_by_owner(req.owner_id)
        return {"status": "cancelled", "owner_id": req.owner_id, "count": count}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gui_app:app", host="0.0.0.0", port=8000, reload=True)


