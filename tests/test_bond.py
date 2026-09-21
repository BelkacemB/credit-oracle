import math
from datetime import date, timedelta

import pytest

from analytics.beta import crowd_beta
from analytics.bond_pd import cashflow_times, implied, interp_curve, price_from_yield, ytm


def test_par_bond_yields_coupon():
    asof, mat = date(2026, 9, 21), date(2031, 9, 21)
    y = ytm(100.0, 5.0, asof, mat, freq=1)
    assert y == pytest.approx(0.05, abs=2e-4)


def test_ytm_roundtrip():
    asof, mat = date(2026, 1, 1), date(2030, 1, 1)
    times = cashflow_times(asof, mat, 2)
    assert len(times) == 8
    p = price_from_yield(0.07, times, 4.0, 2)
    assert ytm(p, 4.0, asof, mat, 2) == pytest.approx(0.07, abs=1e-6)


def test_credit_triangle_worked_example():
    # 300bp over a flat 3% curve, R=40% -> λ=5%, PD1y = 1-exp(-0.05) ≈ 4.88%
    asof, mat = date(2026, 1, 1), date(2031, 1, 1)
    times = cashflow_times(asof, mat, 1)
    price = price_from_yield(0.06, times, 6.0, 1)
    out = implied(price, 6.0, asof, mat, {1: 0.03, 10: 0.03}, recovery=0.4)
    assert out["spread"] == pytest.approx(0.03, abs=1e-5)
    assert out["hazard"] == pytest.approx(0.05, abs=2e-5)
    assert out["pd_1y"] == pytest.approx(1 - math.exp(-0.05), abs=1e-4)


def test_interp_curve():
    c = {1: 0.02, 5: 0.04}
    assert interp_curve(c, 3) == pytest.approx(0.03)
    assert interp_curve(c, 0.5) == 0.02 and interp_curve(c, 10) == 0.04


def test_negative_spread_floors_hazard_at_zero():
    asof, mat = date(2026, 1, 1), date(2029, 1, 1)
    times = cashflow_times(asof, mat, 1)
    price = price_from_yield(0.02, times, 2.0, 1)
    out = implied(price, 2.0, asof, mat, {1: 0.04, 5: 0.04}, recovery=0.4)
    assert out["spread"] < 0 and out["hazard"] == 0.0


def test_crowd_beta_recovers_slope():
    d0 = date(2026, 1, 1)
    crowd, bond = [], []
    p, b = 0.20, 60.0
    for k in range(0, 200):
        d = d0 + timedelta(days=k)
        dp = 0.01 * ((k * 7919) % 5 - 2)      # deterministic wiggle in [-2, +2] pts
        p = min(max(p + dp, 0.01), 0.99)
        b = 60 + (p - 0.20) * 100 * 0.5       # bond moves 0.5 pt per probability pt
        crowd.append((d, p)); bond.append((d, b))
    out = crowd_beta(bond, crowd, step=7)
    assert out["n"] >= 25
    assert out["beta"] == pytest.approx(0.5, abs=1e-6)
    assert out["corr"] == pytest.approx(1.0, abs=1e-6)


def test_crowd_beta_too_short():
    d0 = date(2026, 1, 1)
    s = [(d0 + timedelta(days=k), 0.3) for k in range(20)]
    out = crowd_beta(s, s, step=7)
    assert out["beta"] is None and out["n"] < 12
