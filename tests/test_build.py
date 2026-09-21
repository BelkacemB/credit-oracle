"""End-to-end: build from a synthetic snapshot and check the board/hazard JSON."""
import json
from datetime import date

import pytest

from pipeline import build


def _market(id_, question, p, end, label="", liq=50_000, vol=500_000, closed=False):
    return {"id": id_, "question": question, "groupItemTitle": label, "p_yes": p,
            "bestBid": p - 0.005, "bestAsk": p + 0.005, "spread": 0.01, "liquidity": liq,
            "volume": vol, "volume24hr": 0, "endDate": end, "closed": closed, "description": "rules"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    snaps, hist, site = tmp_path / "snapshots", tmp_path / "history", tmp_path / "site"
    snaps.mkdir(); hist.mkdir()
    monkeypatch.setattr(build, "SNAPSHOTS", snaps)
    monkeypatch.setattr(build, "HISTORY", hist)
    monkeypatch.setattr(build, "SITE_DATA", site)
    mappings = tmp_path / "mappings.yaml"
    mappings.write_text("""
- slug: ladder-ev
  title: Ladder
  kind: ladder
  category: special_situations
  direction: positive
  headline: true
  exposures: [{issuer: RBI, instruments: [], channel: c, confidence: high}]
  scenarios: {best: b, base: b, worst: w}
- slug: basket-ev
  title: Basket
  kind: basket
  category: distressed
  direction: negative
  names:
    - {match: Acme, issuer: Acme Corp, instruments: [], channel: direct, confidence: high}
  scenarios: {}
""")
    monkeypatch.setattr(build, "MAPPINGS", mappings)
    snap = {"fetched_at": "2026-09-21T12:00:00+00:00", "events": {
        "ladder-ev": {"id": "1", "title": "Ladder", "markets": [
            _market("a", "X by December 31, 2026?", 0.20, "2027-01-01T04:59:00Z", "December 31"),
            _market("b", "X by June 30, 2026?", 0.0, "2026-07-01T04:59:00Z", "June 30", closed=True),
            _market("c", "X by March 31, 2027?", 0.18, "2027-04-01T04:59:00Z", "March 31, 2027", liq=500, vol=800),  # thin, non-monotone
            _market("d", "X by June 30, 2027?", 0.55, "2027-07-01T04:59:00Z", "June 30, 2027"),
            _market("g", "X by December 31, 2027?", 0.70, "2028-01-01T04:59:00Z", "December 31, 2027"),
        ]},
        "basket-ev": {"id": "2", "title": "Basket", "markets": [
            _market("e", "Will Acme announce bankruptcy before 2027?", 0.07, "2027-01-01T04:59:00Z"),
            _market("f", "Will Other announce bankruptcy before 2027?", 0.02, "2027-01-01T04:59:00Z"),
        ]},
    }}
    (snaps / "2026-09-21.json").write_text(json.dumps(snap))
    # 40 days of flat-then-jump history for market a
    pts = [{"t": 1789998132 - 86400 * k, "p": 0.10 if k > 5 else 0.20} for k in range(40, 0, -1)]
    (hist / "a.json").write_text(json.dumps(pts))
    return site


def test_rung_date_parsing():
    assert build.rung_date({"question": "X by December 31, 2026?", "endDate": "2027-01-01T04:59:00Z"}) == date(2026, 12, 31)
    assert build.rung_date({"question": "continues through October 15?", "endDate": "2026-10-15T12:00:00Z"}) == date(2026, 10, 15)
    assert build.rung_date({"question": "no date here", "endDate": "2026-10-15T12:00:00Z"}) == date(2026, 10, 15)


def test_build_outputs(env):
    build.run()
    board = json.loads((env / "board.json").read_text())
    assert board["asof"] == "2026-09-21"
    rows = {r["row_id"]: r for r in board["rows"]}
    assert set(rows) == {"ladder-ev", "basket-ev#e"}          # 'Other' has no mapping -> no row
    lad = rows["ladder-ev"]
    assert lad["headline"] and lad["hazard_12m"] is not None
    assert 0.55 < lad["p"] < 0.70                              # P(12m) interpolated between Jun-27 and Dec-27
    assert lad["d7"] == pytest.approx(0.10)                     # benchmark rung 'a' jumped 10 -> 20
    assert "December 31" in lad["subtitle"]

    ev = json.loads((env / "events" / "ladder-ev.json").read_text())
    H = ev["hazard"]
    assert [r["label"] for r in H["rungs"]] == ["December 31", "March 31, 2027", "June 30, 2027", "December 31, 2027"]  # closed rung dropped
    assert H["violations"] >= 1                                 # thin March rung lifted to >= Dec
    assert all(a <= b for a, b in zip(H["p_fit"], H["p_fit"][1:]))
    assert H["rungs"][1]["grade"] == "C"
    assert H["benchmark_market_id"] == "a"
    assert [m["id"] for m in ev["markets"]] == ["b", "a", "c", "d", "g"]  # sorted by rung date

    haz = json.loads((env / "hazard.json").read_text())
    assert len(haz["curves"]) == 1
