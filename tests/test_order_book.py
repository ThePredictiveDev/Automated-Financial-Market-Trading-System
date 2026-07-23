import pytest

from trading_simulator import Order, OrderBook


def make_order(**kwargs):
    defaults = dict(id="o1", price=100.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="a")
    defaults.update(kwargs)
    return Order(**defaults)


def test_best_bid_ask_empty():
    ob = OrderBook()
    assert ob.get_best_bid() is None
    assert ob.get_best_ask() is None


def test_price_priority_ordering():
    ob = OrderBook()
    ob.add_order(make_order(id="b1", price=99.0, side="buy"))
    ob.add_order(make_order(id="b2", price=101.0, side="buy"))
    ob.add_order(make_order(id="b3", price=100.0, side="buy"))
    assert ob.get_best_bid() == 101.0

    ob.add_order(make_order(id="a1", price=105.0, side="sell"))
    ob.add_order(make_order(id="a2", price=102.0, side="sell"))
    assert ob.get_best_ask() == 102.0


def test_cancel_and_stale_price_cleanup():
    ob = OrderBook()
    ob.add_order(make_order(id="b1", price=100.0, side="buy"))
    assert ob.get_best_bid() == 100.0
    ob.cancel_order("b1")
    assert ob.get_best_bid() is None
    assert "b1" not in ob.order_map


def test_modify_order_changes_price_and_requeues():
    ob = OrderBook()
    ob.add_order(make_order(id="b1", price=100.0, quantity=10, side="buy"))
    ob.modify_order("b1", new_price=105.0, new_quantity=20)
    assert ob.get_best_bid() == 105.0
    assert ob.order_map["b1"].quantity == 20


def test_cancel_orders_by_owner():
    ob = OrderBook()
    ob.add_order(make_order(id="b1", price=100.0, side="buy", owner_id="alice"))
    ob.add_order(make_order(id="b2", price=101.0, side="buy", owner_id="bob"))
    count = ob.cancel_orders_by_owner("alice")
    assert count == 1
    assert "b1" not in ob.order_map
    assert "b2" in ob.order_map


def test_tick_normalization_rounds_price():
    ob = OrderBook()  # default registry: 1 cent tick
    ob.add_order(make_order(id="b1", price=100.004, side="buy"))
    assert ob.order_map["b1"].price == pytest.approx(100.0)
