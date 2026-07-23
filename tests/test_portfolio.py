import pandas as pd
import pytest

from trading_simulator import Portfolio, PortfolioDispatcher, Execution


def mk_exec(**kwargs):
    defaults = dict(trade_id="t1", price=100.0, quantity=10, taker_order_id="to1", maker_order_id="mo1",
                     symbol="X", side="buy", timestamp=pd.Timestamp.now(tz="UTC"),
                     taker_owner_id="alice", maker_owner_id="bob")
    defaults.update(kwargs)
    return Execution(**defaults)


def test_taker_buy_reduces_cash_and_opens_long():
    pf = Portfolio(initial_cash=10_000.0, owner_id="alice")
    pf.on_execution(mk_exec(side="buy", price=100.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    assert pf.cash == pytest.approx(9_000.0)
    assert pf.positions["X"] == 10
    assert pf.avg_price["X"] == pytest.approx(100.0)


def test_maker_sell_increases_cash_and_opens_short():
    pf = Portfolio(initial_cash=10_000.0, owner_id="bob")
    # bob is maker on a taker "buy" execution => bob is effectively selling
    pf.on_execution(mk_exec(side="buy", price=100.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    assert pf.cash == pytest.approx(11_000.0)
    assert pf.positions["X"] == -10


def test_realized_pnl_on_round_trip():
    pf = Portfolio(initial_cash=10_000.0, owner_id="alice")
    pf.on_execution(mk_exec(side="buy", price=100.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    pf.on_execution(mk_exec(side="sell", price=110.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    assert pf.realized_pnl == pytest.approx(100.0)  # 10 shares * $10 gain
    assert pf.positions["X"] == 0


def test_fees_reduce_cash_for_taker():
    pf = Portfolio(initial_cash=10_000.0, fee_bps=10.0, owner_id="alice")  # 10bps = 0.1%
    pf.on_execution(mk_exec(side="buy", price=100.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    expected_fee = 100.0 * 10 * (10.0 / 10_000.0)
    assert pf.cash == pytest.approx(10_000.0 - 1000.0 - expected_fee)


def test_equity_marks_open_positions():
    pf = Portfolio(initial_cash=10_000.0, owner_id="alice")
    pf.on_execution(mk_exec(side="buy", price=100.0, quantity=10, taker_owner_id="alice", maker_owner_id="bob"))
    assert pf.equity({"X": 105.0}) == pytest.approx(9_000.0 + 10 * 105.0)


def test_dispatcher_routes_to_both_sides():
    disp = PortfolioDispatcher()
    disp.ensure("alice", initial_cash=10_000.0)
    disp.ensure("bob", initial_cash=10_000.0)
    disp.on_execution(mk_exec(taker_owner_id="alice", maker_owner_id="bob"))
    assert disp.get_portfolio("alice").positions["X"] == 10
    assert disp.get_portfolio("bob").positions["X"] == -10
