"""Tests for the FIX session-layer state machine (fix_session.py).

Deliberately has zero dependency on `simplefix` or real sockets -- it tests
the actual hard logic (sequencing, gap detection, replay, heartbeat timing,
Logon/Logout) directly, using a fake deterministic clock. This is the part of
the FIX engine this sandbox CAN prove works end to end; the simplefix wire
encode/decode glue in fix_app.py cannot be executed here (simplefix isn't
installed and there's no network access to install it), so it's covered only
by the existing "raises a clear RuntimeError when simplefix is missing" test
in test_optional_deps.py. If you have simplefix installed locally, running a
real FixClient <-> FixApplication session is the next thing worth verifying.
"""
import pytest

from trading_simulator.connectivity.fix_session import FixSessionState, FixSessionError


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _pair(heartbeat=5):
    """A connected acceptor/initiator pair sharing a fake clock."""
    clock = FakeClock()
    acceptor = FixSessionState(role="acceptor", sender_comp_id="SIM", target_comp_id="CLIENT",
                                heartbeat_interval=heartbeat, now_fn=clock)
    initiator = FixSessionState(role="initiator", sender_comp_id="CLIENT", target_comp_id="SIM",
                                 heartbeat_interval=heartbeat, now_fn=clock)
    return acceptor, initiator, clock


def test_logon_handshake_both_sides_end_up_logged_on():
    acceptor, initiator, clock = _pair()
    logon_msg = initiator.build_logon()
    assert logon_msg["MsgType"] == "A"
    assert logon_msg["MsgSeqNum"] == "1"
    assert not initiator.logged_on  # sending Logon doesn't itself flip logged_on

    actions, is_business = acceptor.handle_incoming(logon_msg)
    assert is_business is False
    assert acceptor.logged_on is True
    assert len(actions) == 1 and actions[0]["MsgType"] == "A"  # acceptor's Logon ack

    actions2, is_business2 = initiator.handle_incoming(actions[0])
    assert is_business2 is False
    assert actions2 == []
    assert initiator.logged_on is True


def test_business_message_before_logon_raises():
    acceptor, _initiator, _clock = _pair()
    with pytest.raises(FixSessionError):
        acceptor.handle_incoming({"MsgType": "D", "MsgSeqNum": "1"})  # NewOrderSingle, no Logon yet


def test_heartbeat_interval_negotiated_from_logon():
    acceptor, initiator, clock = _pair(heartbeat=5)
    logon_msg = initiator.build_logon()
    logon_msg["HeartBtInt"] = "45"  # initiator asks for a different interval
    actions, _ = acceptor.handle_incoming(logon_msg)
    assert acceptor.heartbeat_interval == 45
    assert actions[0]["HeartBtInt"] == "45"


def test_test_request_answered_with_heartbeat_carrying_same_id():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())
    initiator.handle_incoming(acceptor._sent_messages[1])

    test_req = acceptor.prepare_outgoing("1", {"TestReqID": "TR-42"})
    actions, is_business = initiator.handle_incoming(test_req)
    assert is_business is False
    assert len(actions) == 1
    assert actions[0]["MsgType"] == "0"
    assert actions[0]["TestReqID"] == "TR-42"


def test_heartbeat_and_disconnect_timers():
    acceptor, initiator, clock = _pair(heartbeat=10)
    acceptor.handle_incoming(initiator.build_logon())

    assert acceptor.due_for_heartbeat() is False  # just sent something (the Logon ack)
    clock.advance(10.5)
    assert acceptor.due_for_heartbeat() is True

    # Counterparty goes silent -- test-request threshold is 1.5x heartbeat.
    assert acceptor.due_for_test_request() is False
    clock.advance(5.0)  # total silence ~15.5s since last receive > 1.5*10=15
    assert acceptor.due_for_test_request() is True

    acceptor.prepare_outgoing("1", {"TestReqID": "probe"})
    acceptor._test_request_pending = True
    assert acceptor.due_for_disconnect() is False
    clock.advance(11.0)  # total silence now > 2.5*10=25
    assert acceptor.due_for_disconnect() is True


def test_sequence_gap_triggers_resend_request_and_does_not_advance():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())
    assert acceptor.next_in_seq == 2

    # Initiator's next real message should be seq 2, but we simulate seq 5 arriving instead.
    skipped_ahead = {"MsgType": "D", "MsgSeqNum": "5", "SenderCompID": "CLIENT", "TargetCompID": "SIM"}
    actions, is_business = acceptor.handle_incoming(skipped_ahead)
    assert is_business is False  # held back, not dispatched to business logic
    assert acceptor.next_in_seq == 2  # NOT advanced -- we're still missing 2,3,4
    assert len(actions) == 1
    resend = actions[0]
    assert resend["MsgType"] == "2"
    assert resend["BeginSeqNo"] == "2"
    assert resend["EndSeqNo"] == "0"


def test_resend_request_replays_original_stored_messages_with_possdup():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())  # acceptor seq 1 = Logon ack

    order_ack = acceptor.prepare_outgoing("8", {"OrderID": "o1", "OrdStatus": "0"})   # seq 2
    fill_report = acceptor.prepare_outgoing("8", {"OrderID": "o1", "OrdStatus": "2"})  # seq 3
    assert order_ack["MsgSeqNum"] == "2" and fill_report["MsgSeqNum"] == "3"

    resend_request = {"MsgType": "2", "MsgSeqNum": "2", "BeginSeqNo": "2", "EndSeqNo": "3"}
    actions, is_business = acceptor.handle_incoming(resend_request)
    assert is_business is False
    assert len(actions) == 2
    assert actions[0]["MsgSeqNum"] == "2" and actions[0]["PossDupFlag"] == "Y" and actions[0]["OrdStatus"] == "0"
    assert actions[1]["MsgSeqNum"] == "3" and actions[1]["PossDupFlag"] == "Y" and actions[1]["OrdStatus"] == "2"


def test_logout_flow_acks_and_closes_both_sides():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())
    initiator.handle_incoming(acceptor._sent_messages[1])
    assert acceptor.logged_on and initiator.logged_on

    logout_msg = initiator.build_logout(text="done for the day")
    actions, is_business = acceptor.handle_incoming(logout_msg)
    assert is_business is False
    assert acceptor.logged_on is False and acceptor.closed is True
    assert len(actions) == 1 and actions[0]["MsgType"] == "5"  # acceptor acks with its own Logout

    actions2, _ = initiator.handle_incoming(actions[0])
    assert initiator.closed is True
    assert actions2 == []  # initiator already sent Logout itself, no double-send


def test_stale_duplicate_without_possdup_is_ignored_not_processed():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())
    order1 = {"MsgType": "D", "MsgSeqNum": "2", "SenderCompID": "CLIENT", "TargetCompID": "SIM"}
    _, is_business = acceptor.handle_incoming(order1)
    assert is_business is True
    assert acceptor.next_in_seq == 3

    replay_without_flag = {"MsgType": "D", "MsgSeqNum": "2", "SenderCompID": "CLIENT", "TargetCompID": "SIM"}
    actions, is_business2 = acceptor.handle_incoming(replay_without_flag)
    assert actions == []
    assert is_business2 is False
    assert acceptor.next_in_seq == 3  # unchanged


def test_business_message_after_logon_is_flagged_for_dispatch():
    acceptor, initiator, clock = _pair()
    acceptor.handle_incoming(initiator.build_logon())
    new_order = {"MsgType": "D", "MsgSeqNum": "2", "ClOrdID": "o1", "SenderCompID": "CLIENT", "TargetCompID": "SIM"}
    actions, is_business = acceptor.handle_incoming(new_order)
    assert is_business is True
    assert actions == []
    assert acceptor.next_in_seq == 3
