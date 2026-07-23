"""Base class for algorithmic traders.

Thread-safety fix vs. the original: `current_price` / any buffered price
history are now protected by a lock. In live mode, market data arrives on
the MarketDataFeed's broadcast thread while `trade()` runs on the trader's
own thread (see start_trader_threads) -- the original read/wrote these
attributes from both threads with no synchronization, a real (if narrow)
data race. Backtest mode calls on_market_data()/trade() synchronously from a
single thread so this was latent there, but live mode could hit it.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class AlgorithmicTrader:
    def __init__(self, symbol: str, matching_engine, interval: float = 0.1) -> None:
        self.symbol = symbol
        self.matching_engine = matching_engine
        self.interval = interval
        self.running = False
        self._lock = threading.RLock()
        self._current_price: Optional[float] = None

    @property
    def current_price(self) -> Optional[float]:
        with self._lock:
            return self._current_price

    @current_price.setter
    def current_price(self, value: Optional[float]) -> None:
        with self._lock:
            self._current_price = value

    def start(self, feed) -> None:
        self.running = True
        feed.subscribe(self)
        while self.running:
            try:
                self.trade()
            except Exception:
                logger.exception("Trader %s.trade() raised", type(self).__name__)
            time.sleep(self.interval)

    def stop(self) -> None:
        self.running = False

    def trade(self) -> None:  # override in subclasses
        pass

    def receive(self, data: Dict[str, Any]) -> None:
        if data["symbol"] == self.symbol:
            self.on_market_data(data)

    def on_market_data(self, data: Dict[str, Any]) -> None:
        self.current_price = float(data["price"])
        self.handle_market_data(data)

    def handle_market_data(self, data: Dict[str, Any]) -> None:  # override in subclasses
        pass
