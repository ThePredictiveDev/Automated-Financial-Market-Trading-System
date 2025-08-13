## Automated Financial Market Trading System
Comprehensive, production-ready Python 3.11+ trading simulator. It models a realistic microstructure with a limit order book, a top-of-book matching engine that supports partial fills, a TCP FIX server, live intraday market data from `yahooquery`, a market maker and synthetic liquidity provider, multiple algorithmic traders, portfolio and risk management, and robust CSV logging. Use the CLI in `trading_simulator_with_algorithmic_traders.py` for backtests and live simulations, explore the components interactively in `Trading Simulator in Python With Algorithmic Traders.ipynb`.

Audience guidance
- Notebook (`Trading Simulator in Python With Algorithmic Traders.ipynb`): best for new and intermediate users to learn concepts step-by-step with inline explanations.
- CLI (`trading_simulator_with_algorithmic_traders.py`): best for advanced/experienced users who want full control, automation, multi-asset backtests, FIX connectivity, and configurable microstructure.

### Table of contents
- Features and architecture
- Installation (minimal and full)
- End-to-end quick start
- Detailed CLI reference and examples
- Components
  - Order book and matching engine
  - FIX application (TCP server)
  - Market data feed (yahooquery)
  - Market maker and synthetic liquidity
  - Algorithmic traders (Momentum, EMA, Swing, Sentiment)
  - Portfolio tracking and Risk manager
  - CSV logging and analytics
- Data sources, caching, timezones
- Strategy registry
- Using FIX from a client (examples)
- Backtesting workflow
- Troubleshooting and operational notes
- Notebook guide: `Trading Simulator in Python With Algorithmic Traders.ipynb`
- Project structure
- License

## Features and architecture
- Order book with per-price FIFO queues, add/modify/cancel, and an `order_map` for O(1) lookup.
- Matching engine with thread-safe execution, partial fills, and trade event subscribers.
- FIX TCP server built on `simplefix` supporting NewOrderSingle (D) and OrderCancelRequest (F).
- Market data feed powered by `yahooquery` with retries, backoff, session caching, and optional rate limiting.
- Market maker with dynamic spread derived from recent price volatility; always-quoting behavior.
- Synthetic liquidity provider for stress testing liquidity and matching.
- Algorithmic traders: Momentum, EMA crossover, Swing (support/resistance), Sentiment (Keras + NewsAPI).
- Portfolio with cash, net positions, average prices, realized PnL, fees; event-driven updates on executions.
- Risk manager enforcing max order quantity, per-symbol exposure, and gross notional pre-trade.
- CSV logging of executions and equity curve for downstream analysis.

## Installation
Python 3.11+ is required. We recommend a virtual environment.

### Minimal setup (core simulator)
```bash
pip install --upgrade pip
pip install yahooquery simplefix pandas numpy
```

### Full setup (enables sentiment, caching, parquet, and smoother live usage)
```bash
pip install --upgrade pip
pip install \
  yahooquery simplefix pandas numpy \
  tensorflow==2.15.1 newsapi-python \
  requests-cache requests-ratelimiter pyrate-limiter \
  pyarrow
```

Notes
- TensorFlow 2.15.1 supports Python 3.11 (CPU). For GPU installs, follow TensorFlow’s official docs.
- `pyarrow` enables faster on-disk caching via Parquet; if missing, the system will fall back to CSV.
- If `requests-cache` and rate limiter are not installed, the system will gracefully fall back to a standard `requests.Session`.

## End-to-end quick start
Run all commands from the project root.

### Backtest
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders --initial-cash 1000000 --fee-bps 0 --log-dir .logs
```
Outputs
- Executions: `.logs/executions.csv`
- Equity curve: `.logs/equity_curve.csv`

### Live
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --md-interval 60 --enable-traders \
  --fix-host localhost --fix-port 5005 \
  --sentiment-model-path sentiment_classifier_model.keras \
  --news-api-key YOUR_NEWSAPI_KEY
```
Stop with Ctrl+C. Shutdown is graceful: live threads are stopped and a final equity snapshot is logged if the last price is known.

### Demo (simple order-book controls)
```bash
python trading_simulator_with_algorithmic_traders.py --mode demo
```

### Optional liquidity injection (live)
```bash
python trading_simulator_with_algorithmic_traders.py --mode live --symbol AAPL --inject-liquidity 5
```

### Multi-asset backtest (single portfolio across symbols)
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbols AAPL,MSFT,GOOG --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders --initial-cash 1000000 --log-dir .logs
```

## Detailed CLI reference
Script: `trading_simulator_with_algorithmic_traders.py`

- **--mode**: `backtest` | `live` | `demo` (default: `backtest`).
- **--symbol**: Ticker symbol (default: `AAPL`).
- **--symbols**: Comma-separated symbols for multi-asset backtest (e.g., `AAPL,MSFT`).
- Backtest only: **--start-date**, **--end-date** (YYYY-MM-DD), **--enable-traders** to include built-in algos during backtest.
- Live data: **--md-interval** in seconds for the yahooquery feed.
- FIX: **--fix-host**, **--fix-port** to bind the server.
- Sentiment: **--sentiment-model-path**, **--news-api-key**, **--sentiment-vocab-path** (TextVectorization vocab file).
- Portfolio/fees: **--initial-cash**, **--fee-bps** (basis points).
- Risk: **--risk-max-order-qty**, **--risk-max-symbol-position**, **--risk-max-gross-notional**.
- Logging: **--log-dir** (folder for CSV outputs).
- Reproducibility: **--seed** to seed Python, NumPy, and TensorFlow RNGs when available.
- Microstructure (backtests): **--slippage-bps-per-100**, **--latency-ms**.
- Reporting: **--export-report**, **--report-out**.
- Parameter search: **--optuna-trials**, **--mlflow-uri**, **--mlflow-experiment**.

### CLI commands cookbook (copy-paste examples)

Basic single-asset backtest
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31
```

Backtest with built-in traders (Momentum, EMA, Swing)
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders
```

Backtest with microstructure and risk controls
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders \
  --slippage-bps-per-100 2.5 --latency-ms 100 \
  --risk-max-order-qty 500 --risk-max-symbol-position 5000 \
  --risk-max-gross-notional 2000000
```

Backtest with fees, custom cash, and CSV output directory
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --initial-cash 2000000 --fee-bps 1.0 --log-dir runs/aapl_2023
```

Export HTML performance report after backtest
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --export-report --report-out report_aapl_2023.html
```

Multi-asset backtest (shared portfolio across symbols)
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbols AAPL,MSFT,GOOG --start-date 2023-01-01 --end-date 2023-12-31 \
  --enable-traders --log-dir runs/multi
```

Parameter search with Optuna (and MLflow logging)
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --optuna-trials 25 --mlflow-uri http://localhost:5000 \
  --mlflow-experiment trading-simulator
```

Live mode (streaming market data)
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --md-interval 60
```

Live mode with built-in traders
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --md-interval 30 --enable-traders
```

Live mode with FIX server enabled
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --enable-traders \
  --fix-host 0.0.0.0 --fix-port 5005
```

Live mode with sentiment trader
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --enable-traders \
  --news-api-key YOUR_NEWSAPI_KEY \
  --sentiment-model-path sentiment_classifier_model.keras \
  --sentiment-vocab-path vocab.txt
```

Live mode with periodic synthetic liquidity injection
```bash
python trading_simulator_with_algorithmic_traders.py --mode live \
  --symbol AAPL --enable-traders --inject-liquidity 5
```

Demo mode (simple order-book controls)
```bash
python trading_simulator_with_algorithmic_traders.py --mode demo
```

Reproducible runs (seeding RNGs)
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --seed 12345
```

Customize CSV output directory
```bash
python trading_simulator_with_algorithmic_traders.py --mode backtest \
  --symbol AAPL --start-date 2023-01-01 --end-date 2023-12-31 \
  --log-dir .logs/aapl_2023
```

Notes
- Combine flags as needed; unspecified flags use sensible defaults.
- All timestamps in logs are UTC.

## Components

### Order book and matching engine
- `OrderBook`: maintains `bids` and `asks` as price→`deque[Order]`, and an `order_map` of id→Order.
- Methods: `add_order`, `remove_order`, `cancel_order`, `modify_order`, `get_best_bid`, `get_best_ask`, `display_order_book`, and utilities to export as DataFrames.
- `MatchingEngine`: thread-safe `match_order` routes to `_match_buy_order` or `_match_sell_order`; `_execute_order` performs partial fills, updates queues, removes empty price levels, and emits `Execution` events to subscribers.

Advanced execution controls
- Time-in-force (TIF): supports `GTC` (default), `IOC`, and `FOK`. `IOC` and `FOK` will not rest residuals on the book.
- Post-only: when enabled on a limit order, it will not cross the spread; if it would, the order is discarded instead of taking liquidity.
- Lot/precision normalization: prices snap to instrument tick size and quantities to lot size where configured.
- Price band protection: limit orders deviating beyond a configured number of basis points from reference price (mid or last) are rejected to avoid fat-finger prints.
- Auction mode: the engine can be switched to `open`/`close` auction collection with a single-price uncross. During auctions, orders can be marked `auction_only`.
- Session checks: orders can be rejected when the local market session is closed (based on instrument trading hours and holidays).

### FIX application (TCP server)
- Parses bytes into FIX messages using `simplefix`, translates tags to human-readable fields, and handles:
  - NewOrderSingle (D) → creates a `limit` order.
  - OrderCancelRequest (F) → cancels the referenced order if present.
- Basic ACK is returned per message; integrate your own client or use the example below.

### Market data feed (yahooquery)
- Fetches 1-minute intraday data with retries, backoff, and optional on-disk cache.
- Normalizes timestamps to UTC and column names to canonical case (`Close`, `Volume`).
- Broadcasts updates to subscribers (market maker, traders, etc.).
- Historical downloads for backtests are cached to `.cache/` (Parquet if available, else CSV) and reused across runs.

### Market maker and synthetic liquidity
- Market maker keeps a recent price window to compute a volatility-based dynamic spread and quotes around the mid.
- Synthetic liquidity provider periodically adds buy/sell orders at the latest price; useful to increase book activity during testing.

### Algorithmic traders
- `MomentumTrader`: trades in the direction of recent price change over a short lookback.
- `EMABasedTrader`: short vs. long EMA crossover signals.
- `SwingTrader`: buys near support and sells near resistance.
- `SentimentAnalysisTrader` (optional): fetches headlines via NewsAPI and infers buy/hold/sell using a Keras model.
Notes
- If the loaded sentiment model expects raw strings, it will be used directly. If it expects tokenized inputs and no vocabulary is provided via `--sentiment-vocab-path`, the trader will auto-disable to avoid garbage predictions.

### Portfolio tracking and Risk manager
- `Portfolio` updates on every `Execution` with fees (bps), average price tracking, and realized PnL on reductions/flips.
- `RiskManager` runs pre-trade checks: order qty bounds, per-symbol exposure, and gross notional versus thresholds.

Owner-aware PnL, fees, and rebates
- Executions track both maker and taker ownership. The portfolio applies taker fees (bps) when it is the taker, and maker rebates (bps) when it is the maker.
- Average cost and realized PnL are updated on increases and reductions/flip events; cash reflects fees/rebates.

Market hours and instrument configuration
- You can define per-symbol trading hours, timezones, tick sizes, lot sizes, and decimal precision. Orders outside hours can be rejected and prices/quantities normalized.
- Example configuration snippet:
```python
from trading_simulator_with_algorithmic_traders import INSTRUMENTS, TICK_SIZE, LOT_SIZE, DECIMAL_PRECISION

INSTRUMENTS['AAPL'] = {
  'tz': 'America/New_York',
  'open': '09:30', 'close': '16:00',
  'holidays': ['2023-12-25']
}
TICK_SIZE['AAPL'] = 0.01
LOT_SIZE['AAPL'] = 1
DECIMAL_PRECISION['AAPL'] = 2
```
Note: these are advanced, code-level settings; not all are exposed as CLI flags.

### CSV logging and analytics
- `executions.csv`: timestamp, symbol, price, quantity, side, taker_order_id, maker_order_id, trade_id.
- `equity_curve.csv`: timestamp, net_liquidation, realized_pnl, cash.
- Use these files to build analytics/visualizations in pandas or BI tools.

## Data sources, caching, timezones
- Live data via yahooquery with a shared `requests` session. If present, `requests-cache` stores responses on disk and rate limiting reduces throttling.
- Historical backtests also use yahooquery and persist normalized frames to `.cache/` in Parquet (if `pyarrow`) or CSV.
- Time is handled as UTC; if inputs are naive, they are localized to UTC.

## Strategy registry
Built-in strategies are discoverable at runtime and include parameter hints:
- `MomentumTrader` (params: `lookback`, `interval`)
- `EMABasedTrader` (params: `short_window`, `long_window`, `interval`)
- `SwingTrader` (params: `support_level`, `resistance_level`, `interval`)
- `CustomTrader` (params: `threshold`, `interval`)
- `SentimentAnalysisTrader` (params: `model_file`, `news_api_key`, `vocab_path`, `interval`)

## Using FIX from a client (examples)
Start the server first (live mode). Then, in a separate Python session, send a NewOrderSingle:
```python
import socket, simplefix

def new_order_msg():
    msg = simplefix.FixMessage()
    msg.append_pair(8, b'FIX.4.2')           # BeginString
    msg.append_pair(35, b'D')                # MsgType = NewOrderSingle
    msg.append_pair(11, b'order-123')        # ClOrdID
    msg.append_pair(54, b'1')                # Side (1=Buy, 2=Sell)
    msg.append_pair(55, b'AAPL')             # Symbol
    msg.append_pair(44, b'190.25')           # Price
    msg.append_pair(38, b'100')              # OrderQty
    msg.append_pair(10, b'000')              # Checksum placeholder
    return msg

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.connect(("localhost", 5005))
    s.sendall(new_order_msg().encode())
    print(s.recv(1024))
```
To cancel an order, send an OrderCancelRequest (F) with `OrigClOrdID` set to the original `ClOrdID`.

## Backtesting workflow
1) Download and cache historical data via yahooquery with retries.
2) Iterate row-by-row, building market data updates and invoking the market maker and traders.
3) Record executions and mark-to-market equity curve; final snapshot printed at end.

Tips
- Use `--enable-traders` to include algos in backtests.
- Adjust risk parameters to prevent unrealistic exposures.
- Set `--seed` for reproducibility (NumPy/TF seeds set when available).
- Tune **--slippage-bps-per-100** and **--latency-ms** to study microstructure impacts on fill quality and PnL.

## Troubleshooting and operational notes
- Yahoo data rate limits: the code uses exponential backoff and optional caching/rate limiting. If throttled, wait a few minutes or lower frequency.
- Sentiment trader disabled: if the Keras model expects preprocessed inputs and no vocabulary is provided, the trader auto-disables to avoid garbage predictions.
- FIX connectivity: ensure firewalls allow TCP on the configured port; the server binds to `--fix-host`/`--fix-port`.
- Windows PowerShell: prefix long commands with backticks for line continuation, or put arguments on one line.
- CSV files locked on Windows: close Excel or other viewers before running; the app appends to CSVs during execution.
 - Auction mode and price bands: these are advanced features intended for programmatic use. If you see unexpected rejections, confirm price band settings and session hours.

## Notebook guide: Trading Simulator in Python With Algorithmic Traders.ipynb
The notebook provides an interactive walkthrough of the system’s components. It mirrors the core concepts but trades off some robustness for readability:
- Sections cover the OrderBook, MatchingEngine, a simple FIX app, MarketDataFeed, MarketMaker, SyntheticLiquidityProvider, and the algorithmic traders.
- You can run cells individually to observe behavior and tweak parameters inline.
- A backtesting section demonstrates historical playback.

How to run
- Open the notebook in Jupyter or VS Code.
- Run all cells sequentially. Some cells create threads; stop them at the end via the provided stop cells.
- Install minimal dependencies first: `pip install yahooquery simplefix pandas numpy` (add `tensorflow newsapi-python` for sentiment).
- If you hit rate limits, re-run after a short backoff; consider adding `requests-cache` and a rate limiter.

## Project structure
- `trading_simulator_with_algorithmic_traders.py`: main CLI with all components wired together.
- `Trading Simulator in Python With Algorithmic Traders.ipynb`: interactive notebook walkthrough.
- `sentiment_classifier_model.keras`: optional Keras sentiment model file used by the sentiment trader.
- `.cache/`: on-disk cache (market data history, response cache).
- `.logs/`: CSV logs (`executions.csv`, `equity_curve.csv`) created at runtime.

## License
MIT
