import pytest

from trading_simulator import EventBus, make_redis_publisher, make_kafka_publisher, REDIS_AVAILABLE, KAFKA_AVAILABLE


def test_event_bus_fans_out_to_all_publishers():
    bus = EventBus()
    calls_a, calls_b = [], []
    bus.add_publisher(lambda evt, data: calls_a.append((evt, data)))
    bus.add_publisher(lambda evt, data: calls_b.append((evt, data)))
    bus.publish("execution", {"symbol": "X", "price": 100.0})
    assert calls_a == [("execution", {"symbol": "X", "price": 100.0})]
    assert calls_b == calls_a


def test_event_bus_one_publisher_failing_does_not_break_others():
    bus = EventBus()
    calls = []

    def bad_publisher(evt, data):
        raise RuntimeError("boom")

    bus.add_publisher(bad_publisher)
    bus.add_publisher(lambda evt, data: calls.append((evt, data)))
    bus.publish("execution", {"symbol": "X"})  # must not raise
    assert calls == [("execution", {"symbol": "X"})]


def test_redis_publisher_unavailable_raises_clear_error():
    if REDIS_AVAILABLE:
        pytest.skip("redis is installed in this environment")
    with pytest.raises(RuntimeError):
        make_redis_publisher("redis://localhost:6379", "trading_events")


def test_kafka_publisher_unavailable_raises_clear_error():
    if KAFKA_AVAILABLE:
        pytest.skip("confluent-kafka is installed in this environment")
    with pytest.raises(RuntimeError):
        make_kafka_publisher("localhost:9092", "trading_events")


def test_engine_trades_can_feed_event_bus():
    """Integration: the documented usage pattern of wiring MatchingEngine
    executions into an EventBus publisher."""
    from trading_simulator import Order, OrderBook, MatchingEngine

    ob = OrderBook()
    eng = MatchingEngine(ob)
    bus = EventBus()
    seen = []
    bus.add_publisher(lambda evt, data: seen.append((evt, data)))
    eng.subscribe_trades(lambda execu: bus.publish("execution", {"symbol": execu.symbol, "price": execu.price, "quantity": execu.quantity}))

    eng.match_order(Order(id="s1", price=10.0, quantity=5, side="sell", type="limit", symbol="X", owner_id="a"))
    eng.match_order(Order(id="b1", price=10.0, quantity=5, side="buy", type="limit", symbol="X", owner_id="b"))

    assert len(seen) == 1
    assert seen[0][0] == "execution"
    assert seen[0][1]["symbol"] == "X"
