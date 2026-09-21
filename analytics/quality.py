"""Liquidity grading for a single Polymarket market.

A prediction-market price is only a probability if someone can trade it.
Three rules, stated verbatim on the methodology page:

  C  if book liquidity < $1k  or  bid-ask spread > 8pts
  A  if liquidity >= $20k  and  spread <= 3pts  and  lifetime volume >= $50k
  B  otherwise

Calibrated on the 2026-09-21 snapshot: the Ukraine ladder rungs are A,
the ECB/BoE outcome markets are B, single-name bankruptcy markets are mostly C.
"""
from __future__ import annotations

from dataclasses import dataclass

C_LIQ, C_SPREAD = 1_000, 0.08
A_LIQ, A_SPREAD, A_VOL = 20_000, 0.03, 50_000


@dataclass
class Quality:
    grade: str          # A / B / C
    reasons: list[str]


def grade_market(
    liquidity_usd: float | None,
    volume_usd: float | None,
    spread: float | None,          # ask - bid in probability units (0..1)
) -> Quality:
    liq = liquidity_usd or 0.0
    vol = volume_usd or 0.0
    reasons: list[str] = []

    if liq < C_LIQ:
        reasons.append(f"book liquidity ${liq:,.0f} < ${C_LIQ:,}")
    if spread is None:
        reasons.append("no quoted spread")
    elif spread > C_SPREAD:
        reasons.append(f"spread {spread * 100:.0f}pts > {C_SPREAD * 100:.0f}pts")
    if reasons:
        return Quality("C", reasons)

    if liq >= A_LIQ and spread <= A_SPREAD and vol >= A_VOL:
        return Quality("A", [])

    if liq < A_LIQ:
        reasons.append(f"liquidity ${liq:,.0f} < ${A_LIQ:,}")
    if spread > A_SPREAD:
        reasons.append(f"spread {spread * 100:.1f}pts > {A_SPREAD * 100:.0f}pts")
    if vol < A_VOL:
        reasons.append(f"volume ${vol:,.0f} < ${A_VOL:,}")
    return Quality("B", reasons)
