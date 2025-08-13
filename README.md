# 🤖 Automated Financial Market Trading System

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Production%20Ready-brightgreen.svg)](https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System)
[![Contributions](https://img.shields.io/badge/Contributions-Welcome-orange.svg)](CONTRIBUTING.md)
[![Issues](https://img.shields.io/badge/Issues-Open-red.svg)](https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/issues)

> **A comprehensive, production-ready algorithmic trading system with real-time market data, multiple trading strategies, risk management, and advanced backtesting capabilities.**

<div align="center">
  <img src="https://capsule-render.vercel.app/api?text=Automated%20Trading%20System&animation=fadeIn&type=waving&color=gradient&height=100"/>
</div>

## 📋 Table of Contents

- [🚀 Features](#-features)
- [🎯 What You Can Do](#-what-you-can-do)
- [🏗️ Architecture](#️-architecture)
- [📦 Installation](#-installation)
- [⚡ Quick Start](#-quick-start)
- [🔧 Usage Modes](#-usage-modes)
- [🧭 Interactive CLI (No-Flags Guided Mode)](#-interactive-cli-no-flags-guided-mode)
- [📊 Trading Strategies](#-trading-strategies)
- [🛡️ Risk Management](#️-risk-management)
- [📈 Backtesting](#-backtesting)
- [🔌 API Integration](#-api-integration)
- [📝 Configuration](#-configuration)
- [📊 Performance Analytics](#-performance-analytics)
- [🖥️ Live Order Control (Split Terminal)](#️-live-order-control-split-terminal)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

## 🚀 Features

### Core Trading Engine
- **🔧 High-Performance Matching Engine**: Real-time order matching with price-time priority
- **📊 Order Book Management**: Full limit order book with bid/ask depth tracking
- **⚡ Low-Latency Execution**: Sub-millisecond order processing with configurable latency simulation
- **🔄 FIX Protocol Support**: Industry-standard FIX 4.2 protocol integration via simplefix
- **📈 Real-time Market Data**: Live price feeds via yfinance with automatic fallback mechanisms

### Algorithmic Trading Strategies
- **📈 Momentum Trading**: Price momentum-based strategy with configurable lookback periods
- **📊 EMA Crossover**: Exponential Moving Average crossover strategy with customizable windows
- **🔄 Swing Trading**: Support/resistance level-based trading with dynamic level adjustment
- **🧠 Sentiment Analysis**: AI-powered news sentiment trading using TensorFlow/Keras models
- **🎯 Custom Strategies**: Framework for implementing custom trading algorithms

### Market Making & Liquidity
- **🏪 Avellaneda-Stoikov Market Maker**: Advanced market making with inventory management
- **💰 Multi-Level Quoting**: Configurable quote laddering with size decay
- **📊 Dynamic Spread Adjustment**: Volatility-based spread widening and momentum skewing
- **🛡️ Drawdown Protection**: Automatic quote withdrawal on excessive losses
- **🔄 Synthetic Liquidity**: Automated liquidity injection for testing scenarios

### Risk Management System
- **📏 Position Limits**: Per-symbol and portfolio-level position constraints
- **💰 Notional Limits**: Maximum order and portfolio notional value controls
- **⚡ Rate Limiting**: Configurable order submission rate limits per strategy
- **📉 Drawdown Protection**: Automatic trading halt on portfolio drawdown thresholds
- **🔒 Volatility Halts**: Market volatility-based trading suspension
- **🎯 Leverage Controls**: Maximum leverage and gross exposure limits

### Advanced Backtesting
- **📊 Historical Data**: Yahoo Finance integration with intelligent caching
- **⚡ High-Speed Simulation**: Optimized backtesting engine with configurable slippage
- **📈 Performance Analytics**: Comprehensive performance metrics and reporting
- **🔄 Multi-Asset Testing**: Simultaneous testing across multiple symbols
- **📊 Parameter Optimization**: Optuna integration for strategy parameter tuning
- **📈 MLflow Integration**: Experiment tracking and model versioning

### Data & Analytics
- **📊 Real-time Portfolio Tracking**: Live P&L, positions, and equity curve monitoring
- **📈 Trade Cost Analysis (TCA)**: Slippage analysis and adverse selection tracking
- **📊 Execution Analytics**: Detailed execution quality and market impact analysis
- **📈 Performance Metrics**: Sharpe ratio, Sortino ratio, max drawdown, CAGR
- **📊 HTML Reports**: Automated performance report generation with interactive charts
- **📈 CSV Logging**: Comprehensive trade and equity data export

### Infrastructure & Integration
- **🗄️ Database Support**: PostgreSQL integration for persistent data storage
- **📡 Event Streaming**: Redis and Kafka integration for real-time event distribution
- **🔧 Configuration Management**: Flexible configuration system with environment variables
- **📊 Monitoring**: Comprehensive logging and audit trails
- **🔄 Snapshot Management**: Order book state persistence and recovery
- **🎯 Auction Support**: Opening/closing auction mechanisms

## 🎯 What You Can Do

### For Traders & Investors
- **📈 Test Trading Strategies**: Backtest your strategies on historical data with realistic market conditions
- **🔄 Paper Trading**: Practice trading with virtual money in real-time market conditions
- **📊 Portfolio Analysis**: Analyze your trading performance with professional-grade metrics
- **🎯 Strategy Development**: Develop and optimize custom trading algorithms
- **📈 Market Research**: Study market microstructure and order book dynamics

### For Developers & Researchers
- **🔬 Market Microstructure Research**: Study order book dynamics and market impact
- **📊 Algorithm Development**: Build and test new trading algorithms
- **🔧 System Integration**: Integrate with existing trading infrastructure via FIX protocol
- **📈 Performance Testing**: Benchmark trading strategies and execution algorithms
- **🎯 Machine Learning**: Develop ML-based trading strategies with sentiment analysis

### For Institutions
- **🏢 Risk Management**: Implement comprehensive risk controls and monitoring
- **📊 Compliance**: Maintain detailed audit trails and trade records
- **🔧 Infrastructure**: Build scalable trading infrastructure with real-time capabilities
- **📈 Analytics**: Generate institutional-grade performance and risk analytics
- **🔄 Integration**: Connect with existing trading systems and data feeds

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Trading System Architecture                   │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Market Data │  │   FIX API   │  │   Web UI    │             │
│  │    Feed     │  │   Client    │  │  (Future)   │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          │                                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Trading Engine Core                      │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │   Order     │  │ Matching    │  │   Risk      │         │ │
│  │  │   Book      │  │  Engine     │  │ Management  │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                          │                                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  Algorithmic Traders                        │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ Momentum    │  │    EMA      │  │   Swing     │         │ │
│  │  │  Trader     │  │   Trader    │  │   Trader    │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ Sentiment   │  │   Market    │  │   Custom    │         │ │
│  │  │  Trader     │  │   Maker     │  │   Trader    │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                          │                                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Data & Analytics                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ Portfolio   │  │   Trade     │  │ Performance │         │ │
│  │  │  Tracker    │  │   Logger    │  │  Analytics  │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                          │                                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                  Storage & Integration                      │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │ │
│  │  │ PostgreSQL  │  │    Redis    │  │    Kafka    │         │ │
│  │  │   Database  │  │   Cache     │  │   Events    │         │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 Installation

### Prerequisites

- **Python 3.11+** (Required for modern type hints and performance features)
- **Git** (For cloning the repository)
- **pip** (Python package manager)

### Basic Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Automated-Financial-Market-Trading-System.git
cd Automated-Financial-Market-Trading-System

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install core dependencies
pip install -r requirements.txt
```

### Full Installation (all features)

```bash
# Install all features (core + optional integrations)
pip install -r requirements.txt
```

### Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit environment variables
nano .env
```

**Key Environment Variables (placeholders):**
```bash
# API Keys (Optional)
NEWS_API_KEY=your_news_api_key_here
YAHOO_FINANCE_API_KEY=your_yahoo_key_here

# Database Configuration
DATABASE_URL=postgresql://user:pass@localhost/trading_db
REDIS_URL=redis://localhost:6379
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Trading Configuration
DEFAULT_INITIAL_CASH=1000000
DEFAULT_FEE_BPS=1.0
DEFAULT_MAKER_REBATE_BPS=0.5

# Risk Management
MAX_ORDER_QTY=1000
MAX_SYMBOL_POSITION=10000
MAX_GROSS_NOTIONAL=5000000
```

## ⚡ Quick Start

### 1. Simple Backtest

```bash
# Run a basic backtest on AAPL
python trading_simulator_with_algorithmic_traders.py \
  --mode backtest \
  --symbol AAPL \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --enable-traders \
  --export-report
```

### 2. Live Trading Simulation

```bash
# Start live trading simulation with market maker
python trading_simulator_with_algorithmic_traders.py \
  --mode live \
  --symbol AAPL \
  --md-interval 30 \
  --enable-traders
```

### 3. Interactive Demo

```bash
# Run interactive demo mode
python trading_simulator_with_algorithmic_traders.py --mode demo
```

## 🔧 Usage Modes

### Backtest Mode
Run historical simulations with configurable parameters:

```bash
python trading_simulator_with_algorithmic_traders.py \
  --mode backtest \
  --symbol AAPL \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --enable-traders \
  --initial-cash 1000000 \
  --fee-bps 1.0 \
  --slippage-bps-per-100 0.5 \
  --latency-ms 10 \
  --export-report \
  --report-out performance_report.html
```

**Multi-Asset Backtest:**
```bash
python trading_simulator_with_algorithmic_traders.py \
  --mode backtest \
  --symbols "AAPL,MSFT,GOOGL,TSLA" \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --enable-traders
```

### Live Mode
Real-time trading simulation with live market data:

```bash
python trading_simulator_with_algorithmic_traders.py \
  --mode live \
  --symbol AAPL \
  --md-interval 30 \
  --enable-traders \
  --fix-host localhost \
  --fix-port 5005 \
  --inject-liquidity 60
```

### Replay Mode
Historical data replay at configurable speed:

```bash
python trading_simulator_with_algorithmic_traders.py \
  --mode replay \
  --symbol AAPL \
  --start-date 2023-01-01 \
  --end-date 2023-12-31 \
  --replay-speed 5.0 \
  --enable-traders
```

### Demo Mode
Interactive order book demonstration:

```bash
python trading_simulator_with_algorithmic_traders.py --mode demo
```

## 🧭 Interactive CLI (No-Flags Guided Mode)

Prefer prompts over flags? Just run without arguments:

```bash
python trading_simulator_with_algorithmic_traders.py
```

### What you can configure interactively
- Mode: Backtest, Live, Replay, Demo (and an Advanced mode for manual flag entry)
- Symbols and date ranges (Backtest/Replay)
- Market data interval (Live) and replay pacing (Replay)
- Built-in trader parameters (Momentum/EMA/Swing)
- Market microstructure: slippage, latency
- Matching protections: price band (bps), reference (mid/last), taker fee, maker rebate
- Engine: submission queue on/off + queue size, order-book snapshots (interval + dir)
- Risk manager: min/round lots, max qty/position/notional, order rate limit, drawdown limit, volatility halt, leverage, per-symbol gross exposure
- Custom traders: add any number of `module:ClassName` with JSON params
- Reporting & experiments: export HTML report, Optuna trials, MLflow tracking

Each prompt includes short tips to help you choose sensible values.

### Custom traders via prompts
- When asked “Add custom traders?” choose Yes and enter:
  - Trader spec: `yourpkg.strats:MyTrader`
  - JSON params: `{"lookback": 20, "interval": 0.0, "owner_id": "mytrader"}`
- Repeat to add multiple strategies. The system dynamically imports, instantiates, and wires them into the live/backtest pipeline.

### Optuna, MLflow, and TCA
- Optuna: enable and set trials; optionally configure MLflow URI and experiment name for tracking
- TCA: enabled automatically; slippage/adverse selection written to `tca.csv` and `tca_adv.csv`


## 📊 Trading Strategies

### 1. Momentum Trader
Trades based on short-term price momentum:

```python
from trading_simulator import MomentumTrader

trader = MomentumTrader(
    symbol="AAPL",
    matching_engine=engine,
    lookback=5,  # Lookback period for momentum calculation
    interval=0.1  # Trading interval in seconds
)
```

**Strategy Logic:**
- Calculates price change over lookback period
- Buys on positive momentum (price increase)
- Sells on negative momentum (price decrease)
- Aggressively crosses the book at best bid/ask

### 2. EMA-Based Trader
Uses Exponential Moving Average crossover signals:

```python
from trading_simulator import EMABasedTrader

trader = EMABasedTrader(
    symbol="AAPL",
    matching_engine=engine,
    short_window=5,    # Short EMA period
    long_window=20,    # Long EMA period
    interval=0.1
)
```

**Strategy Logic:**
- Calculates short and long EMAs
- Generates buy signal when short EMA > long EMA
- Generates sell signal when short EMA < long EMA
- Implements trend-following approach

### 3. Swing Trader
Trades based on support and resistance levels:

```python
from trading_simulator import SwingTrader

trader = SwingTrader(
    symbol="AAPL",
    matching_engine=engine,
    support_level=100.0,     # Support price level
    resistance_level=200.0,  # Resistance price level
    interval=0.1
)
```

**Strategy Logic:**
- Buys when price approaches support level
- Sells when price approaches resistance level
- Implements mean-reversion approach
- Configurable support/resistance levels

### 4. Sentiment Analysis Trader
AI-powered trading based on news sentiment:

```python
from trading_simulator import SentimentAnalysisTrader

trader = SentimentAnalysisTrader(
    symbol="AAPL",
    matching_engine=engine,
    model_file="sentiment_classifier_model.keras",
    news_api_key="your_api_key",
    interval=60.0  # Check news every 60 seconds
)
```

**Strategy Logic:**
- Fetches latest news via NewsAPI
- Analyzes sentiment using TensorFlow model
- Buys on positive sentiment
- Sells on negative sentiment
- Holds on neutral sentiment

### 5. Market Maker
Advanced market making with inventory management:

```python
from trading_simulator import MarketMaker

maker = MarketMaker(
    symbol="AAPL",
    matching_engine=engine,
    gamma=0.1,              # Risk aversion parameter
    k=1.5,                  # Order book intensity
    horizon_seconds=60.0,   # Quote horizon
    max_inventory=1000,     # Maximum inventory
    base_order_size=100,    # Base quote size
    min_spread=0.01,        # Minimum spread
    num_levels=2,           # Quote levels
    level_spacing_bps=2.0,  # Level spacing in basis points
    size_decay=0.7,         # Size decay factor
    momentum_window=10,     # Momentum calculation window
    alpha_skew=0.5,         # Momentum skew weight
    vol_widen_z=2.0,        # Volatility widening threshold
    drawdown_limit=0.2      # Drawdown protection limit
)
```

**Strategy Logic:**
- Implements Avellaneda-Stoikov market making model
- Adjusts quotes based on inventory position
- Widens spreads during high volatility
- Skews quotes based on price momentum
- Automatically withdraws quotes on drawdown

### 6. Custom Trader
Framework for implementing custom strategies:

```python
from trading_simulator import AlgorithmicTrader

class MyCustomTrader(AlgorithmicTrader):
    def __init__(self, symbol, matching_engine, threshold=0.0):
        super().__init__(symbol, matching_engine, interval=0.1)
        self.threshold = threshold
    
    def trade(self):
        if self.current_price is None:
            return
        
        # Your custom trading logic here
        if self.current_price < self.threshold:
            order = Order(
                id=uuid.uuid4().hex,
                price=self.current_price,
                quantity=10,
                side='buy',
                type='market',
                symbol=self.symbol,
                owner_id='custom'
            )
            self.matching_engine.match_order(order)
```

## 🛡️ Risk Management
### Configure All Risk Controls Interactively
Run the script with no flags and choose to customize risk when prompted. You can set:
- Position/Notional Limits: max order qty, max net position per symbol, max gross notional per order
- Lot Rules: min order qty, lot size, round-lot required
- Rate Limiting: per-owner order rate limit (orders/sec)
- Drawdown Protection: per-owner drawdown limit (fraction)
- Volatility Halts: window length and |z| threshold
- Leverage & Exposure: max leverage and per-symbol gross exposure

All values are validated and applied immediately to the pre-trade risk checks.


### Position Limits
```python
risk_manager = RiskManager(
    portfolio=portfolio,
    max_order_qty=1000,           # Maximum order quantity
    max_symbol_position=10000,    # Maximum position per symbol
    max_gross_notional=5000000,   # Maximum order notional
    min_order_qty=1,              # Minimum order quantity
    lot_size=1,                   # Lot size requirement
    round_lot_required=False      # Round lot requirement
)
```

#### Example Custom Traders (Ready to Use)

Create a module like `examples/strats.py` with:

```python
from collections import deque
import uuid
from trading_simulator_with_algorithmic_traders import AlgorithmicTrader, Order

class BreakoutTrader(AlgorithmicTrader):
    def __init__(self, symbol, matching_engine, lookback=20, band_bps=5, interval=0.0, owner_id='breakout'):
        super().__init__(symbol, matching_engine, interval)
        self.lookback = int(lookback)
        self.band_bps = float(band_bps)
        self.owner_id = str(owner_id)
        self.buf = deque(maxlen=max(3, self.lookback))

    def on_market_data(self, data):
        super().on_market_data(data)
        self.buf.append(float(data['price']))

    def trade(self):
        if self.current_price is None or len(self.buf) < self.lookback:
            return
        hi = max(self.buf)
        lo = min(self.buf)
        band = self.current_price * (self.band_bps / 10000.0)
        ob = self.matching_engine.order_book
        best_ask = ob.get_best_ask()
        best_bid = ob.get_best_bid()
        if best_ask is None or best_bid is None:
            return
        if self.current_price > hi + band:
            o = Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=100, side='buy', type='limit', symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(o)
        elif self.current_price < lo - band:
            o = Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=100, side='sell', type='limit', symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(o)

class MeanRevTrader(AlgorithmicTrader):
    def __init__(self, symbol, matching_engine, lookback=20, z_entry=1.0, interval=0.0, owner_id='meanrev'):
        super().__init__(symbol, matching_engine, interval)
        self.lookback = int(lookback)
        self.z_entry = float(z_entry)
        self.owner_id = str(owner_id)
        self.buf = deque(maxlen=max(3, self.lookback))

    def on_market_data(self, data):
        super().on_market_data(data)
        self.buf.append(float(data['price']))

    def trade(self):
        import numpy as np
        if self.current_price is None or len(self.buf) < self.lookback:
            return
        arr = np.array(self.buf, dtype=float)
        sma = float(arr.mean())
        std = float(arr.std(ddof=0))
        if std <= 0:
            return
        z = (self.current_price - sma) / std
        ob = self.matching_engine.order_book
        best_ask = ob.get_best_ask()
        best_bid = ob.get_best_bid()
        if best_ask is None or best_bid is None:
            return
        if z <= -self.z_entry:
            o = Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=100, side='buy', type='limit', symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(o)
        elif z >= self.z_entry:
            o = Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=100, side='sell', type='limit', symbol=self.symbol, owner_id=self.owner_id)
            self.matching_engine.match_order(o)
```

Add them interactively when prompted by specifying `examples.strats:BreakoutTrader` or `examples.strats:MeanRevTrader` and providing JSON parameters.

### Building Custom Traders (Detailed)

Custom traders must subclass `AlgorithmicTrader` and implement `trade()` (optional `on_market_data`). Constructor signature should be:

```python
def __init__(self, symbol: str, matching_engine: MatchingEngine, **params):
    super().__init__(symbol, matching_engine, interval=params.get('interval', 0.0))
```

They submit orders through `matching_engine.match_order(Order(...))`. Use `owner_id` to segment PnL and risk by strategy.

#### Integration Pipeline
- Market data tick → your trader’s `on_market_data` → your `trade()` → create `Order` → risk checks → matching → `executions.csv`/TCA → owner-aware Portfolio → `equity_curve.csv`
- The system tracks adverse selection and slippage automatically.

#### Adding Custom Traders Interactively
1. Run `python trading_simulator_with_algorithmic_traders.py` with no flags
2. Choose a mode (Backtest/Replay/Live)
3. When prompted “Add custom traders?”
   - Enter `module.path:ClassName`
   - Provide JSON params, e.g. `{ "lookback": 20, "interval": 0.0, "owner_id": "mytrader" }`
4. Repeat to add more; leave blank to continue.

Example (Backtest):
- Add `mypkg.strats:BreakoutTrader` with `{ "lookback": 15, "band_bps": 8, "owner_id": "bo15" }`
- Add `mypkg.strats:MeanRevTrader` with `{ "lookback": 30, "z_entry": 1.25, "owner_id": "mr30" }`

#### Best Practices
- Cross at best bid/ask for immediate fills when you want action; use resting orders deliberately
- Use small `interval` or `0.0` in backtests for per-bar evaluation
- Set a unique `owner_id` per strategy for clean PnL/risk isolation
- Keep code non-blocking; do not sleep inside `trade()`


### Rate Limiting
```python
risk_manager = RiskManager(
    # ... other parameters ...
    order_rate_limit_per_sec=10,  # Max orders per second per owner
    owner_drawdown_limit=0.2,     # 20% drawdown limit
    max_leverage=3.0,             # Maximum leverage
    max_symbol_gross_exposure=1000000  # Max gross exposure per symbol
)
```

### Volatility Protection
```python
risk_manager = RiskManager(
    # ... other parameters ...
    volatility_window=20,         # Volatility calculation window
    volatility_halt_z=3.0         # Z-score threshold for volatility halt
)
```

### Kill Switches
```python
# Disable specific traders
risk_manager.disable_owner("momentum_trader")

# Disable specific symbols
risk_manager.disable_symbol("TSLA")

# Re-enable when conditions improve
risk_manager.enable_owner("momentum_trader")
risk_manager.enable_symbol("TSLA")
```

## 📈 Backtesting

### Basic Backtest
```python
from trading_simulator import run_backtest, load_historical_data

# Load historical data
data = load_historical_data("AAPL", "2023-01-01", "2023-12-31")

# Create components
order_book = OrderBook()
engine = MatchingEngine(order_book)
portfolio = Portfolio(initial_cash=1000000)
market_maker = MarketMaker(symbol="AAPL", matching_engine=engine)

# Create traders
traders = [
    MomentumTrader(symbol="AAPL", matching_engine=engine, lookback=5),
    EMABasedTrader(symbol="AAPL", matching_engine=engine, short_window=5, long_window=20),
    SwingTrader(symbol="AAPL", matching_engine=engine, support_level=100, resistance_level=200)
]

# Run backtest
run_backtest(data, market_maker, engine, traders=traders, portfolio=portfolio)
```

### Multi-Asset Backtest
```python
from trading_simulator import run_multi_backtest, load_multi_historical_data

# Load data for multiple symbols
data_map = load_multi_historical_data(
    ["AAPL", "MSFT", "GOOGL"], 
    "2023-01-01", 
    "2023-12-31"
)

# Create engines and market makers for each symbol
engines = {}
makers = {}
for symbol in ["AAPL", "MSFT", "GOOGL"]:
    ob = OrderBook()
    eng = MatchingEngine(ob)
    engines[symbol] = eng
    makers[symbol] = MarketMaker(symbol=symbol, matching_engine=eng)

# Run multi-asset backtest
run_multi_backtest(data_map, engines, makers, portfolio=portfolio)
```

### Parameter Optimization
```python
import optuna
from trading_simulator import objective_optuna

# Define optimization objective
def objective(trial):
    return objective_optuna(
        trial, 
        symbol="AAPL", 
        start="2023-01-01", 
        end="2023-12-31",
        base_params={
            'initial_cash': 1000000,
            'fee_bps': 1.0,
            'risk_max_order_qty': 1000,
            'risk_max_symbol_position': 10000,
            'risk_max_gross_notional': 5000000
        },
        log_dir=".logs"
    )

# Create study and optimize
study = optuna.create_study(direction='maximize')
study.optimize(objective, n_trials=100)

print(f"Best parameters: {study.best_params}")
print(f"Best value: {study.best_value}")
```

## 🔌 API Integration

### FIX Protocol Integration
```python
from trading_simulator import FixApplication

# Create FIX application
fix_app = FixApplication(matching_engine)

# Start FIX server
fix_app.start(host='localhost', port=5005)

# Send FIX order
order_msg = fix_app.create_order_message({
    'id': 'ORDER001',
    'side': 'buy',
    'symbol': 'AAPL',
    'price': 150.0,
    'quantity': 100
})

fix_app.send_message(order_msg, host='localhost', port=5005)
```

### Market Data Integration
```python
from trading_simulator import MarketDataFeed

# Create market data feed
feed = MarketDataFeed(symbol="AAPL")

# Subscribe to market data
class MySubscriber:
    def receive(self, data):
        print(f"Price: {data['price']}, Volume: {data['volume']}")

subscriber = MySubscriber()
feed.subscribe(subscriber)

# Start feed
feed.start(interval_seconds=60)
```

### Database Integration
```python
from trading_simulator import DbLogger

# Create database logger
db_logger = DbLogger("postgresql://user:pass@localhost/trading_db")

# Log execution
db_logger.log_execution(execution)

# Log equity
db_logger.log_equity(timestamp, net_liq, realized, cash)

# Save configuration
db_logger.save_config("strategy_config", {
    'momentum_lookback': 5,
    'ema_short_window': 5,
    'ema_long_window': 20
})
```

### Event Streaming
```python
from trading_simulator import EventBus, make_redis_publisher, make_kafka_publisher

# Create event bus
event_bus = EventBus()

# Add Redis publisher
redis_pub = make_redis_publisher("redis://localhost:6379", "trading_events")
event_bus.add_publisher(redis_pub)

# Add Kafka publisher
kafka_pub = make_kafka_publisher("localhost:9092", "trading_events")
event_bus.add_publisher(kafka_pub)

# Publish events
event_bus.publish("order_executed", {
    'order_id': 'ORDER001',
    'price': 150.0,
    'quantity': 100,
    'timestamp': '2023-01-01T10:00:00Z'
})
```

## 📝 Configuration

### Command Line Arguments
```bash
# Mode selection
--mode {backtest,live,demo,replay}

# Symbol and data
--symbol SYMBOL                    # Trading symbol (default: AAPL)
--symbols SYMBOLS                  # Comma-separated symbols for multi-asset
--start-date START_DATE           # Backtest start date (YYYY-MM-DD)
--end-date END_DATE               # Backtest end date (YYYY-MM-DD)

# Trading parameters
--initial-cash INITIAL_CASH       # Initial portfolio cash (default: 1000000)
--fee-bps FEE_BPS                 # Execution fee in basis points (default: 0.0)
--slippage-bps-per-100 SLIPPAGE   # Slippage in bps per 100 shares (default: 0.0)
--latency-ms LATENCY              # Order latency in milliseconds (default: 0)

# Risk management
--risk-max-order-qty QTY          # Maximum order quantity (default: 1000)
--risk-max-symbol-position POS    # Maximum position per symbol (default: 10000)
--risk-max-gross-notional NOT     # Maximum gross notional (default: 5000000)

# Market maker parameters
--mm-gamma GAMMA                  # Risk aversion parameter (default: 0.1)
--mm-k K                          # Order book intensity (default: 1.5)
--mm-horizon-seconds HORIZON      # Quote horizon (default: 60.0)
--mm-max-inventory INVENTORY      # Maximum inventory (default: 1000)
--mm-base-order-size SIZE         # Base order size (default: 100)
--mm-min-spread SPREAD            # Minimum spread (default: 0.01)
--mm-num-levels LEVELS            # Number of quote levels (default: 2)
--mm-level-spacing-bps SPACING    # Level spacing in bps (default: 2.0)
--mm-size-decay DECAY             # Size decay factor (default: 0.7)
--mm-momentum-window WINDOW       # Momentum window (default: 10)
--mm-alpha-skew SKEW              # Momentum skew weight (default: 0.5)
--mm-vol-widen-z Z                # Volatility widening threshold (default: 2.0)
--mm-drawdown-limit LIMIT         # Drawdown limit (default: 0.2)

# Trader parameters
--momentum-lookback LOOKBACK      # Momentum lookback (default: 5)
--ema-short-window SHORT          # EMA short window (default: 5)
--ema-long-window LONG            # EMA long window (default: 20)
--swing-support SUPPORT           # Swing support level (default: 100.0)
--swing-resistance RESISTANCE     # Swing resistance level (default: 200.0)

# Output and logging
--log-dir LOG_DIR                 # Log directory (default: .logs)
--export-report                   # Export HTML performance report
--report-out REPORT_OUT           # Report output path (default: report.html)

# Advanced features
--enable-traders                  # Enable algorithmic traders
--inject-liquidity SECONDS        # Inject synthetic liquidity every N seconds
--seed SEED                       # Random seed for reproducibility
--optuna-trials TRIALS            # Number of Optuna optimization trials
--mlflow-uri URI                  # MLflow tracking URI
--mlflow-experiment EXPERIMENT    # MLflow experiment name
```

### Configuration Files
```yaml
# config.yaml
trading:
  default_symbol: "AAPL"
  initial_cash: 1000000
  fee_bps: 1.0
  maker_rebate_bps: 0.5

risk_management:
  max_order_qty: 1000
  max_symbol_position: 10000
  max_gross_notional: 5000000
  order_rate_limit_per_sec: 10
  owner_drawdown_limit: 0.2
  max_leverage: 3.0
  volatility_halt_z: 3.0

market_maker:
  gamma: 0.1
  k: 1.5
  horizon_seconds: 60.0
  max_inventory: 1000
  base_order_size: 100
  min_spread: 0.01
  num_levels: 2
  level_spacing_bps: 2.0
  size_decay: 0.7
  momentum_window: 10
  alpha_skew: 0.5
  vol_widen_z: 2.0
  drawdown_limit: 0.2

traders:
  momentum:
    lookback: 5
    interval: 0.1
  ema:
    short_window: 5
    long_window: 20
    interval: 0.1
  swing:
    support_level: 100.0
    resistance_level: 200.0
    interval: 0.1

backtesting:
  slippage_bps_per_100: 0.5
  latency_ms: 10
  export_report: true
  report_out: "performance_report.html"

data:
  cache_dir: ".cache"
  yahoo_finance_timeout: 30
  max_retries: 5
  base_backoff: 1.5

logging:
  level: "INFO"
  format: "%(asctime)s - %(levelname)s - %(message)s"
  log_dir: ".logs"
```

## 📊 Performance Analytics
### Periodic Metrics During Runs
The system prints rolling metrics during Replay and at the end of Backtest/Live runs:
- Net Liq, Cash, Realized PnL
- Sharpe (ann), Sortino (ann), Volatility (ann)
- Current and Maximum Drawdown, CAGR
- Trades, Buys, Sells, Total Notional, Avg Trade Qty
- Average Slippage vs Mid (bps), Adverse Selection Rate

These are computed from `equity_curve.csv`, `executions.csv`, `tca.csv`, and `tca_adv.csv` in your chosen log directory.

## 🖥️ Live Order Control (Split Terminal)

Place, cancel, or modify orders while a Live run is executing—without FIX. This lightweight order shell uses JSON-over-TCP and integrates with the same risk/matching/TCA pipeline.

### Enable
- Interactive CLI: answer “Enable local order-control server for live mode?” → Yes
- Flags: add `--order-cli-enable --order-cli-host 127.0.0.1 --order-cli-port 8765 --order-cli-owner cli`

When enabled, the server listens on host:port and logs:
```
Order CLI enabled: send JSON to 127.0.0.1:8765 (actions: new/cancel/modify)
```

### Protocol
- One JSON per connection; server responds with JSON `{ "ok": true/false, ... }`
- Actions:
  - New order:
    ```json
    {
      "action": "new",
      "symbol": "AAPL",
      "side": "buy",           
      "type": "limit",         
      "price": 150.25,          
      "quantity": 100,
      "tif": "GTC",            
      "owner_id": "cli"        
    }
    ```
  - Cancel:
    ```json
    { "action": "cancel", "order_id": "<returned id>" }
    ```
  - Modify (in-book):
    ```json
    { "action": "modify", "order_id": "<id>", "price": 150.4, "quantity": 50 }
    ```

Notes:
- `owner_id` routes PnL/risk to that portfolio owner (default from `--order-cli-owner`).
- Orders pass the same risk checks; executions hit TCA and CSV logs.
- Works offline: the live feed auto-simulates if data fetching fails.

### Usage Examples

Windows PowerShell
```powershell
$host = "127.0.0.1"; $port = 8765
python -c "import socket,json,sys; h=sys.argv[1]; p=int(sys.argv[2]); o={'action':'new','symbol':'AAPL','side':'buy','type':'limit','price':150.25,'quantity':100,'tif':'GTC','owner_id':'cli'}; s=socket.socket(); s.connect((h,p)); s.sendall(json.dumps(o).encode()); print(s.recv(4096).decode()); s.close()" $host $port
```

Cancel (replace with returned order_id):
```powershell
$host = "127.0.0.1"; $port = 8765
python -c "import socket,json,sys; h=sys.argv[1]; p=int(sys.argv[2]); o={'action':'cancel','order_id':'REPLACE_WITH_ORDER_ID'}; s=socket.socket(); s.connect((h,p)); s.sendall(json.dumps(o).encode()); print(s.recv(4096).decode()); s.close()" $host $port
```

Modify:
```powershell
$host = "127.0.0.1"; $port = 8765
python -c "import socket,json,sys; h=sys.argv[1]; p=int(sys.argv[2]); o={'action':'modify','order_id':'REPLACE_WITH_ORDER_ID','price':150.4,'quantity':50}; s=socket.socket(); s.connect((h,p)); s.sendall(json.dumps(o).encode()); print(s.recv(4096).decode()); s.close()" $host $port
```

bash/zsh
```bash
host=127.0.0.1; port=8765
python - << 'PY'
import socket, json, os
host = os.environ.get('HOST','127.0.0.1'); port = int(os.environ.get('PORT','8765'))
o = {"action":"new","symbol":"AAPL","side":"buy","type":"limit","price":150.25,"quantity":100,"tif":"GTC","owner_id":"cli"}
s = socket.socket(); s.connect((host,port)); s.sendall(json.dumps(o).encode()); print(s.recv(4096).decode()); s.close()
PY
```


### Performance Metrics
```python
from trading_simulator import compute_performance_metrics, export_html_report

# Load equity curve
equity_df = pd.read_csv(".logs/equity_curve.csv")

# Compute metrics
metrics = compute_performance_metrics(equity_df)

print(f"Initial Value: ${metrics['initial']:,.2f}")
print(f"Final Value: ${metrics['final']:,.2f}")
print(f"CAGR: {metrics['cagr']:.2%}")
print(f"Sharpe Ratio: {metrics['sharpe']:.2f}")
print(f"Sortino Ratio: {metrics['sortino']:.2f}")
print(f"Max Drawdown: {metrics['max_drawdown']:.2%}")

# Export HTML report
export_html_report(equity_df, metrics, "performance_report.html")
```

### Trade Cost Analysis
```python
from trading_simulator import CsvLogger

# Analyze TCA data
tca_df = pd.read_csv(".logs/tca.csv")

# Calculate average slippage
avg_slippage_mid = tca_df['slippage_mid_bps'].mean()
avg_slippage_last = tca_df['slippage_last_bps'].mean()

print(f"Average Mid Slippage: {avg_slippage_mid:.2f} bps")
print(f"Average Last Trade Slippage: {avg_slippage_last:.2f} bps")

# Analyze adverse selection
adv_df = pd.read_csv(".logs/tca_adv.csv")
adverse_rate = adv_df['adverse'].mean()

print(f"Adverse Selection Rate: {adverse_rate:.2%}")
```

### Portfolio Analysis
```python
from trading_simulator import Portfolio, mark_to_market

# Get portfolio snapshot
snapshot = portfolio.snapshot()

print(f"Cash: ${snapshot['cash']:,.2f}")
print(f"Realized PnL: ${snapshot['realized_pnl']:,.2f}")
print(f"Positions: {snapshot['positions']}")

# Mark to market
last_prices = {'AAPL': 150.0, 'MSFT': 300.0}
net_liq = mark_to_market(portfolio, last_prices) + portfolio.realized_pnl

print(f"Net Liquidation Value: ${net_liq:,.2f}")
```

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

### Development Setup
```bash
# Clone repository
git clone https://github.com/yourusername/Automated-Financial-Market-Trading-System.git
cd Automated-Financial-Market-Trading-System

# Create development environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install

# Run tests
pytest tests/

# Run linting
flake8 trading_simulator/
black trading_simulator/
isort trading_simulator/
```

### Code Style
- **Python**: Follow PEP 8 with 88-character line length
- **Type Hints**: Use type hints for all function parameters and return values
- **Docstrings**: Use Google-style docstrings for all public functions
- **Tests**: Maintain 90%+ test coverage
- **Documentation**: Update documentation for all new features

### Pull Request Process
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Update documentation
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

## 📄 License

This project is licensed under the MIT License © 2025 Devansh Garg - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Yahoo Finance** for market data
- **NewsAPI** for sentiment analysis data
- **TensorFlow** for machine learning capabilities
- **Optuna** for hyperparameter optimization
- **MLflow** for experiment tracking
- **PostgreSQL** for data persistence
- **Redis** for caching and event streaming
- **Apache Kafka** for real-time event processing

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/issues)

---

<div align="center">
  <p>Made with ❤️ by the Trading System Team</p>
  <p>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/stargazers">
      <img src="https://img.shields.io/github/stars/ThePredictiveDev/Automated-Financial-Market-Trading-System" alt="Stars">
    </a>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/network">
      <img src="https://img.shields.io/github/forks/ThePredictiveDev/Automated-Financial-Market-Trading-System" alt="Forks">
    </a>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/issues">
      <img src="https://img.shields.io/github/issues/ThePredictiveDev/Automated-Financial-Market-Trading-System" alt="Issues">
    </a>
    <a href="https://github.com/ThePredictiveDev/Automated-Financial-Market-Trading-System/blob/main/LICENSE">
      <img src="https://img.shields.io/github/license/ThePredictiveDev/Automated-Financial-Market-Trading-System" alt="License">
    </a>
  </p>
</div>
