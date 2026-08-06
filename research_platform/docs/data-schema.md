# Research Platform — Data Schema

## Storage model

Metadata lives in a single SQLite database (`<root>/research.db`); content
(configs, dataset blobs, experiment run artifacts) lives on the filesystem
under the same root. Everything the runner produces is append-only; there
are no delete or update paths for registered content.

## SQLite tables

### datasets

| column | type | notes |
|--------|------|-------|
| id | TEXT PK | uuid |
| name | TEXT UNIQUE | optional display name; lookups by id or name |
| source | TEXT NOT NULL | vendor/source of the data |
| provider | TEXT NOT NULL | |
| version | TEXT NOT NULL | data version |
| symbol | TEXT NOT NULL | |
| timeframe | TEXT NOT NULL | |
| timezone | TEXT NOT NULL | |
| pipeline | TEXT | preprocessing pipeline description |
| feature_version | TEXT | feature engineering version |
| checksum | TEXT NOT NULL | SHA-256 of the blob content |
| file_name | TEXT | original file name (used to derive the extension) |
| total_bytes | INTEGER | |
| created_at | TEXT | ISO-8601 UTC (Z suffix) |
| meta | TEXT | JSON object |

Immutability: the blob lives at `datasets/objects/<checksum><ext>`, so
identical content is stored once and a given checksum path can never be
overwritten by different bytes. `verify_dataset` re-hashes the blob and
compares to `checksum`.

### experiments

| column | type | notes |
|--------|------|-------|
| uuid | TEXT PK | |
| hypothesis | TEXT NOT NULL | |
| objective | TEXT NOT NULL | |
| author | TEXT NOT NULL | |
| created_at | TEXT | |
| dataset_id | TEXT NULL FK→datasets | resolved from the config's dataset ref |
| params | TEXT | canonical JSON of the frozen parameter set |
| seed | INTEGER | |
| status | TEXT | created/queued/running/completed/failed/aborted |
| status_changed_at | TEXT | |
| started_at / finished_at | TEXT NULL | |
| runtime_seconds | REAL NULL | |
| config_hash | TEXT | SHA-256 of the config document |
| sweep_id | TEXT NULL | config hash when the experiment came from a sweep |
| sweep_parameter | TEXT NULL | |
| sweep_value | TEXT NULL | canonical JSON of the value |
| repeat_index | INTEGER | index into the seeds list |
| assumptions | TEXT | JSON list of declared assumptions |
| tags | TEXT | JSON list |
| module | TEXT | experiment module import path |
| function | TEXT | default `run` |
| module_checksum | TEXT | SHA-256 of the module source file |
| git_commit | TEXT NULL | HEAD of the repo containing the run cwd |
| git_repo | TEXT NULL | repo root path |
| git_dirty | INTEGER NULL | 1 if the working tree had uncommitted changes |
| failure_reason | TEXT NULL | set when status = failed |
| meta | TEXT | JSON object |

### runs

Primary key `(experiment_uuid, run_number)`; reproductions append runs
without modifying earlier ones.

| column | type | notes |
|--------|------|-------|
| experiment_uuid | TEXT FK→experiments | |
| run_number | INTEGER | 1-based, monotonic per experiment |
| status | TEXT | running/completed/failed |
| metrics | TEXT | canonical JSON of the metric dict |
| tests | TEXT | JSON list of test records |
| artifacts | TEXT | JSON object name → {kind, path, sha256} |
| log_path | TEXT | path to log.txt |
| env | TEXT | environment snapshot JSON (see below) |
| result_checksum | TEXT | SHA-256 of canonical JSON of metrics |
| started_at / finished_at | TEXT NULL | |
| runtime_seconds | REAL NULL | |
| failure_reason | TEXT NULL | |

### reproductions

| column | type | notes |
|--------|------|-------|
| original_uuid | TEXT FK→experiments | |
| run_number | INTEGER | the run that was re-executed |
| status | TEXT | matched / differed / unverifiable |
| new_run_number | INTEGER | the appended run (0 when not executed) |
| max_metric_abs_diff | REAL NULL | maximum |a-b| across comparable floats |
| metric_names | TEXT | JSON list of compared metric keys |
| explanation | TEXT | human-readable verdict rationale |
| checked_at | TEXT | |

## Filesystem content

### configs/<sha256>.json
The canonical config document (`ExperimentConfig.to_document()`), stored
once per hash. The hash is the sweep identity for all its experiments.

### datasets/<uuid>/manifest.json
The dataset manifest (`DatasetRecord.manifest()`): every field of the
`datasets` row plus `name`/`meta`.

### experiments/<uuid>/manifest.json
The experiment record: uuid, hypothesis, objective, author, created_at,
dataset_id, params, seed, status, config_hash, module, function,
module_checksum, assumptions, tags, sweep fields, repeat_index, and the
git block `{commit, repo, dirty}`.

### experiments/<uuid>/run_<n>/
| file | content |
|------|---------|
| env.json | environment snapshot |
| params.json | frozen parameters |
| metrics.json | metric dict |
| tests.json | test records |
| log.txt | ctx.log lines + traceback on failure |
| artifacts/<name>.(npy\|bin\|txt\|json) | artifact bytes |

## Environment snapshot (env.json)

```json
{
  "python_version": "3.9.6",
  "python_implementation": "CPython",
  "platform": "macOS-...",
  "system": "Darwin",
  "machine": "arm64",
  "hostname": "...",
  "cwd": "/...",
  "timezone": "UTC",
  "numpy_version": "2.0.2",
  "env": {"PYTHONHASHSEED": ""},
  "git": {"repo": "...", "commit": "...", "dirty": false}
}
```

## Checksums

* Dataset blob: SHA-256 of file bytes (content addressing).
* Config hash: SHA-256 of canonical JSON of the config document.
* Module checksum: SHA-256 of the experiment module source file.
* Result checksum: SHA-256 of canonical JSON of `metrics`.
* Artifacts: SHA-256 of stored bytes, recorded per artifact.

Canonical JSON = sorted keys, compact separators, numpy→python scalars,
ndarray→lists, bytes→base64 (`base64:` prefix), complex numbers rejected.
