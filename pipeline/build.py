"""Turn snapshot + history + mappings into the JSON the static site reads.

  site/data/board.json          rows for the Catalyst Board + top movers
  site/data/events/<slug>.json  everything for one event page
  site/data/hazard.json         all hazard curves, for the overlay page
  site/data/meta.json           asof, counts
"""
from __future__ import annotations

import json
import math
import re
import sys
from datetime import UTC, date, datetime

import yaml

from analytics.hazard import Rung, build_curve, to_dict as hazard_to_dict
from analytics.moves import compute_moves
from analytics.quality import grade_market
from pipeline.config import HISTORY, MAPPINGS, SITE_DATA, SNAPSHOTS
from pipeline.credit import event_credit, load_rates

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july",
     "august", "september", "october", "november", "december"], 1)}
DATE_RE = re.compile(r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2})(?:,?\s+(\d{4}))?", re.I)


def rung_date(market: dict) -> date:
    """Date a ladder rung refers to: parse the question, fall back to endDate."""
    end = datetime.fromisoformat(market["endDate"].replace("Z", "+00:00")).date()
    m = DATE_RE.search(market.get("question") or "")
    if m:
        month, day, year = MONTHS[m.group(1).lower()], int(m.group(2)), m.group(3)
        y = int(year) if year else end.year
        try:
            d = date(y, month, day)
            # "through July 18?" without a year: pick the year that lands nearest endDate
            if not year and abs((d - end).days) > 180:
                d = date(y - 1 if d > end else y + 1, month, day)
            return d
        except ValueError:
            pass
    return end


def load_latest_snapshot() -> tuple[date, dict]:
    files = sorted(SNAPSHOTS.glob("*.json"))
    if not files:
        sys.exit("no snapshots; run pipeline.fetch_polymarket first")
    f = files[-1]
    return date.fromisoformat(f.stem), json.loads(f.read_text())


def history_series(market_id: str) -> list[tuple[date, float]]:
    f = HISTORY / f"{market_id}.json"
    if not f.exists():
        return []
    pts = json.loads(f.read_text())
    # one point per day: keep the last observation of each day
    by_day: dict[date, float] = {}
    for p in pts:
        by_day[datetime.fromtimestamp(p["t"], UTC).date()] = float(p["p"])
    return sorted(by_day.items())


def mid(m: dict) -> float | None:
    b, a = m.get("bestBid"), m.get("bestAsk")
    if b is not None and a is not None and 0 < a <= 1 and 0 <= b < 1 and a >= b:
        return (a + b) / 2
    return m.get("p_yes")


def enrich(m: dict, asof: date) -> dict:
    """Attach mid, grade and moves to a slim market dict."""
    p = mid(m)
    q = grade_market(m.get("liquidity"), m.get("volume"), m.get("spread"))
    series = history_series(m["id"])
    if p is not None:
        series = [(d, v) for d, v in series if d < asof] + [(asof, p)]
    mv = compute_moves(series, asof)
    return {
        "id": m["id"], "question": m["question"], "label": m.get("groupItemTitle") or "",
        "p": p, "bid": m.get("bestBid"), "ask": m.get("bestAsk"), "spread": m.get("spread"),
        "liquidity": m.get("liquidity"), "volume": m.get("volume"), "volume24h": m.get("volume24hr"),
        "endDate": m.get("endDate"), "closed": m.get("closed"),
        "grade": q.grade, "grade_reasons": q.reasons,
        "d1": mv.d1, "d7": mv.d7, "d30": mv.d30, "z7": mv.z7,
        "history": [[d.isoformat(), round(v, 4)] for d, v in series],
        "description": m.get("description"),
    }


def interp_cdf(curve: dict, t_years: float) -> float | None:
    """Linear interpolation of the fitted CDF at a tenor; None if beyond last rung."""
    xs, ys = curve["tenor_years"], curve["p_fit"]
    if not xs or t_years > xs[-1]:
        return None
    prev_x, prev_y = 0.0, 0.0
    for x, y in zip(xs, ys):
        if t_years <= x:
            return prev_y + (y - prev_y) * (t_years - prev_x) / (x - prev_x) if x > prev_x else y
        prev_x, prev_y = x, y
    return ys[-1]


def hazard_history(markets: list[dict], kind: str, asof: date, days: int = 120,
                   tenors: tuple[float, ...] = (0.25, 0.5, 0.75, 1.0, 1.25, 1.5)) -> dict:
    """Rebuild the ladder's fitted curve for each past day from the rungs' own
    price histories, and sample the average hazard to fixed tenors. Feeds the
    time × tenor heatmap. Rungs without a price on a given day are skipped."""
    import math
    from datetime import timedelta

    by_day: dict[str, list[tuple[date, float, str]]] = {}
    for m in markets:
        t = date.fromisoformat(m["rung_t"])
        for d, v in m["history"]:
            p = 1 - v if kind == "survival" else v
            by_day.setdefault(d, []).append((t, p, m["grade"]))
    rows: list[dict] = []
    for k in range(days, -1, -1):
        d = asof - timedelta(days=k)
        rs = by_day.get(d.isoformat())
        if not rs or len(rs) < 3:
            continue
        curve = build_curve([Rung(t=t, p=p, grade=g) for t, p, g in rs], d)
        cd = hazard_to_dict(curve)
        vals: list[float | None] = []
        for T in tenors:
            pT = interp_cdf(cd, T)
            vals.append(-math.log(1 - pT) / T if pT is not None and pT < 1 else None)
        rows.append({"asof": d.isoformat(), "avg_hazard": vals})
    return {"tenors": list(tenors), "rows": rows}


def exposures_summary(exps: list[dict]) -> list[str]:
    return [e["issuer"] for e in exps]


def build_event(entry: dict, ev: dict, asof: date, rates: dict) -> tuple[dict, list[dict]]:
    slug = entry["slug"]
    kind = entry["kind"]
    markets = [enrich(m, asof) for m in ev["markets"]]
    live = [m for m in markets if not m["closed"]]
    base_row = {
        "slug": slug, "title": entry["title"], "kind": kind,
        "category": entry["category"], "direction": entry.get("direction", "mixed"),
        "headline": bool(entry.get("headline")),
        "exposures": exposures_summary(entry.get("exposures", [])),
    }
    rows: list[dict] = []
    hazard: dict | None = None

    if kind in ("ladder", "survival"):
        for m, raw in zip(markets, ev["markets"]):
            m["rung_t"] = rung_date(raw).isoformat()
        markets.sort(key=lambda m: m["rung_t"])
        live = [m for m in markets if not m["closed"]]
        rungs = [
            Rung(t=date.fromisoformat(m["rung_t"]), p=1 - m["p"] if kind == "survival" else m["p"],
                 label=m["label"] or m["question"], grade=m["grade"], market_id=m["id"])
            for m in markets if m["p"] is not None
        ]
        curve = build_curve(rungs, asof)
        hazard = hazard_to_dict(curve)
        hazard["kind"] = kind
        hazard["history"] = hazard_history(markets, kind, asof) if entry.get("headline") else None
        p12 = interp_cdf(hazard, 1.0)
        # board row: P(12m) from the fitted curve; moves from the benchmark rung
        # (highest lifetime volume among live rungs) so a newly-listed thin rung
        # never drives the Δ columns
        live_ids = {r.market_id for r in curve.rungs}
        tm = max((m for m in live if m["id"] in live_ids), key=lambda m: m["volume"] or 0, default=None)
        hazard["benchmark_market_id"] = tm["id"] if tm else None
        target = next((r for r in curve.rungs if tm and r.market_id == tm["id"]), None)
        sign = -1 if kind == "survival" else 1
        last_rung = curve.rungs[-1] if curve.rungs else None
        if p12 is not None:
            p_row, p_note = p12, "P(event within 12m), interpolated on fitted curve"
            sub = f"P(12m) · moves on benchmark rung {tm['label'] or tm['question']}" if tm else "P(12m)"
        elif last_rung is not None:
            p_row, p_note = curve.p_last, f"P(by last rung, {last_rung.t.isoformat()}) — ladder ends before 12m"
            sub = f"P(by {last_rung.label}) · moves on benchmark rung {tm['label'] or tm['question']}" if tm else ""
        else:
            p_row, p_note, sub = None, "", ""
        rows.append({**base_row,
            "row_id": slug, "subtitle": sub, "p": p_row, "p_note": p_note,
            "hazard_12m": -math.log(1 - p12) if p12 is not None and p12 < 1 else None,
            "grade": tm["grade"] if tm else "C",
            "d1": sign * tm["d1"] if tm and tm["d1"] is not None else None,
            "d7": sign * tm["d7"] if tm and tm["d7"] is not None else None,
            "d30": sign * tm["d30"] if tm and tm["d30"] is not None else None,
            "z7": tm["z7"] if tm else None,
            "market_id": tm["id"] if tm else None,
        })
    elif kind == "menu":
        focus = entry.get("focus", "")
        fm = next((m for m in live if m["label"] == focus), None) or (live[0] if live else None)
        if fm:
            rows.append({**base_row, "row_id": slug, "subtitle": fm["label"], "p": fm["p"],
                         "p_note": f"P({fm['label']})", "grade": fm["grade"],
                         "d1": fm["d1"], "d7": fm["d7"], "d30": fm["d30"], "z7": fm["z7"],
                         "market_id": fm["id"]})
    elif kind == "basket":
        for name in entry.get("names", []):
            nm = next((m for m in live if name["match"].lower() in m["question"].lower()), None)
            if not nm:
                print(f"  !! no market matching {name['match']!r} in {slug}", file=sys.stderr)
                continue
            rows.append({**base_row, "row_id": f"{slug}#{nm['id']}", "subtitle": name["issuer"],
                         "title": f"{name['issuer']} bankruptcy", "p": nm["p"], "p_note": "P(YES)",
                         "grade": nm["grade"], "d1": nm["d1"], "d7": nm["d7"], "d30": nm["d30"],
                         "z7": nm["z7"], "market_id": nm["id"],
                         "exposures": [name["issuer"]]})
    else:  # single
        if live:
            m = live[0]
            rows.append({**base_row, "row_id": slug, "subtitle": "", "p": m["p"], "p_note": "P(YES)",
                         "grade": m["grade"], "d1": m["d1"], "d7": m["d7"], "d30": m["d30"],
                         "z7": m["z7"], "market_id": m["id"]})

    by_id = {m["id"]: m for m in markets}
    for r in rows:
        m = by_id.get(r.get("market_id"))
        r["spark"] = [v for _, v in m["history"][-30:]] if m else []
        r["p_raw"] = m["p"] if m else None

    # credit side: bond quotes, implied hazard, beta to the crowd series
    def _series(m: dict | None) -> list[tuple[date, float]]:
        if not m:
            return []
        sign = kind == "survival"
        return [(date.fromisoformat(d), (1 - v) if sign else v) for d, v in m["history"]]
    bench = None
    if kind in ("ladder", "survival") and hazard and hazard.get("benchmark_market_id"):
        bench = by_id.get(hazard["benchmark_market_id"])
    elif kind == "menu":
        bench = by_id.get(rows[0]["market_id"]) if rows else None
    elif kind == "single":
        bench = live[0] if live else None
    name_series = None
    if kind == "basket":
        name_series = {n["match"]: _series(by_id.get(r["market_id"]))
                       for n, r in zip(entry.get("names", []), rows)}
    credit = event_credit(entry, _series(bench), asof, rates, name_series)
    for r in rows:
        hl = next((c for c in credit["rows"] if c["isin"] == credit["headline"]), None)
        if kind == "basket":
            hl = next((c for c in credit["rows"] if c["quoted"] and c.get("issuer") == r["subtitle"]), None)
        r["beta"] = hl["beta"]["beta"] if hl and hl.get("beta") and hl["beta"].get("beta") is not None else None
        r["beta_isin"] = hl["isin"] if hl else None

    desc = next((m["description"] for m in live if m.get("description")), None)
    event_json = {
        **base_row, "asof": asof.isoformat(),
        "polymarket_url": f"https://polymarket.com/event/{slug}",
        "focus": entry.get("focus"), "names": entry.get("names", []),
        "exposures_full": entry.get("exposures", []), "scenarios": entry.get("scenarios", {}),
        "resolution": desc, "hazard": hazard, "credit": credit,
        "markets": [{k: v for k, v in m.items() if k != "description"} for m in markets],
        "event_volume": ev.get("volume"), "event_liquidity": ev.get("liquidity"),
    }
    return event_json, rows


def run() -> None:
    asof, snap = load_latest_snapshot()
    mappings = yaml.safe_load(MAPPINGS.read_text())
    (SITE_DATA / "events").mkdir(parents=True, exist_ok=True)

    rates = load_rates()
    rows: list[dict] = []
    curves: list[dict] = []
    for entry in mappings:
        ev = snap["events"].get(entry["slug"])
        if not ev:
            print(f"  !! {entry['slug']} missing from snapshot", file=sys.stderr)
            continue
        event_json, ev_rows = build_event(entry, ev, asof, rates)
        (SITE_DATA / "events" / f"{entry['slug']}.json").write_text(json.dumps(event_json))
        rows.extend(ev_rows)
        if event_json["hazard"] and event_json["hazard"]["rungs"]:
            curves.append({"slug": entry["slug"], "title": entry["title"],
                           "category": entry["category"], "headline": event_json["headline"],
                           **event_json["hazard"]})

    movers = sorted((r for r in rows if r.get("d7") is not None), key=lambda r: -abs(r["d7"]))[:5]
    board = {"asof": asof.isoformat(), "fetched_at": snap["fetched_at"], "rows": rows,
             "movers": [r["row_id"] for r in movers]}
    (SITE_DATA / "board.json").write_text(json.dumps(board))
    (SITE_DATA / "hazard.json").write_text(json.dumps({"asof": asof.isoformat(), "curves": curves}))
    (SITE_DATA / "meta.json").write_text(json.dumps({
        "asof": asof.isoformat(), "fetched_at": snap["fetched_at"],
        "n_events": len(mappings), "n_rows": len(rows), "n_curves": len(curves),
        "built_at": datetime.now(UTC).isoformat()}))
    print(f"board: {len(rows)} rows, {len(curves)} hazard curves, asof {asof}")


if __name__ == "__main__":
    run()
