# Research Platform — Specification

Version 0.1.0. This document is the requirements traceability map for the
independent research framework: every required capability is listed with
the module and function that implements it, and the test that proves it.

## 1. Scope and independence

The framework lives in `research_platform/` as an isolated Python package
with **no platform integration, no UI, no FastAPI**. Its only runtime
dependency is numpy. It exists so quantitative results can be produced,
stored, compared, and reproduced *independently* of the AI Trading Brain
platform; any later integration goes through ADRs, never by coupling
modules.

The `quant_research` codebase is frozen and is **not** modified by this
framework.

## 2. Requirements traceability

| # | Requirement | Implementation | Test |
|---|-------------|----------------|------|
| R1 | Independent, standalone framework (no platform/UI/FastAPI deps) | `pyproject.toml` (deps: numpy only); package docstring | suite runs with stdlib + numpy |
| R2 | Immutable dataset registry | `store.ResearchStore.register_dataset` (content-addressed blobs by SHA-256, manifest per uuid, idempotent per content) | `tests/test_store.py` |
| R3 | Dataset integrity verification (immutability proof) | `store.ResearchStore.verify_dataset` (re-hash stored blob) | `test_verify_dataset_and_immutability` |
| R4 | Experiment registry with mandatory provenance: UUID, hypothesis, objective, author, creation timestamp, git commit, dataset snapshot, parameter set, random seed, status | `schema.ExperimentRecord`; `store.create_experiment` (validation via `ExperimentRecord.validate_meta` + `_validate_params`) | `tests/test_schema.py`, `test_store.py` |
| R5 | Dataset provenance: id, source, provider, version, symbol, timeframe, timezone, preprocessing pipeline, feature version, checksum, creation date | `schema.DatasetRecord` (+ manifest) | `test_dataset_manifest_round_trip`, `test_register_dataset_records_manifest` |
| R6 | One atomic experiment = one (params, seed); sweeps/repeats materialized as sibling experiments sharing `sweep_id` = config hash | `config.ExperimentConfig.plan`; `runner.run_atomic` (sweep_id = config hash) | `test_sweep_and_repeats_materialize_siblings` |
| R7 | Config-driven, deterministic execution from JSON config files | `config.load_config`, `config.plan` (deterministic order: sweep-values outer, seeds inner) | `test_plan_order_sweep_outer_seeds_inner` |
| R8 | `seeds` (explicit list) XOR `repeats: R` (seeds 0..R-1), never both | `ExperimentConfig.__init__` validation | `test_seeds_and_repeats_exclusive` |
| R9 | `seed` forbidden inside `parameters` | `_validate_params` (config + store level) | `test_seed_in_parameters_rejected`, `test_create_rejects_seed_in_params` |
| R10 | Config hash recorded; deterministic canonical-JSON hashing | `store.record_config` / `store.config_hash`; `_util.canonical_json` | `test_config_storage`, `test_canonical_json_deterministic` |
| R11 | Experiment execution never crashes a sweep: failures recorded with reason, never raised | `runner._execute` (try/except records failed run + status) | `test_experiment_failure_is_recorded_not_raised` |
| R12 | Runner seeds `ctx.rng = default_rng(seed)` and `random.seed(seed)` per atomic run | `runner._execute` | `test_experiment_context_log` (rng determinism), reproducibility suite |
| R13 | Experiment module contract: `module` exposes `function` (default `run`) taking `ctx` with `params`, `seed`, `rng`, `dataset`, `log()`; returns dict with optional `metrics`, `tests` (entries need `name`), `artifacts`, `logs` | `runner.ExperimentContext`, `runner.load_experiment_function`, `RunRecord.validate_result` | `test_successful_atomic_run`, `test_schema.py` |
| R14 | Durable per-run storage: metrics, tests, artifacts (ndarray→.npy, bytes→.bin, str→.txt, else .json), logs, params, env snapshot, git commit, runtime, failure reason | `runner._execute` + `store.save_run`; filesystem run directories | `test_successful_atomic_run` |
| R15 | Result checksum (canonical JSON of metrics) | `runner._execute` (`result_checksum`) | `test_successful_atomic_run` |
| R16 | Comparison engine: `best` (median-over-seeds ranking) | `compare.best` | `test_best_ranks_by_median` |
| R17 | Comparison engine: `significance` (numpy-only two-sample permutation test, p = (count+1)/(P+1)) | `compare.significance` / `compare.permutation_two_sample` | `test_permutation_test_*`, `test_significance_verdict` |
| R18 | Comparison engine: `robustness` (pass rate per parameter value) | `compare.robustness` | `test_robustness_groups_by_parameter` |
| R19 | Comparison engine: `failures` (failed experiments with reasons) | `compare.failures` | `test_failures_lists_failed` |
| R20 | Comparison engine: `alpha_by_assumption` (metric distribution per declared assumption set) | `compare.alpha_by_assumption` | `test_alpha_by_assumption_buckets` |
| R21 | Reproducibility engine: `research run UUID` re-executes the same experiment uuid, appending a run; report status matched | `reproduce.reproduce` → `runner._execute` | `test_matched_reproduction` |
| R22 | Reproducibility engine: verdicts `matched` / `differed` / `unverifiable` with explanation; recorded in `reproductions` table | `reproduce.reproduce`, `schema.ReproductionRecord` | `test_differed_reproduction`, `test_unverifiable_when_module_changed` |
| R23 | Reproducibility preconditions: dataset still registered & verified, module checksum unchanged, git commit unchanged | `reproduce.audit_preconditions` | `test_missing_dataset_is_unverifiable`, `test_audit_static_report` |
| R24 | Static audit command (no re-execution) | `reproduce.audit` | `test_audit_static_report` |
| R25 | CLI `research` console script, JSON output, no third-party deps | `cli.py`, `[project.scripts] research` | manual/CLI validation |
| R26 | Env snapshot recorded per run (python, platform, numpy, git, cwd, tz, PYTHONHASHSEED) | `_util.env_snapshot` | `test_env_snapshot_keys` |
| R27 | CLI rejects `--repeats`/`--seed` runtime overrides (would break config-hash determinism) | `cli.cmd_run` | manual |
| R28 | Dataset payload passed to runs as `{"meta": manifest, "data": content}`; .npy/.npz/.csv/raw loading | `runner.resolve_dataset_payload`, `load_dataset_content` | `test_run_atomic_with_dataset`, `test_load_dataset_content` |
| R29 | Experiments without a git workspace handled gracefully (commit recorded as None, audit non-blocking) | `_util.git_state`; `reproduce.audit_preconditions` | `test_git_state_outside_repo`, `test_audit_preconditions_list` |

## 3. Data model summary

* **Dataset**: id (uuid), provenance fields (source, provider, version,
  symbol, timeframe, timezone, pipeline, feature_version), checksum
  (SHA-256 of content), file_name, total_bytes, created_at, meta.
  Blob stored content-addressed at `objects/<sha256><ext>`; manifest at
  `datasets/<uuid>/manifest.json`.
* **Experiment**: uuid, hypothesis, objective, author, created_at,
  dataset_id, params, seed, status, config_hash, module, function,
  module_checksum, assumptions, tags, sweep_id, sweep_parameter,
  sweep_value, repeat_index, git commit/repo/dirty, timestamps, runtime,
  failure_reason, meta.
* **Run**: experiment_uuid + run_number, status, metrics, tests, artifacts
  (with per-artifact sha256), log_path, env snapshot, result_checksum,
  timestamps, runtime, failure_reason.
* **Reproduction**: original_uuid, run_number, status (matched | differed |
  unverifiable), new_run_number, max_metric_abs_diff, metric_names,
  explanation, checked_at.

## 4. Determinism contract

1. A config file fully determines the experiment family; the config hash
   (SHA-256 of canonical JSON) is the sweep's identity.
2. Plan order is fixed: sweep values outer, seeds inner.
3. Every atomic run seeds `numpy` (via `default_rng(seed)`) and `random`
   (`random.seed(seed)`).
4. Seeds are declared in the config (`seeds` list or `repeats`), never in
   `parameters`.
5. Results are stored under canonical-JSON checksums; two equal metric
   payloads always hash identically.
6. The reproducibility engine proves unchanged inputs (git commit, dataset
   blob hash, module source hash) before declaring a reproduction valid;
   anything the experiment does outside the seeded contract (network,
   unseeded libraries) is the author's responsibility and is flagged by
   the recorded environment snapshot.

## 5. Out of scope (this version)

* Any AI Trading Brain platform integration (deferred to ADRs).
* Web UI, FastAPI endpoints, notebooks.
* Distributed execution, parallelism, or a task queue.
* Deleting or mutating registered content (by design: append-only).
