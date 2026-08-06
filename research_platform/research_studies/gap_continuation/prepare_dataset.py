#!/usr/bin/env python3
"""Gap Continuation Study — dataset preparation.

Reads the raw daily OHLC CSV (data/ES_F_10y.csv, canonical source) and
produces the registered study dataset as a float matrix:

    data/es_f_10y_ohlc_v1.npz
        ohlc   (n, 4) float64  [open, high, low, close]
        dates  (n,) int64      days since 1970-01-01 (numpy datetime64)

Transformations (documented pipeline; recorded on the dataset record):
    - date strings -> integer epoch days (no interpretation, no resampling)
    - price columns -> float64, verbatim
    - no missing-value imputation, no adjustments, no synthetic rows

Output is derived 1:1 from the CSV: row order and values are preserved.
This script performs data engineering only — no statistics.
"""

import csv
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "ES_F_10y.csv"
OUT = ROOT / "data" / "es_f_10y_ohlc_v1.npz"


def main() -> None:
    with open(SRC, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == ["date", "open", "high", "low", "close"], reader.fieldnames
        dates = []
        rows = []
        for row in reader:
            dates.append(np.datetime64(row["date"], "D").astype("int64"))
            rows.append([float(row["open"]), float(row["high"]),
                         float(row["low"]), float(row["close"])])
    ohlc = np.asarray(rows, dtype=np.float64)
    epoch_days = np.asarray(dates, dtype=np.int64)
    assert ohlc.shape[0] == epoch_days.shape[0] == 2513, ohlc.shape
    assert ohlc.shape[1] == 4
    assert np.isfinite(ohlc).all()
    assert (ohlc[:, 1] >= ohlc[:, 2]).all(), "high < low in raw data"

    np.savez(OUT, ohlc=ohlc, dates=epoch_days)
    print("wrote %s: %d rows x %d cols, %d bytes"
          % (OUT, ohlc.shape[0], ohlc.shape[1], OUT.stat().st_size))


if __name__ == "__main__":
    main()
