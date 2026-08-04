"""Historical OHLC candles for the dashboard's price chart -- read once
from the same CSVs already used to validate this system's backtests
(data/), cached in memory per symbol.

This is NOT a live feed. Paper mode currently has no market-data source
wired into the running service (see README) -- LiveEngine only reacts to
bars that arrive via Broker.subscribe_bars, and nothing calls feed_bar()
outside of tests. Until that's built, the chart shows real historical
price action so the dashboard isn't a blank panel with no context, but a
freshly started paper session will show no NEW candles forming live.
"""

import csv
from pathlib import Path
from typing import Dict, List

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

_SYMBOL_FILES = {
    "GC=F": "GC_F.csv",
    "ES=F": "ES_F.csv",
    "CL=F": "CL_F.csv",
    "EURUSD=X": "EURUSD_X.csv",
}

_cache: Dict[str, List[dict]] = {}


def _load(symbol: str) -> List[dict]:
    filename = _SYMBOL_FILES.get(symbol)
    if filename is None:
        return []
    path = DATA_DIR / filename
    if not path.exists():
        return []
    bars = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                bars.append({
                    "time": row["date"].strip()[:10],
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                })
            except (KeyError, ValueError):
                continue
    bars.sort(key=lambda b: b["time"])
    return bars


def get_candles(symbol: str, limit: int = 300) -> List[dict]:
    if symbol not in _cache:
        _cache[symbol] = _load(symbol)
    bars = _cache[symbol]
    return bars[-limit:] if limit and limit > 0 else bars


def available_symbols() -> List[str]:
    return list(_SYMBOL_FILES.keys())
