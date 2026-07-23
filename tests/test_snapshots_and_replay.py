import os

from trading_simulator import Order, OrderBook, MatchingEngine, EventLogger, ReplayRunner


def test_snapshot_save_and_load_round_trip(tmp_path):
    ob, eng = OrderBook(), None
    eng = MatchingEngine(ob)
    eng.match_order(Order(id="b1", price=99.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="alice"))
    eng.match_order(Order(id="b2", price=100.0, quantity=5, side="buy", type="limit", symbol="X", owner_id="alice"))
    eng.match_order(Order(id="s1", price=105.0, quantity=7, side="sell", type="limit", symbol="X", owner_id="bob"))

    eng.snapshot_dir = str(tmp_path)
    eng.snapshot_now()
    files = os.listdir(tmp_path)
    assert len(files) == 1

    # Load into a fresh engine and verify the book state matches.
    ob2 = OrderBook()
    eng2 = MatchingEngine(ob2)
    eng2.load_snapshot_file(str(tmp_path / files[0]))
    assert ob2.get_best_bid() == 100.0
    assert ob2.get_best_ask() == 105.0
    assert sum(o.quantity for q in ob2.bids.values() for o in q) == 15
    assert sum(o.quantity for q in ob2.asks.values() for o in q) == 7


def test_snapshot_of_empty_book_round_trips_to_empty_book(tmp_path):
    ob, eng = OrderBook(), MatchingEngine(OrderBook())
    eng.snapshot_dir = str(tmp_path)
    eng.snapshot_now()
    files = os.listdir(tmp_path)
    assert len(files) == 1
    ob2 = OrderBook()
    eng2 = MatchingEngine(ob2)
    eng2.load_snapshot_file(str(tmp_path / files[0]))
    assert ob2.get_best_bid() is None
    assert ob2.get_best_ask() is None


def test_event_logger_replay_reproduces_same_fills(tmp_path):
    logger = EventLogger(str(tmp_path))

    ob, eng = OrderBook(), None
    eng = MatchingEngine(ob)
    eng.event_logger = logger
    fills = []
    eng.subscribe_trades(lambda e: fills.append((e.price, e.quantity)))

    eng.match_order(Order(id="s1", price=50.0, quantity=10, side="sell", type="limit", symbol="X", owner_id="alice"))
    eng.match_order(Order(id="b1", price=50.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="bob"))
    logger.log_cancel("nonexistent")  # exercise cancel logging path too

    assert len(fills) == 1

    events = logger.replay()
    new_events = [e for e in events if e["event"] in ("NEW", "CANCEL")]
    replayed = ReplayRunner(new_events).run()

    assert replayed["orders"] == 2
    assert replayed["cancels"] == 1
    replayed_engine = replayed["engine"]
    # The replayed engine independently regenerates its own executions from
    # the same NEW order sequence -- it should reach the same crossed state.
    assert replayed_engine.order_book.get_best_bid() is None
    assert replayed_engine.order_book.get_best_ask() is None


def test_event_logger_replay_with_resting_order_left_open(tmp_path):
    logger = EventLogger(str(tmp_path))
    ob, eng = OrderBook(), MatchingEngine(OrderBook())
    eng = MatchingEngine(ob)
    eng.event_logger = logger
    eng.match_order(Order(id="b1", price=99.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="alice"))

    events = logger.replay()
    replayed = ReplayRunner(events).run()
    assert replayed["orders"] == 1
    assert replayed["engine"].order_book.get_best_bid() == 99.0
