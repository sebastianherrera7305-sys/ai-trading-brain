# ADR-0002: Registry status is an append-only transition log, not a mutable column

**Status:** Accepted
**Date:** 2026-08-04

## Context

The frozen ADD's own `registry` schema sketch (§32) has one `status`
column per artifact row (`'research' | 'shadow' | 'paper' | 'live' |
'retired'`), implying each promotion `UPDATE`s that column in place.
Building Subsystem 2 (Registry) against that literal schema surfaces the
same class of problem ADR-0001 caught for storage: the ADD's own Part III
(§41) established that an audit trail with an update path isn't one, and
(§30) calls the Registry "the security boundary between research and
capital" — but a mutable `status` column can only ever answer "what is
this artifact's status *right now*," not "what was it at 3pm on the day
this specific trade fired." Part III §41 already asks for
`signals.registry_artifact_id` so a trade's provenance can be traced back
to the exact artifact version that produced it; that's not actually
answerable from a single mutable-status row, because "which version was
`live` at that timestamp" requires point-in-time history, not current
state.

## The eight questions

1. **Module boundaries** — unaffected; entirely inside Registry's own schema.
2. **Coupling** — no change; downstream readers (Decision Replay, Edge Monitoring) will want "status as of time T" regardless of how it's stored, so this doesn't create new coupling, it makes an already-needed query possible.
3. **Maintainability** — improves it. "Current status" as a derived query (latest transition per artifact) is one small view/query, versus a mutable column that would otherwise need a *separate* shadow history table added later anyway once someone asks "when did this go live" — which is a near-certainty for a system whose stated purpose is knowledge accumulation (Part III).
4. **Reproducibility** — improves it directly, per the point above.
5. **Auditability** — the whole reason for this ADR. A mutable status column is exactly the pattern §41 already rejected for `signals`/`trades`/`settings_audit_log`; applying a different rule to `registry` without a reason would be an inconsistency, not a design choice.
6. **Determinism** — neutral.
7. **Unnecessary complexity** — two tables instead of one adds a small amount of schema surface, but "current status" stays a one-line query (`ORDER BY transitioned_at DESC LIMIT 1`); this is not remotely the complexity of a workflow engine (already rejected, §43) — it's the same append-only pattern already used three times over in this schema.
8. **Technical debt in two years** — a mutable `status` column is the debt. The day someone needs "was this strategy actually live during the March drawdown" and the answer is unrecoverable, this gets rebuilt anyway, with a live system depending on the schema instead of nothing depending on it yet, which is the worst possible time to make this change.

## Decision

Split the ADD §32 `registry` table into:

- **`registry_artifacts`** — one immutable row per artifact: `artifact_id`, `artifact_type`, `version`, `source_experiment_id`, `created_at`. Never updated after insert.
- **`registry_status_transitions`** — append-only log: `artifact_id`, `status`, `transitioned_at`, `promoted_by`, `promotion_checklist_snapshot` (the Part III §42 addition). Current status for an artifact = its latest transition row.

## Alternatives considered

- **Build it exactly as §32 sketched it (mutable `status`).** Rejected per the eight questions — this is the ADD's own Part III principles applied inconsistently to its own Part II sketch, not a real alternative design.
- **A mutable `status` column plus a separate audit-log table mirroring every change.** Rejected as strictly more complex than the chosen design for no benefit — that's two tables recording the same information once as current state and once as history, with a synchronization obligation between them. The chosen design has one source of truth (the transition log) and derives current state from it.

## Consequences

- `docs/specs/02-registry.md`'s data contracts reflect this split, not §32's literal sketch.
- Any future reader of `docs/ARCHITECTURE.md` §32 should treat this ADR as superseding that one table's shape — the ADD's own text stays as written (not edited post-freeze, per the ADD's stated process) but this ADR is the record of the actual implemented shape.
