"""Live market data feed: polls yahooquery/yfinance on an interval and
broadcasts ticks to subscribers (traders, market maker). Falls back to a
synthetic random walk after repeated fetch failures so a live session stays
alive offline/in demos instead of going silent."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from .history import fetch_history_with_retry

logger = logging.getLogger(__name__)


class MarketDataFeed:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.subscribers: List[Any] = []
        self.running = False
        self._last_price: Optional[float] = None
        self._fail_count = 0
        self._simulate = False

    def subscribe(self, client: Any) -> None:
        self.subscribers.append(client)

    def broadcast(self, data: Dict[str, Any]) -> None:
        for client in list(self.subscribers):
            try:
                client.receive(data)
            except Exception:
                logger.exception("Subscriber %s raised on market data", type(client).__name__)

    def fetch_market_data(self) -> Optional[Dict[str, Any]]:
        try:
            data = fetch_history_with_retry(self.symbol, period="1d", interval="1m", max_retries=4, base_backoff=1.8)
        except Exception as exc:
            logger.warning("MarketDataFeed fetch failed: %s", exc)
            return None
        if data is None or data.empty:
            return None
        latest = data.iloc[-1]
        ts = latest.name
        if isinstance(ts, pd.Timestamp):
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        else:
            ts = pd.to_datetime(ts, utc=True)
        return {"symbol": self.symbol, "timestamp": ts, "price": float(latest["Close"]), "volume": int(latest.get("Volume", 0))}

    def _synthetic_tick(self) -> Dict[str, Any]:
        base = float(self._last_price) if self._last_price is not None else 100.0
        shock = float(np.random.normal(loc=0.0, scale=base * 0.001))
        price = max(0.01, base + shock)
        self._last_price = price
        return {"symbol": self.symbol, "timestamp": pd.Timestamp.now(tz="UTC"), "price": price, "volume": 0}

    def _tick_once(self) -> None:
        market_data = None if self._simulate else self.fetch_market_data()
        if market_data is not None:
            self._fail_count = 0
            self._simulate = False
            self._last_price = float(market_data["price"])
            self.broadcast(market_data)
            return
        self._fail_count += 1
        if self._fail_count >= 3:
            self._simulate = True
        if self._simulate:
            self.broadcast(self._synthetic_tick())

    def start(self, interval_seconds: int = 60) -> None:
        self.running = True
        try:
            self._tick_once()
        except Exception:
            logger.warning("MarketDataFeed warm-start failed", exc_info=True)
        while self.running:
            try:
                self._tick_once()
            except Exception:
                logger.exception("MarketDataFeed tick error")
            time.sleep(max(1, int(interval_seconds)))

    def stop(self) -> None:
        self.running = False

    def last_price(self) -> Optional[float]:
        return self._last_price
