# Automated Financial Market Trading System
 This project is a Python-based trading simulator that allows users to simulate trading strategies, manage an order book, and interact with a mock trading environment using various algorithmic traders. The simulator includes a FIX (Financial Information eXchange) protocol handler, a market-making algorithm, and synthetic liquidity generation.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
  - [With Algorithmic Traders](#with-algorithmic-traders)
  - [Without Algorithmic Traders](#without-algorithmic-traders)
- [Usage](#usage)
  - [Initializing Everything](#initializing-everything)
  - [Order Creation and Control](#order-creation-and-control)
  - [Synthetic Liquidity Controls](#synthetic-liquidity-controls)
  - [Algo Trading Bot Controls](#algo-trading-bot-controls)
  - [Stop All Components](#stop-all-components)
- [Backtesting](#backtesting)
- [License](#license)

## Features

- **Order Book Management**: A robust order book implementation that supports adding, modifying, and canceling orders.
- **Matching Engine**: A matching engine that handles the execution of orders based on the best available prices in the order book.
- **FIX Protocol Handler**: A simple FIX protocol implementation that can handle new orders and order cancellations.
- **Market Data Feed**: A live market data feed using `yfinance` that can be subscribed to by various components.
- **Market Maker**: A basic market-making algorithm that posts bid and ask prices around the current market price.
- **Synthetic Liquidity Provider**: A module to inject synthetic liquidity into the order book to simulate a more active trading environment.
- **Algorithmic Traders**: Various algorithmic trading strategies, including momentum-based, EMA-based, swing trading, and sentiment analysis-driven trading.

## Installation

### With Algorithmic Traders

To install the required libraries, use the following `requirements.txt`:
```plaintext
tensorflow==2.6.0
newsapi-python==0.2.6
simplefix==1.0.12
yfinance==0.1.63
numpy==1.21.2
pandas==1.3.3
```
Install using pip
```bash
pip install -r requirements.txt
```

### Without Algorithmic Traders
If you prefer to run the program without the algorithmic traders, use the following `requirements.txt`:
```plaintext
simplefix==1.0.12
yfinance==0.1.63
numpy==1.21.2
pandas==1.3.3
```
Install using pip
```bash
pip install -r requirements.txt
```

## Usage
### Initializing Everything
To start the simulator, initialize the various components like the order book, matching engine, market data feed, and FIX server
```python
order_book = OrderBook()
matching_engine = MatchingEngine(order_book)
fix_app = FixApplication(matching_engine)

# Prompt user for the stock ticker
ticker_symbol = input("Enter the stock ticker symbol you want to track (e.g., AAPL): ").upper()

# Initialize the MarketDataFeed with the user-provided ticker symbol
market_data_feed = MarketDataFeed(symbol=ticker_symbol)
market_maker = MarketMaker(symbol=ticker_symbol, matching_engine=matching_engine)

# Start FIX server
fix_thread = threading.Thread(target=fix_app.start)
fix_thread.start()

# Start market data feed
feed_thread = threading.Thread(target=market_data_feed.start)
feed_thread.start()

# Start market maker
market_maker.start(market_data_feed)

```

### Order Creation and Control
Create, modify, and cancel orders in the order book:
```python
# Create an ask order
ask_order = Order(id='2', price=415, quantity=100, side='sell', type='limit', symbol='MSFT')
order_book.add_order(ask_order)

# Modify an order's quantity and price
order_book.modify_order(order_id='2', new_quantity=30, new_price=100.5)

# Cancel an order
order_book.cancel_order(order_id='3')

# Display the order book
order_book.display_order_book()

```
### Synthetic Liquidity Controls
Inject synthetic liquidity into the order book to simulate a more dynamic trading environment:
```python
liquidity_provider = SyntheticLiquidityProvider(symbol=symbol, matching_engine=matching_engine, num_orders=10)
liquidity_provider.generate_liquidity()

# Optionally, inject liquidity at regular intervals
def auto_inject_liquidity(provider, interval=5):
    while True:
        provider.generate_liquidity()
        time.sleep(interval)

liquidity_thread = threading.Thread(target=auto_inject_liquidity, args=(liquidity_provider, 5))  # Inject every 5 seconds
liquidity_thread.start()

```
### Algo Trading Bot Controls
Start algorithmic traders such as momentum-based, EMA-based, swing trading, and sentiment analysis-driven trading:
```python
# Load the pre-trained sentiment analysis model (assuming it’s stored as 'sentiment_classifier_model.h5')
sentiment_model = tf.keras.models.load_model('sentiment_classifier_model.h5')

# Initialize the traders
momentum_trader = MomentumTrader(symbol=ticker_symbol, matching_engine=matching_engine, interval=10)
ema_trader = EMABasedTrader(symbol=ticker_symbol, matching_engine=matching_engine, interval=30)
swing_trader = SwingTrader(symbol=ticker_symbol, matching_engine=matching_engine, interval=15)
sentiment_trader = SentimentAnalysisTrader(
    symbol=ticker_symbol,
    matching_engine=matching_engine,
    model_file='sentiment_classifier_model.h5',
    news_api_key="your_newsapi_key_here",
    interval=60
)

# Collect all traders into a list
traders = [momentum_trader, ema_trader, swing_trader, sentiment_trader]

# Start each trader in its own thread
trader_threads = []
for trader in traders:
    thread = threading.Thread(target=trader.start, args=(market_data_feed,))
    thread.start()
    trader_threads.append(thread)

```
### Stop All Components
Stop the market maker, market data feed, FIX server, and all traders:
```python
market_maker.stop()
market_data_feed.stop()
fix_app.stop()

# Stop all traders
for trader in traders:
    trader.stop()

# Join all threads to ensure they have finished
for thread in trader_threads:
    thread.join()

```

## Backtesting
Run a backtest using historical data
```python
def load_historical_data(symbol, start_date, end_date):
    """Load historical data from yfinance."""
    data = yf.download(symbol, start=start_date, end=end_date)
    # Ensure the data is formatted as expected
    data.reset_index(inplace=True)
    return data

def run_backtest(historical_data, market_maker, matching_engine):
    """Simulate historical data through the market maker and matching engine."""
    for index, row in historical_data.iterrows():
        # Simulate a market data update for the market maker
        market_data = {
            'symbol': market_maker.symbol,
            'price': row['Close'],
            'timestamp': row['Date']
        }

        # MarketMaker reacts to the incoming market data
        market_maker.on_market_data(market_data)

    print("Backtest completed.")

if __name__ == "__main__":
    # Initialize historical data
    symbol = "AAPL"
    start_date = "2023-01-01"
    end_date = "2023-12-31"
    historical_data = load_historical_data(symbol, start_date, end_date)

    # Initialize the market maker, matching engine, and other components
    order_book = OrderBook()
    matching_engine = MatchingEngine(order_book)
    market_maker = MarketMaker(symbol=symbol, matching_engine=matching_engine)

    # Run the backtest
    run_backtest(historical_data, market_maker, matching_engine)

```

## License
This project is licensed under the MIT License





