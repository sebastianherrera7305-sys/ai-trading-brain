# Research Platform — Architecture and Public Interfaces

## Overview

`research_platform` is a zero-platform, numpy-only framework for
reproducible quantitative experiments. It is a sibling of (and
deliberately independent from) the AI Trading Brain platform.

The pipeline:

```
config.json ──▶ ExperimentConfig ──▶ plan() ──▶ atomic (params, seed) items
                                                    │
dataset file ──▶ register_dataset ──▶ immutable blob (SHA-256 addressed)
                                                    │
                            runner._execute (seeded, contract ctx)
                                                    │
                              experiments/<uuid>/run_<n>/   (durable)
                              SQLite registry (queryable)
                                                    │
                            compare.*   ── five research questions
                            reproduce.* ── run UUID ──▶ matched/differed/unverifiable
```

## Layout

```
research_platform/
├── pyproject.toml            # numpy-only; [project.scripts] research
├── conftest.py               # makes the package importable under pytest
├── research_platform/
│   ├── __init__.py           # v0.1.0
│   ├── _util.py              # canonical JSON, hashing, env/git snapshots
│   ├── schema.py             # DatasetRecord, ExperimentRecord, RunRecord,
│   │                         # ReproductionRecord, ValidationError
│   ├── config.py             # ExperimentConfig, PlanItem, load_config
│   ├── store.py              # ResearchStore (SQLite + filesystem), open_store
│   ├── runner.py             # ExperimentContext, load_experiment_function,
│   │                         # run_atomic, run_config
│   ├── compare.py            # best, significance, robustness, failures,
│   │                         # alpha_by_assumption, permutation_two_sample
│   ├── reproduce.py          # audit, audit_preconditions, reproduce
│   └── cli.py                # `research` console script
├── tests/                    # 97 tests, stdlib + numpy + pytest only
├── docs/                     # specification, architecture, data schema, guide
└── examples/
    ├── configs/momentum_scan.json
    └── experiments/momentum_scan.py
```

Store layout (`$RESEARCH_HOME` or `~/.research`):

```
<root>/
├── research.db                    # SQLite registry
├── configs/<sha256>.json          # recorded configs (content-addressed)
├── datasets/
│   ├── objects/<sha256><ext>      # immutable dataset blobs
│   └── <uuid>/manifest.json
└── experiments/<uuid>/
    ├── manifest.json
    └── run_<n>/
        ├── env.json  params.json  metrics.json  tests.json
        ├── log.txt
        └── artifacts/<name>.(npy|bin|txt|json)
```

## Public interfaces (stable)

### config
* `load_config(path) -> ExperimentConfig` — validate a config file.
* `ExperimentConfig.plan() -> List[PlanItem]` — deterministic atomic plan.
* `ExperimentConfig.to_document() -> dict` — canonical re-parseable config.

### store
* `open_store(root=None) -> ResearchStore` — root defaults to
  `$RESEARCH_HOME` / `~/.research`.
* `ResearchStore.register_dataset(file_path, source, provider, version,
  symbol, timeframe, timezone, name=None, pipeline="", feature_version="",
  meta=None) -> DatasetRecord`
* `ResearchStore.get_dataset(ref)`, `list_datasets()`, `verify_dataset(ref)`.
* `ResearchStore.create_experiment(rec)`, `get_experiment(uuid)`,
  `find_experiments(...)`, `set_status(...)`, `set_module_checksum(...)`.
* `ResearchStore.next_run_number(uuid)`, `save_run(rec)`,
  `get_runs(uuid)`, `get_latest_run(uuid)`.
* `ResearchStore.record_config(config) -> config_hash`,
  `ResearchStore.record_reproduction(rec)`, `get_reproductions(uuid)`.

### runner
* `run_atomic(store, config, item, config_hash, cwd=None, quiet=False)
  -> ExperimentRecord`
* `run_config(store, config_path, cwd=None, quiet=False) -> summary`
  (cwd defaults to the config file's directory).
* `ExperimentContext(params, seed, rng, dataset, log(), ...)` — the only
  window the experiment code gets.
* `RunnerError` for infrastructure failures.

### compare
* `best(store, metric, direction="max", tag=None, assumption=None,
  sweep_id=None, author=None, limit=10)`
* `significance(store, group_a_ref, group_b_ref, metric,
  n_permutations=10000, seed=0)`
* `robustness(store, metric, parameter, threshold=None, direction="max",
  sweep_id=None, tag=None)`
* `failures(store, tag=None, author=None, limit=50)`
* `alpha_by_assumption(store, metric, direction="max", tag=None)`
* `permutation_two_sample(a, b, n_permutations=10000, seed=0)`

### reproduce
* `audit(store, uuid, cwd=None) -> report` — static audit, no execution.
* `reproduce(store, uuid, cwd=None, force=False) -> report` — audit,
  re-execute, verify. `force=True` re-executes even when inputs cannot be
  proven unchanged.
* `ReproduceError` for invalid reproduce requests.

### cli
`research` console script; every command prints JSON to stdout.
See `docs/user-guide.md`.

## Experiment module contract

A module named in `experiment.module` must expose a function (default
`run`) with signature `run(ctx) -> dict`. The returned dict may contain:

* `metrics` — JSON-safe dict (recorded verbatim; also the reproducibility
  comparison payload).
* `tests` — list of dicts; every entry needs a `name` key.
* `artifacts` — dict name → value; numpy arrays → `.npy`, `bytes` →
  `.bin`, `str` → `.txt`, JSON-safe → `.json`; every artifact is
  checksummed.
* `logs` — string or list of strings appended to `log.txt`.

`ctx` provides `params`, `seed`, `rng` (`np.random.default_rng(seed)`),
`dataset` (`None` or `{"meta": manifest, "data": content}`), and
`ctx.log(message)`.

Failure contract: any exception raised by the module (or by loading it)
is recorded as a failed run with the traceback in `log.txt`; the
experiment status becomes `failed` with `failure_reason`. Sweeps never
crash.

## Determinism contract

1. Seeds come from the config (`seeds` list, or `repeats: R` → 0..R-1).
   `seed` inside `parameters` is rejected.
2. Plan order: sweep values outer, seeds inner.
3. `default_rng(seed)` + `random.seed(seed)` before every atomic run.
4. `--repeats`/`--seed` CLI overrides are rejected — they would break the
   config-hash identity.
5. Canonical JSON (sorted keys) drives config hashes and result checksums.
6. Reproducibility requires unchanged git commit, dataset blob, and module
   source; otherwise the verdict is `unverifiable` with the explanation.

## Testing

```
cd research_platform
python3 -m pytest tests -q     # 97 passed
```

The subproject has its own `pyproject.toml` (`testpaths = ["tests"]`), so
running pytest from `research_platform/` stays isolated from the root
repository's pytest configuration.
