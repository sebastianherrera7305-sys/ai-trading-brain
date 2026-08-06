"""Deterministic generator for the Gap Continuation study config family.

Every config this study runs is emitted by this script (committed to the
repo), so the full parameter grid is explicit, reviewable, and
reproducible: re-running this script must reproduce the exact same JSON
documents.

Grid
    - threshold_pct sweep: [0.3, 0.5, 0.7, 1.0]
    - hold_days x direction: 3 x 3 fixed cells (one config per cell)
    - cost robustness: the same 36 cells re-run at 2.5 and 5.0 bps
    - benchmarks: buy & hold, random entries (3 seeds), SMA and EMA
      crossover pairs
    - meta-validation config (dataset registered after trial assembly)

Usage
    python3 generate_configs.py [out_dir]
"""

import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)

HYPOTHESIS = (
    "Overnight gaps in ES daily futures tend to continue (gap continuation): "
    "entering in the gap direction after a gap exceeding threshold_pct and "
    "holding for hold_days yields a positive edge after transaction costs."
)
AUTHOR = "sebastian"

THRESHOLDS = [0.3, 0.5, 0.7, 1.0]
HOLDS = [1, 2, 3]
DIRECTIONS = ["up", "down", "both"]
STRATEGY_SEEDS = [0, 1, 2]
RANDOM_SEEDS = [0, 1, 2]
CROSSOVER_PAIRS = [(5, 50), (10, 100), (20, 200)]


def base(module, dataset, parameters, objective, seeds, sweep=None):
    doc = {
        "hypothesis": HYPOTHESIS,
        "objective": objective,
        "author": AUTHOR,
        "experiment": {
            "module": module,
            "function": "run",
            "parameters": parameters,
            "dataset": dataset,
        },
        "seeds": seeds,
    }
    if sweep is not None:
        doc["sweep"] = sweep
    return doc


def cell_scan_configs():
    configs = {}
    for hold in HOLDS:
        for direction in DIRECTIONS:
            name = "config_scan_h%d_d%s.json" % (hold, direction)
            configs[name] = base(
                "gap_strategy", "es-f-10y-ohlc-v1",
                {"threshold_pct": 0.5, "hold_days": hold,
                 "direction": direction, "cost_bps": 0.0},
                ("Scan threshold_pct in [0.3, 0.5, 0.7, 1.0] for "
                 "hold_days=%d, direction=%s at zero cost (seed 0-2): "
                 "the search set for the trial matrix." % (hold, direction)),
                STRATEGY_SEEDS,
                sweep={"parameter": "threshold_pct", "values": THRESHOLDS},
            )
    return configs


def cost_configs():
    configs = {}
    for hold in HOLDS:
        for direction in DIRECTIONS:
            for cost in (2.5, 5.0):
                name = "config_cost_h%d_d%s_%g.json" % (hold, direction, cost)
                configs[name] = base(
                    "gap_strategy", "es-f-10y-ohlc-v1",
                    {"threshold_pct": 0.5, "hold_days": hold,
                     "direction": direction, "cost_bps": cost},
                    ("Cost robustness: same grid as the scan but with "
                     "%.1f bps round-trip cost (seed 0-2)." % cost),
                    STRATEGY_SEEDS,
                    sweep={"parameter": "threshold_pct", "values": THRESHOLDS},
                )
    return configs


def benchmark_configs():
    configs = {
        "config_buyhold.json": base(
            "buy_hold", "es-f-10y-ohlc-v1", {},
            "Benchmark: fully invested buy & hold of the ES index.", [0],
        ),
    }
    for hold in HOLDS:
        configs["config_random_h%d.json" % hold] = base(
            "random_entries", "es-f-10y-ohlc-v1",
            {"entry_prob": 0.05, "hold_days": hold},
            ("Benchmark: random non-overlapping entries (p=0.05), "
             "hold_days=%d; stochastic, 3 seeds." % hold),
            RANDOM_SEEDS,
        )
    for kind, module in (("sma", "sma_crossover"), ("ema", "ema_crossover")):
        for fast, slow in CROSSOVER_PAIRS:
            configs["config_%s_%d_%d.json" % (kind, fast, slow)] = base(
                module, "es-f-10y-ohlc-v1",
                {"fast": fast, "slow": slow},
                "Benchmark: %s(%d, %d) crossover, long-only." % (kind.upper(), fast, slow),
                [0],
            )
    return configs


def meta_config():
    return {
        "config_meta.json": {
            "hypothesis": HYPOTHESIS,
            "objective": (
                "Meta-validation of the Gap Continuation search: DSR, "
                "White's Reality Check and benchmark comparisons over the "
                "assembled trial matrix (dataset registered by the "
                "assembly script). Seeds 0-2."
            ),
            "author": AUTHOR,
            "experiment": {
                "module": "gap_meta",
                "function": "run",
                "parameters": {},
                "dataset": "es-gap-trial-matrix-v1",
            },
            "seeds": [0, 1, 2],
        }
    }


def main():
    configs = {}
    configs.update(cell_scan_configs())
    configs.update(cost_configs())
    configs.update(benchmark_configs())
    configs.update(meta_config())

    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, doc in sorted(configs.items()):
        (OUT / name).write_text(
            json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        written.append(name)
    print("wrote %d configs to %s:" % (len(written), OUT))
    for name in sorted(written):
        print("  %s" % name)


if __name__ == "__main__":
    main()
