"""How much does the bond move when the crowd probability moves?

Align a bond price series with a Polymarket probability series on common
dates, difference both over `step` calendar days, and regress bond price
changes (points) on probability changes (points). Reported with n and the
correlation, and only when n is large enough to mean anything.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from datetime import date, timedelta


def _at_or_before(dates: list[date], vals: list[float], d: date) -> float | None:
    i = bisect_right(dates, d) - 1
    return vals[i] if i >= 0 else None


def crowd_beta(bond: list[tuple[date, float]], crowd: list[tuple[date, float]],
               step: int = 7, min_n: int = 12) -> dict | None:
    bond, crowd = sorted(bond), sorted(crowd)
    if len(bond) < 2 or len(crowd) < 2:
        return None
    bd, bv = [d for d, _ in bond], [v for _, v in bond]
    cd, cv = [d for d, _ in crowd], [v for _, v in crowd]
    start, end = max(bd[0], cd[0]), min(bd[-1], cd[-1])
    xs: list[float] = []
    ys: list[float] = []
    d = start + timedelta(days=step)
    while d <= end:
        b1, b0 = _at_or_before(bd, bv, d), _at_or_before(bd, bv, d - timedelta(days=step))
        c1, c0 = _at_or_before(cd, cv, d), _at_or_before(cd, cv, d - timedelta(days=step))
        if None not in (b1, b0, c1, c0):
            xs.append((c1 - c0) * 100)   # probability points
            ys.append(b1 - b0)           # price points
        d += timedelta(days=step)
    n = len(xs)
    if n < min_n:
        return {"n": n, "beta": None, "corr": None, "step_days": step, "pairs": []}
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sxx < 1e-9 or syy < 1e-9:
        return {"n": n, "beta": None, "corr": None, "step_days": step, "pairs": list(zip(xs, ys))}
    return {
        "n": n, "beta": sxy / sxx, "corr": sxy / math.sqrt(sxx * syy), "step_days": step,
        "pairs": [(round(x, 2), round(y, 2)) for x, y in zip(xs, ys)],
        "window": [start.isoformat(), end.isoformat()],
    }
