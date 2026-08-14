"""
Web API Server for Automated Financial Trading System.
Bridges the Python MatchingEngine, OrderBook, Portfolio, RiskManager, MarketMaker, and Algorithmic Traders
to a real-time web application frontend without altering any core backend matching logic.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
import uuid
from typing import Any, Dict, List, Optional, Set
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from trading_simulator import (
    Order,
    OrderBook,
    MatchingEngine,
    Portfolio,
    RiskManager,
    MarketMaker,
    MomentumTrader,
    EMABasedTrader,
    SwingTrader,
    Execution,
)
from trading_simulator.strategies.twap import TWAPTrader
from trading_simulator.replay import ReplayRecorder, ReplayServer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trading_web_server")

# -----------------------------------------------------------------------------
# Global Market Engine State
# -----------------------------------------------------------------------------
class SystemState:
    def __init__(self):
        self.active_symbol: str = "AAPL"
        self.symbols: List[str] = ["AAPL", "NVDA", "TSLA", "MSFT", "AMZN"]
        self.base_prices: Dict[str, float] = {
            "AAPL": 185.50,
            "NVDA": 125.20,
            "TSLA": 245.80,
            "MSFT": 440.00,
            "AMZN": 180.00,
        }
        self.current_prices: Dict[str, float] = dict(self.base_prices)
        self.price_histories: Dict[str, List[Dict[str, Any]]] = {
            s: [] for s in self.symbols
        }

        # Core simulator components per symbol
        self.order_books: Dict[str, OrderBook] = {}
        self.matching_engines: Dict[str, MatchingEngine] = {}
        self.market_makers: Dict[str, MarketMaker] = {}
        self.momentum_traders: Dict[str, MomentumTrader] = {}
        self.ema_traders: Dict[str, EMABasedTrader] = {}
        self.swing_traders: Dict[str, SwingTrader] = {}
        self.twap_traders: Dict[str, TWAPTrader] = {}

        # User portfolio — tracks only orders submitted through /api/order
        self.portfolio = Portfolio(initial_cash=1_000_000.0, owner_id="user")
        self.risk_manager = RiskManager(
            portfolio=self.portfolio,
            max_order_qty=5000,
            max_symbol_position=50000,
            max_gross_notional=10_000_000,
            order_rate_limit_per_sec=50,
        )

        # Isolated portfolio for algorithmic bots — prevents bot fills from
        # contaminating the user's displayed cash, P&L, and position counters.
        # Order sizing for momentum/EMA uses this equity (~$500K), not the
        # user's $1M, keeping per-trade quantities proportionate to the
        # market maker's capital_base of $200K.
        self.bot_portfolio = Portfolio(initial_cash=500_000.0, owner_id="algo_bot")

        # Execution audit log
        self.recent_trades: List[Dict[str, Any]] = []

        # Toggles
        self.strategy_states: Dict[str, bool] = {
            "market_maker": True,
            "momentum": True,
            "ema": False,
            "swing": False,
            "twap": False,
        }
        
        # Track previous state for detecting enable transitions (for TWAP reset)
        self._prev_strategy_states: Dict[str, bool] = dict(self.strategy_states)

        # Replay recorder for session recording
        self.recorder = ReplayRecorder()

        # Initialize engines
        for sym in self.symbols:
            ob = ob_for_sym = OrderBook()
            
            # Monkeypatch orderbook.add_order to capture entering the book (genuine event)
            original_add_order = ob.add_order
            def make_patched_add_order(symbol_val, original_fn, ob_ref):
                def patched_add_order(order: Order):
                    original_fn(order)
                    if order.owner_id == "user":
                        LifecycleEventManager.emit_sync(
                            stage="ENTERED_ORDER_BOOK",
                            order_id=order.id,
                            symbol=order.symbol,
                            details=f"Added to bids/asks price-time priority list: {order.quantity} shs @ ${order.price:.2f}"
                        )
                return patched_add_order

            ob.add_order = make_patched_add_order(sym, original_add_order, ob)

            me = MatchingEngine(ob)
            # Risk checks for user orders are performed explicitly at the
            # /api/order endpoint (lines below) before match_order() is called.
            # Attaching the user's RiskManager here would incorrectly validate
            # bot orders against the user's portfolio position counters.
            me.risk_manager = None
            
            # Subscribe trade audit listener & portfolio listeners.
            # User portfolio only receives fills from orders owned by "user"
            # (the on_execution handler filters by owner_id internally).
            # Bot portfolio receives fills from all bot-owned orders via wrapper.
            me.subscribe_trades(self._on_trade_executed)
            me.subscribe_trades(self.portfolio.on_execution)
            me.subscribe_trades(self._bot_portfolio_execution_wrapper)

            self.order_books[sym] = ob
            self.matching_engines[sym] = me

            mm = MarketMaker(
                symbol=sym,
                matching_engine=me,
                gamma=0.1,
                k=1.5,
                horizon_seconds=60.0,
                max_inventory=2000,
                base_order_size=100,
                min_spread=0.05,
                num_levels=3,
                level_spacing_bps=5.0,
                drawdown_limit=0.25,
                capital_base=200_000.0,
                ks_cooldown_ticks=150,  # 60 s at 0.4 s/tick before peak resets
                owner_id="MARKET_MAKER",  # Unique ID for execution feed attribution
            )
            me.subscribe_trades(mm.on_execution)
            self.market_makers[sym] = mm

            mom = MomentumTrader(
                symbol=sym,
                matching_engine=me,
                portfolio=self.bot_portfolio,
                lookback=5,
                interval=0.5,
                owner_id="MOMENTUM",  # Unique ID for execution feed attribution
            )
            self.momentum_traders[sym] = mom

            ema = EMABasedTrader(
                symbol=sym,
                matching_engine=me,
                portfolio=self.bot_portfolio,
                short_window=5,
                long_window=15,
                interval=0.5,
                owner_id="EMA",  # Unique ID for execution feed attribution
            )
            self.ema_traders[sym] = ema

            # Mean reversion: buy near support, sell near resistance
            base_px = self.base_prices[sym]
            support = round(base_px * 0.94, 2)  # ~6% below base
            resistance = round(base_px * 1.06, 2)  # ~6% above base
            swing = SwingTrader(
                symbol=sym,
                matching_engine=me,
                portfolio=self.bot_portfolio,
                support_level=support,
                resistance_level=resistance,
                interval=0.5,
                risk_fraction=0.01,
                owner_id="SWING",  # Unique ID for execution feed attribution
            )
            self.swing_traders[sym] = swing

            # TWAP execution algorithm: slices large parent orders over time
            twap = TWAPTrader(
                symbol=sym,
                matching_engine=me,
                side="buy",  # Direction of parent order
                total_quantity=500,  # Parent order size to slice
                num_slices=5,  # Number of child orders
                duration_seconds=10.0,  # Execution window
                interval=0.5,
                owner_id="TWAP",  # Unique ID for execution feed attribution
                portfolio=self.bot_portfolio,
            )
            self.twap_traders[sym] = twap

            # Seed initial price point
            self.price_histories[sym].append({
                "timestamp": time.time(),
                "price": self.base_prices[sym],
                "volume": 0,
            })

    def _bot_portfolio_execution_wrapper(self, execu: Execution) -> None:
        """Route bot strategy executions to bot_portfolio.
        
        Strategies use unique owner_ids (MARKET_MAKER, MOMENTUM, EMA, SWING, TWAP)
        for execution feed attribution, but bot_portfolio expects owner_id="algo_bot".
        This wrapper translates strategy owner_ids to "algo_bot" for portfolio tracking.

        Bot-vs-bot fills are skipped: all bots share one omnibus portfolio, so an
        internal match is a wash (long + short cancel). Applying only the taker
        side previously created phantom inventory and could inflate equity-based
        order sizing without bound.
        """
        BOT_STRATEGIES = {"MARKET_MAKER", "MOMENTUM", "EMA", "SWING", "TWAP"}
        
        # Check if either taker or maker is a bot strategy
        is_bot_taker = execu.taker_owner_id in BOT_STRATEGIES
        is_bot_maker = execu.maker_owner_id in BOT_STRATEGIES
        
        if not is_bot_taker and not is_bot_maker:
            return  # Not a bot trade, skip

        if is_bot_taker and is_bot_maker:
            return  # Internal bot wash — no net omnibus portfolio change
        
        # Create a modified execution with owner_id="algo_bot" for portfolio tracking
        # (Execution is already imported at module scope from trading_simulator)
        modified_execu = Execution(
            trade_id=execu.trade_id,
            price=execu.price,
            quantity=execu.quantity,
            taker_order_id=execu.taker_order_id,
            maker_order_id=execu.maker_order_id,
            symbol=execu.symbol,
            side=execu.side,
            timestamp=execu.timestamp,
            taker_owner_id="algo_bot" if is_bot_taker else execu.taker_owner_id,
            maker_owner_id="algo_bot" if is_bot_maker else execu.maker_owner_id,
        )
        
        # Route to bot_portfolio with modified owner_ids
        self.bot_portfolio.on_execution(modified_execu)
    
    def _on_trade_executed(self, execu: Execution) -> None:
        trade_record = {
            "id": execu.trade_id,
            "symbol": execu.symbol,
            "price": float(execu.price),
            "quantity": int(execu.quantity),
            "side": execu.side,
            "buyer_id": execu.taker_owner_id if execu.side == "buy" else (execu.maker_owner_id or "maker"),
            "seller_id": execu.maker_owner_id if execu.side == "buy" else (execu.taker_owner_id or "taker"),
            "timestamp": time.time(),
        }
        self.recent_trades.insert(0, trade_record)
        if len(self.recent_trades) > 100:
            self.recent_trades.pop()

        self.current_prices[execu.symbol] = float(execu.price)
        
        # Record trade execution if recording is active
        self.recorder.record_trade(trade_record)

        # Notify trade executed / order matched if it belongs to user
        is_user_trade = (trade_record["buyer_id"] == "user" or trade_record["seller_id"] == "user")
        if is_user_trade:
            user_order_id = execu.taker_order_id if execu.taker_owner_id == "user" else execu.maker_order_id
            LifecycleEventManager.emit_sync(
                stage="ORDER_MATCHED",
                order_id=user_order_id,
                symbol=execu.symbol,
                details=f"Order matched: user execution for {execu.quantity} shs @ ${execu.price:.2f}"
            )

# NOTE: 'loop' is reassigned in the lifespan hook once uvicorn's event loop is running.
# emit_sync captures it at call time via asyncio.get_event_loop() so it always
# targets the active loop rather than the stale import-time loop.
loop: asyncio.AbstractEventLoop | None = None

class LifecycleEventManager:
    @staticmethod
    def emit_sync(stage: str, order_id: Optional[str] = None, symbol: Optional[str] = None, status: str = "SUCCESS", details: Optional[str] = None):
        """Thread-safe emission from synchronous (non-async) call sites such as order-book callbacks."""
        running_loop = loop  # use the loop assigned by the lifespan startup hook
        if running_loop is None or not running_loop.is_running():
            return  # server not yet started; drop the event silently
        asyncio.run_coroutine_threadsafe(
            LifecycleEventManager.emit(stage, order_id, symbol, status, details),
            running_loop
        )

    @staticmethod
    async def emit(stage: str, order_id: Optional[str] = None, symbol: Optional[str] = None, status: str = "SUCCESS", details: Optional[str] = None):
        """Asynchronous broadcast of a structured lifecycle event."""
        event_payload = {
            "type": "LIFECYCLE",
            "order_id": order_id,
            "symbol": symbol or (state.active_symbol if 'state' in globals() else None),
            "timestamp": time.time(),
            "stage": stage,
            "status": status
        }
        if details is not None:
            event_payload["details"] = details
        
        # Record lifecycle event if recording is active
        if 'state' in globals() and hasattr(state, 'recorder'):
            state.recorder.record_lifecycle(
                stage=stage,
                order_id=order_id,
                symbol=symbol or state.active_symbol,
                details=details,
                status=status
            )
        
        if 'manager' in globals():
            await manager.broadcast(event_payload)

state = SystemState()
replay_server = ReplayServer()  # Global replay server instance

# -----------------------------------------------------------------------------
# WebSocket Connection Manager
# -----------------------------------------------------------------------------
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)
        for dc in dead_connections:
            self.active_connections.discard(dc)

manager = ConnectionManager()

# Internal matching / bot cadence (unchanged). Live WS snapshots are sent
# less often so Render outbound bandwidth stays within the free-tier cap.
SIM_TICK_SECONDS = 0.4
WS_BROADCAST_INTERVAL_SECONDS = 1.0
# Last chart-history timestamp included in a *broadcast* SNAPSHOT (not the
# per-connection handshake). Used so follow-up frames send only new points.
_ws_history_watermark: Dict[str, float] = {}

# -----------------------------------------------------------------------------
# Background Synthetic Market Data & Bot Runner
# -----------------------------------------------------------------------------
async def market_simulation_loop():
    """Runs a real-time synthetic random walk and drives the strategy bots."""
    prev_portfolio_state = {
        "cash": float(state.portfolio.cash),
        "realized_pnl": float(state.portfolio.realized_pnl)
    }
    # Deadline is advanced by exactly one interval per broadcast (rather than
    # reset to "now") so the long-run average stays at 1 Hz instead of drifting
    # out to the next 0.4s tick boundary every time.
    next_ws_broadcast_at = time.monotonic() + WS_BROADCAST_INTERVAL_SECONDS
    last_ws_broadcast_symbol: Optional[str] = None
    while True:
        try:
            await asyncio.sleep(SIM_TICK_SECONDS)

            # Check portfolio updates
            current_cash = float(state.portfolio.cash)
            current_pnl = float(state.portfolio.realized_pnl)
            if (current_cash != prev_portfolio_state["cash"] or 
                current_pnl != prev_portfolio_state["realized_pnl"]):
                prev_portfolio_state["cash"] = current_cash
                prev_portfolio_state["realized_pnl"] = current_pnl
                current_prices_map = dict(state.current_prices)
                net_liq = float(state.portfolio.equity(current_prices_map))
                await LifecycleEventManager.emit(
                    stage="PORTFOLIO_UPDATED",
                    details=f"Balances updated: Cash = ${current_cash:,.2f}, PnL = ${current_pnl:.2f}, NetLiq = ${net_liq:,.2f}"
                )

            for sym in state.symbols:
                me = state.matching_engines[sym]
                ob = state.order_books[sym]
                mm = state.market_makers[sym]
                mom = state.momentum_traders[sym]
                ema = state.ema_traders[sym]
                swing = state.swing_traders[sym]
                twap = state.twap_traders[sym]

                # Sophisticated random walk with moving fair-value and occasional jumps
                prev_price = state.current_prices[sym]
                
                # 1. Update the "Fair Value" (Moving Mean Target)
                # In real life, fair value isn't a fixed number; it drifts as the world changes.
                # This makes the target center walk slowly, breaking the "fixed pattern" feel.
                state.base_prices[sym] += random.gauss(0, 0.004) 
                base_px = state.base_prices[sym]
                
                # 2. Damped Mean Reversion: Price is pulled toward the moving target,
                # but with less force (0.2% per tick) than before to allow for longer local trends.
                drift = (base_px - prev_price) * 0.002
                
                # 3. Poisson Jumps: 0.5% chance of a "news shock" (a larger sudden move)
                # to simulate how markets actually jump on discrete information.
                jump = 0
                if random.random() < 0.005:
                    jump = random.choice([-1, 1]) * random.uniform(0.15, 0.40)
                
                # 4. Standard volatility + Jumps
                change = random.gauss(drift, 0.015) + jump
                
                new_price = round(max(1.0, prev_price + change), 2)
                state.current_prices[sym] = new_price

                # Keep strategy mark-to-market maps in sync for equity-based sizing
                mark_prices = dict(state.current_prices)
                mom.mark_prices = mark_prices
                ema.mark_prices = mark_prices
                swing.mark_prices = mark_prices

                # Record price tick if recording is active
                state.recorder.record_tick(sym, new_price)

                market_event = {"symbol": sym, "price": new_price}

                # Feed market data to market maker
                if state.strategy_states["market_maker"]:
                    mm.receive(market_event)

                # Feed strategy traders
                if state.strategy_states["momentum"]:
                    mom.receive(market_event)
                    mom.trade()

                if state.strategy_states["ema"]:
                    ema.receive(market_event)
                    ema.trade()

                if state.strategy_states["swing"]:
                    swing.receive(market_event)
                    swing.trade()

                # TWAP: Reset if transitioning from disabled to enabled
                if state.strategy_states["twap"] and not state._prev_strategy_states["twap"]:
                    twap.reset()
                    logger.info("TWAP strategy reset for %s (re-enabled)", sym)
                
                if state.strategy_states["twap"]:
                    twap.receive(market_event)
                    twap.trade()

                # Heal any locked/crossed book left by self-trade residuals
                # from before the lock guard (or rare edge races). No-op when
                # best_bid < best_ask.
                bb, ba = ob.get_best_bid(), ob.get_best_ask()
                if bb is not None and ba is not None and bb >= ba:
                    n = me.unlock_self_locked_book()
                    if n:
                        logger.info("Unlocked self-locked book for %s (%d cancels)", sym, n)

                # Record history point
                best_bid = ob.get_best_bid() or round(new_price - 0.05, 2)
                best_ask = ob.get_best_ask() or round(new_price + 0.05, 2)
                mid_p = round((best_bid + best_ask) / 2.0, 2)

                history = state.price_histories[sym]
                history.append({
                    "timestamp": time.time(),
                    "price": mid_p,
                    "bid": best_bid,
                    "ask": best_ask,
                    "volume": random.randint(10, 500),
                })
                if len(history) > 300:
                    history.pop(0)

            # Update previous state tracking for next iteration
            state._prev_strategy_states = dict(state.strategy_states)
            
            # Periodic checkpoint for replay (disk only — not a WS payload)
            if state.recorder.should_checkpoint():
                snapshot = build_snapshot_payload(state.active_symbol)
                state.recorder.record_checkpoint(snapshot)

            # H4: do not build live WS snapshots when nobody is connected.
            # H2: broadcast at ~1 Hz; sim / matching / bots still tick at 0.4s.
            if manager.active_connections:
                now_mono = time.monotonic()
                if now_mono >= next_ws_broadcast_at:
                    symbol = state.active_symbol
                    send_full_history = (
                        last_ws_broadcast_symbol is None
                        or symbol != last_ws_broadcast_symbol
                    )
                    history_since = (
                        None
                        if send_full_history
                        else _ws_history_watermark.get(symbol)
                    )
                    snapshot = build_snapshot_payload(symbol, history_since=history_since)
                    await manager.broadcast(snapshot)
                    hist = snapshot.get("history") or []
                    if hist:
                        _ws_history_watermark[symbol] = float(hist[-1]["timestamp"])
                    next_ws_broadcast_at += WS_BROADCAST_INTERVAL_SECONDS
                    # If the loop stalled (long GC, blocking bot tick), don't
                    # burst-send to catch up on a backlog of missed deadlines.
                    if next_ws_broadcast_at <= now_mono:
                        next_ws_broadcast_at = now_mono + WS_BROADCAST_INTERVAL_SECONDS
                    last_ws_broadcast_symbol = symbol

        except Exception as e:
            logger.error(f"Error in simulation loop: {e}", exc_info=True)

def _chart_history_for_snapshot(symbol: str, history_since: Optional[float] = None) -> List[Dict[str, Any]]:
    """Last 60 chart points, or only points newer than a live-WS watermark (H1)."""
    full_history = state.price_histories.get(symbol, [])
    if history_since is None:
        return full_history[-60:]
    incremental = [p for p in full_history if p["timestamp"] > history_since]
    if len(incremental) > 60:
        return incremental[-60:]
    return incremental

def build_snapshot_payload(symbol: str, history_since: Optional[float] = None) -> Dict[str, Any]:
    ob = state.order_books[symbol]
    me = state.matching_engines[symbol]

    # Bids & Asks depth
    bids_raw = ob.bids_to_dataframe()
    asks_raw = ob.asks_to_dataframe()

    bids_aggregated = {}
    if not bids_raw.empty:
        for _, row in bids_raw.iterrows():
            p = float(row["Price"])
            q = int(row["Quantity"])
            bids_aggregated[p] = bids_aggregated.get(p, 0) + q

    asks_aggregated = {}
    if not asks_raw.empty:
        for _, row in asks_raw.iterrows():
            p = float(row["Price"])
            q = int(row["Quantity"])
            asks_aggregated[p] = asks_aggregated.get(p, 0) + q

    bids = [{"price": p, "quantity": q} for p, q in sorted(bids_aggregated.items(), reverse=True)[:15]]
    asks = [{"price": p, "quantity": q} for p, q in sorted(asks_aggregated.items())[:15]]

    best_bid = ob.get_best_bid()
    best_ask = ob.get_best_ask()
    spread = round(best_ask - best_bid, 2) if (best_bid and best_ask) else 0.0

    # User open orders
    user_orders = []
    with ob._lock:
        for oid, order in ob.order_map.items():
            if order.owner_id == "user":
                user_orders.append({
                    "id": order.id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "type": order.type,
                    "price": float(order.price),
                    "quantity": int(order.quantity),
                    "tif": order.tif,
                })

    # Portfolio metrics
    current_prices_map = dict(state.current_prices)
    net_liq = float(state.portfolio.equity(current_prices_map))

    return {
        "type": "SNAPSHOT",
        "symbol": symbol,
        "symbols": state.symbols,
        "last_price": state.current_prices.get(symbol, 0.0),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": spread,
        "bids": bids,
        "asks": asks,
        "history": _chart_history_for_snapshot(symbol, history_since),
        "user_orders": user_orders,
        "recent_trades": [t for t in state.recent_trades if t["symbol"] == symbol][:20],
        "portfolio": {
            "cash": round(float(state.portfolio.cash), 2),
            "realized_pnl": round(float(state.portfolio.realized_pnl), 2),
            "net_liq": round(net_liq, 2),
            "positions": {k: int(v) for k, v in state.portfolio.positions.items()},
        },
        "strategy_states": state.strategy_states,
    }

# -----------------------------------------------------------------------------
# FastAPI App Lifecycle
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()  # capture the real uvicorn event loop
    sim_task = asyncio.create_task(market_simulation_loop())
    yield
    sim_task.cancel()

app = FastAPI(title="Trading Simulator Web API", lifespan=lifespan)

# Browser CORS applies to REST (e.g. POST /api/order) but not to WebSockets.
# Always allow local Vite plus the production Vercel origin. CORS_ORIGINS can
# add more hosts; it no longer *replaces* these defaults (a missing/wrong env
# var was dropping the live frontend from the allow list).
PRODUCTION_FRONTEND_ORIGIN = "https://tradeflow-demo-omega.vercel.app"


def _load_cors_origins(env_value: Optional[str] = None) -> List[str]:
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        PRODUCTION_FRONTEND_ORIGIN,
    ]
    raw = os.getenv("CORS_ORIGINS", "") if env_value is None else env_value
    extra = [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]
    return list(dict.fromkeys(defaults + extra))


_cors_origins = _load_cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# -----------------------------------------------------------------------------
# Pydantic Schemas
# -----------------------------------------------------------------------------
class PlaceOrderRequest(BaseModel):
    symbol: str = Field(default="AAPL")
    side: str = Field(default="buy")  # buy or sell
    type: str = Field(default="limit")  # limit or market
    price: float = Field(default=100.0)
    quantity: int = Field(default=100)
    tif: str = Field(default="GTC")
    owner_id: str = Field(default="user")

class StrategyToggleRequest(BaseModel):
    strategy_name: str  # market_maker, momentum, ema
    enabled: bool

class SymbolChangeRequest(BaseModel):
    symbol: str

# -----------------------------------------------------------------------------
# REST Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/state")
async def get_state(symbol: Optional[str] = None):
    sym = symbol or state.active_symbol
    if sym not in state.symbols:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    return build_snapshot_payload(sym)

@app.post("/api/symbol")
async def set_active_symbol(req: SymbolChangeRequest):
    if req.symbol not in state.symbols:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    state.active_symbol = req.symbol
    return {"status": "ok", "active_symbol": state.active_symbol}

@app.post("/api/order")
async def place_order(req: PlaceOrderRequest):
    if req.symbol not in state.symbols:
        raise HTTPException(status_code=400, detail="Invalid symbol")

    order_id = uuid.uuid4().hex[:12]
    
    # 1. Emit Submitted
    await LifecycleEventManager.emit(
        stage="ORDER_SUBMITTED",
        order_id=order_id,
        symbol=req.symbol,
        details=f"Order received: {req.side.upper()} {req.quantity} shs {req.symbol} @ ${req.price:.2f}"
    )

    order = Order(
        id=order_id,
        price=req.price,
        quantity=req.quantity,
        side=req.side.lower(),
        type=req.type.lower(),
        symbol=req.symbol,
        tif=req.tif,
        owner_id=req.owner_id,
    )

    me = state.matching_engines[req.symbol]
    
    # Pre-trade risk checks
    if state.risk_manager:
        rejection_reason = "unknown"
        def on_reject_cb(payload):
            nonlocal rejection_reason
            rejection_reason = payload.get("reason", "unknown")
            
        state.risk_manager.on_reject = on_reject_cb
        ok = state.risk_manager.allow_order(order)
        state.risk_manager.on_reject = None

        if not ok:
            await LifecycleEventManager.emit(
                stage="RISK_VALIDATION",
                status="FAILED",
                order_id=order_id,
                symbol=req.symbol,
                details=f"Risk check failed: {rejection_reason}"
            )
            raise HTTPException(status_code=400, detail=f"Risk check rejected order: {rejection_reason}")
        else:
            await LifecycleEventManager.emit(
                stage="RISK_VALIDATION",
                status="PASSED",
                order_id=order_id,
                symbol=req.symbol,
                details="Pre-trade risk gateway passed successfully."
            )

    # 3. Emit Accepted
    await LifecycleEventManager.emit(
        stage="ORDER_ACCEPTED",
        order_id=order_id,
        symbol=req.symbol,
        details="Gateway Accepted: FIX MsgType=8 ACK dispatched."
    )

    # Record user order if recording is active
    state.recorder.record_user_order({
        "order_id": order_id,
        "symbol": req.symbol,
        "side": req.side,
        "type": req.type,
        "price": order.price,
        "quantity": order.quantity,
        "tif": req.tif
    })
    
    me.match_order(order)
    
    # Checkpoint immediately after processing so replay captures the exact
    # order-book and portfolio state resulting from this order (fills, new
    # resting orders, updated cash/positions) rather than waiting for the
    # next periodic checkpoint.
    state.recorder.record_checkpoint(build_snapshot_payload(req.symbol))
    
    return {"status": "submitted", "order_id": order_id}

@app.delete("/api/order/{symbol}/{order_id}")
async def cancel_order(symbol: str, order_id: str):
    if symbol not in state.symbols:
        raise HTTPException(status_code=400, detail="Invalid symbol")
    ob = state.order_books[symbol]
    ob.cancel_order(order_id)
    
    # Record user cancel if recording is active
    state.recorder.record_user_cancel(order_id, symbol)
    state.recorder.record_checkpoint(build_snapshot_payload(symbol))
    
    return {"status": "cancelled", "order_id": order_id}

@app.post("/api/strategies/toggle")
async def toggle_strategy(req: StrategyToggleRequest):
    if req.strategy_name not in state.strategy_states:
        raise HTTPException(status_code=400, detail="Unknown strategy")
    state.strategy_states[req.strategy_name] = req.enabled
    
    # Record strategy toggle if recording is active
    state.recorder.record_strategy_toggle(req.strategy_name, req.enabled)
    state.recorder.record_checkpoint(build_snapshot_payload(state.active_symbol))
    
    return {"status": "ok", "strategy_states": state.strategy_states}

# -----------------------------------------------------------------------------
# Recording Control Endpoints
# -----------------------------------------------------------------------------
class RecordingStartRequest(BaseModel):
    session_name: Optional[str] = None

@app.post("/api/recording/start")
async def start_recording(req: RecordingStartRequest = RecordingStartRequest()):
    """Start a new recording session."""
    try:
        result = state.recorder.start_recording(req.session_name)
        
        # Record SESSION_START event with initial configuration
        initial_state = {
            "symbols": state.symbols,
            "base_prices": state.base_prices,
            "active_symbol": state.active_symbol,
            "strategy_states": dict(state.strategy_states),
            "initial_portfolio": {
                "cash": float(state.portfolio.cash),
                "realized_pnl": float(state.portfolio.realized_pnl),
                "positions": dict(state.portfolio.positions)
            }
        }
        state.recorder.record_session_start(initial_state)
        
        # Immediately capture a full CHECKPOINT (order book, chart history,
        # portfolio, user orders, strategy states) so replay always has a
        # complete starting point even for very short recordings that would
        # otherwise end before the periodic checkpoint interval elapses.
        state.recorder.record_checkpoint(build_snapshot_payload(state.active_symbol))
        
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/recording/stop")
async def stop_recording():
    """Stop the current recording session."""
    try:
        return state.recorder.stop_recording()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/recording/status")
async def get_recording_status():
    """Get current recording status."""
    return state.recorder.get_status()

@app.get("/api/recording/sessions")
async def list_recording_sessions():
    """List all available recording sessions."""
    return {"sessions": ReplayRecorder.list_sessions()}

# -----------------------------------------------------------------------------
# Replay Control Endpoints
# -----------------------------------------------------------------------------
class ReplayLoadRequest(BaseModel):
    filename: str

class ReplaySeekRequest(BaseModel):
    target: float | int  # Index, timestamp, or progress ratio

class ReplaySpeedRequest(BaseModel):
    speed: float

class ReplayStepRequest(BaseModel):
    direction: int = Field(default=1)

@app.post("/api/replay/load")
async def replay_load(req: ReplayLoadRequest):
    """Load a replay session file."""
    try:
        metadata = await replay_server.load_session(req.filename)
        return {"status": "loaded", "session": metadata}
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/replay/play")
async def replay_play():
    """Start or resume replay playback."""
    try:
        return await replay_server.play()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/replay/pause")
async def replay_pause():
    """Pause replay playback."""
    return await replay_server.pause()

@app.post("/api/replay/stop")
async def replay_stop():
    """Stop replay and reset to beginning."""
    return await replay_server.stop()

@app.post("/api/replay/seek")
async def replay_seek(req: ReplaySeekRequest):
    """Seek to a specific position in replay."""
    try:
        return await replay_server.seek(req.target)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/replay/speed")
async def replay_set_speed(req: ReplaySpeedRequest):
    """Set replay playback speed."""
    return replay_server.set_speed(req.speed)

@app.post("/api/replay/step")
async def replay_step(req: ReplayStepRequest = ReplayStepRequest()):
    """Step forward/backward by N events."""
    try:
        return await replay_server.step(req.direction)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/replay/status")
async def replay_status():
    """Get current replay status."""
    return replay_server.get_status()

@app.get("/api/replay/sessions")
async def replay_list_sessions():
    """List available replay sessions."""
    return {"sessions": ReplayRecorder.list_sessions()}

# -----------------------------------------------------------------------------
# WebSocket Stream Endpoint
# -----------------------------------------------------------------------------
@app.websocket("/ws/stream")
async def websocket_stream(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Handshake: full SNAPSHOT including the last 60 chart points (H1).
        await websocket.send_json(build_snapshot_payload(state.active_symbol))
        while True:
            # Keep connection open & handle incoming client messages if any
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

@app.websocket("/ws/replay")
async def websocket_replay(websocket: WebSocket):
    """WebSocket endpoint for replay mode streaming."""
    await websocket.accept()
    await replay_server.add_connection(websocket)
    try:
        # Send initial status
        await websocket.send_json({
            "type": "REPLAY_CONNECTED",
            "data": replay_server.get_status()
        })
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Could handle client commands here if needed
    except WebSocketDisconnect:
        await replay_server.remove_connection(websocket)
    except Exception as e:
        logger.error(f"Replay WebSocket error: {e}")
        await replay_server.remove_connection(websocket)

if __name__ == "__main__":
    import uvicorn
    # Bind 0.0.0.0 so cloud hosts (Render, etc.) can reach the service.
    # PORT is injected by the platform; default 8000 for local/dev.
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
