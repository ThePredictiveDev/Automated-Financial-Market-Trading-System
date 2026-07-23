"""Generic pub-sub fan-out plus optional Redis/Kafka publishers.

Regression note: this module existed in the original single-file script
(README advertises it under "Event Streaming: Redis and Kafka integration
for real-time event distribution") but was dropped entirely during the
package rewrite -- an oversight caught by testing the rewrite against the
original feature list rather than just against the code that got ported.

Usage (matches the README's documented pattern):

    from trading_simulator import EventBus, make_redis_publisher

    bus = EventBus()
    bus.add_publisher(make_redis_publisher("redis://localhost:6379", "trading_events"))
    engine.subscribe_trades(lambda execu: bus.publish("execution", {
        "symbol": execu.symbol, "price": execu.price, "quantity": execu.quantity,
    }))
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

try:
    import redis  # type: ignore
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False

try:
    from confluent_kafka import Producer  # type: ignore
    KAFKA_AVAILABLE = True
except ImportError:
    Producer = None  # type: ignore
    KAFKA_AVAILABLE = False


class EventBus:
    """Fans out (event_type, payload) pairs to any number of publisher
    callables. A publisher raising is logged and does not affect the others
    or the caller (event publishing should never break the trading loop)."""

    def __init__(self) -> None:
        self._publishers: List[Callable[[str, Dict[str, Any]], None]] = []

    def add_publisher(self, fn: Callable[[str, Dict[str, Any]], None]) -> None:
        self._publishers.append(fn)

    def publish(self, event_type: str, payload: Dict[str, Any]) -> None:
        for fn in list(self._publishers):
            try:
                fn(event_type, payload)
            except Exception:
                logger.warning("Event publisher %r raised for event %r", fn, event_type, exc_info=True)


def make_redis_publisher(url: str, channel: str) -> Callable[[str, Dict[str, Any]], None]:
    if not REDIS_AVAILABLE:
        raise RuntimeError("redis is not installed; `pip install redis` to use make_redis_publisher")
    client = redis.from_url(url)  # type: ignore[union-attr]
    ch = str(channel)

    def _pub(evt: str, data: Dict[str, Any]) -> None:
        client.publish(ch, json.dumps({"event": evt, "data": data}, default=str))

    return _pub


def make_kafka_publisher(bootstrap_servers: str, topic: str) -> Callable[[str, Dict[str, Any]], None]:
    if not KAFKA_AVAILABLE:
        raise RuntimeError("confluent-kafka is not installed; `pip install confluent-kafka` to use make_kafka_publisher")
    producer = Producer({"bootstrap.servers": bootstrap_servers})  # type: ignore[misc]
    tp = str(topic)

    def _delivery_report(err, msg) -> None:  # type: ignore[no-untyped-def]
        if err is not None:
            logger.warning("Kafka delivery failed: %s", err)

    def _pub(evt: str, data: Dict[str, Any]) -> None:
        producer.produce(tp, json.dumps({"event": evt, "data": data}, default=str), callback=_delivery_report)
        producer.poll(0)

    return _pub
