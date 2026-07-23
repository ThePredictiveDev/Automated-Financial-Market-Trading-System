import pytest

from trading_simulator import Order, OrderBook, MatchingEngine, Venue, MarketRouter


def mk_venue(name, fee_bps=0.0, latency_ms=0):
    ob = OrderBook()
    eng = MatchingEngine(ob)
    return Venue(name, eng, fee_bps=fee_bps, latency_ms=latency_ms), ob, eng


def test_nbbo_aggregates_best_prices_across_venues():
    va, oba, ea = mk_venue("A")
    vb, obb, eb = mk_venue("B")
    ea.match_order(Order(id="a-ask", price=100.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))
    eb.match_order(Order(id="b-ask", price=99.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))
    eb.match_order(Order(id="b-bid", price=95.0, quantity=50, side="buy", type="limit", symbol="X", owner_id="mm"))

    router = MarketRouter()
    router.add_venue(va)
    router.add_venue(vb)
    nbbo = router.nbbo()
    assert nbbo["best_ask"] == 99.0
    assert nbbo["best_bid"] == 95.0
    assert len(nbbo["venues"]) == 2


def test_route_order_raises_with_no_venues():
    router = MarketRouter()
    with pytest.raises(RuntimeError):
        router.route_order(Order(id="m1", price=0.0, quantity=10, side="buy", type="market", symbol="X", owner_id="t"))


def test_single_venue_routing_picks_cheapest_venue():
    va, oba, ea = mk_venue("A")
    vb, obb, eb = mk_venue("B")
    ea.match_order(Order(id="a-ask", price=100.0, quantity=100, side="sell", type="limit", symbol="X", owner_id="mm"))
    eb.match_order(Order(id="b-ask", price=99.0, quantity=100, side="sell", type="limit", symbol="X", owner_id="mm"))

    router = MarketRouter()
    router.inter_market_sweep = False
    router.add_venue(va)
    router.add_venue(vb)
    router.route_order(Order(id="m1", price=0.0, quantity=30, side="buy", type="market", symbol="X", owner_id="trader"))

    assert obb.depth_at("sell", 99.0) == 70   # filled at the cheaper venue
    assert oba.depth_at("sell", 100.0) == 100  # untouched


def test_inter_market_sweep_splits_across_venues_by_depth():
    va, oba, ea = mk_venue("A")
    vb, obb, eb = mk_venue("B")
    ea.match_order(Order(id="a-ask", price=100.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))
    eb.match_order(Order(id="b-ask", price=99.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))

    router = MarketRouter()
    router.add_venue(va)
    router.add_venue(vb)
    router.route_order(Order(id="m1", price=0.0, quantity=80, side="buy", type="market", symbol="X", owner_id="trader"))

    # Cheaper venue B (50 shares available) fills first, remaining 30 sweeps to A.
    assert obb.get_best_ask() is None  # fully consumed
    assert oba.depth_at("sell", 100.0) == 20  # 50 - 30 remaining


def test_sweep_fee_bps_affects_venue_selection():
    """A venue with a slightly better price but a high taker fee should lose
    to a venue with a worse headline price but lower effective (fee-adjusted) cost."""
    va, oba, ea = mk_venue("A", fee_bps=0.0)
    vb, obb, eb = mk_venue("B", fee_bps=200.0)  # 2% taker fee
    ea.match_order(Order(id="a-ask", price=100.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))
    eb.match_order(Order(id="b-ask", price=99.0, quantity=50, side="sell", type="limit", symbol="X", owner_id="mm"))
    # effective price at B = 99 * 1.02 = 100.98, worse than A's 100.0 even though headline price is lower

    router = MarketRouter()
    router.inter_market_sweep = False
    router.add_venue(va)
    router.add_venue(vb)
    router.route_order(Order(id="m1", price=0.0, quantity=10, side="buy", type="market", symbol="X", owner_id="trader"))

    assert oba.depth_at("sell", 100.0) == 40   # filled at A despite B's lower headline price
    assert obb.depth_at("sell", 99.0) == 50    # B untouched
