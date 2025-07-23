# Enhanced Trading Simulator in Python
# Comprehensive version with advanced features built upon existing framework

from collections import deque, namedtuple
from bisect import insort
import pandas as pd
import simplefix
import socket
import time
import threading
import logging
import random
import yfinance as yf
import statistics
import numpy as np
import tensorflow as tf
from tensorflow.keras.models import load_model
from tensorflow.keras.layers import TextVectorization
from newsapi import NewsApiClient
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import json
import pickle
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
import warnings
warnings.filterwarnings('ignore')

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_simulator.log'),
        logging.StreamHandler()
    ]
)

## Enhanced Order Book with Analytics

Order = namedtuple('Order', ['id', 'price', 'quantity', 'side', 'type', 'symbol', 'timestamp', 'trader_id'])

class EnhancedOrderBook:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.order_map = {}
        self.order_history = []
        self.trade_history = []
        self.market_depth = {}

    def add_order(self, order):
        """Add a new order to the order book with enhanced tracking."""
        if not hasattr(order, 'timestamp') or order.timestamp is None:
            order = order._replace(timestamp=datetime.now())
        
        if order.side == 'buy':
            if order.price not in self.bids:
                self.bids[order.price] = deque()
            self.bids[order.price].append(order)
        else:
            if order.price not in self.asks:
                self.asks[order.price] = deque()
            self.asks[order.price].append(order)
        
        self.order_map[order.id] = order
        self.order_history.append(order)
        self.update_market_depth()
        
        logging.info(f"Order added: {order.id} - {order.side} {order.quantity} {order.symbol} @ {order.price}")

    def remove_order(self, order_id):
        """Remove an order from the order book."""
        if order_id in self.order_map:
            order = self.order_map[order_id]
            if order.side == 'buy':
                self.bids[order.price].remove(order)
                if not self.bids[order.price]:
                    del self.bids[order.price]
            else:
                self.asks[order.price].remove(order)
                if not self.asks[order.price]:
                    del self.asks[order.price]
            del self.order_map[order_id]
            self.update_market_depth()
            logging.info(f"Order removed: {order_id}")

    def modify_order(self, order_id, new_quantity=None, new_price=None):
        """Modify an existing order's quantity and/or price."""
        if order_id in self.order_map:
            order = self.order_map[order_id]
            self.remove_order(order_id)
            if new_quantity is not None:
                order = order._replace(quantity=new_quantity)
            if new_price is not None:
                order = order._replace(price=new_price)
            self.add_order(order)
            logging.info(f"Order modified: {order_id}")
        else:
            logging.warning(f"Order {order_id} not found for modification.")

    def get_best_bid(self):
        """Get the highest bid price."""
        if self.bids:
            return max(self.bids)
        return None

    def get_best_ask(self):
        """Get the lowest ask price."""
        if self.asks:
            return min(self.asks)
        return None

    def get_spread(self):
        """Calculate current bid-ask spread."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return best_ask - best_bid
        return None

    def get_mid_price(self):
        """Calculate mid price."""
        best_bid = self.get_best_bid()
        best_ask = self.get_best_ask()
        if best_bid and best_ask:
            return (best_bid + best_ask) / 2
        return None

    def update_market_depth(self):
        """Update market depth information."""
        self.market_depth = {
            'bids': {price: sum(order.quantity for order in orders) 
                    for price, orders in self.bids.items()},
            'asks': {price: sum(order.quantity for order in orders) 
                    for price, orders in self.asks.items()}
        }

    def get_market_depth(self, levels=10):
        """Get market depth for specified number of levels."""
        bid_prices = sorted(self.bids.keys(), reverse=True)[:levels]
        ask_prices = sorted(self.asks.keys())[:levels]
        
        depth = {
            'bids': [(price, self.market_depth['bids'].get(price, 0)) for price in bid_prices],
            'asks': [(price, self.market_depth['asks'].get(price, 0)) for price in ask_prices]
        }
        return depth

    def record_trade(self, buy_order, sell_order, price, quantity):
        """Record a completed trade."""
        trade = {
            'timestamp': datetime.now(),
            'price': price,
            'quantity': quantity,
            'buy_order_id': buy_order.id,
            'sell_order_id': sell_order.id,
            'symbol': buy_order.symbol
        }
        self.trade_history.append(trade)
        logging.info(f"Trade recorded: {quantity} @ {price}")

    def get_order_book_summary(self):
        """Get a summary of the current order book state."""
        return {
            'best_bid': self.get_best_bid(),
            'best_ask': self.get_best_ask(),
            'spread': self.get_spread(),
            'mid_price': self.get_mid_price(),
            'total_bid_orders': len(self.order_map),
            'total_ask_orders': len(self.order_map),
            'market_depth': self.get_market_depth()
        }

    def display_order_book(self):
        """Display the current state of the order book."""
        print("\n=== Order Book Summary ===")
        summary = self.get_order_book_summary()
        print(f"Best Bid: {summary['best_bid']}")
        print(f"Best Ask: {summary['best_ask']}")
        print(f"Spread: {summary['spread']}")
        print(f"Mid Price: {summary['mid_price']}")
        
        print("\n=== Market Depth ===")
        depth = summary['market_depth']
        print("Bids:")
        for price, qty in depth['bids']:
            print(f"  {price}: {qty}")
        print("Asks:")
        for price, qty in depth['asks']:
            print(f"  {price}: {qty}")

## Enhanced Matching Engine

class EnhancedMatchingEngine:
    def __init__(self, order_book):
        self.order_book = order_book
        self.execution_stats = {
            'total_trades': 0,
            'total_volume': 0,
            'avg_trade_size': 0,
            'execution_latency': []
        }

    def match_order(self, incoming_order):
        """Match incoming orders against the order book with enhanced execution tracking."""
        start_time = time.time()
        
        if incoming_order.side == 'buy':
            self.match_buy_order(incoming_order)
        else:
            self.match_sell_order(incoming_order)
        
        # Record execution latency
        latency = time.time() - start_time
        self.execution_stats['execution_latency'].append(latency)

    def match_buy_order(self, order):
        """Match buy orders with enhanced execution tracking."""
        while order.quantity > 0 and self.order_book.get_best_ask() is not None:
            best_ask_price = self.order_book.get_best_ask()
            
            if order.price >= best_ask_price:
                self.execute_order(order, best_ask_price, 'sell')
            else:
                # Add remaining quantity to order book
                if order.quantity > 0:
                    self.order_book.add_order(order)
                break

    def match_sell_order(self, order):
        """Match sell orders with enhanced execution tracking."""
        while order.quantity > 0 and self.order_book.get_best_bid() is not None:
            best_bid_price = self.order_book.get_best_bid()
            
            if order.price <= best_bid_price:
                self.execute_order(order, best_bid_price, 'buy')
            else:
                # Add remaining quantity to order book
                if order.quantity > 0:
                    self.order_book.add_order(order)
                break

    def execute_order(self, order, price, counter_side):
        """Execute orders at the given price with enhanced tracking."""
        counter_orders = self.order_book.asks if counter_side == 'sell' else self.order_book.bids
        queue = counter_orders.get(price, deque())

        while order.quantity > 0 and queue:
            best_order = queue[0]
            trade_quantity = min(order.quantity, best_order.quantity)
            
            # Execute the trade
            self.order_book.record_trade(
                buy_order=order if order.side == 'buy' else best_order,
                sell_order=order if order.side == 'sell' else best_order,
                price=price,
                quantity=trade_quantity
            )
            
            # Update statistics
            self.execution_stats['total_trades'] += 1
            self.execution_stats['total_volume'] += trade_quantity
            
            # Update order quantities
            order = order._replace(quantity=order.quantity - trade_quantity)
            best_order = best_order._replace(quantity=best_order.quantity - trade_quantity)
            
            if best_order.quantity == 0:
                self.order_book.remove_order(best_order.id)
            else:
                self.order_book.modify_order(best_order.id, best_order.quantity)
            
            logging.info(f"Trade executed: {trade_quantity} @ {price}")

    def get_execution_stats(self):
        """Get execution statistics."""
        stats = self.execution_stats.copy()
        if stats['total_trades'] > 0:
            stats['avg_trade_size'] = stats['total_volume'] / stats['total_trades']
            stats['avg_latency'] = np.mean(stats['execution_latency'])
        return stats

## Risk Management System

class RiskManager:
    def __init__(self, max_position_size=10000, max_daily_loss=1000, max_drawdown=0.1):
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        self.positions = {}
        self.daily_pnl = 0
        self.peak_equity = 0
        self.current_equity = 0
        self.trade_history = []

    def check_order_risk(self, order, current_price):
        """Check if an order meets risk parameters."""
        symbol = order.symbol
        current_position = self.positions.get(symbol, 0)
        
        # Check position size limits
        if order.side == 'buy':
            new_position = current_position + order.quantity
        else:
            new_position = current_position - order.quantity
            
        if abs(new_position) > self.max_position_size:
            logging.warning(f"Order rejected: Position size {new_position} exceeds limit {self.max_position_size}")
            return False
        
        # Check daily loss limit
        if self.daily_pnl < -self.max_daily_loss:
            logging.warning(f"Order rejected: Daily loss limit exceeded")
            return False
        
        # Check drawdown limit
        if self.current_equity < self.peak_equity * (1 - self.max_drawdown):
            logging.warning(f"Order rejected: Maximum drawdown exceeded")
            return False
        
        return True

    def update_position(self, trade):
        """Update position after trade execution."""
        symbol = trade['symbol']
        quantity = trade['quantity']
        price = trade['price']
        
        if symbol not in self.positions:
            self.positions[symbol] = 0
        
        # Calculate P&L impact
        if self.positions[symbol] > 0:  # Long position
            if quantity > 0:  # Buying more
                self.positions[symbol] += quantity
            else:  # Selling
                pnl = (price - self.get_avg_cost(symbol)) * min(abs(quantity), self.positions[symbol])
                self.daily_pnl += pnl
                self.positions[symbol] = max(0, self.positions[symbol] + quantity)
        else:  # Short position or no position
            if quantity < 0:  # Selling more
                self.positions[symbol] -= abs(quantity)
            else:  # Buying
                pnl = (self.get_avg_cost(symbol) - price) * min(quantity, abs(self.positions[symbol]))
                self.daily_pnl += pnl
                self.positions[symbol] = min(0, self.positions[symbol] + quantity)
        
        self.trade_history.append(trade)
        self.update_equity()

    def get_avg_cost(self, symbol):
        """Calculate average cost for a position."""
        return 100.0  # Placeholder

    def update_equity(self):
        """Update current equity and peak equity."""
        self.current_equity = self.daily_pnl
        self.peak_equity = max(self.peak_equity, self.current_equity)

    def get_risk_metrics(self):
        """Get current risk metrics."""
        return {
            'positions': self.positions.copy(),
            'daily_pnl': self.daily_pnl,
            'current_equity': self.current_equity,
            'peak_equity': self.peak_equity,
            'drawdown': (self.peak_equity - self.current_equity) / self.peak_equity if self.peak_equity > 0 else 0
        }

## Performance Analytics

class PerformanceAnalytics:
    def __init__(self):
        self.trades = []
        self.daily_returns = []
        self.positions = []

    def add_trade(self, trade):
        """Add a trade to the analytics."""
        self.trades.append(trade)

    def calculate_returns(self, initial_capital=100000):
        """Calculate various return metrics."""
        if not self.trades:
            return {}
        
        # Calculate cumulative P&L
        cumulative_pnl = 0
        daily_pnl = {}
        
        for trade in self.trades:
            pnl = trade.get('pnl', 0)
            cumulative_pnl += pnl
            
            date = trade['timestamp'].date()
            if date not in daily_pnl:
                daily_pnl[date] = 0
            daily_pnl[date] += pnl
        
        # Calculate metrics
        total_return = cumulative_pnl / initial_capital
        daily_returns = list(daily_pnl.values())
        
        if daily_returns:
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) if np.std(daily_returns) > 0 else 0
            max_drawdown = self.calculate_max_drawdown(daily_returns)
            win_rate = len([r for r in daily_returns if r > 0]) / len(daily_returns)
        else:
            sharpe_ratio = 0
            max_drawdown = 0
            win_rate = 0
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': len(self.trades),
            'cumulative_pnl': cumulative_pnl
        }

    def calculate_max_drawdown(self, returns):
        """Calculate maximum drawdown from returns."""
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        return np.min(drawdown)

    def plot_performance(self):
        """Plot performance charts."""
        if not self.trades:
            print("No trades to plot")
            return
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        # Cumulative P&L
        cumulative_pnl = []
        running_pnl = 0
        for trade in self.trades:
            running_pnl += trade.get('pnl', 0)
            cumulative_pnl.append(running_pnl)
        
        axes[0, 0].plot(cumulative_pnl)
        axes[0, 0].set_title('Cumulative P&L')
        axes[0, 0].set_xlabel('Trade Number')
        axes[0, 0].set_ylabel('P&L')
        
        # Daily returns
        daily_pnl = {}
        for trade in self.trades:
            date = trade['timestamp'].date()
            if date not in daily_pnl:
                daily_pnl[date] = 0
            daily_pnl[date] += trade.get('pnl', 0)
        
        dates = list(daily_pnl.keys())
        returns = list(daily_pnl.values())
        
        axes[0, 1].bar(range(len(returns)), returns)
        axes[0, 1].set_title('Daily Returns')
        axes[0, 1].set_xlabel('Day')
        axes[0, 1].set_ylabel('Return')
        
        # Trade size distribution
        trade_sizes = [trade.get('quantity', 0) for trade in self.trades]
        axes[1, 0].hist(trade_sizes, bins=20)
        axes[1, 0].set_title('Trade Size Distribution')
        axes[1, 0].set_xlabel('Trade Size')
        axes[1, 0].set_ylabel('Frequency')
        
        # Price distribution
        prices = [trade.get('price', 0) for trade in self.trades]
        axes[1, 1].hist(prices, bins=20)
        axes[1, 1].set_title('Trade Price Distribution')
        axes[1, 1].set_xlabel('Price')
        axes[1, 1].set_ylabel('Frequency')
        
        plt.tight_layout()
        plt.show()

## Market Event Simulator

class MarketEventSimulator:
    def __init__(self, order_book, matching_engine):
        self.order_book = order_book
        self.matching_engine = matching_engine
        self.events = []
        self.running = False

    def simulate_flash_crash(self, symbol, severity=0.1):
        """Simulate a flash crash event."""
        current_price = self.order_book.get_mid_price()
        if current_price:
            crash_price = current_price * (1 - severity)
            
            # Add large sell orders
            for i in range(5):
                order = Order(
                    id=f'crash_sell_{i}',
                    price=crash_price * (1 - i * 0.01),
                    quantity=random.randint(1000, 5000),
                    side='sell',
                    type='limit',
                    symbol=symbol,
                    timestamp=datetime.now(),
                    trader_id='market_event'
                )
                self.matching_engine.match_order(order)
            
            logging.info(f"Flash crash simulated: {severity*100}% price drop")

    def simulate_liquidity_drain(self, symbol):
        """Simulate a liquidity drain event."""
        # Cancel random orders to reduce liquidity
        orders_to_cancel = random.sample(list(self.order_book.order_map.keys()), 
                                       min(5, len(self.order_book.order_map)))
        
        for order_id in orders_to_cancel:
            self.order_book.remove_order(order_id)
        
        logging.info(f"Liquidity drain simulated: {len(orders_to_cancel)} orders cancelled")

    def simulate_news_event(self, symbol, sentiment='positive'):
        """Simulate a news-driven price movement."""
        current_price = self.order_book.get_mid_price()
        if current_price:
            if sentiment == 'positive':
                price_change = current_price * 0.05
                side = 'buy'
            else:
                price_change = -current_price * 0.05
                side = 'sell'
            
            # Add orders in the direction of the news
            for i in range(3):
                order = Order(
                    id=f'news_{sentiment}_{i}',
                    price=current_price + price_change * (1 + i * 0.01),
                    quantity=random.randint(500, 2000),
                    side=side,
                    type='limit',
                    symbol=symbol,
                    timestamp=datetime.now(),
                    trader_id='market_event'
                )
                self.matching_engine.match_order(order)
            
            logging.info(f"News event simulated: {sentiment} sentiment")

    def start_event_simulation(self, interval=30):
        """Start periodic market event simulation."""
        self.running = True
        while self.running:
            # Randomly trigger events
            if random.random() < 0.1:  # 10% chance per interval
                event_type = random.choice(['flash_crash', 'liquidity_drain', 'news_event'])
                if event_type == 'flash_crash':
                    self.simulate_flash_crash('AAPL', random.uniform(0.05, 0.15))
                elif event_type == 'liquidity_drain':
                    self.simulate_liquidity_drain('AAPL')
                elif event_type == 'news_event':
                    sentiment = random.choice(['positive', 'negative'])
                    self.simulate_news_event('AAPL', sentiment)
            
            time.sleep(interval)

    def stop_event_simulation(self):
        """Stop market event simulation."""
        self.running = False

## Enhanced Algorithmic Traders

class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""
    
    def __init__(self, symbol, matching_engine, risk_manager):
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.risk_manager = risk_manager
        self.position = 0
        self.trades = []

    @abstractmethod
    def generate_signals(self, market_data):
        """Generate trading signals based on market data."""
        pass

    def execute_order(self, side, quantity, price, order_type='limit'):
        """Execute a trading order."""
        order = Order(
            id=str(random.randint(10000, 99999)),
            price=price,
            quantity=quantity,
            side=side,
            type=order_type,
            symbol=self.symbol,
            timestamp=datetime.now(),
            trader_id=self.__class__.__name__
        )
        
        if self.risk_manager.check_order_risk(order, price):
            self.matching_engine.match_order(order)
            self.trades.append(order)
            return order
        return None

class EnhancedMomentumStrategy(BaseStrategy):
    def __init__(self, symbol, matching_engine, risk_manager, lookback=20, threshold=0.02):
        super().__init__(symbol, matching_engine, risk_manager)
        self.lookback = lookback
        self.threshold = threshold
        self.price_history = []

    def generate_signals(self, market_data):
        """Generate momentum-based trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) > self.lookback:
            self.price_history.pop(0)
        
        if len(self.price_history) < self.lookback:
            return []
        
        # Calculate momentum
        momentum = (self.price_history[-1] - self.price_history[0]) / self.price_history[0]
        
        orders = []
        if momentum > self.threshold and self.position <= 0:
            # Strong upward momentum - buy
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, market_data['price'])
            if order:
                self.position += quantity
                orders.append(order)
        
        elif momentum < -self.threshold and self.position >= 0:
            # Strong downward momentum - sell
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, market_data['price'])
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class MeanReversionStrategy(BaseStrategy):
    def __init__(self, symbol, matching_engine, risk_manager, lookback=50, std_dev=2):
        super().__init__(symbol, matching_engine, risk_manager)
        self.lookback = lookback
        self.std_dev = std_dev
        self.price_history = []

    def generate_signals(self, market_data):
        """Generate mean reversion trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) > self.lookback:
            self.price_history.pop(0)
        
        if len(self.price_history) < self.lookback:
            return []
        
        # Calculate Bollinger Bands
        mean_price = np.mean(self.price_history)
        std_price = np.std(self.price_history)
        
        upper_band = mean_price + self.std_dev * std_price
        lower_band = mean_price - self.std_dev * std_price
        
        current_price = market_data['price']
        orders = []
        
        if current_price < lower_band and self.position <= 0:
            # Price below lower band - buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif current_price > upper_band and self.position >= 0:
            # Price above upper band - sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class GridTradingStrategy(BaseStrategy):
    def __init__(self, symbol, matching_engine, risk_manager, grid_levels=10, grid_spacing=0.01):
        super().__init__(symbol, matching_engine, risk_manager)
        self.grid_levels = grid_levels
        self.grid_spacing = grid_spacing
        self.grid_orders = {}

    def generate_signals(self, market_data):
        """Generate grid trading signals."""
        current_price = market_data['price']
        orders = []
        
        # Create grid levels
        for i in range(self.grid_levels):
            buy_price = current_price * (1 - (i + 1) * self.grid_spacing)
            sell_price = current_price * (1 + (i + 1) * self.grid_spacing)
            
            # Place buy orders below current price
            if buy_price > current_price * 0.8:  # Limit downside
                order = self.execute_order('buy', 50, buy_price)
                if order:
                    self.grid_orders[order.id] = {'type': 'buy', 'price': buy_price}
                    orders.append(order)
            
            # Place sell orders above current price
            if sell_price < current_price * 1.2:  # Limit upside
                order = self.execute_order('sell', 50, sell_price)
                if order:
                    self.grid_orders[order.id] = {'type': 'sell', 'price': sell_price}
                    orders.append(order)
        
        return orders

## Strategy Testing Framework

class StrategyTester:
    def __init__(self, order_book, matching_engine, risk_manager):
        self.order_book = order_book
        self.matching_engine = matching_engine
        self.risk_manager = risk_manager
        self.analytics = PerformanceAnalytics()
        self.strategies = {}

    def register_strategy(self, name, strategy):
        """Register a trading strategy for testing."""
        self.strategies[name] = strategy

    def run_backtest(self, historical_data, strategy_name, initial_capital=100000):
        """Run a backtest for a specific strategy."""
        if strategy_name not in self.strategies:
            raise ValueError(f"Strategy {strategy_name} not found")
        
        strategy = self.strategies[strategy_name]
        
        for index, row in historical_data.iterrows():
            # Update market data
            market_data = {
                'symbol': strategy.symbol,
                'price': row['Close'],
                'timestamp': row['Date'],
                'volume': row['Volume']
            }
            
            # Let strategy make decisions
            orders = strategy.generate_signals(market_data)
            
            # Execute orders
            for order in orders:
                if self.risk_manager.check_order_risk(order, market_data['price']):
                    self.matching_engine.match_order(order)
                    
                    # Record trade for analytics
                    trade = {
                        'timestamp': market_data['timestamp'],
                        'price': order.price,
                        'quantity': order.quantity,
                        'side': order.side,
                        'symbol': order.symbol,
                        'pnl': 0  # Calculate P&L based on position
                    }
                    self.analytics.add_trade(trade)
        
        # Calculate performance metrics
        performance = self.analytics.calculate_returns(initial_capital)
        performance['strategy_name'] = strategy_name
        
        return performance

    def compare_strategies(self, historical_data, initial_capital=100000):
        """Compare multiple strategies."""
        results = {}
        
        for strategy_name in self.strategies:
            # Reset for each strategy
            self.order_book = EnhancedOrderBook()
            self.matching_engine = EnhancedMatchingEngine(self.order_book)
            self.risk_manager = RiskManager()
            self.analytics = PerformanceAnalytics()
            
            results[strategy_name] = self.run_backtest(historical_data, strategy_name, initial_capital)
        
        return results

    def plot_strategy_comparison(self, results):
        """Plot comparison of different strategies."""
        metrics = ['total_return', 'sharpe_ratio', 'max_drawdown', 'win_rate']
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        
        for i, metric in enumerate(metrics):
            row, col = i // 2, i % 2
            values = [results[strategy][metric] for strategy in results]
            strategies = list(results.keys())
            
            axes[row, col].bar(strategies, values)
            axes[row, col].set_title(f'{metric.replace("_", " ").title()}')
            axes[row, col].tick_params(axis='x', rotation=45)
        
        plt.tight_layout()
        plt.show()

## Main Trading Simulator Class

class ComprehensiveTradingSimulator:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.order_book = EnhancedOrderBook()
        self.matching_engine = EnhancedMatchingEngine(self.order_book)
        self.risk_manager = RiskManager()
        self.analytics = PerformanceAnalytics()
        self.strategy_tester = StrategyTester(self.order_book, self.matching_engine, self.risk_manager)
        self.market_event_simulator = MarketEventSimulator(self.order_book, self.matching_engine)
        
        # Initialize strategies
        self.strategies = {
            'momentum': EnhancedMomentumStrategy('AAPL', self.matching_engine, self.risk_manager),
            'mean_reversion': MeanReversionStrategy('AAPL', self.matching_engine, self.risk_manager),
            'grid_trading': GridTradingStrategy('AAPL', self.matching_engine, self.risk_manager)
        }
        
        # Register strategies with tester
        for name, strategy in self.strategies.items():
            self.strategy_tester.register_strategy(name, strategy)

    def run_simulation(self, duration_minutes=60):
        """Run the complete trading simulation."""
        logging.info("Starting comprehensive trading simulation")
        
        # Start market event simulation
        event_thread = threading.Thread(target=self.market_event_simulator.start_event_simulation)
        event_thread.start()
        
        # Run simulation for specified duration
        start_time = time.time()
        while time.time() - start_time < duration_minutes * 60:
            # Generate market data
            try:
                ticker = yf.Ticker('AAPL')
                data = ticker.history(period="1d", interval="1m")
                if not data.empty:
                    latest_data = data.iloc[-1]
                    market_data = {
                        'symbol': 'AAPL',
                        'price': latest_data['Close'],
                        'timestamp': latest_data.name,
                        'volume': latest_data['Volume']
                    }
                    
                    # Let strategies generate signals
                    for strategy in self.strategies.values():
                        strategy.generate_signals(market_data)
                    
                    # Update analytics
                    self.analytics.add_trade({
                        'timestamp': market_data['timestamp'],
                        'price': market_data['price'],
                        'quantity': 0,
                        'pnl': 0
                    })
            
            except Exception as e:
                logging.error(f"Error processing market data: {e}")
            
            time.sleep(60)  # Update every minute
        
        # Stop simulation
        self.market_event_simulator.stop_event_simulation()
        event_thread.join()
        
        logging.info("Trading simulation completed")

    def run_backtest(self, start_date, end_date):
        """Run backtest for all strategies."""
        logging.info(f"Running backtest from {start_date} to {end_date}")
        
        # Load historical data
        historical_data = yf.download('AAPL', start=start_date, end=end_date)
        historical_data.reset_index(inplace=True)
        
        # Run backtest for all strategies
        results = self.strategy_tester.compare_strategies(historical_data, self.initial_capital)
        
        # Display results
        print("\n=== Backtest Results ===")
        for strategy_name, metrics in results.items():
            print(f"\n{strategy_name.upper()}:")
            for metric, value in metrics.items():
                if metric != 'strategy_name':
                    print(f"  {metric}: {value:.4f}")
        
        # Plot comparison
        self.strategy_tester.plot_strategy_comparison(results)
        
        return results

    def get_simulation_summary(self):
        """Get a comprehensive summary of the simulation."""
        execution_stats = self.matching_engine.get_execution_stats()
        risk_metrics = self.risk_manager.get_risk_metrics()
        performance_metrics = self.analytics.calculate_returns(self.initial_capital)
        order_book_summary = self.order_book.get_order_book_summary()
        
        return {
            'execution_stats': execution_stats,
            'risk_metrics': risk_metrics,
            'performance_metrics': performance_metrics,
            'order_book_summary': order_book_summary,
            'total_trades': len(self.analytics.trades),
            'simulation_duration': time.time()
        }

    def save_simulation_results(self, filename='simulation_results.pkl'):
        """Save simulation results to file."""
        results = {
            'trades': self.analytics.trades,
            'performance': self.analytics.calculate_returns(self.initial_capital),
            'execution_stats': self.matching_engine.get_execution_stats(),
            'risk_metrics': self.risk_manager.get_risk_metrics(),
            'order_book_history': self.order_book.order_history,
            'trade_history': self.order_book.trade_history
        }
        
        with open(filename, 'wb') as f:
            pickle.dump(results, f)
        
        logging.info(f"Simulation results saved to {filename}")

    def load_simulation_results(self, filename='simulation_results.pkl'):
        """Load simulation results from file."""
        try:
            with open(filename, 'rb') as f:
                results = pickle.load(f)
            
            self.analytics.trades = results.get('trades', [])
            logging.info(f"Simulation results loaded from {filename}")
            return results
        
        except FileNotFoundError:
            logging.warning(f"Results file {filename} not found")
            return None

## Demo Functions

def run_comprehensive_demo():
    """Run a comprehensive demonstration of the trading simulator."""
    print("=== Comprehensive Trading Simulator Demo ===\n")
    
    # Initialize simulator
    simulator = ComprehensiveTradingSimulator()
    
    # Run backtest
    print("Running backtest...")
    backtest_results = simulator.run_backtest('2023-01-01', '2023-12-31')
    
    # Run live simulation
    print("\nRunning live simulation...")
    simulator.run_simulation(duration_minutes=5)
    
    # Get summary
    summary = simulator.get_simulation_summary()
    print("\n=== Simulation Summary ===")
    print(f"Total Trades: {summary['total_trades']}")
    print(f"Performance Metrics: {summary['performance_metrics']}")
    print(f"Risk Metrics: {summary['risk_metrics']}")
    
    # Save results
    simulator.save_simulation_results()
    
    # Plot performance
    simulator.analytics.plot_performance()
    
    return simulator

def test_individual_components():
    """Test individual components of the simulator."""
    print("=== Testing Individual Components ===\n")
    
    # Test Order Book
    print("Testing Enhanced Order Book...")
    order_book = EnhancedOrderBook()
    
    # Add some orders
    orders = [
        Order(id='1', price=100.0, quantity=10, side='buy', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test'),
        Order(id='2', price=101.0, quantity=20, side='buy', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test'),
        Order(id='3', price=102.0, quantity=15, side='sell', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test'),
        Order(id='4', price=103.0, quantity=25, side='sell', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test')
    ]
    
    for order in orders:
        order_book.add_order(order)
    
    order_book.display_order_book()
    
    # Test Matching Engine
    print("\nTesting Enhanced Matching Engine...")
    matching_engine = EnhancedMatchingEngine(order_book)
    
    # Test a matching order
    matching_order = Order(id='5', price=102.5, quantity=10, side='buy', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test')
    matching_engine.match_order(matching_order)
    
    print("Order book after matching:")
    order_book.display_order_book()
    
    # Test Risk Manager
    print("\nTesting Risk Manager...")
    risk_manager = RiskManager()
    
    test_order = Order(id='6', price=100.0, quantity=1000, side='buy', type='limit', symbol='AAPL', timestamp=datetime.now(), trader_id='test')
    risk_check = risk_manager.check_order_risk(test_order, 100.0)
    print(f"Risk check result: {risk_check}")
    
    # Test Market Event Simulator
    print("\nTesting Market Event Simulator...")
    event_simulator = MarketEventSimulator(order_book, matching_engine)
    event_simulator.simulate_news_event('AAPL', 'positive')
    
    print("Order book after news event:")
    order_book.display_order_book()

if __name__ == "__main__":
    # Run component tests
    test_individual_components()
    
    # Run comprehensive demo
    print("\n" + "="*50)
    simulator = run_comprehensive_demo()
    
    print("\n=== Demo Completed Successfully ===")