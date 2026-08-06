"""Deterministic generator for the Gap Fading study config family (C002).

Every config this study runs is emitted by this script (committed to the
repo), so the full parameter grid is explicit, reviewable, and
reproducible: re-running this script must reproduce the exact same JSON
documents.

Grid
    - threshold_pct sweep: [0.3, 0.5, 0.7, 1.0]
    - hold_days x direction: 3 x 3 fixed cells (one config per cell)
    - cost robustness: the same 36 cells re-run at 2.5 and 5.0 bps
    - delayed-entry layer: the same 36 cells at 0 bps, fill at the
      gap-day close (spec §7.5 — separate search, robustness only)
    - meta-validation config (dataset registered after trial assembly)
    - smoke config (end-to-end module check)

Benchmarks are NOT regenerated: C001's 16 benchmark runs (E-0002) are
reused from the store on the identical basis (spec §8); a spot
reproduction of the 4 headline benchmarks at launch doubles as the
Gate F reproducibility proof.

Usage
    python3 generate_configs.py [out_dir]
"""

import json
import sys
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent)

HYPOTHESIS = (
    "Overnight gaps in ES daily futures tend to fade (gap fading): "
    "entering against the gap direction after a gap exceeding "
    "threshold_pct (short after up gaps, long after down gaps) and "
    "holding for hold_days yields a positive edge after transaction "
    "costs."
)
HYPOTHESIS_ID = "H-MS-01"
AUTHOR = "sebastian"

THRESHOLDS = [0.3, 0.5, 0.7, 1.0]
HOLDS = [1, 2, 3]
DIRECTIONS = ["up", "down", "both"]
STRATEGY_SEEDS = [0, 1, 2]


def base(module, dataset, parameters, objective, seeds, sweep=None):
    doc = {
        "hypothesis": HYPOTHESIS_ID,
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


def cell_scan_configs(module="gap_fading", cost=0.0, delayed=False):
    configs = {}
    for hold in HOLDS:
        for direction in DIRECTIONS:
            prefix = "delayed" if delayed else "scan"
            name = "config_%s_h%d_d%s.json" % (prefix, hold, direction)
            objective = (
                "Delayed-entry robustness: the fade rule entered at the "
                "gap-day close (no open fill) for hold_days=%d, direction=%s "
                "at zero cost (seed 0-2): the separate 36-cell search." % (hold, direction)
                if delayed else
                ("Scan threshold_pct in [0.3, 0.5, 0.7, 1.0] for "
                 "hold_days=%d, direction=%s at zero cost (seed 0-2): "
                 "the search set for the fade trial matrix." % (hold, direction))
            )
            configs[name] = base(
                module, "es-f-10y-ohlc-v1",
                {"threshold_pct": 0.5, "hold_days": hold,
                 "direction": direction, "cost_bps": cost},
                objective,
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
                    "gap_fading", "es-f-10y-ohlc-v1",
                    {"threshold_pct": 0.5, "hold_days": hold,
                     "direction": direction, "cost_bps": cost},
                    ("Cost robustness: same grid as the scan but with "
                     "%.1f bps round-trip cost (seed 0-2)." % cost),
                    STRATEGY_SEEDS,
                    sweep={"parameter": "threshold_pct", "values": THRESHOLDS},
                )
    return configs


def meta_config():
    return {
        "config_meta.json": {
            "hypothesis": HYPOTHESIS_ID,
            "objective": (
                "Meta-validation of the Gap Fading search: DSR, "
                "White's Reality Check, benchmark comparisons and the "
                "paired C001-vs-C002 best-cell comparison over the "
                "assembled fade trial matrix (dataset registered by the "
                "assembly script). Seeds 0-2."
            ),
            "author": AUTHOR,
            "experiment": {
                "module": "gap_fading_meta",
                "function": "run",
                "parameters": {},
                "dataset": "es-gap-fade-trial-matrix-v1",
            },
            "seeds": [0, 1, 2],
        }
    }


def smoke_config():
    return {
        "config_smoke.json": {
            "hypothesis": HYPOTHESIS_ID,
            "objective": (
                "Smoke test: verify gap_fading executes end-to-end against "
                "the registered ES dataset and emits metrics/tests/artifacts."
            ),
            "author": AUTHOR,
            "experiment": {
                "module": "gap_fading",
                "function": "run",
                "parameters": {
                    "threshold_pct": 0.5,
                    "hold_days": 1,
                    "direction": "both",
                    "cost_bps": 0.0,
                },
                "dataset": "es-f-10y-ohlc-v1",
            },
            "seeds": [0],
        }
    }


def main():
    configs = {}
    configs.update(cell_scan_configs())
    configs.update(cell_scan_configs(module="gap_fading_delayed", delayed=True))
    configs.update(cost_configs())
    configs.update(meta_config())
    configs.update(smoke_config())

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
