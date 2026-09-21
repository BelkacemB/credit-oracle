from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MAPPINGS = DATA / "mappings.yaml"
SNAPSHOTS = DATA / "snapshots"
HISTORY = DATA / "history"
SITE_DATA = ROOT / "site" / "data"

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
USER_AGENT = "credit-oracle/0.1 (research; github.com/BelkacemB)"
