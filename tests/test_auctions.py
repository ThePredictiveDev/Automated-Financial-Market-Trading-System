import logging

from trading_simulator import Order, OrderBook, MatchingEngine


def mk_engine():
    ob = OrderBook()
    return ob, MatchingEngine(ob)


def test_auction_uncross_crosses_at_single_clearing_price():
    ob, eng = mk_engine()
    fills = []
    eng.subscribe_trades(lambda e: fills.append(e))

    eng.start_auction("open")
    eng.match_order(Order(id="b1", price=101.0, quantity=100, side="buy", type="limit", symbol="X",
                           owner_id="alice", auction_only=True, auction_phase="open"))
    eng.match_order(Order(id="s1", price=99.0, quantity=100, side="sell", type="limit", symbol="X",
                           owner_id="bob", auction_only=True, auction_phase="open"))
    assert eng.auction_mode == "open"
    assert len(fills) == 0  # nothing executes until uncross

    eng.uncross_auction()

    assert eng.auction_mode is None
    assert len(fills) == 1
    assert fills[0].price == 99.0  # clears at the lower of the two crossing prices
    assert fills[0].quantity == 100
    assert ob.get_best_bid() is None
    assert ob.get_best_ask() is None


def test_auction_uncross_no_cross_discards_pool_with_warning(caplog):
    ob, eng = mk_engine()
    fills = []
    eng.subscribe_trades(lambda e: fills.append(e))

    eng.start_auction("open")
    eng.match_order(Order(id="b1", price=95.0, quantity=100, side="buy", type="limit", symbol="X",
                           owner_id="alice", auction_only=True, auction_phase="open"))
    eng.match_order(Order(id="s1", price=105.0, quantity=100, side="sell", type="limit", symbol="X",
                           owner_id="bob", auction_only=True, auction_phase="open"))

    with caplog.at_level(logging.WARNING):
        eng.uncross_auction()

    assert len(fills) == 0
    assert eng.auction_mode is None
    assert ob.get_best_bid() is None and ob.get_best_ask() is None  # orders never rested, now discarded
    assert any("discarding" in r.message for r in caplog.records), "no-cross discard should be logged, not silent"


def test_regular_limit_orders_rest_during_auction_without_executing():
    ob, eng = mk_engine()
    fills = []
    eng.subscribe_trades(lambda e: fills.append(e))
    eng.start_auction("open")
    # A normal (non-auction_only) limit order during an auction rests in the book.
    eng.match_order(Order(id="b1", price=100.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="alice"))
    assert ob.get_best_bid() == 100.0
    assert len(fills) == 0


def test_market_order_during_auction_is_buffered_not_executed():
    ob, eng = mk_engine()
    fills = []
    eng.subscribe_trades(lambda e: fills.append(e))
    eng.start_auction("open")
    eng.match_order(Order(id="m1", price=0.0, quantity=10, side="buy", type="market", symbol="X", owner_id="alice"))
    assert len(fills) == 0
    assert "m1" not in ob.order_map  # buffered into the auction pool, not resting
    assert len(eng._auction_orders) == 1
