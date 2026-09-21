import math
from datetime import date

import pytest

from analytics.hazard import Rung, build_curve, pava


def test_pava_identity_when_monotone():
    assert pava([0.1, 0.2, 0.3]) == [0.1, 0.2, 0.3]


def test_pava_pools_violators():
    out = pava([0.1, 0.3, 0.2, 0.4])
    assert out == pytest.approx([0.1, 0.25, 0.25, 0.4])
    assert all(a <= b for a, b in zip(out, out[1:]))


def test_pava_weights_pull_toward_heavier_point():
    out = pava([0.3, 0.2], [1.0, 0.1])
    assert out[0] == out[1]
    assert out[0] > 0.25  # heavier first point dominates


def test_constant_hazard_recovered():
    # Build rungs from a known constant hazard of 20%/yr and check we get it back.
    asof = date(2026, 1, 1)
    lam = 0.20
    dates = [date(2026, 7, 1), date(2027, 1, 1), date(2027, 7, 1), date(2028, 1, 1)]
    rungs = []
    for d in dates:
        ty = (d - asof).days / 365.25
        rungs.append(Rung(t=d, p=1 - math.exp(-lam * ty)))
    c = build_curve(rungs, asof)
    assert c.violations == 0
    for h in c.hazard:
        assert h == pytest.approx(lam, rel=1e-6)
    assert c.p_last == pytest.approx(rungs[-1].p)


def test_past_rungs_dropped_and_noted():
    asof = date(2026, 9, 21)
    rungs = [
        Rung(t=date(2026, 6, 30), p=0.0),   # resolved NO
        Rung(t=date(2026, 12, 31), p=0.2),
        Rung(t=date(2027, 6, 30), p=0.55),
    ]
    c = build_curve(rungs, asof)
    assert len(c.rungs) == 2
    assert "1 resolved/past rung(s) excluded" in c.notes


def test_non_monotone_ladder_is_fixed_and_counted():
    asof = date(2026, 9, 21)
    rungs = [
        Rung(t=date(2026, 12, 31), p=0.20),
        Rung(t=date(2027, 1, 31), p=0.18, grade="C"),  # thin rung below its neighbour
        Rung(t=date(2027, 3, 31), p=0.38),
    ]
    c = build_curve(rungs, asof)
    assert c.violations == 2
    assert all(a <= b for a, b in zip(c.p_fit, c.p_fit[1:]))
    assert all(h >= 0 for h in c.hazard)
    # the C-grade rung should have moved more than the A-grade one
    assert abs(c.p_fit[1] - 0.18) > abs(c.p_fit[0] - 0.20)


def test_extreme_prices_do_not_blow_up():
    asof = date(2026, 9, 21)
    rungs = [Rung(t=date(2026, 12, 31), p=0.0), Rung(t=date(2027, 12, 31), p=1.0)]
    c = build_curve(rungs, asof)
    assert all(math.isfinite(h) for h in c.hazard)
    assert c.expected_time_years is not None


def test_single_rung():
    asof = date(2026, 9, 21)
    c = build_curve([Rung(t=date(2027, 9, 21), p=0.1)], asof)
    ty = c.tenor_years[0]
    assert c.hazard[0] == pytest.approx(-math.log(0.9) / ty)


def test_empty():
    c = build_curve([], date(2026, 9, 21))
    assert c.rungs == [] and c.expected_time_years is None
