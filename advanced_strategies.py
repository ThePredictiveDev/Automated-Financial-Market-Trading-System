# Advanced Trading Strategies
# Additional strategies for the enhanced trading simulator

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import talib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
import logging

# Import base classes from main simulator
from enhanced_trading_simulator import BaseStrategy, Order

class RSIStrategy(BaseStrategy):
    """RSI-based mean reversion strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, period=14, oversold=30, overbought=70):
        super().__init__(symbol, matching_engine, risk_manager)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.price_history = []

    def calculate_rsi(self, prices):
        """Calculate RSI using talib."""
        if len(prices) < self.period + 1:
            return None
        return talib.RSI(np.array(prices), timeperiod=self.period)[-1]

    def generate_signals(self, market_data):
        """Generate RSI-based trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) < self.period + 1:
            return []
        
        rsi = self.calculate_rsi(self.price_history)
        if rsi is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
        if rsi < self.oversold and self.position <= 0:
            # Oversold - buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif rsi > self.overbought and self.position >= 0:
            # Overbought - sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class MACDStrategy(BaseStrategy):
    """MACD-based trend following strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, fast_period=12, slow_period=26, signal_period=9):
        super().__init__(symbol, matching_engine, risk_manager)
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.signal_period = signal_period
        self.price_history = []

    def calculate_macd(self, prices):
        """Calculate MACD using talib."""
        if len(prices) < self.slow_period + self.signal_period:
            return None, None
        
        macd, signal, hist = talib.MACD(np.array(prices), 
                                       fastperiod=self.fast_period,
                                       slowperiod=self.slow_period,
                                       signalperiod=self.signal_period)
        
        return macd[-1], signal[-1]

    def generate_signals(self, market_data):
        """Generate MACD-based trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) < self.slow_period + self.signal_period:
            return []
        
        macd, signal = self.calculate_macd(self.price_history)
        if macd is None or signal is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
        if macd > signal and self.position <= 0:
            # Bullish crossover - buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif macd < signal and self.position >= 0:
            # Bearish crossover - sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class MLPricePredictionStrategy(BaseStrategy):
    """Machine learning-based price prediction strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, lookback=60, prediction_threshold=0.02):
        super().__init__(symbol, matching_engine, risk_manager)
        self.lookback = lookback
        self.prediction_threshold = prediction_threshold
        self.price_history = []
        self.volume_history = []
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def prepare_features(self):
        """Prepare features for ML model."""
        if len(self.price_history) < self.lookback:
            return None
        
        # Calculate technical indicators
        prices = np.array(self.price_history)
        volumes = np.array(self.volume_history)
        
        # Price-based features
        returns = np.diff(prices) / prices[:-1]
        price_ma_5 = talib.SMA(prices, timeperiod=5)
        price_ma_20 = talib.SMA(prices, timeperiod=20)
        rsi = talib.RSI(prices, timeperiod=14)
        macd, signal, hist = talib.MACD(prices)
        
        # Volume-based features
        volume_ma = talib.SMA(volumes, timeperiod=20)
        volume_ratio = volumes / volume_ma
        
        # Combine features
        features = np.column_stack([
            returns[-self.lookback:],
            price_ma_5[-self.lookback:],
            price_ma_20[-self.lookback:],
            rsi[-self.lookback:],
            macd[-self.lookback:],
            signal[-self.lookback:],
            volume_ratio[-self.lookback:]
        ])
        
        # Remove NaN values
        features = features[~np.isnan(features).any(axis=1)]
        
        if len(features) < self.lookback:
            return None
        
        return features

    def train_model(self):
        """Train the ML model."""
        features = self.prepare_features()
        if features is None:
            return False
        
        # Create labels (1 for price increase, 0 for decrease)
        prices = np.array(self.price_history)
        future_returns = np.diff(prices[1:]) / prices[:-1]
        labels = (future_returns > 0).astype(int)
        
        # Align features and labels
        min_len = min(len(features), len(labels))
        features = features[:min_len]
        labels = labels[:min_len]
        
        # Scale features
        features_scaled = self.scaler.fit_transform(features)
        
        # Train Random Forest model
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.model.fit(features_scaled, labels)
        
        self.is_trained = True
        logging.info("ML model trained successfully")
        return True

    def predict_price_movement(self):
        """Predict price movement using trained model."""
        if not self.is_trained:
            return None
        
        features = self.prepare_features()
        if features is None:
            return None
        
        # Use the most recent features
        recent_features = features[-1:].reshape(1, -1)
        features_scaled = self.scaler.transform(recent_features)
        
        # Get prediction probability
        prob = self.model.predict_proba(features_scaled)[0]
        return prob[1]  # Probability of price increase

    def generate_signals(self, market_data):
        """Generate ML-based trading signals."""
        self.price_history.append(market_data['price'])
        self.volume_history.append(market_data.get('volume', 0))
        
        # Train model if we have enough data
        if len(self.price_history) >= self.lookback * 2 and not self.is_trained:
            self.train_model()
        
        if not self.is_trained:
            return []
        
        # Get prediction
        prediction_prob = self.predict_price_movement()
        if prediction_prob is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
        if prediction_prob > 0.5 + self.prediction_threshold and self.position <= 0:
            # Strong buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif prediction_prob < 0.5 - self.prediction_threshold and self.position >= 0:
            # Strong sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class LSTMStrategy(BaseStrategy):
    """LSTM-based price prediction strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, sequence_length=60, prediction_threshold=0.02):
        super().__init__(symbol, matching_engine, risk_manager)
        self.sequence_length = sequence_length
        self.prediction_threshold = prediction_threshold
        self.price_history = []
        self.model = None
        self.scaler = StandardScaler()
        self.is_trained = False

    def create_lstm_model(self, input_shape):
        """Create LSTM model architecture."""
        model = Sequential([
            LSTM(50, return_sequences=True, input_shape=input_shape),
            Dropout(0.2),
            LSTM(50, return_sequences=False),
            Dropout(0.2),
            Dense(25),
            Dense(1, activation='sigmoid')
        ])
        
        model.compile(optimizer='adam', loss='binary_crossentropy', metrics=['accuracy'])
        return model

    def prepare_sequences(self, data):
        """Prepare sequences for LSTM."""
        sequences = []
        targets = []
        
        for i in range(len(data) - self.sequence_length):
            sequence = data[i:i + self.sequence_length]
            target = 1 if data[i + self.sequence_length] > data[i + self.sequence_length - 1] else 0
            sequences.append(sequence)
            targets.append(target)
        
        return np.array(sequences), np.array(targets)

    def train_model(self):
        """Train the LSTM model."""
        if len(self.price_history) < self.sequence_length * 2:
            return False
        
        # Prepare data
        prices = np.array(self.price_history)
        prices_scaled = self.scaler.fit_transform(prices.reshape(-1, 1)).flatten()
        
        sequences, targets = self.prepare_sequences(prices_scaled)
        
        if len(sequences) < 100:  # Need minimum data
            return False
        
        # Split data
        split_idx = int(len(sequences) * 0.8)
        X_train, X_test = sequences[:split_idx], sequences[split_idx:]
        y_train, y_test = targets[:split_idx], targets[split_idx:]
        
        # Create and train model
        self.model = self.create_lstm_model((self.sequence_length, 1))
        self.model.fit(X_train, y_train, epochs=50, batch_size=32, validation_data=(X_test, y_test), verbose=0)
        
        self.is_trained = True
        logging.info("LSTM model trained successfully")
        return True

    def predict_price_movement(self):
        """Predict price movement using trained LSTM model."""
        if not self.is_trained or len(self.price_history) < self.sequence_length:
            return None
        
        # Prepare recent sequence
        recent_prices = self.price_history[-self.sequence_length:]
        prices_scaled = self.scaler.transform(np.array(recent_prices).reshape(-1, 1))
        sequence = prices_scaled.reshape(1, self.sequence_length, 1)
        
        # Get prediction
        prediction = self.model.predict(sequence, verbose=0)[0][0]
        return prediction

    def generate_signals(self, market_data):
        """Generate LSTM-based trading signals."""
        self.price_history.append(market_data['price'])
        
        # Train model if we have enough data
        if len(self.price_history) >= self.sequence_length * 3 and not self.is_trained:
            self.train_model()
        
        if not self.is_trained:
            return []
        
        # Get prediction
        prediction_prob = self.predict_price_movement()
        if prediction_prob is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
        if prediction_prob > 0.5 + self.prediction_threshold and self.position <= 0:
            # Strong buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif prediction_prob < 0.5 - self.prediction_threshold and self.position >= 0:
            # Strong sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

class BollingerBandsStrategy(BaseStrategy):
    """Bollinger Bands mean reversion strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, period=20, std_dev=2):
        super().__init__(symbol, matching_engine, risk_manager)
        self.period = period
        self.std_dev = std_dev
        self.price_history = []

    def calculate_bollinger_bands(self, prices):
        """Calculate Bollinger Bands."""
        if len(prices) < self.period:
            return None, None, None
        
        sma = talib.SMA(np.array(prices), timeperiod=self.period)
        std = talib.STDDEV(np.array(prices), timeperiod=self.period)
        
        upper_band = sma + (self.std_dev * std)
        lower_band = sma - (self.std_dev * std)
        
        return upper_band[-1], sma[-1], lower_band[-1]

    def generate_signals(self, market_data):
        """Generate Bollinger Bands-based trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) < self.period:
            return []
        
        upper_band, middle_band, lower_band = self.calculate_bollinger_bands(self.price_history)
        if upper_band is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
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

class StochasticStrategy(BaseStrategy):
    """Stochastic oscillator strategy."""
    
    def __init__(self, symbol, matching_engine, risk_manager, k_period=14, d_period=3, oversold=20, overbought=80):
        super().__init__(symbol, matching_engine, risk_manager)
        self.k_period = k_period
        self.d_period = d_period
        self.oversold = oversold
        self.overbought = overbought
        self.price_history = []

    def calculate_stochastic(self, prices):
        """Calculate Stochastic oscillator."""
        if len(prices) < self.k_period:
            return None, None
        
        slowk, slowd = talib.STOCH(np.array(prices), np.array(prices), np.array(prices),
                                  fastk_period=self.k_period,
                                  slowk_period=self.d_period,
                                  slowd_period=self.d_period)
        
        return slowk[-1], slowd[-1]

    def generate_signals(self, market_data):
        """Generate Stochastic-based trading signals."""
        self.price_history.append(market_data['price'])
        
        if len(self.price_history) < self.k_period:
            return []
        
        k_value, d_value = self.calculate_stochastic(self.price_history)
        if k_value is None:
            return []
        
        orders = []
        current_price = market_data['price']
        
        if k_value < self.oversold and d_value < self.oversold and self.position <= 0:
            # Oversold - buy signal
            quantity = min(100, abs(self.position) + 50)
            order = self.execute_order('buy', quantity, current_price)
            if order:
                self.position += quantity
                orders.append(order)
        
        elif k_value > self.overbought and d_value > self.overbought and self.position >= 0:
            # Overbought - sell signal
            quantity = min(100, self.position + 50)
            order = self.execute_order('sell', quantity, current_price)
            if order:
                self.position -= quantity
                orders.append(order)
        
        return orders

def test_advanced_strategies():
    """Test the advanced strategies."""
    print("=== Testing Advanced Strategies ===\n")
    
    # Import required components
    from enhanced_trading_simulator import EnhancedOrderBook, EnhancedMatchingEngine, RiskManager
    
    # Initialize components
    order_book = EnhancedOrderBook()
    matching_engine = EnhancedMatchingEngine(order_book)
    risk_manager = RiskManager()
    
    # Test RSI Strategy
    print("Testing RSI Strategy...")
    rsi_strategy = RSIStrategy('AAPL', matching_engine, risk_manager)
    
    # Simulate some price data
    for i in range(50):
        price = 100 + np.sin(i * 0.1) * 10  # Oscillating price
        market_data = {'price': price, 'volume': 1000}
        signals = rsi_strategy.generate_signals(market_data)
        if signals:
            print(f"RSI signal generated at price {price}")
    
    # Test MACD Strategy
    print("\nTesting MACD Strategy...")
    macd_strategy = MACDStrategy('AAPL', matching_engine, risk_manager)
    
    # Simulate trending price data
    for i in range(50):
        price = 100 + i * 0.5 + np.random.normal(0, 1)  # Trending price
        market_data = {'price': price, 'volume': 1000}
        signals = macd_strategy.generate_signals(market_data)
        if signals:
            print(f"MACD signal generated at price {price}")
    
    # Test Bollinger Bands Strategy
    print("\nTesting Bollinger Bands Strategy...")
    bb_strategy = BollingerBandsStrategy('AAPL', matching_engine, risk_manager)
    
    # Simulate mean-reverting price data
    for i in range(50):
        price = 100 + np.sin(i * 0.2) * 15  # Mean-reverting price
        market_data = {'price': price, 'volume': 1000}
        signals = bb_strategy.generate_signals(market_data)
        if signals:
            print(f"Bollinger Bands signal generated at price {price}")
    
    print("\nAdvanced strategy testing completed!")

if __name__ == "__main__":
    test_advanced_strategies()