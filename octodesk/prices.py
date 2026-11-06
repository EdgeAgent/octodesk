"""Price series: live from Yahoo Finance if the network cooperates, otherwise
the bundled fixture so the Kraken can always hunt (and tests never flake).
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

UNIVERSE = ["NVDA", "AMZN", "TSLA", "MSFT", "META", "GOOGL",
            "AAPL", "JPM", "V", "XOM", "JNJ", "PG"]

_FIXTURE = Path(__file__).with_name("data") / "fixture_prices.json"
_cache = {"ts": 0.0, "data": None}
CACHE_SECONDS = 300


def load_fixture():
    raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return {sym: [float(x) for x in raw["assets"][sym]] for sym in UNIVERSE}


def fetch_live(timeout=6):
    """Fetch ~6 months of daily closes per asset from Yahoo's chart API."""
    out = {}
    for sym in UNIVERSE:
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
               f"?range=6mo&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "OctoDesk/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        result = payload["chart"]["result"][0]
        closes = result["indicators"]["quote"][0]["close"]
        series = [float(c) for c in closes if c is not None]
        if len(series) < 30:
            raise ValueError(f"not enough live data for {sym}")
        out[sym] = series
    return out


def get_prices(live=True):
    """Return (series_by_symbol, source) where source is 'live' or 'fixture'."""
    if not live:
        return load_fixture(), "fixture"
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < CACHE_SECONDS:
        return _cache["data"], "live"
    try:
        data = fetch_live()
    except Exception:
        return load_fixture(), "fixture"
    _cache.update(ts=now, data=data)
    return data, "live"
