"""Example custom strategies, referenced by the README's "Custom Traders"
section. Load them with:

    python -m trading_simulator --mode backtest --enable-traders \\
      --custom-trader examples.strats:BreakoutTrader \\
      --custom-trader-params '{"lookback": 15, "band_bps": 8, "owner_id": "bo15"}'

(Previously the README documented this exact file and these exact classes,
but the file did not exist anywhere in the repository -- copying the
README's own instructions would fail. This is that file.)
"""
from __future__ import annotations

import uuid
from collections import deque

import numpy as np

from trading_simulator import AlgorithmicTrader, Order


class BreakoutTrader(AlgorithmicTrader):
    """Buys when price breaks above its recent high by `band_bps`, sells
    when it breaks below its recent low by the same margin."""

    def __init__(self, symbol, matching_engine, lookback=20, band_bps=5, interval=0.0, owner_id="breakout"):
        super().__init__(symbol, matching_engine, interval)
        self.lookback = int(lookback)
        self.band_bps = float(band_bps)
        self.owner_id = str(owner_id)
        self.buf = deque(maxlen=max(3, self.lookback))

    def on_market_data(self, data):
        super().on_market_data(data)
        self.buf.append(float(data["price"]))

    def trade(self):
        if self.current_price is None or len(self.buf) < self.lookback:
            return
        hi, lo = max(self.buf), min(self.buf)
        band = self.current_price * (self.band_bps / 10000.0)
        ob = self.matching_engine.order_book
        best_ask, best_bid = ob.get_best_ask(), ob.get_best_bid()
        if best_ask is None or best_bid is None:
            return
        if self.current_price > hi + band:
            self.matching_engine.match_order(Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=100,
                                                     side="buy", type="limit", symbol=self.symbol, owner_id=self.owner_id))
        elif self.current_price < lo - band:
            self.matching_engine.match_order(Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=100,
                                                     side="sell", type="limit", symbol=self.symbol, owner_id=self.owner_id))


class MeanRevTrader(AlgorithmicTrader):
    """Buys when price is `z_entry` standard deviations below its recent
    mean, sells when it's that far above."""

    def __init__(self, symbol, matching_engine, lookback=20, z_entry=1.0, interval=0.0, owner_id="meanrev"):
        super().__init__(symbol, matching_engine, interval)
        self.lookback = int(lookback)
        self.z_entry = float(z_entry)
        self.owner_id = str(owner_id)
        self.buf = deque(maxlen=max(3, self.lookback))

    def on_market_data(self, data):
        super().on_market_data(data)
        self.buf.append(float(data["price"]))

    def trade(self):
        if self.current_price is None or len(self.buf) < self.lookback:
            return
        arr = np.array(self.buf, dtype=float)
        sma, std = float(arr.mean()), float(arr.std(ddof=0))
        if std <= 0:
            return
        z = (self.current_price - sma) / std
        ob = self.matching_engine.order_book
        best_ask, best_bid = ob.get_best_ask(), ob.get_best_bid()
        if best_ask is None or best_bid is None:
            return
        if z <= -self.z_entry:
            self.matching_engine.match_order(Order(id=uuid.uuid4().hex, price=float(best_ask), quantity=100,
                                                     side="buy", type="limit", symbol=self.symbol, owner_id=self.owner_id))
        elif z >= self.z_entry:
            self.matching_engine.match_order(Order(id=uuid.uuid4().hex, price=float(best_bid), quantity=100,
                                                     side="sell", type="limit", symbol=self.symbol, owner_id=self.owner_id))
