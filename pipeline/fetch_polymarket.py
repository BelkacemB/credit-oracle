"""Pull every market referenced by data/mappings.yaml from Polymarket.

Writes
  data/snapshots/<YYYY-MM-DD>.json   one file per run-day: raw market fields we care about
  data/history/<market_id>.json      Polymarket's own daily price history (overwritten each run)

Both are committed by the scheduled Action so the repo *is* the database.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime

import httpx
import yaml

from pipeline.config import CLOB, GAMMA, HISTORY, MAPPINGS, SNAPSHOTS, USER_AGENT

KEEP = [
    "id", "question", "slug", "groupItemTitle", "outcomes", "outcomePrices",
    "clobTokenIds", "bestBid", "bestAsk", "spread", "lastTradePrice",
    "volume", "volume24hr", "liquidity", "endDate", "closed", "active",
    "oneDayPriceChange", "oneWeekPriceChange", "oneMonthPriceChange",
    "description", "resolutionSource", "updatedAt",
]


def _f(x) -> float | None:
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def fetch_event(client: httpx.Client, slug: str) -> dict | None:
    r = client.get(f"{GAMMA}/events/slug/{slug}")
    if r.status_code == 404:
        print(f"  !! event not found: {slug}", file=sys.stderr)
        return None
    r.raise_for_status()
    return r.json()


def fetch_history(client: httpx.Client, token_id: str) -> list[dict]:
    r = client.get(f"{CLOB}/prices-history",
                   params={"market": token_id, "interval": "max", "fidelity": 1440})
    r.raise_for_status()
    return r.json().get("history", [])


def yes_token(market: dict) -> str | None:
    try:
        ids = json.loads(market.get("clobTokenIds") or "[]")
        outcomes = json.loads(market.get("outcomes") or "[]")
    except json.JSONDecodeError:
        return None
    if not ids:
        return None
    # outcomes are normally ["Yes","No"]; be defensive about order
    for o, t in zip(outcomes, ids):
        if str(o).lower() == "yes":
            return t
    return ids[0]


def slim(market: dict) -> dict:
    m = {k: market.get(k) for k in KEEP}
    try:
        prices = json.loads(market.get("outcomePrices") or "[]")
        m["p_yes"] = _f(prices[0]) if prices else None
    except json.JSONDecodeError:
        m["p_yes"] = None
    for k in ("bestBid", "bestAsk", "spread", "lastTradePrice", "volume", "volume24hr",
              "liquidity", "oneDayPriceChange", "oneWeekPriceChange", "oneMonthPriceChange"):
        m[k] = _f(m[k])
    m["yes_token"] = yes_token(market)
    return m


def run(fetch_hist: bool = True) -> dict:
    mappings = yaml.safe_load(MAPPINGS.read_text())
    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    HISTORY.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    snapshot = {"fetched_at": now.isoformat(), "events": {}}

    with httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for entry in mappings:
            slug = entry["slug"]
            print(f"- {slug}")
            ev = fetch_event(client, slug)
            if ev is None:
                continue
            markets = [slim(m) for m in ev.get("markets", [])]
            snapshot["events"][slug] = {
                "id": ev.get("id"), "title": ev.get("title"), "endDate": ev.get("endDate"),
                "volume": _f(ev.get("volume")), "liquidity": _f(ev.get("liquidity")),
                "markets": markets,
            }
            if not fetch_hist:
                continue
            for m in markets:
                if m["closed"] or not m["yes_token"]:
                    continue
                try:
                    hist = fetch_history(client, m["yes_token"])
                except httpx.HTTPError as e:
                    print(f"  !! history failed for {m['id']}: {e}", file=sys.stderr)
                    continue
                (HISTORY / f"{m['id']}.json").write_text(json.dumps(hist))
                time.sleep(0.15)

    out = SNAPSHOTS / f"{now.date().isoformat()}.json"
    out.write_text(json.dumps(snapshot, indent=1))
    print(f"wrote {out} ({len(snapshot['events'])} events)")
    return snapshot


if __name__ == "__main__":
    run(fetch_hist="--no-history" not in sys.argv)
