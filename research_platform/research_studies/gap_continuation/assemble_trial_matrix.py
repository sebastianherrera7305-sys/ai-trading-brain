"""Assemble the Gap Continuation trial matrix from registry artifacts.

Data-engineering step (no statistics — all statistics happen in the
meta-validation experiment via quant_research):

    - strategy_trials: (36, n_days) daily P&L of every strategy cell at
      zero cost, one row per (threshold_pct, hold_days, direction) cell,
      ordered by (threshold, hold, direction), row = seed-0 run (the
      strategy P&L is deterministic given params).
    - trial_threshold / trial_hold / trial_direction: the cell params
      of each row.
    - random_series: (9, n_days) random-entries benchmark (3 holds x 3
      seeds, all stochastic draws are rows).
    - buyhold_series: (1, n_days).
    - sma_series / ema_series: (3, n_days) each.

The resulting npz is registered as dataset `es-gap-trial-matrix-v1`
(registration command printed; the registry is the single source of
truth for what the meta-validation experiment consumes).

Usage:
    python3 assemble_trial_matrix.py [--root /tmp/research-study] [--out data/es_gap_trial_matrix_v1.npz]
"""

import argparse
import sys
from pathlib import Path

import numpy as np

STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(STUDY_DIR.parents[1]))

from research_platform.store import ResearchStore  # noqa: E402

THRESHOLDS = [0.3, 0.5, 0.7, 1.0]
HOLDS = [1, 2, 3]
DIRECTIONS = ["up", "down", "both"]
CROSSOVER_PAIRS = [(5, 50), (10, 100), (20, 200)]
TRIAL_DAYS = 2513


def load_run_series(store: ResearchStore, exp, name="daily_returns") -> np.ndarray:
    run = store.get_latest_run(exp.uuid)
    if run is None or run.status != "completed":
        raise RuntimeError("experiment %s has no completed run" % exp.uuid)
    art = run.artifacts.get(name)
    if art is None:
        raise RuntimeError("experiment %s has no artifact %s" % (exp.uuid, name))
    path = store.run_dir(exp.uuid, run.run_number) / art["path"]
    arr = np.load(path)
    if arr.shape[0] != TRIAL_DAYS:
        raise RuntimeError("unexpected length %d for %s" % (arr.shape[0], exp.uuid))
    return arr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/research-study")
    ap.add_argument("--out", default=str(REPO_ROOT / "data/es_gap_trial_matrix_v1.npz"))
    args = ap.parse_args()

    store = ResearchStore(args.root)

    strategy = store.find_experiments(module="gap_strategy", status="completed")
    cells = {}
    for exp in strategy:
        p = exp.params
        if float(p.get("cost_bps", 0.0)) != 0.0:
            continue
        key = (float(p["threshold_pct"]), int(p["hold_days"]), str(p["direction"]))
        if key not in cells or exp.seed == 0:
            cells[key] = exp
    expected = len(THRESHOLDS) * len(HOLDS) * len(DIRECTIONS)
    missing = [k for k in [
        (t, h, d)
        for t in THRESHOLDS for h in HOLDS for d in DIRECTIONS
    ] if k not in cells]
    if missing:
        raise RuntimeError("missing strategy cells: %s" % (missing,))
    if len(cells) != expected:
        raise RuntimeError("expected %d cells, found %d" % (expected, len(cells)))

    ordered = [(t, h, d) for t in THRESHOLDS for h in HOLDS for d in DIRECTIONS]
    trials = np.stack([load_run_series(store, cells[k]) for k in ordered])
    trial_threshold = np.asarray([k[0] for k in ordered], dtype=np.float64)
    trial_hold = np.asarray([k[1] for k in ordered], dtype=np.float64)
    trial_direction = np.asarray([k[2].encode() for k in ordered], dtype="S4")

    def rows(module, sort_key):
        exps = store.find_experiments(module=module, status="completed")
        if not exps:
            raise RuntimeError("no completed %s experiments" % module)
        exps.sort(key=sort_key)
        return np.stack([load_run_series(store, e) for e in exps])

    random_series = rows("random_entries", lambda e: (int(e.params["hold_days"]), e.seed))
    buyhold_series = rows("buy_hold", lambda e: e.uuid)
    sma_series = rows("sma_crossover", lambda e: (int(e.params["fast"]), int(e.params["slow"])))
    ema_series = rows("ema_crossover", lambda e: (int(e.params["fast"]), int(e.params["slow"])))

    np.savez_compressed(
        args.out,
        strategy_trials=trials,
        trial_threshold=trial_threshold,
        trial_hold=trial_hold,
        trial_direction=trial_direction,
        random_series=random_series,
        buyhold_series=buyhold_series,
        sma_series=sma_series,
        ema_series=ema_series,
    )

    import hashlib
    sha = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print("wrote %s (%d bytes)" % (args.out, Path(args.out).stat().st_size))
    print("sha256 %s" % sha)
    print("strategy cells %d, random rows %d, buyhold rows %d, sma rows %d, ema rows %d"
          % (len(ordered), random_series.shape[0], buyhold_series.shape[0],
             sma_series.shape[0], ema_series.shape[0]))
    print("register with: python3 -m research_platform.cli --root %s dataset register %s "
          "--source 'CME E-mini S&P 500 futures (ES), continuous front month' "
          "--provider 'study assembly (registry -> npz)' --version v1 --symbol ES "
          "--timeframe 1d --timezone America/New_York "
          "--name es-gap-trial-matrix-v1 "
          "--pipeline 'trial matrix assembled from registered experiment artifacts; no statistics'" % (
              args.root, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
