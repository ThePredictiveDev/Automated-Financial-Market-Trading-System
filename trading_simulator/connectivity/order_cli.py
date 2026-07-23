"""Minimal JSON-over-TCP order control channel for live mode.

Protocol: one JSON object per connection:
  {"action": "new", "symbol": "AAPL", "side": "buy|sell", "type": "limit|market",
   "price": 150.25, "quantity": 100, "tif": "GTC|IOC|FOK", "owner_id": "cli"}
  {"action": "cancel", "order_id": "..."}
  {"action": "modify", "order_id": "...", "quantity": 50, "price": 150.4}
Response: {"ok": true/false, ...}
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import uuid
from typing import Optional

from ..core.order import Order, OrderValidationError

logger = logging.getLogger(__name__)


class OrderCliServer:
    def __init__(self, matching_engine, host: str = "127.0.0.1", port: int = 8765, default_owner: str = "cli") -> None:
        self.engine = matching_engine
        self.host = host
        self.port = int(port)
        self.default_owner = str(default_owner)
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            raw = conn.recv(8192)
            data = json.loads(raw.decode("utf-8")) if raw else {}
            action = str(data.get("action", "")).lower()
            if action == "new":
                try:
                    order = Order(
                        id=uuid.uuid4().hex, symbol=str(data["symbol"]), side=str(data["side"]).lower(),
                        type=str(data.get("type", "limit")).lower(), price=float(data.get("price", 0.0)),
                        quantity=int(data.get("quantity", 0)), tif=str(data.get("tif", "GTC")).upper(),
                        owner_id=str(data.get("owner_id", self.default_owner)),
                    )
                    order.validate()
                    self.engine.match_order(order)
                    resp = {"ok": True, "order_id": order.id}
                except (KeyError, ValueError, OrderValidationError) as exc:
                    resp = {"ok": False, "error": str(exc)}
            elif action == "cancel":
                try:
                    oid = str(data["order_id"])
                    self.engine.cancel_order(oid)
                    resp = {"ok": True, "order_id": oid}
                except KeyError as exc:
                    resp = {"ok": False, "error": str(exc)}
            elif action == "modify":
                try:
                    oid = str(data["order_id"])
                    q, p = data.get("quantity"), data.get("price")
                    self.engine.order_book.modify_order(oid, new_quantity=int(q) if q is not None else None,
                                                        new_price=float(p) if p is not None else None)
                    resp = {"ok": True, "order_id": oid}
                except (KeyError, ValueError) as exc:
                    resp = {"ok": False, "error": str(exc)}
            else:
                resp = {"ok": False, "error": f"unknown action {action!r}"}
            conn.sendall(json.dumps(resp).encode("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            try:
                conn.sendall(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))
            except OSError:
                pass
        finally:
            conn.close()

    def _serve(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        # If port=0 was requested, record the OS-assigned ephemeral port so
        # callers (and tests) can discover it via `.port` after `start()`
        # instead of having to guess or hardcode one.
        self.port = self._sock.getsockname()[1]
        self._sock.listen(8)
        self._running = True
        logger.info("Order CLI server listening on %s:%d", self.host, self.port)
        self._ready.set()
        while self._running:
            try:
                conn, _ = self._sock.accept()
                threading.Thread(target=self._handle_conn, args=(conn,), daemon=True).start()
            except OSError:
                break

    def start(self, wait_ready: bool = True, timeout: float = 5.0) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        if wait_ready:
            self._ready.wait(timeout=timeout)

    def stop(self) -> None:
        self._running = False
        if self._sock is not None:
            self._sock.close()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
