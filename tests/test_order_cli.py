import json
import socket

import pytest

from trading_simulator import Order, OrderBook, MatchingEngine, OrderCliServer


@pytest.fixture
def server():
    ob = OrderBook()
    eng = MatchingEngine(ob)
    srv = OrderCliServer(eng, host="127.0.0.1", port=0)  # port=0 -> OS assigns a free ephemeral port
    srv.start()  # blocks until actually listening (fixes a real start/connect race)
    yield srv, ob, eng
    srv.stop()


def _send(port, payload):
    with socket.create_connection(("127.0.0.1", port), timeout=5) as sock:
        sock.sendall(json.dumps(payload).encode("utf-8"))
        return json.loads(sock.recv(8192).decode("utf-8"))


def test_new_order_via_socket_lands_in_book(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "new", "symbol": "X", "side": "buy", "type": "limit",
                             "price": 100.0, "quantity": 10, "owner_id": "cli_user"})
    assert resp["ok"] is True
    assert resp["order_id"] in ob.order_map
    assert ob.get_best_bid() == 100.0


def test_cancel_via_socket(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "new", "symbol": "X", "side": "buy", "type": "limit", "price": 100.0, "quantity": 10})
    oid = resp["order_id"]
    assert oid in ob.order_map
    resp2 = _send(srv.port, {"action": "cancel", "order_id": oid})
    assert resp2["ok"] is True
    assert oid not in ob.order_map


def test_modify_via_socket(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "new", "symbol": "X", "side": "buy", "type": "limit", "price": 100.0, "quantity": 10})
    oid = resp["order_id"]
    resp2 = _send(srv.port, {"action": "modify", "order_id": oid, "quantity": 25, "price": 101.0})
    assert resp2["ok"] is True
    assert ob.order_map[oid].quantity == 25
    assert ob.order_map[oid].price == 101.0


def test_unknown_action_returns_error_not_crash(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "frobnicate"})
    assert resp["ok"] is False
    assert "error" in resp


def test_malformed_json_returns_error_not_crash(server):
    srv, ob, eng = server
    with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as sock:
        sock.sendall(b"{not valid json")
        resp = json.loads(sock.recv(8192).decode("utf-8"))
    assert resp["ok"] is False


def test_new_order_missing_required_field_returns_error(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "new", "side": "buy", "price": 100.0, "quantity": 10})  # no symbol
    assert resp["ok"] is False


def test_cancel_unknown_order_id_still_returns_ok(server):
    srv, ob, eng = server
    resp = _send(srv.port, {"action": "cancel", "order_id": "does-not-exist"})
    # Cancelling a nonexistent id is a benign no-op at the OrderBook level
    assert resp["ok"] is True


def test_server_handles_multiple_sequential_connections(server):
    srv, ob, eng = server
    for i in range(5):
        resp = _send(srv.port, {"action": "new", "symbol": "X", "side": "sell", "type": "limit",
                                 "price": 105.0 + i, "quantity": 1, "owner_id": f"c{i}"})
        assert resp["ok"] is True
    assert len(ob.asks) == 5
