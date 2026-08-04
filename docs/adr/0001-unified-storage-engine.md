# ADR-0001: Unified storage engine — DuckDB from the start, not SQLite-then-migrate

**Status:** Accepted
**Date:** 2026-08-04

## Context

The frozen ADD contains an internal inconsistency, and building Subsystem
1 (Storage Layer + Event Bus) is the first place it becomes a real
decision instead of a documentation detail. Part I §15 recommends SQLite
for the operational schema (§18: `signals`, `trades`, `regime_history`,
`settings_audit_log`, `account_snapshots`). Part II §31 recommends
consolidating *everything* — that same operational schema plus the
research schema (§32: `features`, `experiments`, `registry`, etc.) — into
one DuckDB file, explicitly reasoning that two database engines with a
sync problem between them is worse than one. Part III's additions
(§40's dataset snapshotting, §41's append-only enforcement) are written
assuming the DuckDB consolidation already happened.

Building the storage layer on SQLite now, and migrating to DuckDB when
Subsystem-7-ish (research schema) lands, would mean writing the
repository layer, its tests, and its migration tooling twice against two
different SQL dialects — for a decision the ADD itself already resolved
in Part II, just not by editing Part I's now-frozen text. This is exactly
the kind of thing the pre-implementation checklist exists to catch before
code gets written, not after.

## The eight questions

1. **Module boundaries** — unaffected either way; this is entirely inside the Storage module's own implementation choice.
2. **Coupling** — DuckDB-from-the-start *reduces* coupling versus the alternative: no repository code anywhere ever depends on SQLite-specific syntax that has to be un-coupled later.
3. **Maintainability** — improves it. One engine, one migration history, one thing to back up and reason about, from day one.
4. **Reproducibility** — improves it. DuckDB's Parquet/columnar affinity is exactly what §40's dataset snapshotting needs; building that against SQLite first would mean redesigning the snapshot mechanism during the later migration anyway.
5. **Auditability** — neutral; §41's append-only enforcement (trigger-based or repository-level) is expressible in either engine.
6. **Determinism** — neutral.
7. **Unnecessary complexity** — DuckDB is a single embedded file, same operational simplicity as SQLite (§31 already made this case against a real "data lake"). Choosing it now adds no complexity SQLite wouldn't also have.
8. **Technical debt in two years** — SQLite-then-migrate is the debt. A migration that's known to be coming, with a firm date in the same document that mandated it, and no reason to delay it, is the textbook case an ADR should catch and prevent rather than schedule.

## Decision

Build the Storage Layer on **DuckDB** from Subsystem 1 onward. No SQLite
code gets written. Part I §15's SQLite recommendation is superseded by
Part II §31's DuckDB recommendation — this ADR is the record of that
supersession being acted on, not a new architectural idea.

## Alternatives considered

- **SQLite now, migrate later, as the ADD's Part I literally says.**
  Rejected per the eight questions above — known, scheduled technical
  debt with no offsetting benefit today (DuckDB is not harder to stand up
  than SQLite at this scale).
- **Postgres from the start.** Rejected — Part I §15 and Part II §31 both
  already reasoned through this: no multi-process or multi-user need
  exists yet, and Postgres requires running a server process this
  single-file-embedded system doesn't need.

## Consequences

- `trading_brain/storage/` targets DuckDB's SQL dialect and Python client from its first line of code.
- `pyproject.toml` gains `duckdb` as a dependency now, not deferred.
- Part I §15's text is stale relative to this decision; flagged here rather than silently edited, per the "ADD isn't edited directly after v1.0" rule this ADR is itself the first instance of.
