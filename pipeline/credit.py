"""Attach the bond side to an event: quotes, bullet-bond implied hazard, and
the bond's beta to the crowd probability series."""
from __future__ import annotations

import json
from datetime import date

from analytics.beta import crowd_beta
from analytics.bond_pd import implied
from pipeline.config import DATA

BONDS = DATA / "bonds"
RATES = DATA / "rates.json"

# Recovery assumptions by instrument type, shown on the methodology page.
RECOVERY = {"senior_preferred": 0.40, "senior_hy": 0.40, "senior_secured": 0.50, "sovereign": 0.35,
            "hybrid": 0.20, "T2": 0.20, "RT1": 0.10, "AT1": 0.10, "convertible": 0.30}


def load_rates() -> dict:
    if not RATES.exists():
        return {"EUR": {}, "USD": {}}
    r = json.loads(RATES.read_text())
    return {k: {float(t): v for t, v in r.get(k, {}).items()} for k in ("EUR", "USD")} | {
        "EUR_date": r.get("EUR_date"), "USD_date": r.get("USD_date")}


def bond_record(isin: str) -> dict | None:
    f = BONDS / f"{isin}.json"
    return json.loads(f.read_text()) if f.exists() else None


def instrument_credit(instr: dict, asof: date, crowd: list[tuple[date, float]], rates: dict) -> dict:
    """One row of the 'crowd vs credit' table. Never raises."""
    out = {"isin": instr.get("isin"), "type": instr.get("type"), "note": instr.get("note"),
           "quoted": False}
    rec = bond_record(instr["isin"]) if instr.get("isin") else None
    if not rec or not rec.get("quote"):
        return out
    q, md = rec["quote"], rec.get("master") or {}
    price = q.get("lastPrice")
    bid, ask = q.get("bidLimit"), q.get("askLimit")
    if bid and ask and bid > 0 and ask > 0:
        mid = (bid + ask) / 2
    else:
        mid = price
    coupon = md.get("cupon")
    out.update({
        "quoted": mid is not None, "price": mid, "last": price, "bid": bid or None, "ask": ask or None,
        "last_trade": str(q.get("timestampLastPrice") or "")[:10], "currency": md.get("issueCurrency"),
        "coupon": coupon, "maturity": md.get("maturity"), "subordinated": md.get("subordinated"),
        "running_yield": (coupon / mid) if coupon and mid else None,
        "history": [[h["date"], h["close"]] for h in sorted(rec.get("history", []), key=lambda h: h["date"])],
    })
    # bullet-bond implied hazard
    if md.get("maturity") and coupon is not None and mid and md.get("issueCurrency") in ("EUR", "USD"):
        curve = rates.get(md["issueCurrency"], {})
        rec_rate = RECOVERY.get(instr.get("type"), 0.40)
        try:
            imp = implied(mid, coupon, asof, date.fromisoformat(md["maturity"]), curve, rec_rate,
                          freq=2 if md.get("issueCurrency") == "USD" else 1)
        except Exception:  # noqa: BLE001
            imp = None
        out["implied"] = imp
    # beta to the crowd series
    series = [(date.fromisoformat(d), c) for d, c in out["history"]]
    out["beta"] = crowd_beta(series, crowd) if series and crowd else None
    return out


def event_credit(entry: dict, benchmark_series: list[tuple[date, float]] | None, asof: date,
                 rates: dict, name_series: dict[str, list[tuple[date, float]]] | None = None) -> dict:
    """Credit block for one event. For baskets, each name uses its own market series."""
    rows: list[dict] = []
    headline: str | None = None
    groups = entry.get("exposures", []) or entry.get("names", [])
    for g in groups:
        crowd = benchmark_series or []
        if name_series is not None and g.get("match") in name_series:
            crowd = name_series[g["match"]]
        for instr in g.get("instruments", []):
            row = instrument_credit(instr, asof, crowd, rates)
            row["issuer"] = g.get("issuer")
            rows.append(row)
            if g.get("headline_instrument") == instr.get("isin") and row["quoted"]:
                headline = instr["isin"]
    if headline is None:
        best = max((r for r in rows if r["quoted"] and r.get("beta") and r["beta"].get("n", 0) >= 12),
                   key=lambda r: r["beta"]["n"], default=None)
        headline = best["isin"] if best else next((r["isin"] for r in rows if r["quoted"]), None)
    return {"rows": rows, "headline": headline, "rates_date": {"EUR": rates.get("EUR_date"), "USD": rates.get("USD_date")},
            "recovery": RECOVERY}
