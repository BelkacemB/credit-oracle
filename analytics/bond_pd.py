"""Bond-implied default intensity for bullet bonds — deliberately simple.

  ytm      : solve price = Σ c/(1+y)^t + 100/(1+y)^T   (annual compounding, ACT/365.25)
  spread   : ytm − risk-free at the same tenor (linear interpolation on a spot curve)
  hazard   : λ = spread / (1 − R)          (credit-triangle approximation)
  PD(T)    : 1 − exp(−λ T)

Ignores accrued, liquidity premia, term structure of hazard, and step-up
coupons (Ukraine): stated as such on the methodology page. Perpetuals are not
priced here — a yield-to-call needs the first-call date, which the public
master data does not carry.
"""
from __future__ import annotations

import math
from datetime import date

DAYS_PER_YEAR = 365.25


def cashflow_times(asof: date, maturity: date, freq: int) -> list[float]:
    """Coupon dates in years from asof, walking back from maturity every 12/freq months."""
    times: list[float] = []
    y, m, d = maturity.year, maturity.month, maturity.day
    step = 12 // freq
    while True:
        try:
            cd = date(y, m, min(d, 28))
        except ValueError:
            break
        t = (cd - asof).days / DAYS_PER_YEAR
        if t <= 0:
            break
        times.append(t)
        m -= step
        while m <= 0:
            m += 12
            y -= 1
    return sorted(times)


def price_from_yield(y: float, times: list[float], coupon: float, freq: int) -> float:
    c = coupon / freq
    pv = sum(c / (1 + y) ** t for t in times)
    return pv + 100 / (1 + y) ** times[-1]


def ytm(price: float, coupon: float, asof: date, maturity: date, freq: int = 1) -> float | None:
    """Annual-compounded yield to maturity; bisection on [-50%, 200%]."""
    times = cashflow_times(asof, maturity, freq)
    if not times or price <= 0:
        return None
    lo, hi = -0.5, 2.0
    if price_from_yield(lo, times, coupon, freq) < price or price_from_yield(hi, times, coupon, freq) > price:
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if price_from_yield(mid, times, coupon, freq) > price:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def interp_curve(curve: dict[float, float], tenor: float) -> float | None:
    """curve: {tenor_years: yield_decimal}. Flat extrapolation beyond the ends."""
    if not curve:
        return None
    pts = sorted(curve.items())
    if tenor <= pts[0][0]:
        return pts[0][1]
    if tenor >= pts[-1][0]:
        return pts[-1][1]
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if t0 <= tenor <= t1:
            return y0 + (y1 - y0) * (tenor - t0) / (t1 - t0)
    return None


def implied(price: float, coupon: float, asof: date, maturity: date, curve: dict[float, float],
            recovery: float, freq: int = 1) -> dict | None:
    y = ytm(price, coupon, asof, maturity, freq)
    if y is None:
        return None
    tenor = (maturity - asof).days / DAYS_PER_YEAR
    rf = interp_curve(curve, tenor)
    if rf is None:
        return {"ytm": y, "tenor": tenor, "rf": None, "spread": None, "hazard": None, "pd_1y": None, "pd_T": None}
    s = y - rf
    lam = max(s, 0.0) / (1 - recovery)
    return {
        "ytm": y, "tenor": tenor, "rf": rf, "spread": s, "hazard": lam,
        "pd_1y": 1 - math.exp(-lam * min(1.0, tenor)),
        "pd_T": 1 - math.exp(-lam * tenor),
        "recovery": recovery,
    }
