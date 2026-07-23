# 📈 Automated Financial Trading System

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-109%20passing-brightgreen.svg)](tests)
[![Version](https://img.shields.io/badge/version-2.2.0-blueviolet.svg)](pyproject.toml)
[![Contributions](https://img.shields.io/badge/Contributions-Welcome-orange.svg)](CONTRIBUTING.md)

<img src="https://capsule-render.vercel.app/api?type=waving&color=gradient&customColorList=12,20,25&height=140&section=header&text=Trade.%20Simulate.%20Understand.&fontSize=38&fontColor=ffffff&animation=fadeIn&fontAlignY=38&desc=A%20full%20stock%20exchange%2C%20built%20from%20scratch%2C%20that%20runs%20on%20your%20laptop&descAlignY=58&descAlign=50" width="100%"/>

</div>

## What is this, really?

Imagine you could build your own tiny stock exchange — one with real buyers
and sellers, a real order book, and real price competition — except nobody's
money is actually at risk and you can rewind time as many times as you want.
That's what this is.

You feed it a stock symbol, tell it how you want to trade (or let one of the
built-in robot traders do it for you), and watch as orders get matched,
prices move, and a portfolio grows or shrinks in real time — powered by the
same mechanics real exchanges use under the hood.

**In one line:** a from-scratch limit order book, matching engine, market
maker, algorithmic traders, multi-venue router, FIX protocol engine, and
backtester — a complete miniature electronic market you run entirely on your
own machine.

For anyone who wants the deeper version: this is a research and education
platform for market microstructure. It implements price-time priority
matching, self-trade prevention, time-in-force handling (GTC/IOC/FOK),
Avellaneda-Stoikov market making, pre-trade risk controls, multi-venue NBBO
routing, opening/closing auctions, a real FIX 4.2 session layer, and
institutional-grade backtesting with Sharpe/Sortino/drawdown analytics — all
as an installable Python package with both a guided, no-flags CLI and a full
scriptable one.

## 🎯 What You Can Do With It

**If you trade or invest** — backtest a strategy against real historical
data, paper-trade it live against a simulated market, and see exactly how it
would have performed with professional-grade metrics, before ever risking
real money.

**If you build or research** — study market microstructure hands-on: watch
how price-time priority actually resolves a crossed book, how a market
maker's quotes skew with inventory, how an order gets swept across venues
for the best effective price. Wire in your own strategy in a dozen lines of
code.

**If you teach or learn** — every mechanism is small enough to read
end-to-end and readable enough to actually learn from: the whole matching
engine is a few hundred lines, not a black box.

## 📋 Table of Contents

- [What's Included](#-whats-included)
- [Project Layout](#-project-layout)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [CLI Reference](#-cli-reference)
- [Guided CLI (No Flags)](#-guided-cli-no-flags)
- [Trading Strategies](#-trading-strategies)
- [Custom Traders](#-custom-traders)
- [Market Making](#-market-making)
- [Multi-Venue Routing (NBBO + Sweep)](#-multi-venue-routing-nbbo--sweep)
- [Risk Management](#-risk-management)
- [Backtesting](#-backtesting)
- [Order Book Snapshots & Deterministic Replay](#-order-book-snapshots--deterministic-replay)
- [Auctions](#-auctions)
- [Execution Algorithms (TWAP/VWAP)](#-execution-algorithms-twapvwap)
- [FIX Protocol Engine](#-fix-protocol-engine)
- [Live Order Control (JSON over TCP)](#️-live-order-control-json-over-tcp)
- [Event Streaming](#-event-streaming)
- [Database Persistence](#-database-persistence)
- [Performance Analytics & TCA](#-performance-analytics--tca)
- [Testing](#-testing)
- [Optional Dependencies](#-optional-dependencies)
- [Contributing](#-contributing)
- [License](#-license)

## 🚀 What's Included

**Core engine**
- Limit order book with strict price-time priority and tick/lot normalization
- Matching engine supporting limit/market orders, GTC/IOC/FOK time-in-force,
  post-only, self-trade prevention (that preserves other participants'
  queue priority instead of corrupting it), price bands, halts, and
  configurable slippage/latency simulation
- Per-instrument configuration (tick size, lot size, trading hours) via
  `InstrumentRegistry`, instantiated per engine so parallel backtests and
  Optuna trials never leak state into each other
- Order book snapshotting (interval-based or on demand) and deterministic
  event-log replay (`EventLogger` + `ReplayRunner`)
- Opening/closing auction uncrossing (single clearing price maximizing
  matched volume)

**Trading & market making**
- Built-in algorithmic traders: Momentum, EMA crossover, Swing (support/
  resistance), and a news-sentiment trader (TensorFlow-based, with memory of
  already-traded headlines so it doesn't re-trade stale news)
- Avellaneda-Stoikov-inspired market maker: multi-level laddering, inventory
  skew, volatility-based spread widening, momentum skew, and a drawdown
  kill-switch measured against a configurable capital base
- Framework for custom traders: subclass `AlgorithmicTrader`, load by
  `module:ClassName` from the CLI or guided prompts
- TWAP/VWAP parent-order slicing for reduced market impact on large orders

**Risk & connectivity**
- Pre-trade risk manager: position/notional limits, round-lot enforcement,
  per-owner order rate limiting, per-owner drawdown kill-switch, volatility
  halts, leverage caps, per-symbol gross exposure caps, and manual
  owner/symbol enable/disable switches
- Multi-venue router: NBBO aggregation across independent `MatchingEngine`
  instances and inter-market-sweep order splitting by depth and effective
  (fee-adjusted) price
- **A real FIX 4.2 engine**, not just a message-format demo: full session
  layer (Logon, Heartbeat, TestRequest, ResendRequest with true message
  replay, SequenceReset, Logout), MsgSeqNum tracking in both directions, and
  real ExecutionReport/Reject generation — with both a server
  (`FixApplication`) and a client (`FixClient`) so it talks to itself out of
  the box. See [FIX Protocol Engine](#-fix-protocol-engine).
- A lightweight JSON-over-TCP order control channel for live mode (place/
  cancel/modify orders from a second terminal without FIX)
- Event streaming: a generic pub-sub `EventBus` plus optional Redis and
  Kafka publishers

**Backtesting & analytics**
- Single-asset and multi-asset backtesting against historical data
  (yahooquery/yfinance, with local caching and retry/backoff)
- Performance metrics (Sharpe, Sortino, CAGR, max drawdown), HTML report
  export, and rolling metrics printed during live/replay runs
- Trade cost analysis (TCA): slippage vs. mid/last and adverse-selection
  tracking, written to CSV
- Optional Optuna hyperparameter search and MLflow experiment tracking
- Optional PostgreSQL persistence (`DbLogger`) for executions, equity, and
  strategy configs

**Usability**
- Two CLIs in one: a guided, prompt-driven mode for anyone who doesn't want
  to memorize flags, and a full `argparse` flag interface for scripting/CI
- Clean, actionable error messages for expected failures (missing market
  data provider, bad custom-trader spec, etc.) instead of raw tracebacks --
  pass `--debug` to get the full traceback back when you actually want it
- Every optional third-party dependency (simplefix, tensorflow, sqlalchemy,
  optuna, mlflow, redis, confluent-kafka) degrades gracefully: if it's not
  installed, the feature that needs it raises one clear `RuntimeError`
  telling you what to `pip install`, instead of crashing somewhere deep in
  the call stack
- 109 automated tests covering the matching engine, order book, portfolio,
  risk manager, strategies, market maker, router, the FIX session layer,
  DB/streaming graceful-degradation paths, socket-level order-CLI behavior,
  snapshot/replay round-trips, auctions, and the CLI itself end to end

## 🏗️ Project Layout

```
trading_simulator/
├── __init__.py            # top-level re-exports: `from trading_simulator import X`
├── __main__.py             # `python -m trading_simulator` entry point
├── config.py                # environment-variable-driven defaults
├── core/
│   ├── order.py              # Order dataclass + validation
│   ├── order_book.py          # price-time-priority book, its own lock
│   ├── matching_engine.py       # matching, TIF, auctions, snapshots, risk hook
│   ├── instruments.py            # per-symbol tick/lot/hours registry
│   └── execution.py               # Execution/fill record
├── portfolio/                # Portfolio + multi-owner PortfolioDispatcher
├── risk/                      # RiskManager (pre-trade checks, kill-switches)
├── strategies/                  # Momentum/EMA/Swing/Sentiment/Custom traders
├── marketmaker/                   # Avellaneda-Stoikov MarketMaker
├── marketdata/                      # historical + live feed, synthetic liquidity
├── connectivity/                      # FIX engine, order-CLI socket server, router
│   ├── fix_session.py                    # FIX session-layer state machine
│   ├── fix_app.py                         # FixApplication (server) + FixClient
│   ├── order_cli.py                        # JSON-over-TCP order control
│   └── router.py                            # NBBO aggregation + sweep routing
├── execution_algos/                     # TWAP/VWAP slicing
├── persistence/                           # CSV/audit/event logging, optional DB
├── streaming/                              # EventBus + Redis/Kafka publishers
├── backtest/                                # runner, metrics, replay, Optuna glue
└── cli/
    ├── args.py                                 # argparse flag definitions
    ├── guided.py                                 # no-flags interactive menu
    ├── prompts.py                                  # shared prompt helpers
    └── main.py                                       # mode dispatch, error handling

tests/                # 109 tests -- see Testing below
examples/strats.py    # ready-to-use custom trader examples (BreakoutTrader, MeanRevTrader)
```

## 📦 Installation

Requires **Python 3.10+**. CI runs the test suite on 3.10, 3.11, and 3.12.

```bash
git clone https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System.git
cd Automated-Financial-Market-Trading-System

python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Core only (numpy/pandas/requests) -- enough for demo mode and the test suite:
pip install -e .

# Historical/live market data + FIX (recommended for backtest/live/replay):
pip install -r requirements.txt

# Everything, including sentiment trading, DB persistence, event streaming,
# and Optuna/MLflow:
pip install -r requirements-full.txt

# If you're contributing:
pip install -r requirements-dev.txt
```

Copy `.env.example` to `.env` and fill in anything you plan to use (NewsAPI
key, database URL, Redis/Kafka endpoints). Nothing in `.env` is required for
`--mode demo` or for running the test suite.

## ⚡ Quick Start

```bash
# No network, no setup -- a self-contained order-book demo:
python -m trading_simulator --mode demo

# A single-symbol backtest with built-in traders and an HTML report
# (requires yahooquery or yfinance -- see requirements.txt):
python -m trading_simulator --mode backtest --symbol AAPL \
  --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders --export-report

# Prefer prompts over flags? Just run it with nothing after it:
python -m trading_simulator
```

If a market data provider isn't installed, backtest/live/replay modes fail
with one clear message and exit code 1 instead of a traceback -- try
`--mode demo` (no data dependency) or add `--debug` to see the full
traceback if you're actually debugging the fetch path.

## 📖 CLI Reference

Every flag below lives in `trading_simulator/cli/args.py`. Run
`python -m trading_simulator --help` for the authoritative, always-in-sync
list.

**Mode & data**
| Flag | Default | Description |
|---|---|---|
| `--mode` | `backtest` | `backtest`, `live`, `replay`, or `demo` |
| `--debug` | off | Show full tracebacks on expected/actionable errors |
| `--symbol` | `AAPL` | Ticker symbol |
| `--symbols` | *(none)* | Comma-separated symbols for multi-asset backtest |
| `--start-date` / `--end-date` | `2023-01-01` / `2023-12-31` | Backtest/replay date range |
| `--seed` | *(none)* | Random seed for reproducibility |
| `--log-dir` | `.logs` | Directory for CSV logs (equity/executions/TCA) |

**Trading & fees**
| Flag | Default | Description |
|---|---|---|
| `--enable-traders` | off | Enable the built-in Momentum/EMA/Swing traders |
| `--initial-cash` | `1000000` | Starting portfolio cash |
| `--fee-bps` / `--taker-fee-bps` / `--maker-rebate-bps` | `0.0` | Execution fees |
| `--slippage-bps-per-100` | `0.0` | Backtest slippage per 100 shares |
| `--latency-ms` | `0` | Simulated order delay |
| `--momentum-lookback`, `--ema-short-window`, `--ema-long-window`, `--swing-support`, `--swing-resistance` | see `--help` | Built-in trader parameters |
| `--custom-trader module:ClassName` (repeatable) + `--custom-trader-params '{"...json..."}'` | — | Load custom strategies |

**Market maker** (always constructed for backtest/replay/live; tune or leave defaults)
| Flag | Default | Description |
|---|---|---|
| `--mm-gamma` | `0.1` | Risk-aversion coefficient |
| `--mm-k` | `1.5` | Order-book liquidity/decay parameter |
| `--mm-horizon-seconds` | `60.0` | Quoting horizon |
| `--mm-max-inventory` | `1000` | Max absolute inventory before skewing quotes |
| `--mm-base-order-size` | `100` | Base quote size per level |
| `--mm-min-spread` | `0.01` | Minimum quoted spread |
| `--mm-num-levels` | `2` | Quote levels per side |
| `--mm-level-spacing-bps` | `2.0` | Spacing between levels, in bps |
| `--mm-size-decay` | `0.7` | Per-level size decay (0-1] |
| `--mm-momentum-window` | `10` | Momentum lookback (ticks) |
| `--mm-alpha-skew` | `0.5` | Quote skew sensitivity |
| `--mm-vol-widen-z` | `2.0` | Spread-widening volatility threshold |
| `--mm-drawdown-limit` | `0.2` | Kill-switch drawdown limit (fraction of capital base) |
| `--mm-capital-base` | `100000.0` | Capital base the kill-switch measures drawdown against |

**Risk manager**
| Flag | Default | Description |
|---|---|---|
| `--risk-max-order-qty` | `1000` | Max single order quantity |
| `--risk-max-symbol-position` | `10000` | Max net position per symbol |
| `--risk-max-gross-notional` | `5000000` | Max order notional |
| `--risk-min-order-qty` / `--risk-lot-size` / `--risk-round-lot-required` | `1` / `1` / off | Lot rules |
| `--risk-order-rate-limit` | *(none)* | Orders/sec per owner |
| `--risk-owner-drawdown-limit` | *(none)* | Per-owner drawdown kill-switch (fraction) |
| `--risk-volatility-window` / `--risk-volatility-halt-z` | `20` / *(none)* | Volatility halt |
| `--risk-max-leverage` / `--risk-max-symbol-gross-exposure` | *(none)* | Leverage/exposure caps |

**Matching protections & engine**
| Flag | Default | Description |
|---|---|---|
| `--price-band-bps` / `--band-reference` | `0.0` / `mid` | Reject outlier prices beyond this band |
| `--use-queue` / `--queue-max` | off / `10000` | Optional order submission queue |
| `--snapshot-interval-sec` / `--snapshot-dir` | `0` (disabled) | Periodic order-book snapshots |

**Live mode extras**
| Flag | Default | Description |
|---|---|---|
| `--md-interval` | `60` | Market data poll interval (seconds) |
| `--fix-host` / `--fix-port` | `localhost` / `5005` | FIX server (needs `simplefix`) |
| `--fix-sender-comp-id` / `--fix-target-comp-id` | `SIMULATOR` / `CLIENT` | FIX SenderCompID/TargetCompID (tags 49/56) |
| `--fix-heartbeat-interval` | `30` | FIX HeartBtInt in seconds (tag 108) |
| `--order-cli-enable` / `--order-cli-host` / `--order-cli-port` / `--order-cli-owner` | off / `127.0.0.1` / `8765` / `cli` | JSON order-control socket (`--order-cli-port 0` picks a free OS-assigned port; check the log line for the actual port) |
| `--inject-liquidity` | `0` (disabled) | Inject synthetic liquidity every N seconds |
| `--news-api-key`, `--sentiment-model-path`, `--sentiment-vocab-path` | — | Enable the sentiment trader (needs `tensorflow` + a NewsAPI key) |

**Replay mode**
| Flag | Default | Description |
|---|---|---|
| `--replay-speed` | `1.0` | Playback speed multiplier |
| `--replay-interval-seconds` | *(none)* | Fixed per-tick delay (overrides `--replay-speed`) |

**Reporting & experiments**
| Flag | Default | Description |
|---|---|---|
| `--export-report` / `--report-out` | off / `report.html` | HTML performance report |
| `--optuna-trials` | `0` (disabled) | Optuna hyperparameter search trial count |
| `--mlflow-uri` / `--mlflow-experiment` | *(none)* / `trading-simulator` | MLflow tracking (requires `--optuna-trials` > 0) |

## 🧭 Guided CLI (No Flags)

Prefer prompts over flags? Run it with nothing after it:

```bash
python -m trading_simulator
```

You'll be asked to pick a mode (Backtest / Live / Replay / Demo / Advanced),
then walked through the relevant flags above with short tips and sensible
defaults -- press Enter to accept a default. "Advanced" lets you type raw
flags if you already know exactly what you want. Ctrl+C at any prompt
cancels cleanly (no traceback).

Adding custom traders interactively: answer "Yes" to "Add custom traders?",
then enter a `module:ClassName` spec (e.g. `examples.strats:BreakoutTrader`)
and JSON params (e.g. `{"lookback": 15, "band_bps": 8, "owner_id": "bo15"}`).
Repeat to add more; leave the spec blank to continue.

## 📊 Trading Strategies

```python
from trading_simulator import MomentumTrader, EMABasedTrader, SwingTrader

momentum = MomentumTrader(symbol="AAPL", matching_engine=engine, lookback=5, interval=0.1)
ema = EMABasedTrader(symbol="AAPL", matching_engine=engine, short_window=5, long_window=20, interval=0.1)
swing = SwingTrader(symbol="AAPL", matching_engine=engine, support_level=100.0, resistance_level=200.0, interval=0.1)
```

- **Momentum**: buys on positive short-term price momentum, sells on
  negative momentum, crosses the book aggressively at best bid/ask.
- **EMA crossover**: trend-following; buys when the short EMA is above the
  long EMA, sells when it flips.
- **Swing**: mean-reversion between a fixed support and resistance level.
- **Sentiment** (`SentimentAnalysisTrader`): fetches recent headlines via
  NewsAPI, scores them with a TensorFlow/Keras model, and trades on the
  sentiment -- remembers headlines it's already acted on so it doesn't
  re-trade the same stale news every poll.

Position sizing for the three built-in traders can scale with account
equity instead of a fixed share count -- pass `portfolio=...` and optionally
`risk_fraction=...`; omit both to keep a fixed default size.

## 🧩 Custom Traders

Subclass `AlgorithmicTrader` and implement `trade()` (and optionally
`on_market_data`):

```python
from trading_simulator import AlgorithmicTrader, Order
import uuid

class MyCustomTrader(AlgorithmicTrader):
    def __init__(self, symbol, matching_engine, threshold=0.0, interval=0.1, owner_id="custom"):
        super().__init__(symbol, matching_engine, interval)
        self.threshold = threshold
        self.owner_id = owner_id

    def trade(self):
        if self.current_price is None:
            return
        if self.current_price < self.threshold:
            order = Order(id=uuid.uuid4().hex, price=self.current_price, quantity=10,
                           side="buy", type="market", symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(order)
```

`examples/strats.py` ships two ready-to-use examples --
`BreakoutTrader` (buys/sells when price clears its recent range by a
basis-point band) and `MeanRevTrader` (z-score mean reversion). Load either
one from the CLI:

```bash
python -m trading_simulator --mode backtest --enable-traders \
  --custom-trader examples.strats:BreakoutTrader \
  --custom-trader-params '{"lookback": 15, "band_bps": 8, "owner_id": "bo15"}'
```

A typo'd or missing `module:ClassName` spec fails with a clear message at
load time (`StrategyLoadError`), not a confusing `AttributeError` deep in
the trading loop.

**Integration pipeline:** market data tick -> your trader's
`on_market_data` -> your `trade()` -> `Order(...)` -> pre-trade risk checks
-> matching -> `executions.csv` / TCA -> owner-aware `Portfolio` ->
`equity_curve.csv`. Use a unique `owner_id` per strategy for clean PnL/risk
isolation, and keep `trade()` non-blocking (no `sleep()` inside it).

## 🏪 Market Making

```python
from trading_simulator import MarketMaker

maker = MarketMaker(
    symbol="AAPL", matching_engine=engine,
    gamma=0.1, k=1.5, horizon_seconds=60.0,
    max_inventory=1000, base_order_size=100, min_spread=0.01,
    num_levels=2, level_spacing_bps=2.0, size_decay=0.7,
    momentum_window=10, alpha_skew=0.5, vol_widen_z=2.0,
    drawdown_limit=0.2, capital_base=100_000.0,
)
```

Avellaneda-Stoikov-inspired quoting: reservation price adjusts for
inventory, spread widens under high volatility, quotes skew with recent
momentum, and size decays across levels. Quotes route through the same
`match_order()` path as every other participant (so they get pre-trade risk
checks, price-band protection, and audit logging -- a quote that crosses
the book fills immediately as taker instead of only ever resting). The
drawdown kill-switch tracks realized P&L plus mark-to-market inventory
against `capital_base`, not against its own noisy peak, so it doesn't
false-trigger on ordinary inventory swings that cross zero.

## 🔀 Multi-Venue Routing (NBBO + Sweep)

```python
from trading_simulator import Venue, MarketRouter, Order

router = MarketRouter()
router.add_venue(Venue("NYSE", engine_nyse, fee_bps=0.0))
router.add_venue(Venue("ARCA", engine_arca, fee_bps=2.0))

print(router.nbbo())  # {"best_bid": ..., "best_ask": ..., "venues": [...]}

order = Order(id="o1", price=100.0, quantity=200, side="buy", type="limit", symbol="AAPL")
router.route_order(order)  # sweeps depth across venues by effective (fee-adjusted) price
```

`nbbo()` aggregates the best bid/ask across every registered venue.
`route_order()` picks the single cheapest venue when one venue has enough
depth, or splits the order across venues (an inter-market sweep) when it
doesn't -- ranking venues by *effective* price (quoted price adjusted for
that venue's fee), so a nominally-better price at a higher-fee venue can
correctly lose to a nominally-worse price with no fee.

## 🛡️ Risk Management

```python
from trading_simulator import RiskManager

risk_manager = RiskManager(
    portfolio=portfolio,
    max_order_qty=1000, max_symbol_position=10000, max_gross_notional=5_000_000,
    min_order_qty=1, lot_size=1, round_lot_required=False,
    order_rate_limit_per_sec=10, owner_drawdown_limit=0.2,
    volatility_window=20, volatility_halt_z=3.0,
    max_leverage=3.0, max_symbol_gross_exposure=1_000_000,
)

# Manual kill switches:
risk_manager.disable_owner("momentum_trader")
risk_manager.disable_symbol("TSLA")
risk_manager.enable_owner("momentum_trader")
risk_manager.enable_symbol("TSLA")
```

All of the above are also configurable interactively (run with no flags and
choose "Customize risk manager?" when prompted) or via the `--risk-*` flags
in the [CLI Reference](#-cli-reference).

## 📈 Backtesting

```python
from trading_simulator import (
    OrderBook, MatchingEngine, MarketMaker, Portfolio,
    MomentumTrader, EMABasedTrader, SwingTrader,
    run_backtest, load_historical_data,
)

data = load_historical_data("AAPL", "2023-01-01", "2023-12-31")
order_book = OrderBook()
engine = MatchingEngine(order_book)
portfolio = Portfolio(initial_cash=1_000_000)
market_maker = MarketMaker(symbol="AAPL", matching_engine=engine)
traders = [
    MomentumTrader(symbol="AAPL", matching_engine=engine, lookback=5),
    EMABasedTrader(symbol="AAPL", matching_engine=engine, short_window=5, long_window=20),
    SwingTrader(symbol="AAPL", matching_engine=engine, support_level=100, resistance_level=200),
]
run_backtest(data, market_maker, engine, traders=traders, portfolio=portfolio)
```

**Multi-asset:**

```python
from trading_simulator import run_multi_backtest, load_multi_historical_data

data_map = load_multi_historical_data(["AAPL", "MSFT", "GOOGL"], "2023-01-01", "2023-12-31")
engines, makers = {}, {}
for symbol in data_map:
    ob = OrderBook()
    engines[symbol] = MatchingEngine(ob)
    makers[symbol] = MarketMaker(symbol=symbol, matching_engine=engines[symbol])
run_multi_backtest(data_map, engines, makers, portfolio=portfolio)
```

**Parameter search (requires `optuna`):**

```python
import optuna
from trading_simulator.backtest import objective_optuna

def objective(trial):
    return objective_optuna(
        trial, symbol="AAPL", start="2023-01-01", end="2023-12-31",
        base_params={"initial_cash": 1_000_000, "fee_bps": 1.0,
                      "risk_max_order_qty": 1000, "risk_max_symbol_position": 10000,
                      "risk_max_gross_notional": 5_000_000},
        log_dir=".logs",
    )

study = optuna.create_study(direction="maximize")
study.optimize(objective, n_trials=100)
```

Or from the CLI directly: `--optuna-trials 100 --mlflow-uri file:/tmp/mlruns`.

## 📸 Order Book Snapshots & Deterministic Replay

Two independent mechanisms:

**Snapshots** (point-in-time book state, for fast warm-starts):

```python
engine.snapshot_dir = "snapshots/"
engine.snapshot_now()                       # write one snapshot immediately
engine.start_snapshotting(interval_sec=30, out_dir="snapshots/")  # or periodically

# Elsewhere / later:
fresh_engine.load_snapshot_file("snapshots/<file>.json")
```

**Event log + replay** (every NEW/CANCEL event, for deterministically
reconstructing a full session from scratch):

```python
from trading_simulator import EventLogger, ReplayRunner

logger = EventLogger(base_dir=".logs")
engine.event_logger = logger          # engine now logs every NEW/CANCEL

# ... run your session ...

events = logger.replay()
result = ReplayRunner(events).run()   # rebuilds a fresh engine from the log
print(result["orders"], result["cancels"])
replayed_engine = result["engine"]
```

## 🔔 Auctions

```python
engine.start_auction(phase="open")   # buffer subsequent orders instead of matching immediately
# ... orders submitted during this phase are pooled, not matched ...
engine.uncross_auction()             # clears at the single price that maximizes matched volume
```

If no cross exists at uncross time, pooled auction-only orders are
discarded -- and a warning is logged naming exactly which order IDs were
dropped, so you're not left wondering where they went.

## ⏱️ Execution Algorithms (TWAP/VWAP)

```python
from trading_simulator import twap_schedule, vwap_schedule

# Split 10,000 shares into 20 equal clips over 30 minutes:
plan = twap_schedule(total_quantity=10_000, num_slices=20, duration_seconds=1800)

# Split proportionally to a historical intraday volume profile:
plan = vwap_schedule(total_quantity=10_000, volume_profile=[0.05, 0.08, ...], duration_seconds=1800)

for child in plan:
    # child.offset_seconds, child.quantity -- submit each child order through
    # the normal MatchingEngine at (algo_start_time + child.offset_seconds)
    ...
```

Intentionally simple slicing (fixed schedules, no adaptive participation
rate) so it's easy to audit and extend rather than a black box.

## 🔌 FIX Protocol Engine

This is a real FIX 4.2 order-entry engine with a session layer, not just a
message-format demo. `FixApplication` (the server) requires a proper Logon
before it will process any business message, answers Heartbeat/TestRequest/
ResendRequest/Logout correctly, tracks MsgSeqNum in both directions, detects
sequence gaps and replays real previously-sent messages (with PossDupFlag)
to recover from them, and turns order flow into real ExecutionReport (35=8)
and Reject (35=3) messages. `FixClient` is the matching client counterpart
-- it logs on, sends NewOrderSingle/OrderCancelRequest with correctly
sequenced headers, and collects ExecutionReports, so the engine has
something real to talk to end to end.

```python
from trading_simulator import FixApplication, FixClient
import threading

# Server side (run in live mode, or stand this up yourself):
fix_app = FixApplication(engine, sender_comp_id="SIMULATOR", target_comp_id="CLIENT",
                          heartbeat_interval=30)
threading.Thread(target=fix_app.start, kwargs={"host": "localhost", "port": 5005}, daemon=True).start()

# Client side:
client = FixClient(sender_comp_id="CLIENT", target_comp_id="SIMULATOR", heartbeat_interval=30)
client.connect("localhost", 5005, timeout=5.0)   # blocks until Logon is acknowledged
cl_ord_id = client.send_new_order(symbol="AAPL", side="buy", price=150.0, quantity=100)
report = client.wait_for_execution_report(timeout=5.0)   # -> dict of translated FIX fields
client.send_cancel(orig_cl_ord_id=cl_ord_id)
client.logout()
```

Or via the CLI in live mode: `--fix-host localhost --fix-port 5005
--fix-sender-comp-id SIMULATOR --fix-target-comp-id CLIENT
--fix-heartbeat-interval 30`, or through the guided CLI's "Start FIX
server?" prompt. The session-layer state machine that powers all of this
(`connectivity/fix_session.py`) is fully unit-tested with zero external
dependencies (`tests/test_fix_session.py`).

## 🖥️ Live Order Control (JSON over TCP)

Place, cancel, or modify orders while a live run is executing, from a second
terminal, without FIX:

```bash
python -m trading_simulator --mode live --symbol AAPL \
  --order-cli-enable --order-cli-host 127.0.0.1 --order-cli-port 8765 --order-cli-owner cli
```

The server logs the host:port it's actually listening on (use
`--order-cli-port 0` to let the OS assign a free port, then read the real
port from that log line). One JSON object per TCP connection; the server
responds with `{"ok": true/false, ...}`:

```json
{"action": "new", "symbol": "AAPL", "side": "buy", "type": "limit",
 "price": 150.25, "quantity": 100, "tif": "GTC", "owner_id": "cli"}
```
```json
{"action": "cancel", "order_id": "<returned id>"}
```
```json
{"action": "modify", "order_id": "<id>", "price": 150.4, "quantity": 50}
```

```bash
python - <<'PY'
import socket, json
order = {"action": "new", "symbol": "AAPL", "side": "buy", "type": "limit",
         "price": 150.25, "quantity": 100, "tif": "GTC", "owner_id": "cli"}
s = socket.create_connection(("127.0.0.1", 8765))
s.sendall(json.dumps(order).encode())
print(s.recv(4096).decode())
s.close()
PY
```

Orders submitted this way pass the same risk checks as any other order, and
their executions hit the same TCA/CSV logs. The live feed auto-falls-back to
a synthetic random walk if the real market data provider isn't
installed/reachable, so the whole loop keeps running offline.

## 📡 Event Streaming

```python
from trading_simulator import EventBus, make_redis_publisher, make_kafka_publisher

bus = EventBus()
bus.add_publisher(make_redis_publisher("redis://localhost:6379", "trading_events"))
bus.add_publisher(make_kafka_publisher("localhost:9092", "trading_events"))

engine.subscribe_trades(lambda execu: bus.publish("execution", {
    "symbol": execu.symbol, "price": execu.price, "quantity": execu.quantity,
}))
```

A publisher that raises is logged and skipped -- it never breaks the
trading loop or the other publishers.

## 🗄️ Database Persistence

```python
from trading_simulator import DbLogger

db_logger = DbLogger("postgresql://user:pass@localhost/trading_db")
db_logger.log_execution(execution)
db_logger.log_equity(timestamp, net_liq, realized, cash)
db_logger.save_config("strategy_config", {"momentum_lookback": 5, "ema_short_window": 5})
```

Use it directly in your own scripts alongside the engine to persist
executions, equity curves, and strategy configs to Postgres.

## 📊 Performance Analytics & TCA

Rolling metrics print during replay and at the end of backtest/live runs:
net liquidation, cash, realized PnL, annualized Sharpe/Sortino/volatility,
current/max drawdown, trade count. Computed from `equity_curve.csv`,
`executions.csv`, `tca.csv`, and `tca_adv.csv` in your `--log-dir`.

```python
import pandas as pd
from trading_simulator import compute_performance_metrics, export_html_report

equity_df = pd.read_csv(".logs/equity_curve.csv")
metrics = compute_performance_metrics(equity_df)
print(f"CAGR: {metrics['cagr']:.2%}  Sharpe: {metrics['sharpe']:.2f}  MaxDD: {metrics['max_drawdown']:.2%}")
export_html_report(equity_df, metrics, "report.html")

tca_df = pd.read_csv(".logs/tca.csv")
print(f"Avg mid slippage: {tca_df['slippage_mid_bps'].mean():.2f} bps")
```

```python
snapshot = portfolio.snapshot()
print(snapshot["cash"], snapshot["realized_pnl"], snapshot["positions"])
net_liq = portfolio.equity({"AAPL": 150.0}) + portfolio.realized_pnl
```

## ✅ Testing

```bash
pip install -r requirements-dev.txt
pip install -e .
pytest                                        # 109 tests
pytest --cov=trading_simulator --cov-report=term-missing
```

The suite covers the matching engine (price-time priority, self-trade
prevention, TIF/post-only, price bands, halts), order book, portfolio, risk
manager, strategies, market maker, order-book snapshots and event-log
replay, auctions, the multi-venue router (NBBO + sweep + fee-adjusted
routing), socket-level order-CLI behavior, the FIX session-layer state
machine, the EventBus and Redis/Kafka publisher guards, graceful-degradation
for every optional dependency, and the CLI end to end (guided and
flag-driven) using synthetic in-memory data. CI
(`.github/workflows/ci.yml`) runs the same suite on Python 3.10, 3.11, and
3.12.

## 🧰 Optional Dependencies

Only `numpy`, `pandas`, and `requests` are required for `--mode demo` and
the test suite. Everything else degrades gracefully: if a feature's
dependency isn't installed, using that feature raises one clear
`RuntimeError` with a `pip install` hint.

| Feature | Package(s) | Behavior if missing |
|---|---|---|
| Historical/live market data (backtest/live/replay) | `yahooquery`, `yfinance` | Clean `RuntimeError` naming both providers and suggesting `--mode demo` |
| FIX engine | `simplefix` | `FixApplication(...)`/`FixClient(...)` raise on construction |
| Sentiment trader | `tensorflow`, `newsapi-python` | `SentimentAnalysisTrader(...)` raises on construction |
| Database persistence | `SQLAlchemy` (+ `psycopg2-binary` for Postgres) | `DbLogger(...)` raises on construction |
| Redis streaming | `redis` | `make_redis_publisher(...)` raises when called |
| Kafka streaming | `confluent-kafka` | `make_kafka_publisher(...)` raises when called |
| Hyperparameter search | `optuna` | `--optuna-trials` logs a warning and the backtest still completes |
| Experiment tracking | `mlflow` | Silently skipped if `--mlflow-uri` is set without `mlflow` installed |

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup, test expectations,
and code-style notes. Bug reports on the matching engine are especially
useful with a minimal reproducing order sequence (see the style in
`tests/test_matching_engine.py`).

## 📄 License

This project is licensed under the MIT License © 2025 Devansh Garg -- see
the [LICENSE](LICENSE) file for details.

---

<div align="center">
  <p>Built for anyone curious about how markets actually work.</p>
  <p>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/stargazers">
      <img src="https://img.shields.io/github/stars/ThePredictiveDev/Automated-Financial-Market-Trading-System?style=social" alt="Stars">
    </a>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/network/members">
      <img src="https://img.shields.io/github/forks/ThePredictiveDev/Automated-Financial-Market-Trading-System?style=social" alt="Forks">
    </a>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/issues">
      <img src="https://img.shields.io/github/issues/ThePredictiveDev/Automated-Financial-Market-Trading-System" alt="Issues">
    </a>
  </p>
</div>
