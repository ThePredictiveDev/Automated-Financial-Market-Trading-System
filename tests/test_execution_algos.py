import pytest

from trading_simulator import twap_schedule, vwap_schedule


def test_twap_splits_evenly_and_conserves_total_quantity():
    plans = twap_schedule(total_quantity=100, num_slices=4, duration_seconds=60.0)
    assert sum(p.quantity for p in plans) == 100
    assert len(plans) == 4
    assert plans[0].offset_seconds == 0.0
    assert plans[-1].offset_seconds == pytest.approx(45.0)


def test_twap_distributes_remainder():
    plans = twap_schedule(total_quantity=10, num_slices=3, duration_seconds=30.0)
    assert sum(p.quantity for p in plans) == 10
    assert [p.quantity for p in plans] == [4, 3, 3]


def test_vwap_weights_by_volume_profile_and_conserves_total():
    plans = vwap_schedule(total_quantity=1000, volume_profile=[1, 2, 1], duration_seconds=90.0)
    assert sum(p.quantity for p in plans) == 1000
    # Middle bucket has 2x the weight of the others
    qty_by_offset = {p.offset_seconds: p.quantity for p in plans}
    assert qty_by_offset[30.0] > qty_by_offset[0.0]


def test_vwap_rejects_all_zero_profile():
    with pytest.raises(ValueError):
        vwap_schedule(total_quantity=100, volume_profile=[0, 0, 0], duration_seconds=60.0)


def test_twap_rejects_non_positive_inputs():
    with pytest.raises(ValueError):
        twap_schedule(total_quantity=0, num_slices=4, duration_seconds=60.0)
    with pytest.raises(ValueError):
        twap_schedule(total_quantity=100, num_slices=0, duration_seconds=60.0)
