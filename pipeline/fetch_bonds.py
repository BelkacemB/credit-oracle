"""Best-effort public bond quotes for every ISIN in data/mappings.yaml.

  data/bonds/<isin>.json     quote + master + ~400d of daily closes (overwritten each run)
  data/rates.json            EUR AAA spot curve (ECB) and UST constant-maturity (FRED)

Every source is public and unofficial. Any failure is logged and skipped; the
site renders "n/a" for what is missing. Never let this module fail the build.
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from datetime import UTC, datetime

import httpx
import yaml

from pipeline.boerse_frankfurt import BoerseFrankfurt
from pipeline.config import DATA, MAPPINGS

BONDS = DATA / "bonds"
RATES = DATA / "rates.json"

ECB_URL = ("https://data-api.ecb.europa.eu/service/data/YC/"
           "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_1Y+SR_2Y+SR_3Y+SR_5Y+SR_7Y+SR_10Y+SR_15Y"
           "?lastNObservations=1&format=csvdata")
FRED = {1: "DGS1", 2: "DGS2", 3: "DGS3", 5: "DGS5", 7: "DGS7", 10: "DGS10"}


def all_isins() -> list[str]:
    seen: list[str] = []
    for e in yaml.safe_load(MAPPINGS.read_text()):
        for x in e.get("exposures", []) + e.get("names", []):
            for i in x.get("instruments", []):
                if i.get("isin") and i["isin"] not in seen:
                    seen.append(i["isin"])
    return seen


def fetch_rates(client: httpx.Client) -> dict:
    out: dict = {"asof": datetime.now(UTC).date().isoformat(), "EUR": {}, "USD": {}}
    try:
        r = client.get(ECB_URL); r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            key = row["KEY"].rsplit(".", 1)[-1]          # SR_5Y
            tenor = int(key[3:-1])
            out["EUR"][tenor] = float(row["OBS_VALUE"]) / 100
        out["EUR_date"] = row["TIME_PERIOD"]
    except Exception as e:  # noqa: BLE001
        print(f"  !! ECB curve failed: {e}", file=sys.stderr)
    for tenor, sid in FRED.items():
        try:
            r = client.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"); r.raise_for_status()
            last = [ln for ln in r.text.strip().splitlines()[1:] if not ln.endswith(",.")][-1]
            d, v = last.split(",")
            out["USD"][tenor] = float(v) / 100
            out["USD_date"] = d
        except Exception as e:  # noqa: BLE001
            print(f"  !! FRED {sid} failed: {e}", file=sys.stderr)
    return out


def run() -> None:
    BONDS.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        rates = fetch_rates(client)
    RATES.write_text(json.dumps(rates, indent=1))
    print(f"rates: EUR {len(rates['EUR'])} tenors, USD {len(rates['USD'])} tenors")

    try:
        bf = BoerseFrankfurt()
    except Exception as e:  # noqa: BLE001
        print(f"  !! Deutsche Börse connector failed: {e} — keeping previous bond files", file=sys.stderr)
        return
    ok = 0
    for isin in all_isins():
        rec: dict = {"isin": isin, "fetched_at": datetime.now(UTC).isoformat(), "quote": None,
                     "master": None, "history": []}
        try:
            rec["quote"] = bf.quote(isin)
        except Exception as e:  # noqa: BLE001
            print(f"  -- {isin}: no quote ({type(e).__name__})", file=sys.stderr)
            (BONDS / f"{isin}.json").write_text(json.dumps(rec))
            continue
        for fn, key in (("bond_master", "master"),):
            try:
                rec[key] = getattr(bf, fn)(isin)
            except Exception:  # noqa: BLE001
                pass
        try:
            rec["history"] = [{"date": h["date"], "close": h["close"]} for h in bf.price_history(isin, days=400)
                              if h.get("close") is not None]
        except Exception as e:  # noqa: BLE001
            print(f"  -- {isin}: no history ({type(e).__name__})", file=sys.stderr)
        (BONDS / f"{isin}.json").write_text(json.dumps(rec))
        ok += 1
        time.sleep(0.3)
    print(f"bonds: {ok} quoted of {len(all_isins())}")


if __name__ == "__main__":
    run()
