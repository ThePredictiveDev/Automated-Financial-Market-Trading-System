from trading_simulator import Order, Portfolio, RiskManager


def mk_order(**kwargs):
    defaults = dict(id="o1", price=100.0, quantity=10, side="buy", type="limit", symbol="X", owner_id="alice")
    defaults.update(kwargs)
    return Order(**defaults)


def test_rejects_over_max_order_qty():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=5, max_symbol_position=1000, max_gross_notional=1e9)
    assert rm.allow_order(mk_order(quantity=10)) is False
    assert rm.allow_order(mk_order(quantity=5)) is True


def test_rejects_over_gross_notional():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=1000, max_symbol_position=1000, max_gross_notional=500.0)
    assert rm.allow_order(mk_order(price=100.0, quantity=10)) is False  # $1000 notional
    assert rm.allow_order(mk_order(price=10.0, quantity=10)) is True   # $100 notional


def test_rejects_over_symbol_position_limit():
    pf = Portfolio()
    pf.positions["X"] = 95
    rm = RiskManager(portfolio=pf, max_order_qty=1000, max_symbol_position=100, max_gross_notional=1e9)
    assert rm.allow_order(mk_order(side="buy", quantity=10)) is False  # would project to 105
    assert rm.allow_order(mk_order(side="sell", quantity=10)) is True  # would project to 85


def test_owner_kill_switch():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=1000, max_symbol_position=1000, max_gross_notional=1e9)
    rm.disable_owner("alice")
    assert rm.allow_order(mk_order()) is False
    rm.enable_owner("alice")
    assert rm.allow_order(mk_order()) is True


def test_symbol_kill_switch():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=1000, max_symbol_position=1000, max_gross_notional=1e9)
    rm.disable_symbol("X")
    assert rm.allow_order(mk_order(symbol="X")) is False


def test_rate_limit():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=1000, max_symbol_position=1000, max_gross_notional=1e9,
                      order_rate_limit_per_sec=2)
    assert rm.allow_order(mk_order(id="o1")) is True
    assert rm.allow_order(mk_order(id="o2")) is True
    assert rm.allow_order(mk_order(id="o3")) is False


def test_round_lot_enforcement():
    rm = RiskManager(portfolio=Portfolio(), max_order_qty=1000, max_symbol_position=1000, max_gross_notional=1e9,
                      lot_size=10, round_lot_required=True)
    assert rm.allow_order(mk_order(quantity=15)) is False
    assert rm.allow_order(mk_order(quantity=20)) is True
