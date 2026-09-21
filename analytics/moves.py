"""Probability moves over standard windows, plus a z-score of the 7d move
against the market's own trailing distribution of 7d moves.

Input is a daily series [(date, p)], ascending. Missing days are tolerated:
'delta over N days' uses the last observation at or before asof - N days.
"""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass
class Moves:
    p_now: float | None
    d1: float | None
    d7: float | None
    d30: float | None
    z7: float | None       # (d7 - mean(d7 hist)) / std(d7 hist), trailing 90d
    n_obs: int


def _value_at_or_before(dates: list[date], ps: list[float], d: date) -> float | None:
    i = bisect_right(dates, d) - 1
    return ps[i] if i >= 0 else None


def compute_moves(series: list[tuple[date, float]], asof: date) -> Moves:
    series = sorted(series)
    if not series:
        return Moves(None, None, None, None, None, 0)
    dates = [d for d, _ in series]
    ps = [p for _, p in series]

    p_now = _value_at_or_before(dates, ps, asof)
    if p_now is None:
        return Moves(None, None, None, None, None, len(series))

    def delta(n: int) -> float | None:
        prev = _value_at_or_before(dates, ps, asof - timedelta(days=n))
        return None if prev is None else p_now - prev

    d1, d7, d30 = delta(1), delta(7), delta(30)

    # trailing distribution of 7d moves, one per observed day in the last 90d
    z7: float | None = None
    if d7 is not None:
        hist: list[float] = []
        for d in dates:
            if asof - timedelta(days=90) <= d < asof:
                cur = _value_at_or_before(dates, ps, d)
                prev = _value_at_or_before(dates, ps, d - timedelta(days=7))
                if cur is not None and prev is not None:
                    hist.append(cur - prev)
        if len(hist) >= 20:
            mu = sum(hist) / len(hist)
            var = sum((x - mu) ** 2 for x in hist) / (len(hist) - 1)
            sd = math.sqrt(var)
            if sd > 1e-6:
                z7 = (d7 - mu) / sd

    return Moves(p_now, d1, d7, d30, z7, len(series))
