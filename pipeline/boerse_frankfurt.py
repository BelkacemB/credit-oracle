"""Thin client for the undocumented Deutsche Börse (ex boerse-frankfurt.de) data API.

The site's own front-end signs each request with an MD5 trace id derived from a
salt embedded in its main JS bundle (approach from github.com/joqueka/bf4py).
Public, delayed 15 min, and entirely best-effort: everything here may break
without notice, and callers must treat failures as "no quote".
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx

SITE = "https://live.deutsche-boerse.com"
BASE = "https://api.live.deutsche-boerse.com/v1/data/"


class BoerseFrankfurt:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=20, follow_redirects=True)
        self.client.headers.update({
            "origin": SITE,
            "referer": SITE + "/",
            "user-agent": "Mozilla/5.0 (Macintosh) credit-oracle research",
        })
        self.salt = self._fetch_salt()

    def _fetch_salt(self) -> str:
        home = self.client.get(SITE + "/")
        home.raise_for_status()
        files = re.findall(r'(?<=src=")main\.\w*\.js', home.text)
        if len(files) != 1:
            raise RuntimeError("boerse-frankfurt: main JS bundle not found")
        js = self.client.get(SITE + "/" + files[0])
        js.raise_for_status()
        salts = re.findall(r'(?<=salt:")\w*', js.text)
        if len(salts) != 1:
            raise RuntimeError("boerse-frankfurt: tracing salt not found")
        return salts[0]

    def _headers(self, url: str) -> dict[str, str]:
        # Mirrors the bundle's generateHeaders(): date-fns formatISO of local time
        # (seconds precision, numeric offset), md5(date + url + salt), md5(yyyyMMddHHmm).
        now = datetime.now().astimezone()
        ts = now.isoformat(timespec="seconds")
        if ts.endswith("+00:00"):
            ts = ts[:-6] + "Z"
        trace = hashlib.md5((ts + url + self.salt).encode()).hexdigest()
        sec = hashlib.md5(now.strftime("%Y%m%d%H%M").encode()).hexdigest()
        return {"client-date": ts, "x-client-traceid": trace, "x-security": sec,
                "accept": "application/json, text/plain, */*"}

    def get(self, function: str, **params) -> dict | list:
        url = BASE + function + "?" + urlencode(params)
        r = self.client.get(url, headers=self._headers(url))
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and data.get("messages"):
            raise RuntimeError(f"boerse-frankfurt: {data['messages']}")
        return data

    # --- convenience wrappers ------------------------------------------------
    def bond_master(self, isin: str) -> dict:
        return self.get("master_data_bond", isin=isin)

    def quote(self, isin: str, mic: str = "XFRA") -> dict:
        return self.get("quote_box/single", isin=isin, mic=mic)

    def bid_ask(self, isin: str, mic: str = "XFRA") -> dict:
        return self.get("bid_ask_overview", isin=isin, mic=mic)

    def price_history(self, isin: str, mic: str = "XFRA", days: int = 365) -> list:
        from datetime import timedelta
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days)
        d = self.get("price_history", limit=400, offset=0, isin=isin, mic=mic,
                     minDate=start.isoformat(), maxDate=end.isoformat(), cleanSplit="false",
                     cleanPayout="false", cleanSubscriptionRights="false")
        return d.get("data", []) if isinstance(d, dict) else d
