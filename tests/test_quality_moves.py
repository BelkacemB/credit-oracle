from datetime import date, timedelta

import pytest

from analytics.moves import compute_moves
from analytics.quality import grade_market


def test_grade_a_liquid_tight():
    q = grade_market(liquidity_usd=75_000, volume_usd=2_000_000, spread=0.01)
    assert q.grade == "A" and q.reasons == []


def test_grade_c_on_wide_spread_regardless_of_volume():
    q = grade_market(liquidity_usd=75_000, volume_usd=2_000_000, spread=0.12)
    assert q.grade == "C"
    assert any("spread" in r for r in q.reasons)


def test_grade_c_on_thin_book():
    q = grade_market(737, 12_791, 0.04)   # the French budget market, 2026-09-21
    assert q.grade == "C"


def test_grade_b_with_reasons():
    q = grade_market(3_061, 51_036, 0.01)  # ECB Oct-26 "25bps increase"
    assert q.grade == "B"
    assert q.reasons == ["liquidity $3,061 < $20,000"]


def test_moves_basic():
    asof = date(2026, 9, 21)
    series = [(asof - timedelta(days=k), 0.10 + 0.01 * (40 - k)) for k in range(40, -1, -1)]
    m = compute_moves(series, asof)
    assert m.p_now == 0.50
    assert round(m.d1, 6) == 0.01
    assert round(m.d7, 6) == 0.07
    assert round(m.d30, 6) == 0.30
    # perfectly linear series: all 7d moves identical -> sd ~ 0 -> z undefined
    assert m.z7 is None


def test_moves_with_gap_uses_last_known():
    asof = date(2026, 9, 21)
    series = [(asof - timedelta(days=10), 0.2), (asof, 0.3)]
    m = compute_moves(series, asof)
    assert m.d7 == 0.3 - 0.2
    assert m.d30 is None  # nothing at or before asof-30d


def test_moves_z_score_detects_outlier():
    asof = date(2026, 9, 21)
    series = [(asof - timedelta(days=k), 0.30) for k in range(90, 0, -1)]
    series.append((asof, 0.45))  # sudden 15pt jump
    m = compute_moves(series, asof)
    assert m.d7 == pytest.approx(0.15)
    assert m.z7 is None  # flat history -> sd 0 -> z undefined rather than infinite
