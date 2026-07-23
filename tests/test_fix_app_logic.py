"""Tests for the parts of trading_simulator.connectivity.fix_app that do NOT
require `simplefix` to be installed: the pure lookup tables, the MsgType
reverse-mapping helper, and the order-routing bookkeeping struct.

FixApplication/FixClient themselves raise RuntimeError at construction time
when simplefix is missing (covered in test_optional_deps.py), so their wire
encode/decode methods can't be exercised in this sandbox. Everything tested
here is plain Python with no such dependency, and is exactly the logic that
turns a parsed FIX message into routable, human-readable fields and back.
"""
from trading_simulator.connectivity.fix_app import (
    FIX_TAGS, SIDE_MAPPING, SIDE_TO_FIX, MSG_TYPE_MAPPING,
    EXEC_NEW, EXEC_PARTIAL, EXEC_FILL, EXEC_CANCELED, EXEC_REJECTED,
    _reverse_msg_type, _OrderRoute,
)


def test_side_mappings_are_inverses_of_each_other():
    for fix_code, human in SIDE_MAPPING.items():
        assert SIDE_TO_FIX[human.lower()] == fix_code


def test_reverse_msg_type_maps_human_name_back_to_fix_code():
    assert _reverse_msg_type("NewOrderSingle") == "D"
    assert _reverse_msg_type("Logon") == "A"
    assert _reverse_msg_type("ExecutionReport") == "8"
    assert _reverse_msg_type("Reject") == "3"


def test_reverse_msg_type_passes_through_unknown_names_unchanged():
    # Session-layer messages (Heartbeat/TestRequest/etc.) already carry their
    # raw one-character FIX code as the "human" name in MSG_TYPE_MAPPING, but
    # anything genuinely unrecognized should round-trip rather than raise.
    assert _reverse_msg_type("SomethingWeirdAndUnmapped") == "SomethingWeirdAndUnmapped"


def test_msg_type_mapping_and_reverse_are_consistent_round_trip():
    for code, human in MSG_TYPE_MAPPING.items():
        assert _reverse_msg_type(human) == code


def test_fix_tags_cover_session_and_execution_report_fields():
    required_names = {
        "MsgType", "MsgSeqNum", "SenderCompID", "TargetCompID", "SendingTime",
        "ClOrdID", "OrigClOrdID", "Side", "Symbol", "Price", "OrderQty",
        "EncryptMethod", "HeartBtInt", "ResetSeqNumFlag", "PossDupFlag",
        "TestReqID", "Text", "BeginSeqNo", "EndSeqNo", "OrderID", "OrdStatus",
        "ExecType", "ExecID", "AvgPx", "CumQty", "LeavesQty", "TransactTime",
    }
    assert required_names.issubset(set(FIX_TAGS.values()))


def test_exec_type_constants_match_fix42_codes():
    assert (EXEC_NEW, EXEC_PARTIAL, EXEC_FILL, EXEC_CANCELED, EXEC_REJECTED) == ("0", "1", "2", "4", "8")


def test_order_route_tracks_cumulative_fill_quantity():
    route = _OrderRoute(sock=None, session=None, cl_ord_id="CL1", symbol="AAPL",
                         side="buy", orig_qty=100, price=150.0)
    assert route.cum_qty == 0
    route.cum_qty += 40
    assert route.cum_qty == 40
    leaves = route.orig_qty - route.cum_qty
    assert leaves == 60
