"""Ladder markets -> survival function -> piecewise-constant hazard rate.

A Polymarket "ladder" is a set of markets "Will X happen by <date_i>?" for
increasing dates. Each YES price is P(event by t_i), i.e. a point on the CDF
of the event time. From that we get the survival function S(t) = 1 - F(t)
and, assuming a constant hazard between rungs, lambda_i = -ln(S_i/S_{i-1}) / dt_i.

This is the same object as a CDS-implied hazard curve, which is the point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

DAYS_PER_YEAR = 365.25
P_EPS = 1e-4  # clamp so ln() and division stay finite when a rung trades at 0 or 1


@dataclass
class Rung:
    t: date
    p: float            # P(event by t), raw mid
    label: str = ""
    grade: str = "A"    # liquidity grade A/B/C, informational only
    market_id: str = ""


@dataclass
class HazardCurve:
    asof: date
    rungs: list[Rung]                    # sorted by t
    p_fit: list[float]                   # monotone (isotonic) fit of the CDF
    survival: list[float]                # S(t_i) = 1 - p_fit_i
    hazard: list[float]                  # lambda_i in 1/yr, constant on (t_{i-1}, t_i]
    tenor_years: list[float]             # (t_i - asof) in years
    expected_time_years: float | None    # E[T | T <= t_last]
    p_last: float                        # P(event by last rung)
    violations: int = 0                  # how many raw rungs the monotone fit moved
    notes: list[str] = field(default_factory=list)


def pava(y: list[float], w: list[float] | None = None) -> list[float]:
    """Pool-adjacent-violators: least-squares non-decreasing fit of y.

    Small enough to own rather than pull scipy for one function.
    """
    n = len(y)
    if n == 0:
        return []
    w = list(w) if w is not None else [1.0] * n
    # blocks of (value, weight, count)
    vals: list[float] = []
    wts: list[float] = []
    cnt: list[int] = []
    for yi, wi in zip(y, w):
        vals.append(yi)
        wts.append(wi)
        cnt.append(1)
        # merge backwards while the last block violates monotonicity
        while len(vals) > 1 and vals[-2] > vals[-1]:
            v2, w2, c2 = vals.pop(), wts.pop(), cnt.pop()
            v1, w1, c1 = vals.pop(), wts.pop(), cnt.pop()
            wsum = w1 + w2
            vals.append((v1 * w1 + v2 * w2) / wsum)
            wts.append(wsum)
            cnt.append(c1 + c2)
    out: list[float] = []
    for v, c in zip(vals, cnt):
        out.extend([v] * c)
    return out


def grade_weight(grade: str) -> float:
    return {"A": 1.0, "B": 0.5, "C": 0.15}.get(grade, 0.15)


def build_curve(rungs: list[Rung], asof: date) -> HazardCurve:
    """Fit a hazard curve to ladder rungs.

    Rungs already in the past (t <= asof) are dropped: their price is a
    resolved 0/1, not a forecast. Rungs are weighted by liquidity grade in
    the isotonic fit so a thin rung can't drag a liquid one.
    """
    import math

    live = sorted((r for r in rungs if r.t > asof), key=lambda r: r.t)
    notes: list[str] = []
    dropped = len(rungs) - len(live)
    if dropped:
        notes.append(f"{dropped} resolved/past rung(s) excluded")
    if not live:
        return HazardCurve(asof, [], [], [], [], [], None, 0.0, 0, notes)

    raw = [min(max(r.p, P_EPS), 1 - P_EPS) for r in live]
    fit = pava(raw, [grade_weight(r.grade) for r in live])
    fit = [min(max(p, P_EPS), 1 - P_EPS) for p in fit]
    violations = sum(1 for a, b in zip(raw, fit) if abs(a - b) > 1e-9)

    tenor = [(r.t - asof).days / DAYS_PER_YEAR for r in live]
    surv = [1.0 - p for p in fit]
    hazard: list[float] = []
    prev_s, prev_t = 1.0, 0.0
    for s, t in zip(surv, tenor):
        dt = t - prev_t
        lam = -math.log(s / prev_s) / dt if dt > 0 else 0.0
        hazard.append(max(lam, 0.0))
        prev_s, prev_t = s, t

    # E[T | T <= t_last] via the discrete mass on each interval, midpoint rule
    p_last = fit[-1]
    et: float | None = None
    if p_last > P_EPS:
        acc, prev_p, prev_t = 0.0, 0.0, 0.0
        for p, t in zip(fit, tenor):
            acc += (p - prev_p) * (prev_t + t) / 2
            prev_p, prev_t = p, t
        et = acc / p_last

    return HazardCurve(
        asof=asof, rungs=live, p_fit=fit, survival=surv, hazard=hazard,
        tenor_years=tenor, expected_time_years=et, p_last=p_last,
        violations=violations, notes=notes,
    )


def to_dict(c: HazardCurve) -> dict:
    return {
        "asof": c.asof.isoformat(),
        "rungs": [
            {"t": r.t.isoformat(), "p_raw": r.p, "label": r.label,
             "grade": r.grade, "market_id": r.market_id}
            for r in c.rungs
        ],
        "p_fit": c.p_fit,
        "survival": c.survival,
        "hazard": c.hazard,
        "tenor_years": c.tenor_years,
        "expected_time_years": c.expected_time_years,
        "p_last": c.p_last,
        "violations": c.violations,
        "notes": c.notes,
    }
