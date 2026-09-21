# Credit Oracle

**Prediction markets as a catalyst screen for event-driven credit.**
Crowd-implied probabilities — and, for ladder markets, full hazard curves — for the events that move European subordinated and special-situations paper.

Live site: https://creditoracle.belkacem.xyz (GitHub Pages; DNS pending)

## The idea in one paragraph

An event-driven credit process has a step where someone has to answer *how likely is the catalyst?* — a best / base / worst scenario tree filled with analyst judgement. For a subset of catalysts (ceasefires, elections, budgets, central-bank decisions, single-name bankruptcies, M&A completions) there is now a live, tradeable, time-stamped probability: a prediction market. This tool pulls those markets from Polymarket, maps each to the instruments on the other end of the transmission channel, and presents the probabilities in the shape credit people already read — a term structure and a hazard rate.

The hook: a Polymarket *ladder* ("ceasefire by October / November / December …") is a cumulative distribution over the event time. Take the survival function, assume constant intensity between rungs, and you have the same object a CDS curve gives you.

## What's in it

| Page | What it shows |
|---|---|
| **Catalyst Board** | One row per mapped event: P, Δ7d / Δ30d with a z-score vs. the market's own history, liquidity grade, direction for the credit, exposed issuers. Sortable, filterable. |
| **Event** | P history, CDF (raw rungs + isotonic fit), piecewise-constant hazard curve, every market in the event, **crowd vs. credit** (Frankfurt quotes for the exposed bonds, their β to the crowd probability, bond-implied hazard for bullets), exposed instruments with channel and confidence, best/base/worst scenarios, Polymarket's resolution rules. |
| **Hazard curves** | All ladders overlaid as hazard curves; the headline ladder's curve rebuilt day by day as a time × tenor heatmap; per-ladder P(12m), λ(12m), E[T \| occurs]. |
| **Methodology** | Every number's "how", the grading rules verbatim, and what's missing. |

## How it works

```
data/mappings.yaml          hand-curated: event → channel → instruments (this is the product)
pipeline/fetch_polymarket   Gamma API (markets, best bid/ask) + CLOB API (daily price history)
pipeline/fetch_bonds        Deutsche Börse quotes/closes for every ISIN in the mapping; ECB + FRED curves. Best effort.
pipeline/credit             bond rows per event: quote, bullet-bond implied hazard, β to the crowd series
analytics/hazard            ladder → monotone CDF (PAVA, liquidity-weighted) → survival → hazard
analytics/quality           A / B / C liquidity grade, three rules
analytics/moves             Δ1d/7d/30d and a trailing-90d z-score
analytics/bond_pd           YTM → spread over govt → λ = s/(1−R) → PD, bullets only
analytics/beta              OLS of 7-day bond price changes on 7-day crowd probability changes
pipeline/build              → site/data/*.json
site/                       static HTML + inline SVG charts, no framework
.github/workflows/update    every 6h: fetch, build, commit the snapshot, deploy Pages
```

The repository is the database: every snapshot and history file is committed.

## Run it

```sh
uv sync
uv run pytest
uv run python -m pipeline.fetch_polymarket   # ~70 API calls, no auth
uv run python -m pipeline.fetch_bonds        # optional; skips anything it can't get
uv run python -m pipeline.build
cd site && python3 -m http.server 8765        # open http://localhost:8765
```

## Deploy

Push to GitHub, enable **Settings → Pages → Source: GitHub Actions**, then run the `update` workflow once from the Actions tab. The cron takes it from there.

## Honesty

Prediction-market prices are thin, US-centric, and only a probability where someone will trade them — hence the grade next to every number and the raw dots on every fitted curve. Polymarket has almost no European single-name bankruptcy markets; that gap is stated on the site rather than hidden. This is a research tool and a screen input, not advice and not a signal.

## Roadmap

- Same-issuer crowd PD vs. bond PD — blocked on a US bond price source (the names with Polymarket bankruptcy markets aren't quoted in Frankfurt).
- Yield-to-call for AT1s / hybrids once first-call dates are in the mapping.
- LLM-assisted screening of new Polymarket events into a review queue — nothing goes live without a human accepting it into `mappings.yaml`.

---
Built in Hamburg by [Belkacem Berchiche](https://belkacem.xyz) · also [BayesFC](https://bayesfc.com)
