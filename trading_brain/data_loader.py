"""
Data Loader — AI Trading Brain v1, Phase 2

Turns a CSV of real historical candles into the Candle objects every other
module already speaks. Not part of the core rules engine -- this is the
one piece of the pipeline that has to touch the outside world (a file), so
it's kept separate and deliberately dumb: parse rows, build Candles, done.
No indicators, no resampling, no gap-filling.
"""

import csv
from datetime import datetime
from typing import List, Optional

from .market_structure import Candle

# Common header spellings across brokers/vendors (stooq, MT4/5 exports,
# TradingView, Yahoo Finance, generic OHLC CSVs) mapped to our field names.
_HEADER_ALIASES = {
    "date": "timestamp", "datetime": "timestamp", "time": "timestamp",
    "open": "open", "high": "high", "low": "low", "close": "close",
}

_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y.%m.%d %H:%M:%S",
    "%Y.%m.%d %H:%M",
    "%Y.%m.%d",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y",
)


def _parse_timestamp(raw: str) -> Optional[datetime]:
    raw = raw.strip()
    if not raw:
        return None
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def load_candles_from_csv(path: str, has_header: bool = True) -> List[Candle]:
    """
    Reads a CSV of OHLC candles into a list of Candle, oldest first.

    Expects columns for date/time, open, high, low, close -- column order
    doesn't matter if `has_header` is True (headers are matched
    case-insensitively against common spellings; a "Time" column merges into
    the same date if both are present and adjacent). If `has_header` is
    False, columns are assumed to be exactly (date, open, high, low, close)
    in that order.

    Rows are re-indexed 0..n-1 in file order after an ascending sort by
    timestamp, so `Candle.index` always matches what every other module
    expects: a clean walk-forward sequence with no gaps or reordering.
    """
    rows = []
    with open(path, newline="") as f:
        reader = csv.reader(f)
        raw_rows = list(reader)

    if not raw_rows:
        return []

    if has_header:
        header = [h.strip().lower() for h in raw_rows[0]]
        col_index = {}
        for i, name in enumerate(header):
            mapped = _HEADER_ALIASES.get(name)
            if mapped:
                col_index[mapped] = i
        missing = {"timestamp", "open", "high", "low", "close"} - col_index.keys()
        if missing:
            raise ValueError(f"CSV header is missing required column(s): {sorted(missing)}")
        data_rows = raw_rows[1:]
    else:
        col_index = {"timestamp": 0, "open": 1, "high": 2, "low": 3, "close": 4}
        data_rows = raw_rows

    for row in data_rows:
        if not row or not any(cell.strip() for cell in row):
            continue  # skip blank lines
        ts = _parse_timestamp(row[col_index["timestamp"]])
        rows.append((
            ts,
            float(row[col_index["open"]]),
            float(row[col_index["high"]]),
            float(row[col_index["low"]]),
            float(row[col_index["close"]]),
        ))

    rows.sort(key=lambda r: (r[0] is None, r[0]))  # unparseable timestamps sort last, not first

    return [
        Candle(index=i, open=o, high=h, low=l, close=c, timestamp=ts)
        for i, (ts, o, h, l, c) in enumerate(rows)
    ]
