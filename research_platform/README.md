# Research Platform

An independent framework for reproducible quantitative experiments —
zero platform integration, zero UI, numpy-only.

- **Immutable dataset registry** — content-addressed (SHA-256) storage,
  provenance manifest per dataset, re-hash verification.
- **Experiment registry** — every atomic experiment records UUID,
  hypothesis, objective, author, git commit, dataset snapshot, parameters,
  seed, status, assumptions, tags, and failure reasons.
- **Config-driven deterministic runner** — one atomic experiment per
  (params, seed); sweeps and repeats materialize as sibling experiments
  sharing a config-hash sweep id; seeds are declared in the config
  (`seeds` or `repeats`, never both); `seed` inside parameters is
  rejected.
- **Durable results** — metrics, statistical tests, checksummed artifacts,
  logs, environment and git snapshots per run, with a canonical-JSON
  result checksum.
- **Comparison engine** — `best` (median ranking), `significance`
  (numpy-only permutation test), `robustness` (pass rates), `failures`,
  `alpha_by_assumption`.
- **Reproducibility engine** — `research run <uuid>` re-executes an
  experiment under its own identity, audits unchanged inputs (git commit,
  dataset blob, module source), and reports `matched` / `differed` /
  `unverifiable` with explanations.

## Quick start

```bash
cd research_platform
research init --root /tmp/demo-research
research run --root /tmp/demo-research examples/configs/momentum_scan.json
research compare best --root /tmp/demo-research --metric sharpe --tag momentum
research reproduce --root /tmp/demo-research <uuid>
```

## Docs

- `docs/specification.md` — requirements traceability
- `docs/architecture.md` — layout and public interfaces
- `docs/data-schema.md` — SQLite tables, manifests, checksums
- `docs/user-guide.md` — CLI walkthrough

## Development

```bash
cd research_platform
python3 -m pytest tests -q    # 97 passed; stdlib + numpy + pytest only
```

Dependencies: numpy only (runtime); pytest for tests. The framework is
independent of the AI Trading Brain platform; any future integration goes
through ADRs.
