"""FIX 4.2 order-entry adapter with a real session layer, built on top of
`fix_session.FixSessionState` (see that module for the sequencing/Logon/
Heartbeat/resend logic and its honesty notes about what this sandbox could
and couldn't execute while building it).

`FixApplication` is the acceptor (server) side: it requires a proper Logon
before accepting any business message, answers Heartbeat/TestRequest/
ResendRequest/Logout correctly, and turns order flow into real FIX messages
back to the client -- ExecutionReport (35=8) on acceptance/fill/cancel,
Reject (35=3) on malformed input -- instead of the single raw ack byte the
very first version of this adapter used.

`FixClient` is the initiator (client) side: connects, logs on, sends
NewOrderSingle/OrderCancelRequest with correct sequence numbers, and collects
ExecutionReports so the two actually form a complete, usable round trip
rather than a server nothing real talks to.

Honest scope, still: this is a simplified educational/simulator-grade FIX
engine, not a certified one. No encryption, no FIX 5.0/FIXT split-session
profile, no message store that survives a process restart, no out-of-order
message buffering (see fix_session.py). Good enough to actually hold a
session, detect and recover from a dropped message, and round-trip real
orders and fills -- not good enough to put in front of a real venue.
"""
from __future__ import annotations

import logging
import socket
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..core.order import Order, OrderValidationError
from .fix_session import FixSessionState, FixSessionError

logger = logging.getLogger(__name__)

try:
    import simplefix  # type: ignore
    SIMPLEFIX_AVAILABLE = True
except ImportError:
    simplefix = None  # type: ignore
    SIMPLEFIX_AVAILABLE = False

FIX_TAGS: Dict[int, str] = {
    8: "BeginString", 9: "BodyLength", 35: "MsgType", 34: "MsgSeqNum", 49: "SenderCompID",
    56: "TargetCompID", 52: "SendingTime", 10: "Checksum",
    11: "ClOrdID", 41: "OrigClOrdID", 54: "Side", 55: "Symbol", 44: "Price", 38: "OrderQty",
    98: "EncryptMethod", 108: "HeartBtInt", 141: "ResetSeqNumFlag", 43: "PossDupFlag",
    112: "TestReqID", 58: "Text", 7: "BeginSeqNo", 16: "EndSeqNo", 123: "GapFillFlag", 36: "NewSeqNo",
    37: "OrderID", 39: "OrdStatus", 150: "ExecType", 17: "ExecID", 6: "AvgPx", 14: "CumQty",
    151: "LeavesQty", 60: "TransactTime", 45: "RefSeqNum", 372: "RefMsgType", 373: "SessionRejectReason",
}
SIDE_MAPPING = {"1": "Buy", "2": "Sell"}
SIDE_TO_FIX = {"buy": "1", "sell": "2"}
MSG_TYPE_MAPPING = {
    "D": "NewOrderSingle", "F": "OrderCancelRequest", "8": "ExecutionReport", "3": "Reject",
    "A": "Logon", "0": "Heartbeat", "1": "TestRequest", "2": "ResendRequest", "4": "SequenceReset", "5": "Logout",
}

# OrdStatus / ExecType values used by this adapter (FIX 4.2 codes).
EXEC_NEW, EXEC_PARTIAL, EXEC_FILL, EXEC_CANCELED, EXEC_REJECTED = "0", "1", "2", "4", "8"


def _reverse_msg_type(name: str) -> str:
    for code, human in MSG_TYPE_MAPPING.items():
        if human == name:
            return code
    return name


class _OrderRoute:
    """Tracks a FIX-originated order so fills/cancels can be turned back into
    ExecutionReports on the right connection."""
    __slots__ = ("sock", "session", "cl_ord_id", "symbol", "side", "orig_qty", "cum_qty", "price")

    def __init__(self, sock, session, cl_ord_id, symbol, side, orig_qty, price):
        self.sock = sock
        self.session = session
        self.cl_ord_id = cl_ord_id
        self.symbol = symbol
        self.side = side
        self.orig_qty = orig_qty
        self.cum_qty = 0
        self.price = price


class FixApplication:
    def __init__(self, matching_engine, sender_comp_id: str = "SIMULATOR",
                 target_comp_id: str = "CLIENT", heartbeat_interval: int = 30) -> None:
        if not SIMPLEFIX_AVAILABLE:
            raise RuntimeError("simplefix is not installed; `pip install simplefix` to use FixApplication")
        self.matching_engine = matching_engine
        self.sender_comp_id = sender_comp_id
        self.target_comp_id = target_comp_id
        self.heartbeat_interval = int(heartbeat_interval)
        self.server_socket: Optional[socket.socket] = None
        self.running = False
        self._threads: List[threading.Thread] = []
        self._lock = threading.RLock()
        self._connections: Dict[int, Tuple[socket.socket, FixSessionState]] = {}
        self._routes_by_cl_ord_id: Dict[str, _OrderRoute] = {}
        self._next_exec_id = 1
        self.matching_engine.subscribe_trades(self._on_execution)

    # -- wire helpers --------------------------------------------------------
    def _send(self, sock: socket.socket, fields: Dict[str, str]) -> None:
        msg = simplefix.FixMessage()
        msg.append_pair(8, b"FIX.4.2")
        msg.append_pair(35, fields["MsgType"].encode())
        for name, value in fields.items():
            if name == "MsgType":
                continue
            tag = next((t for t, n in FIX_TAGS.items() if n == name), None)
            if tag is not None:
                msg.append_pair(tag, str(value).encode())
        try:
            sock.sendall(msg.encode())
        except OSError:
            logger.warning("FIX send failed (peer likely disconnected)")

    def translate_fix_message(self, parsed_msg) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for tag, value in parsed_msg:
            value = value.decode() if isinstance(value, (bytes, bytearray)) else str(value)
            field_name = FIX_TAGS.get(tag, f"Unknown({tag})")
            if field_name == "Side":
                value = SIDE_MAPPING.get(value, value)
            if field_name == "MsgType":
                value = MSG_TYPE_MAPPING.get(value, value)
            out[field_name] = value
        return out

    def _next_exec_id_str(self) -> str:
        with self._lock:
            eid = self._next_exec_id
            self._next_exec_id += 1
        return f"EXEC{eid}"

    # -- business message handling -------------------------------------------
    def _handle_new_order(self, sock, session: FixSessionState, msg: Dict[str, str]) -> None:
        cl_ord_id = msg.get("ClOrdID", uuid.uuid4().hex)
        try:
            side_human = msg["Side"].lower()
            order = Order(
                id=uuid.uuid4().hex, symbol=msg["Symbol"], side=side_human, type="limit",
                price=float(msg["Price"]), quantity=int(msg["OrderQty"]), owner_id="fix",
            )
            order.validate()
        except (KeyError, ValueError, OrderValidationError) as exc:
            self._send(sock, self._reject_fields(session, msg, "D", f"malformed NewOrderSingle: {exc}"))
            return

        route = _OrderRoute(sock, session, cl_ord_id, order.symbol, side_human, order.quantity, order.price)
        with self._lock:
            self._routes_by_cl_ord_id[order.id] = route
            self._routes_by_cl_ord_id[cl_ord_id] = route  # look-uppable by either id

        self.matching_engine.match_order(order)
        logger.info("FIX new order processed: %s (ClOrdID=%s)", order.id, cl_ord_id)

        # Acknowledge acceptance (OrdStatus=New) -- a fill, if any happened
        # synchronously inside match_order(), will have already fired
        # _on_execution and sent its own ExecutionReport; this New ack still
        # goes out so the client sees both, exactly like a real venue.
        self._send(sock, self._exec_report_fields(
            session, route, exec_type=EXEC_NEW, ord_status=EXEC_NEW,
            last_qty=0, last_px=0.0, order_id=order.id,
        ))

    def _handle_cancel(self, sock, session: FixSessionState, msg: Dict[str, str]) -> None:
        try:
            orig_id = msg["OrigClOrdID"]
        except KeyError as exc:
            self._send(sock, self._reject_fields(session, msg, "F", f"malformed OrderCancelRequest: {exc}"))
            return
        with self._lock:
            route = self._routes_by_cl_ord_id.get(orig_id)
        self.matching_engine.cancel_order(orig_id)
        logger.info("FIX cancel processed for %s", orig_id)
        if route is not None:
            # Best-effort ack: the engine doesn't distinguish "cancelled" from
            # "already filled/unknown" in its return value, so this reflects
            # cancel *intent* accepted, not a guaranteed book-side outcome.
            self._send(sock, self._exec_report_fields(
                session, route, exec_type=EXEC_CANCELED, ord_status=EXEC_CANCELED,
                last_qty=0, last_px=0.0, order_id=orig_id,
            ))
        else:
            self._send(sock, self._reject_fields(session, msg, "F", f"unknown OrigClOrdID {orig_id!r}"))

    def _reject_fields(self, session: FixSessionState, msg: Dict[str, str], ref_msg_type: str, text: str) -> Dict[str, str]:
        return session.prepare_outgoing("3", {
            "RefSeqNum": msg.get("MsgSeqNum", "0"), "RefMsgType": ref_msg_type,
            "SessionRejectReason": "5", "Text": text,
        })

    def _exec_report_fields(self, session: FixSessionState, route: _OrderRoute, exec_type: str, ord_status: str,
                             last_qty: int, last_px: float, order_id: str) -> Dict[str, str]:
        leaves = max(0, route.orig_qty - route.cum_qty)
        return session.prepare_outgoing("8", {
            "OrderID": order_id, "ClOrdID": route.cl_ord_id, "ExecID": self._next_exec_id_str(),
            "ExecType": exec_type, "OrdStatus": ord_status, "Symbol": route.symbol,
            "Side": SIDE_TO_FIX.get(route.side, "1"), "OrderQty": str(route.orig_qty),
            "Price": str(route.price), "AvgPx": str(route.price), "CumQty": str(route.cum_qty),
            "LeavesQty": str(leaves), "TransactTime": str(time.time()),
        })

    def _on_execution(self, execution) -> None:
        """Subscribed to the matching engine's trade feed; turns fills
        belonging to FIX-originated orders into ExecutionReport (Partial)Fill
        messages sent back on the originating connection."""
        for order_id in (execution.taker_order_id, execution.maker_order_id):
            with self._lock:
                route = self._routes_by_cl_ord_id.get(order_id)
            if route is None:
                continue
            route.cum_qty += int(execution.quantity)
            leaves = max(0, route.orig_qty - route.cum_qty)
            exec_type = EXEC_FILL if leaves == 0 else EXEC_PARTIAL
            try:
                self._send(route.sock, self._exec_report_fields(
                    route.session, route, exec_type=exec_type, ord_status=exec_type,
                    last_qty=execution.quantity, last_px=execution.price, order_id=order_id,
                ))
            except Exception:
                logger.warning("Failed to send ExecutionReport for fill on %s", order_id, exc_info=True)

    def _dispatch_business(self, sock, session: FixSessionState, msg: Dict[str, str]) -> None:
        msg_type = msg.get("MsgType")
        if msg_type == "NewOrderSingle":
            self._handle_new_order(sock, session, msg)
        elif msg_type == "OrderCancelRequest":
            self._handle_cancel(sock, session, msg)
        else:
            self._send(sock, self._reject_fields(session, msg, str(msg_type), f"unsupported message type {msg_type!r}"))

    # -- connection lifecycle -------------------------------------------------
    def _watchdog(self, sock, session: FixSessionState, conn_id: int) -> None:
        while session.logged_on and not session.closed and self.running:
            time.sleep(1.0)
            try:
                if session.due_for_disconnect():
                    logger.warning("FIX session %s: counterparty unresponsive, disconnecting", conn_id)
                    try:
                        sock.close()
                    except OSError:
                        pass
                    return
                if session.due_for_test_request():
                    session._test_request_pending = True
                    self._send(sock, session.prepare_outgoing("1", {"TestReqID": f"TR{int(time.time())}"}))
                elif session.due_for_heartbeat():
                    self._send(sock, session.build_heartbeat())
            except OSError:
                return

    def _handle_connection(self, client_socket: socket.socket, addr) -> None:
        parser = simplefix.parser.FixParser()
        session = FixSessionState(role="acceptor", sender_comp_id=self.sender_comp_id,
                                   target_comp_id=self.target_comp_id, heartbeat_interval=self.heartbeat_interval)
        conn_id = id(client_socket)
        with self._lock:
            self._connections[conn_id] = (client_socket, session)
        logger.info("FIX connection from %s", addr)
        watchdog_thread = threading.Thread(target=self._watchdog, args=(client_socket, session, conn_id), daemon=True)
        try:
            while self.running:
                data = client_socket.recv(4096)
                if not data:
                    break
                parser.append_buffer(data)
                while True:
                    parsed = parser.get_message()
                    if parsed is None:
                        break
                    try:
                        translated = self.translate_fix_message(parsed)
                        # session.handle_incoming expects the *raw* FIX msg type
                        # code (not the human name) so gap/Logon/etc. logic keys
                        # off "A"/"0"/"D" etc. -- reverse-translate MsgType back.
                        raw = dict(translated)
                        raw["MsgType"] = _reverse_msg_type(translated.get("MsgType", ""))
                        actions, is_business = session.handle_incoming(raw)
                        if not watchdog_thread.is_alive() and session.logged_on:
                            watchdog_thread.start()
                        for action in actions:
                            self._send(client_socket, action)
                        if is_business:
                            self._dispatch_business(client_socket, session, translated)
                        if session.closed:
                            client_socket.close()
                            return
                    except FixSessionError as exc:
                        logger.warning("FIX protocol violation from %s: %s", addr, exc)
                        try:
                            self._send(client_socket, session.build_logout(text=str(exc)))
                        finally:
                            client_socket.close()
                        return
                    except (KeyError, ValueError) as exc:
                        logger.warning("Malformed/unsupported FIX message: %s", exc)
        except OSError:
            pass
        finally:
            with self._lock:
                self._connections.pop(conn_id, None)
            try:
                client_socket.close()
            except OSError:
                pass

    def start(self, host: str = "localhost", port: int = 5005) -> None:
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(8)
        self.running = True
        logger.info("FIX server listening on %s:%d", host, port)
        while self.running:
            try:
                client_socket, addr = self.server_socket.accept()
            except OSError:
                break
            t = threading.Thread(target=self._handle_connection, args=(client_socket, addr), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self.running = False
        with self._lock:
            conns = list(self._connections.values())
        for sock, session in conns:
            try:
                self._send(sock, session.build_logout(text="server shutting down"))
                sock.close()
            except OSError:
                pass
        if self.server_socket:
            self.server_socket.close()
        logger.info("FIX server stopped.")

    # -- legacy one-shot helpers (no session semantics -- kept for anyone
    # already depending on them; FixClient is the real way to talk to this
    # server now) ------------------------------------------------------------
    def create_order_message(self, order: Dict[str, Any]):
        msg = simplefix.FixMessage()
        msg.append_pair(8, b"FIX.4.2")
        msg.append_pair(35, b"D")
        msg.append_pair(11, str(order["id"]).encode())
        msg.append_pair(54, b"1" if order["side"] == "buy" else b"2")
        msg.append_pair(55, str(order["symbol"]).encode())
        msg.append_pair(44, str(order["price"]).encode())
        msg.append_pair(38, str(order["quantity"]).encode())
        return msg

    def send_message(self, msg, host: str = "localhost", port: int = 5005) -> None:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, port))
        client_socket.sendall(msg.encode())
        response = client_socket.recv(1024)
        logger.info("FIX response: %s", response.decode(errors="ignore"))
        client_socket.close()


class FixClient:
    """The initiator side of a real FIX session: connects, logs on, sends
    orders/cancels with correctly sequenced headers, and collects
    ExecutionReports. This is what actually exercises `FixApplication` end to
    end -- without it, the acceptor above is a server nothing real talks to."""

    def __init__(self, sender_comp_id: str = "CLIENT", target_comp_id: str = "SIMULATOR",
                 heartbeat_interval: int = 30) -> None:
        if not SIMPLEFIX_AVAILABLE:
            raise RuntimeError("simplefix is not installed; `pip install simplefix` to use FixClient")
        self.sender_comp_id = sender_comp_id
        self.target_comp_id = target_comp_id
        self.heartbeat_interval = int(heartbeat_interval)
        self.sock: Optional[socket.socket] = None
        self.session: Optional[FixSessionState] = None
        self._parser = None
        self._lock = threading.RLock()
        self._running = False
        self._recv_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None
        self.execution_reports: List[Dict[str, str]] = []
        self._exec_report_event = threading.Event()

    def _send(self, fields: Dict[str, str]) -> None:
        msg = simplefix.FixMessage()
        msg.append_pair(8, b"FIX.4.2")
        msg.append_pair(35, fields["MsgType"].encode())
        for name, value in fields.items():
            if name == "MsgType":
                continue
            tag = next((t for t, n in FIX_TAGS.items() if n == name), None)
            if tag is not None:
                msg.append_pair(tag, str(value).encode())
        self.sock.sendall(msg.encode())

    def connect(self, host: str = "localhost", port: int = 5005, timeout: float = 5.0) -> None:
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.session = FixSessionState(role="initiator", sender_comp_id=self.sender_comp_id,
                                        target_comp_id=self.target_comp_id, heartbeat_interval=self.heartbeat_interval)
        self._parser = simplefix.parser.FixParser()
        self._running = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        self._send(self.session.build_logon())

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.session.logged_on:
                self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
                self._watchdog_thread.start()
                return
            time.sleep(0.05)
        raise TimeoutError(f"FIX Logon to {host}:{port} was not acknowledged within {timeout}s")

    def _watchdog(self) -> None:
        while self._running and self.session and not self.session.closed:
            time.sleep(1.0)
            try:
                if self.session.due_for_disconnect():
                    self.close()
                    return
                if self.session.due_for_test_request():
                    self.session._test_request_pending = True
                    self._send(self.session.prepare_outgoing("1", {"TestReqID": f"TR{int(time.time())}"}))
                elif self.session.due_for_heartbeat():
                    self._send(self.session.build_heartbeat())
            except OSError:
                return

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data = self.sock.recv(4096)
            except OSError:
                return
            if not data:
                return
            self._parser.append_buffer(data)
            while True:
                parsed = self._parser.get_message()
                if parsed is None:
                    break
                translated: Dict[str, str] = {}
                for tag, value in parsed:
                    value = value.decode() if isinstance(value, (bytes, bytearray)) else str(value)
                    name = FIX_TAGS.get(tag, f"Unknown({tag})")
                    if name == "Side":
                        value = SIDE_MAPPING.get(value, value)
                    translated[name] = value
                raw = dict(translated)
                raw["MsgType"] = _reverse_msg_type(translated.get("MsgType", ""))
                try:
                    actions, is_business = self.session.handle_incoming(raw)
                except FixSessionError:
                    continue
                for action in actions:
                    try:
                        self._send(action)
                    except OSError:
                        pass
                if is_business and raw.get("MsgType") == "8":
                    with self._lock:
                        self.execution_reports.append(translated)
                    self._exec_report_event.set()

    def send_new_order(self, symbol: str, side: str, price: float, quantity: int,
                        tif: str = "GTC", cl_ord_id: Optional[str] = None) -> str:
        cl_ord_id = cl_ord_id or uuid.uuid4().hex
        self._send(self.session.prepare_outgoing("D", {
            "ClOrdID": cl_ord_id, "Symbol": symbol, "Side": SIDE_TO_FIX.get(side.lower(), "1"),
            "Price": str(price), "OrderQty": str(quantity),
        }))
        return cl_ord_id

    def send_cancel(self, orig_cl_ord_id: str, cl_ord_id: Optional[str] = None) -> str:
        cl_ord_id = cl_ord_id or uuid.uuid4().hex
        self._send(self.session.prepare_outgoing("F", {"ClOrdID": cl_ord_id, "OrigClOrdID": orig_cl_ord_id}))
        return cl_ord_id

    def wait_for_execution_report(self, timeout: float = 5.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.execution_reports:
                    return self.execution_reports.pop(0)
            self._exec_report_event.wait(timeout=max(0.0, deadline - time.time()))
            self._exec_report_event.clear()
        return None

    def logout(self, timeout: float = 5.0) -> None:
        if self.session is None or self.session.closed:
            return
        self._send(self.session.build_logout())
        deadline = time.time() + timeout
        while time.time() < deadline and not self.session.closed:
            time.sleep(0.05)
        self.close()

    def close(self) -> None:
        self._running = False
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
