# Research Platform — User Guide

Everything below uses the `research` console script, which prints JSON to
stdout. Run the commands from the `research_platform/` directory (or
install the package with `pip install -e .` for global access).

## 1. Initialize a store

```
research init                       # uses $RESEARCH_HOME or ~/.research
research init --root /path/to/research-home
```

This creates the SQLite registry and the directory layout. It is safe to
run repeatedly.

## 2. Register a dataset

Datasets are immutable: the file is copied into content-addressed storage
and re-hashed at registration; once registered, the bytes can never be
changed.

```
research dataset register data/es_daily.csv \
    --source ibkr --provider interactive-brokers --version 2024.01 \
    --symbol ES --timeframe 1d --timezone America/New_York \
    --name es-daily --pipeline "ohlcv-cleaned" --feature-version v1
```

Required provenance: `--source --provider --version --symbol --timeframe
--timezone`. Optional: `--name --pipeline --feature-version --meta
(path to a JSON file)`.

Inspect:

```
research dataset list
research dataset show es-daily
research dataset verify es-daily     # re-hash proof of immutability
```

## 3. Run experiments from a config

A config file declares the hypothesis, objective, author, assumptions,
tags, the experiment module + parameters, an optional dataset reference,
and the seeds (explicit `seeds` list, or `repeats: R` → seeds 0..R-1 —
never both; `seed` inside `parameters` is rejected).

```
research run examples/configs/momentum_scan.json
```

The runner materializes one atomic experiment per (parameter set, seed):
sweep values outer, seeds inner. Output lists every experiment's uuid and
status; failures are recorded (with reasons), never raised.

`--repeats` / `--seed` CLI flags are **rejected** by design: they would
break the config-hash identity that makes experiments reproducible. Edit
the config file instead.

## 4. Inspect results

```
research status <uuid>              # experiment record
research results <uuid>             # latest run: metrics, tests, artifacts, env
research results <uuid> --run 1     # a specific run
```

## 5. Answer comparison questions

```
# Best parameter combination (median over seeds)
research compare best --metric sharpe --direction max --tag momentum --limit 5

# Is the difference between two groups significant?
research compare significance \
    --group-a <sweep-id-or-uuid> --group-b <sweep-id-or-uuid> \
    --metric sharpe --permutations 10000

# Robustness: pass rate per parameter value
research compare robustness --metric sharpe --parameter window --threshold 0.5

# Failures and why
research compare failures --limit 20

# Which assumptions consistently produce alpha?
research compare alpha-by-assumption --metric sharpe --direction max
```

`--sweep-id` is the config hash printed by `research run`; a group can
also be a single experiment uuid.

## 6. Audit and reproduce

```
research audit <uuid>               # static audit: are inputs still unchanged?
research reproduce <uuid>           # audit + re-execute + verify
research reproduce <uuid> --force   # re-execute even if inputs can't be verified
```

Reproduction appends a new run to the same experiment (append-only; nothing
is overwritten) and records the verdict in the reproductions table:

* `matched` — inputs verified unchanged, metrics identical;
* `differed` — inputs verified unchanged, metrics changed (nondeterminism
  or a bug in the experiment);
* `unverifiable` — at least one input cannot be proven unchanged (dataset
  missing/tampered, module source changed, different git commit); nothing
  is re-executed unless `--force`.

## 7. Example walkthrough

```
cd research_platform

# 1. fresh store for the example
research init --root /tmp/demo-research

# 2. run the momentum scan (4 windows x 3 seeds = 12 experiments)
research run --root /tmp/demo-research examples/configs/momentum_scan.json

# 3. best window by median Sharpe
research compare best --root /tmp/demo-research \
    --metric sharpe --direction max --tag momentum --limit 3

# 4. robustness of window=20 against a Sharpe floor
research compare robustness --root /tmp/demo-research \
    --metric sharpe --parameter window --threshold 0.0

# 5. reproduce the first experiment
research status --root /tmp/demo-research <uuid>
research reproduce --root /tmp/demo-research <uuid>
```

## 8. Writing an experiment module

```python
import numpy as np

def run(ctx):
    rng = ctx.rng                     # np.random.Generator, seeded with ctx.seed
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, ctx.params["n"])))
    return {
        "metrics": {"final": float(prices[-1])},
        "tests": [{"name": "final_positive", "statistic": float(prices[-1]),
                   "p_value": None, "conclusion": "pass"}],
        "artifacts": {"prices": prices},       # → prices.npy
        "logs": ["done"],
    }
```

The module must be importable from the config's directory (the runner
adds it to `sys.path`). Determinism is the author's responsibility: use
`ctx.rng` and `ctx.seed`, and nothing else that changes between runs.

## 9. Python API

```python
from research_platform.store import open_store
from research_platform.runner import run_config

store = open_store("/tmp/demo-research")
summary = run_config(store, "examples/configs/momentum_scan.json")
print(summary["completed"], "of", summary["experiments"], "completed")
store.close()
```
