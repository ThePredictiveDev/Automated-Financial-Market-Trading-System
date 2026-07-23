import uuid
from unittest.mock import MagicMock

import pytest

from trading_simulator import Order, OrderBook, MatchingEngine, MomentumTrader, EMABasedTrader, SwingTrader


def mk_engine_with_liquidity():
    ob = OrderBook()
    eng = MatchingEngine(ob)
    eng.match_order(Order(id=uuid.uuid4().hex, price=99.0, quantity=1000, side="buy", type="limit", symbol="X", owner_id="lp"))
    eng.match_order(Order(id=uuid.uuid4().hex, price=101.0, quantity=1000, side="sell", type="limit", symbol="X", owner_id="lp"))
    return ob, eng


def test_momentum_trader_buys_on_upward_move():
    ob, eng = mk_engine_with_liquidity()
    trader = MomentumTrader(symbol="X", matching_engine=eng, lookback=3, owner_id="mom")
    for price in [100.0, 100.5, 101.5]:
        trader.on_market_data({"symbol": "X", "price": price})
    trader.trade()
    # Should have crossed the ask side (bought), consuming some of the 1000 resting sell qty
    assert ob.asks[101.0][0].quantity < 1000


def test_momentum_trader_sells_on_downward_move():
    ob, eng = mk_engine_with_liquidity()
    trader = MomentumTrader(symbol="X", matching_engine=eng, lookback=3, owner_id="mom")
    for price in [100.0, 99.5, 98.5]:
        trader.on_market_data({"symbol": "X", "price": price})
    trader.trade()
    assert ob.bids[99.0][0].quantity < 1000


def test_swing_trader_buys_near_support():
    ob, eng = mk_engine_with_liquidity()
    trader = SwingTrader(symbol="X", matching_engine=eng, support_level=100.0, resistance_level=200.0, owner_id="sw")
    trader.on_market_data({"symbol": "X", "price": 99.0})
    trader.trade()
    assert ob.asks[101.0][0].quantity < 1000


def test_ema_trader_requires_full_window_before_trading():
    ob, eng = mk_engine_with_liquidity()
    trader = EMABasedTrader(symbol="X", matching_engine=eng, short_window=2, long_window=5, owner_id="ema")
    for price in [100.0, 100.1, 100.2]:  # only 3 ticks, needs 5
        trader.on_market_data({"symbol": "X", "price": price})
    trader.trade()
    # Not enough history yet -- no trade should have happened
    assert ob.asks[101.0][0].quantity == 1000
    assert ob.bids[99.0][0].quantity == 1000


def test_ema_rejects_short_window_not_less_than_long_window():
    with pytest.raises(ValueError):
        EMABasedTrader(symbol="X", matching_engine=MagicMock(), short_window=10, long_window=5)


def test_swing_rejects_support_above_resistance():
    with pytest.raises(ValueError):
        SwingTrader(symbol="X", matching_engine=MagicMock(), support_level=200.0, resistance_level=100.0)


def test_momentum_position_sizing_scales_with_equity():
    from trading_simulator import Portfolio
    ob, eng = mk_engine_with_liquidity()
    small_pf = Portfolio(initial_cash=10_000.0)
    big_pf = Portfolio(initial_cash=10_000_000.0)
    small_trader = MomentumTrader(symbol="X", matching_engine=eng, lookback=3, portfolio=small_pf, risk_fraction=0.01)
    big_trader = MomentumTrader(symbol="X", matching_engine=eng, lookback=3, portfolio=big_pf, risk_fraction=0.01)
    assert big_trader._order_qty(100.0) > small_trader._order_qty(100.0)


def test_momentum_explicit_quantity_overrides_sizing():
    ob, eng = mk_engine_with_liquidity()
    trader = MomentumTrader(symbol="X", matching_engine=eng, lookback=3, quantity=42)
    assert trader._order_qty(100.0) == 42


def test_sentiment_trader_dedups_headlines():
    """Regression test: the original sentiment trader re-acted on the same
    headline every poll interval forever. `_remember` must return True only
    the first time a headline is seen, and evict the oldest entry once the
    cache is full."""
    from trading_simulator.strategies.sentiment import SentimentAnalysisTrader
    trader = SentimentAnalysisTrader.__new__(SentimentAnalysisTrader)
    from collections import OrderedDict
    trader._seen_headlines = OrderedDict()
    trader._seen_cache_size = 2

    assert trader._remember("Stocks rally on Fed news") is True
    assert trader._remember("Stocks rally on Fed news") is False  # seen before -> skip
    assert trader._remember("Oil prices drop") is True
    assert trader._remember("Tech earnings beat") is True  # evicts "Stocks rally..." (cache size 2)
    assert trader._remember("Stocks rally on Fed news") is True  # was evicted, so "new" again
