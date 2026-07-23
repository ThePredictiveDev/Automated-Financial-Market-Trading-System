"""FIX session-layer state machine: Logon/Heartbeat/TestRequest/ResendRequest/
SequenceReset/Logout, with real MsgSeqNum tracking in both directions and
gap-triggered resend with true message replay (not just gap-fill).

Deliberately decoupled from `simplefix` and sockets: everything here operates
on plain dicts of {FIX field name: string value} and returns lists of outgoing
message dicts for the caller to wire-encode and transmit. Two reasons for this
split:

1. It makes the actual hard part -- sequence tracking, gap detection, replay,
   heartbeat/test-request timing, Logon negotiation -- fully unit-testable
   without a live socket or even `simplefix` installed. `FixApplication` and
   `FixClient` (in fix_app.py) are the thin, simplefix-dependent glue that
   turns these dicts into real wire bytes and back.
2. This sandbox has no network access to `pip install simplefix`, so the
   wire-encoding path itself can't be executed and proven here the way every
   other feature in this codebase was validated (by actually running it).
   The session logic in *this* file is proven by `tests/test_fix_session.py`,
   which runs with zero external dependencies. If you have `simplefix`
   installed locally, running a real two-process Logon/order/ExecutionReport
   exchange via `FixApplication` + `FixClient` is the next thing to verify.

Honest scope: this is still not a certified FIX engine. No encryption
(EncryptMethod is always "0" / none), no FIX 5.0/FIXT split-session profile,
no message store that survives a process restart (resend only works for
messages sent earlier in the *same* running session), and no out-of-order
message buffering -- a message that arrives ahead of a detected gap is not
queued for later re-processing, it's dropped and a ResendRequest is issued
for the missing range. That covers the common case (a dropped/reordered
packet) without the added complexity of a full reassembly buffer.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SESSION_MSG_TYPES = {"A", "0", "1", "2", "4", "5"}  # Logon, Heartbeat, TestRequest, ResendRequest, SequenceReset, Logout


class FixSessionError(Exception):
    """Raised for protocol violations the caller must act on (e.g. a business
    message arriving before Logon)."""


@dataclass
class FixSessionState:
    role: str                       # "acceptor" or "initiator"
    sender_comp_id: str
    target_comp_id: str
    heartbeat_interval: int = 30
    now_fn: Callable[[], float] = field(default=time.monotonic)

    next_out_seq: int = field(default=1, init=False)
    next_in_seq: int = field(default=1, init=False)
    logged_on: bool = field(default=False, init=False)
    closed: bool = field(default=False, init=False)

    _sent_messages: Dict[int, Dict[str, str]] = field(default_factory=dict, init=False)
    _last_sent_time: float = field(default=0.0, init=False)
    _last_received_time: float = field(default=0.0, init=False)
    _test_request_pending: bool = field(default=False, init=False)
    _logout_initiated: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        now = self.now_fn()
        self._last_sent_time = now
        self._last_received_time = now

    # -- outgoing ----------------------------------------------------------
    def _header(self, msg_type: str) -> Dict[str, str]:
        return {
            "MsgType": msg_type,
            "MsgSeqNum": str(self.next_out_seq),
            "SenderCompID": self.sender_comp_id,
            "TargetCompID": self.target_comp_id,
            "SendingTime": str(self.now_fn()),
        }

    def prepare_outgoing(self, msg_type: str, body: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """Assigns the next outgoing MsgSeqNum, records the full message for
        possible later resend, and returns it for the caller to wire-encode
        and transmit. Every call consumes exactly one sequence number --
        callers must only call this once per message actually sent."""
        full = self._header(msg_type)
        full.update(body or {})
        self._sent_messages[self.next_out_seq] = full
        self.next_out_seq += 1
        self._last_sent_time = self.now_fn()
        return full

    def build_logon(self, reset_seq_num: bool = False) -> Dict[str, str]:
        body = {"EncryptMethod": "0", "HeartBtInt": str(self.heartbeat_interval)}
        if reset_seq_num:
            body["ResetSeqNumFlag"] = "Y"
            self.next_out_seq = 1
            self.next_in_seq = 1
        return self.prepare_outgoing("A", body)

    def build_logout(self, text: str = "") -> Dict[str, str]:
        self._logout_initiated = True
        body = {"Text": text} if text else {}
        return self.prepare_outgoing("5", body)

    def build_heartbeat(self, test_req_id: str = "") -> Dict[str, str]:
        body = {"TestReqID": test_req_id} if test_req_id else {}
        return self.prepare_outgoing("0", body)

    # -- heartbeat/test-request timing --------------------------------------
    def seconds_since_last_receive(self) -> float:
        return self.now_fn() - self._last_received_time

    def seconds_since_last_send(self) -> float:
        return self.now_fn() - self._last_sent_time

    def due_for_heartbeat(self) -> bool:
        """True if we haven't sent anything in a full heartbeat interval and
        should send an unsolicited Heartbeat to keep the session alive."""
        return self.logged_on and not self.closed and self.seconds_since_last_send() >= self.heartbeat_interval

    def due_for_test_request(self) -> bool:
        """True if the counterparty has gone quiet for 1.5x the heartbeat
        interval and we haven't already challenged them."""
        return (self.logged_on and not self.closed and not self._test_request_pending
                and self.seconds_since_last_receive() >= self.heartbeat_interval * 1.5)

    def due_for_disconnect(self) -> bool:
        """True if we already sent a TestRequest and still heard nothing
        within a further 1x heartbeat interval -- the connection is dead."""
        return (self._test_request_pending and not self.closed
                and self.seconds_since_last_receive() >= self.heartbeat_interval * 2.5)

    # -- incoming ------------------------------------------------------------
    def handle_incoming(self, msg: Dict[str, str]):
        """Returns (outgoing_actions, is_business_message).

        `outgoing_actions` is a list of message dicts (already run through
        `prepare_outgoing`) the caller must wire-encode and send in response.
        `is_business_message` tells the caller whether it should ALSO run its
        own application-level dispatch (NewOrderSingle -> matching engine,
        ExecutionReport -> user callback, etc.) for this message.
        """
        self._last_received_time = self.now_fn()
        msg_type = msg.get("MsgType", "")
        incoming_seq_raw = msg.get("MsgSeqNum")
        poss_dup = msg.get("PossDupFlag") == "Y"

        if msg_type != "A" and self.role == "acceptor" and not self.logged_on:
            raise FixSessionError(f"business/session message {msg_type!r} received before Logon")

        try:
            incoming_seq = int(incoming_seq_raw)
        except (TypeError, ValueError):
            incoming_seq = self.next_in_seq  # malformed/missing -- treat as in-order, let caller Reject on content

        # Gap detection: something we should have seen is missing.
        if incoming_seq > self.next_in_seq and not poss_dup:
            resend = self.prepare_outgoing("2", {"BeginSeqNo": str(self.next_in_seq), "EndSeqNo": "0"})
            return [resend], False

        # Stale duplicate without PossDupFlag -- ignore, don't advance, don't process.
        if incoming_seq < self.next_in_seq and not poss_dup:
            return [], False

        if incoming_seq >= self.next_in_seq:
            self.next_in_seq = incoming_seq + 1

        if msg_type == "A":
            self._test_request_pending = False
            peer_hb = msg.get("HeartBtInt")
            if peer_hb:
                try:
                    self.heartbeat_interval = int(peer_hb)
                except ValueError:
                    pass
            if msg.get("ResetSeqNumFlag") == "Y":
                self.next_out_seq = 1
                self.next_in_seq = incoming_seq + 1
            was_logged_on = self.logged_on
            self.logged_on = True
            if self.role == "acceptor" and not was_logged_on:
                ack = self.prepare_outgoing("A", {"EncryptMethod": "0", "HeartBtInt": str(self.heartbeat_interval)})
                return [ack], False
            return [], False

        if msg_type == "0":  # Heartbeat
            self._test_request_pending = False
            return [], False

        if msg_type == "1":  # TestRequest -> must answer with Heartbeat carrying the same TestReqID
            hb = self.prepare_outgoing("0", {"TestReqID": msg.get("TestReqID", "")})
            return [hb], False

        if msg_type == "2":  # ResendRequest -> replay real stored messages where we have them
            try:
                begin = int(msg.get("BeginSeqNo", "1"))
            except ValueError:
                begin = 1
            end_raw = msg.get("EndSeqNo", "0")
            end = self.next_out_seq - 1 if end_raw in ("0", "", None) else int(end_raw)
            actions = []
            seq = begin
            while seq <= end:
                stored = self._sent_messages.get(seq)
                if stored is not None:
                    replay = dict(stored)
                    replay["PossDupFlag"] = "Y"
                    actions.append(replay)  # NOTE: does not consume a new seq num -- this IS seq `seq`
                    seq += 1
                else:
                    # We never sent this seq (or didn't keep it) -- gap-fill up to the next
                    # message we DO have, or to `end` if we have nothing further.
                    next_known = min((s for s in self._sent_messages if s > seq and s <= end), default=end + 1)
                    gapfill = self.prepare_outgoing("4", {"GapFillFlag": "Y", "NewSeqNo": str(next_known)})
                    # A gap-fill's own MsgSeqNum should logically be `seq`, not a fresh one --
                    # overwrite it to stay honest about which slot it's filling.
                    gapfill["MsgSeqNum"] = str(seq)
                    actions.append(gapfill)
                    seq = next_known
            return actions, False

        if msg_type == "4":  # SequenceReset (gap-fill or hard reset)
            try:
                new_seq = int(msg.get("NewSeqNo", self.next_in_seq))
                self.next_in_seq = max(self.next_in_seq, new_seq)
            except ValueError:
                pass
            return [], False

        if msg_type == "5":  # Logout
            already_initiated = self._logout_initiated
            self.logged_on = False
            self.closed = True
            if already_initiated:
                return [], False
            ack = self.build_logout()
            self.closed = True
            return [ack], False

        # Anything else is application-level (NewOrderSingle, ExecutionReport, etc.)
        return [], True
