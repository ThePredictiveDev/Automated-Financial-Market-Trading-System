"""Live WebSocket SNAPSHOT bandwidth helpers (H1 / H2 / H4)."""

import asyncio
import time
from unittest.mock import patch

from web_server import (
    SIM_TICK_SECONDS,
    WS_BROADCAST_INTERVAL_SECONDS,
    _chart_history_for_snapshot,
    build_snapshot_payload,
    manager,
    market_simulation_loop,
    state,
)


def test_sim_tick_stays_faster_than_ws_broadcast():
    assert SIM_TICK_SECONDS == 0.4
    assert WS_BROADCAST_INTERVAL_SECONDS == 1.0
    assert WS_BROADCAST_INTERVAL_SECONDS > SIM_TICK_SECONDS


def test_chart_history_full_window_vs_incremental():
    symbol = state.active_symbol
    original = list(state.price_histories[symbol])
    try:
        now = time.time()
        state.price_histories[symbol] = [
            {"timestamp": now - 2, "price": 1.0, "bid": 0.9, "ask": 1.1, "volume": 10},
            {"timestamp": now - 1, "price": 1.1, "bid": 1.0, "ask": 1.2, "volume": 11},
            {"timestamp": now, "price": 1.2, "bid": 1.1, "ask": 1.3, "volume": 12},
        ]
        full = _chart_history_for_snapshot(symbol)
        assert len(full) == 3
        incremental = _chart_history_for_snapshot(symbol, history_since=now - 1.5)
        assert [p["price"] for p in incremental] == [1.1, 1.2]
    finally:
        state.price_histories[symbol] = original


def test_build_snapshot_default_still_includes_full_history_window():
    symbol = state.active_symbol
    original = list(state.price_histories[symbol])
    try:
        now = time.time()
        state.price_histories[symbol] = [
            {
                "timestamp": now - i,
                "price": 100.0 + i,
                "bid": 99.0,
                "ask": 101.0,
                "volume": 10,
            }
            for i in range(80, 0, -1)
        ]
        payload = build_snapshot_payload(symbol)
        assert payload["type"] == "SNAPSHOT"
        assert len(payload["history"]) == 60
        delta = build_snapshot_payload(symbol, history_since=now - 3.5)
        assert 1 <= len(delta["history"]) <= 4
        assert delta["bids"] == payload["bids"]
        assert delta["portfolio"] == payload["portfolio"]
    finally:
        state.price_histories[symbol] = original


def test_manager_starts_with_no_live_ws_subscribers():
    assert len(manager.active_connections) == 0


class _DummyWebSocket:
    def __init__(self):
        self.payloads = []

    async def send_json(self, message):
        self.payloads.append(message)


async def _run_sim_briefly(seconds: float) -> None:
    task = asyncio.create_task(market_simulation_loop())
    try:
        await asyncio.sleep(seconds)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_h4_does_not_build_live_snapshots_without_clients():
    assert not manager.active_connections
    assert not state.recorder.is_recording

    async def _run():
        with patch("web_server.build_snapshot_payload", wraps=build_snapshot_payload) as spy:
            await _run_sim_briefly(1.3)
            return spy.call_count

    assert asyncio.run(_run()) == 0


def test_h2_broadcasts_near_1hz_and_h1_sends_incremental_history():
    dummy = _DummyWebSocket()
    manager.active_connections.add(dummy)
    try:
        asyncio.run(_run_sim_briefly(2.4))
    finally:
        manager.active_connections.discard(dummy)

    snapshots = [p for p in dummy.payloads if p.get("type") == "SNAPSHOT"]
    # First frame at ~1s, second at ~2s. Must not still be 2.5 Hz (~6 frames).
    assert 1 <= len(snapshots) <= 3
    for snap in snapshots:
        assert "bids" in snap and "asks" in snap
        assert "portfolio" in snap
        assert "recent_trades" in snap
        assert "last_price" in snap
    if len(snapshots) >= 2:
        assert len(snapshots[-1]["history"]) <= 8
