import pytest

from trading_simulator import Order, OrderBook, MatchingEngine


def mk_engine():
    ob = OrderBook()
    return ob, MatchingEngine(ob)


def submit(engine, **kwargs):
    defaults = dict(type="limit", tif="GTC", owner_id="default")
    defaults.update(kwargs)
    order = Order(**defaults)
    engine.match_order(order)
    return order


def test_basic_cross_fills_at_resting_price():
    ob, eng = mk_engine()
    fills = []
    eng.subscribe_trades(lambda e: fills.append(e))
    submit(eng, id="s1", price=100.0, quantity=10, side="sell", symbol="X", owner_id="alice")
    submit(eng, id="b1", price=100.0, quantity=10, side="buy", symbol="X", owner_id="bob")
    assert len(fills) == 1
    assert fills[0].price == 100.0
    assert fills[0].quantity == 10


def test_self_trade_prevention_preserves_priority():
    """Regression test for the original queue.rotate(-1) bug: skipping a
    same-owner resting order must not reorder other resting orders."""
    ob, eng = mk_engine()
    submit(eng, id="a1", price=100.0, quantity=10, side="sell", symbol="X", owner_id="alice")
    submit(eng, id="b1", price=100.0, quantity=10, side="sell", symbol="X", owner_id="bob")
    submit(eng, id="a2", price=100.0, quantity=10, side="sell", symbol="X", owner_id="alice")

    fills = []
    eng.subscribe_trades(lambda e: fills.append((e.maker_order_id, e.quantity)))
    submit(eng, id="t1", price=100.0, quantity=10, side="buy", symbol="X", owner_id="alice")

    assert fills == [("b1", 10)], "alice's own orders must be skipped, only bob's should fill"
    remaining = [o.id for o in ob.asks[100.0]]
    assert remaining == ["a1", "a2"], "skipped same-owner orders must keep their original relative order"


def test_fok_excludes_own_liquidity():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=50.0, quantity=100, side="sell", symbol="Y", owner_id="mm")
    fok = Order(id="fok1", price=50.0, quantity=100, side="buy", type="limit", symbol="Y", tif="FOK", owner_id="mm")
    eng.match_order(fok)
    assert fok.quantity == 100, "FOK must not report itself filled against its own resting liquidity"
    assert "fok1" not in ob.order_map, "a killed FOK order must not rest in the book"


def test_fok_fills_against_other_owner():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=50.0, quantity=100, side="sell", symbol="Y", owner_id="alice")
    fok = Order(id="fok1", price=50.0, quantity=100, side="buy", type="limit", symbol="Y", tif="FOK", owner_id="bob")
    eng.match_order(fok)
    assert fok.quantity == 0
    assert ob.get_best_ask() is None


def test_ioc_partial_fill_then_cancels_remainder():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=50.0, quantity=5, side="sell", symbol="Y", owner_id="alice")
    ioc = Order(id="ioc1", price=50.0, quantity=10, side="buy", type="limit", symbol="Y", tif="IOC", owner_id="bob")
    eng.match_order(ioc)
    assert ioc.quantity == 5, "IOC should fill what's available"
    assert "ioc1" not in ob.order_map, "IOC remainder must not rest in the book"


def test_post_only_rejected_if_crossing():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=50.0, quantity=10, side="sell", symbol="Y", owner_id="alice")
    po = Order(id="po1", price=51.0, quantity=10, side="buy", type="limit", symbol="Y", post_only=True, owner_id="bob")
    eng.match_order(po)
    assert "po1" not in ob.order_map
    assert ob.get_best_bid() is None


def test_price_band_rejects_outlier_order():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=100.0, quantity=10, side="sell", symbol="X", owner_id="a")
    submit(eng, id="b1", price=100.0, quantity=10, side="buy", symbol="X", owner_id="b")  # sets last trade price
    eng.price_band_bps = 100.0  # 1% band
    eng.band_reference = "last"
    submit(eng, id="s2", price=150.0, quantity=10, side="sell", symbol="X", owner_id="a")
    assert "s2" not in ob.order_map, "order priced far outside band should be rejected"


def test_market_order_sweeps_multiple_levels():
    ob, eng = mk_engine()
    submit(eng, id="s1", price=100.0, quantity=5, side="sell", symbol="X", owner_id="a")
    submit(eng, id="s2", price=101.0, quantity=5, side="sell", symbol="X", owner_id="a")
    mkt = Order(id="m1", price=0.0, quantity=10, side="buy", type="market", symbol="X", owner_id="b")
    eng.match_order(mkt)
    assert mkt.quantity == 0
    assert ob.get_best_ask() is None


def test_halt_blocks_new_orders():
    ob, eng = mk_engine()
    eng.halt("X")
    submit(eng, id="b1", price=100.0, quantity=10, side="buy", symbol="X")
    assert "b1" not in ob.order_map
    eng.resume("X")
    submit(eng, id="b2", price=100.0, quantity=10, side="buy", symbol="X")
    assert "b2" in ob.order_map
