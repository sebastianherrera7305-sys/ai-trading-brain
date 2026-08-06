"""Assemble the Gap Fading trial matrix from registry artifacts.

Data-engineering step (no statistics — all statistics happen in the
meta-validation experiment via quant_research):

    - strategy_trials: (36, n_days) daily P&L of every fade strategy
      cell at zero cost, one row per (threshold_pct, hold_days,
      direction) cell, ordered by (threshold, hold, direction), row =
      seed-0 run (the strategy P&L is deterministic given params).
    - trial_threshold / trial_hold / trial_direction: the cell params
      of each row.
    - delayed_trials / delayed_threshold / delayed_hold /
      delayed_direction: the 36-cell delayed-entry layer (spec §7.5;
      separate search, reported as a robustness fact at closure).
    - c001_best_series: (1, n_days) daily P&L of the C001 best cell
      (best ann_sharpe among seed-0 zero-cost gap_strategy runs) — the
      paired C001-vs-C002 comparison basis (spec §8/§9.8).
    - random_series: (9, n_days) random-entries benchmark (3 holds x 3
      seeds, all stochastic draws are rows) — C001 runs reused.
    - buyhold_series: (1, n_days). sma_series / ema_series: (3, n_days)
      each — C001 runs reused (E-0002).
    - F-GAP-COMP decomposition arrays (overnight_ret, intraday_ret,
      cumulative drift series) computed by the shared features module
      (feature engineering only; the correlation is computed by the
      meta-validation experiment via quant_research).

Evidence selection (B3): every candidate run is gated by
`_is_eligible_run` — completed, clean git tree (no
UNVERIFIABLE_REPRODUCTION marker, no dirty env/record), full environment
snapshot. Excluded candidates are REPORTED (never hidden), and a cell
whose only candidate was excluded is treated as missing (the assembly
refuses to build the matrix from ineligible evidence). This guarantees
the DSR/Reality Check inputs rest only on acceptance-eligible runs.

The resulting npz is registered as dataset `es-gap-fade-trial-matrix-v1`
(registration command printed; the registry is the single source of
truth for what the meta-validation experiment consumes).

Usage:
    python3 assemble_trial_matrix.py [--root /tmp/research-study] [--out data/es_gap_fade_trial_matrix_v1.npz]
"""

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np

STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(STUDY_DIR.parents[1]))

from research_platform.store import ResearchStore  # noqa: E402

sys.path.insert(0, str(STUDY_DIR))
from features import gap_decomposition  # noqa: E402

THRESHOLDS = [0.3, 0.5, 0.7, 1.0]
HOLDS = [1, 2, 3]
DIRECTIONS = ["up", "down", "both"]
TRIAL_DAYS = 2513
OHLC_DATASET = "es-f-10y-ohlc-v1"


def _is_eligible_run(store: ResearchStore, exp) -> tuple:
    """Evidence eligibility gate for a candidate experiment (B3).

    Returns (eligible: bool, reason: str). A run can support acceptance
    only if its latest execution is completed, was run on a clean git
    tree (no UNVERIFIABLE_REPRODUCTION marker, no dirty env/record flag)
    and carries a full environment snapshot. Anything else is excluded
    from the trial matrix; the exclusion is reported, never hidden.
    """
    run = store.get_latest_run(exp.uuid)
    if run is None:
        return False, "no run recorded"
    if run.status != "completed":
        return False, "run status=%s (not completed)" % run.status
    env = run.env or {}
    git = env.get("git") or {}
    if env.get("unverifiable_reproduction"):
        return False, (
            "UNVERIFIABLE_REPRODUCTION (dirty tree at execution, commit %s)"
            % git.get("commit", "n/a")
        )
    if git.get("dirty"):
        return False, "git dirty at execution (commit %s)" % git.get("commit", "n/a")
    if not env:
        return False, "missing environment snapshot (git state unknown)"
    if getattr(exp, "git_dirty", None):
        return False, "experiment record git_dirty=True (commit %s)" % (exp.git_commit or "n/a")
    return True, "eligible (clean tree, completed, full env)"


def _report_discards(tag: str, discarded: list) -> None:
    """Traceability: record why candidates were excluded from evidence."""
    if not discarded:
        return
    print("evidence selection: %d %s candidate(s) excluded:" % (len(discarded), tag))
    for key, uuid8, reason in discarded:
        print("  cell=%s exp=%s -> %s" % (key, uuid8, reason))


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


def ordered_cells(store: ResearchStore, module: str) -> dict:
    """Evidence-eligible seed-0 zero-cost cell runs keyed by cell.

    Prefers clean-tree, completed, seed-0 runs with full metadata;
    records (and never hides) every excluded candidate. A cell whose
    only candidate was excluded is reported as missing — the assembly
    refuses to build the matrix from ineligible evidence.
    """
    cells = {}
    discarded = []
    for exp in store.find_experiments(module=module, status="completed"):
        p = exp.params
        if float(p.get("cost_bps", 0.0)) != 0.0:
            continue
        if exp.seed != 0:
            continue
        key = (float(p["threshold_pct"]), int(p["hold_days"]), str(p["direction"]))
        if key in cells:
            continue
        ok, reason = _is_eligible_run(store, exp)
        if not ok:
            discarded.append((key, exp.uuid[:8], reason))
            continue
        cells[key] = exp
    _report_discards(module, discarded)
    expected = len(THRESHOLDS) * len(HOLDS) * len(DIRECTIONS)
    missing = [k for k in [
        (t, h, d)
        for t in THRESHOLDS for h in HOLDS for d in DIRECTIONS
    ] if k not in cells]
    if missing:
        raise RuntimeError(
            "missing eligible %s cells: %s (ineligible candidates were excluded; "
            "see discarded list above)" % (module, (missing,))
        )
    if len(cells) != expected:
        raise RuntimeError("expected %d cells, found %d" % (expected, len(cells)))
    return cells


def best_c001_cell(store: ResearchStore):
    """C001 best cell: max ann_sharpe among evidence-eligible seed-0
    zero-cost runs (same B3 eligibility gate; C001 runs are unchanged)."""
    best = None
    best_sharpe = -1.0
    discarded = []
    for exp in store.find_experiments(module="gap_strategy", status="completed"):
        p = exp.params
        if float(p.get("cost_bps", 0.0)) != 0.0 or exp.seed != 0:
            continue
        ok, reason = _is_eligible_run(store, exp)
        if not ok:
            discarded.append((("c001", p.get("threshold_pct"), p.get("hold_days"),
                              p.get("direction")), exp.uuid[:8], reason))
            continue
        run = store.get_latest_run(exp.uuid)
        sharpe = float(run.metrics.get("ann_sharpe", -1.0))
        if sharpe > best_sharpe:
            best, best_sharpe = exp, sharpe
    _report_discards("c001 best-cell", discarded)
    if best is None:
        raise RuntimeError("no C001 best cell found (no eligible seed-0 zero-cost gap_strategy runs)")
    return best, best_sharpe


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="/tmp/research-study")
    ap.add_argument("--out", default=str(REPO_ROOT / "data/es_gap_fade_trial_matrix_v1.npz"))
    args = ap.parse_args()

    store = ResearchStore(args.root)

    cells = ordered_cells(store, "gap_fading")
    ordered = [(t, h, d) for t in THRESHOLDS for h in HOLDS for d in DIRECTIONS]
    trials = np.stack([load_run_series(store, cells[k]) for k in ordered])
    trial_threshold = np.asarray([k[0] for k in ordered], dtype=np.float64)
    trial_hold = np.asarray([k[1] for k in ordered], dtype=np.float64)
    trial_direction = np.asarray([k[2].encode() for k in ordered], dtype="S4")

    delayed_cells = ordered_cells(store, "gap_fading_delayed")
    delayed_trials = np.stack([load_run_series(store, delayed_cells[k]) for k in ordered])
    delayed_threshold = np.asarray([k[0] for k in ordered], dtype=np.float64)
    delayed_hold = np.asarray([k[1] for k in ordered], dtype=np.float64)
    delayed_direction = np.asarray([k[2].encode() for k in ordered], dtype="S4")

    c001_exp, c001_sharpe = best_c001_cell(store)
    c001_best_series = load_run_series(store, c001_exp)

    def rows(module, sort_key):
        exps = []
        discarded = []
        for e in store.find_experiments(module=module, status="completed"):
            ok, reason = _is_eligible_run(store, e)
            if not ok:
                discarded.append(((e.params,), e.uuid[:8], reason))
                continue
            exps.append(e)
        _report_discards(module, discarded)
        if not exps:
            raise RuntimeError("no eligible completed %s experiments" % module)
        exps.sort(key=sort_key)
        return np.stack([load_run_series(store, e) for e in exps])

    random_series = rows("random_entries", lambda e: (int(e.params["hold_days"]), e.seed))
    buyhold_series = rows("buy_hold", lambda e: e.uuid)
    sma_series = rows("sma_crossover", lambda e: (int(e.params["fast"]), int(e.params["slow"])))
    ema_series = rows("ema_crossover", lambda e: (int(e.params["fast"]), int(e.params["slow"])))

    # F-GAP-COMP decomposition arrays (feature engineering only).
    dataset = store.get_dataset(OHLC_DATASET)
    blob = np.load(store.dataset_object_path(dataset))
    decomp = gap_decomposition(blob["ohlc"])

    np.savez_compressed(
        args.out,
        strategy_trials=trials,
        trial_threshold=trial_threshold,
        trial_hold=trial_hold,
        trial_direction=trial_direction,
        delayed_trials=delayed_trials,
        delayed_threshold=delayed_threshold,
        delayed_hold=delayed_hold,
        delayed_direction=delayed_direction,
        c001_best_series=c001_best_series,
        random_series=random_series,
        buyhold_series=buyhold_series,
        sma_series=sma_series,
        ema_series=ema_series,
        overnight_ret=decomp["overnight_ret"],
        intraday_ret=decomp["intraday_ret"],
        cum_overnight=decomp["cum_overnight"],
        cum_intraday=decomp["cum_intraday"],
    )

    sha = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print("wrote %s (%d bytes)" % (args.out, Path(args.out).stat().st_size))
    print("sha256 %s" % sha)
    print("fade cells %d, delayed cells %d, c001 best (thr=%.2f hold=%d dir=%s, Sharpe=%.3f), "
          "random rows %d, buyhold rows %d, sma rows %d, ema rows %d"
          % (len(ordered), len(ordered),
             float(c001_exp.params["threshold_pct"]), int(c001_exp.params["hold_days"]),
             str(c001_exp.params["direction"]), c001_sharpe,
             random_series.shape[0], buyhold_series.shape[0],
             sma_series.shape[0], ema_series.shape[0]))
    print("register with: python3 -m research_platform.cli --root %s dataset register %s "
          "--source 'CME E-mini S&P 500 futures (ES), continuous front month' "
          "--provider 'study assembly (registry -> npz)' --version v1 --symbol ES "
          "--timeframe 1d --timezone America/New_York "
          "--name es-gap-fade-trial-matrix-v1 "
          "--pipeline 'fade trial matrix assembled from registered experiment artifacts; no statistics'" % (
              args.root, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
