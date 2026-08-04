# Subsystem 2: Registry

Follows the same 7-step process as Subsystem 1
(docs/specs/01-storage-and-event-bus.md). Builds on ADR-0002 for the
schema shape — read that first, this doc doesn't repeat its reasoning.

## 1. Technical specification

**Why this subsystem, second:** ARCHITECTURE.md §30 calls the Registry
"the security boundary between research and capital" — nothing crosses
from the offline research loop to the online execution loop without
passing through it. It's the seam the whole two-loop architecture (§30)
depends on, and the natural next step once Subsystem 1 gave the platform
somewhere to persist anything at all.

**Scope of this increment:**

- `registry_artifacts` + `registry_status_transitions` (ADR-0002's split).
- A minimal `experiments` table — `registry_artifacts.
  source_experiment_id` needs somewhere to point. Deliberately minimal:
  durable storage of what a promotion decision cites, not the full
  Experiment Tracking capability (querying/comparing across experiments,
  deflated-Sharpe helpers) ARCHITECTURE.md §33 describes — that's a
  separate later increment once there's more than one caller wanting to
  query experiments, not just Registry wanting to cite one.
- A `Registry` façade class: `promote()`, `current_status()`,
  `history()`, `register_experiment()` — the operations §30's "promotion
  gate" concept actually needs, not a general-purpose CRUD layer over the
  two tables.

**Explicitly out of scope:**

- `dataset_snapshot_id` and `validation_standard_version` on
  `experiments` are stored as free-text columns, not foreign keys — the
  tables they'd properly reference (dataset snapshotting, §40; validation
  standards, §40) are separate, later subsystems per the ADD's own build
  order (§44 items 15-16). Documented here so a free-text column doesn't
  read as an oversight.
- No enforcement yet that a promotion to `'live'` actually required a
  specific validation ladder having passed — `promotion_checklist_snapshot`
  is stored as given by the caller. Enforcing its *contents* (requiring
  specific keys/values before allowing a `'live'` transition) depends on
  `validation_standards` existing (§40) to check against, so it's
  necessarily a later increment; recorded as a known gap, not silently
  assumed solved.
- No actual `Strategy`/`AIDecisionEngine` instances are loaded *from* the
  registry yet (ARCHITECTURE.md §36's stated small coupling change for
  `backtest.py`/`engine_runner.py`) — that's wiring an already-tested
  module to a new one, which per Subsystem 1's own spec doc precedent
  (the broker/service rewiring it deferred) deserves its own increment
  with its own test plan, not a silent bundle into "build the Registry."

## 2. Public interfaces

```python
# trading_brain/registry.py

class ArtifactType(str, Enum):
    STRATEGY = "strategy"
    AI_MODEL = "ai_model"

class ArtifactStatus(str, Enum):
    RESEARCH = "research"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"
    RETIRED = "retired"

# The only legal transitions -- promote() rejects anything else outright,
# rather than silently recording a nonsensical jump (e.g. research -> live).
_ALLOWED_TRANSITIONS: Dict[ArtifactStatus, Set[ArtifactStatus]] = {
    ArtifactStatus.RESEARCH: {ArtifactStatus.SHADOW, ArtifactStatus.RETIRED},
    ArtifactStatus.SHADOW:   {ArtifactStatus.PAPER, ArtifactStatus.RETIRED},
    ArtifactStatus.PAPER:    {ArtifactStatus.LIVE, ArtifactStatus.RETIRED},
    ArtifactStatus.LIVE:     {ArtifactStatus.RETIRED},
    ArtifactStatus.RETIRED:  set(),  # terminal
}

class Registry:
    def __init__(self, storage: Storage): ...

    def register_experiment(self, experiment: ExperimentRecord) -> None: ...

    def register_artifact(
        self, artifact_id: str, artifact_type: ArtifactType, version: str,
        source_experiment_id: str,
    ) -> None:
        """Creates the artifact at status=RESEARCH. This is the only way
        an artifact enters the registry -- there is no bare insert of a
        transition without an artifact existing first."""

    def promote(
        self, artifact_id: str, to_status: ArtifactStatus, promoted_by: str,
        promotion_checklist_snapshot: Optional[dict] = None,
    ) -> None:
        """Raises IllegalTransitionError if to_status isn't reachable from
        the artifact's current status per _ALLOWED_TRANSITIONS."""

    def current_status(self, artifact_id: str) -> Optional[ArtifactStatus]: ...

    def history(self, artifact_id: str) -> List[StatusTransitionRecord]: ...

    def status_as_of(self, artifact_id: str, at: datetime) -> Optional[ArtifactStatus]:
        """Point-in-time query -- the entire reason for ADR-0002. Answers
        'what was this artifact's status at time T', not just 'now'."""

    def live_artifacts(self, artifact_type: Optional[ArtifactType] = None) -> List[ArtifactRecord]: ...
```

## 3. Data contracts

```sql
-- Minimal: what a promotion decision needs to be able to cite. Full
-- Experiment Tracking (querying/comparison) is a later increment -- see
-- spec §1's explicit scope boundary.
CREATE TABLE experiments (
    experiment_id              TEXT PRIMARY KEY,
    experiment_type              TEXT NOT NULL,   -- 'backtest' | 'walk_forward' | 'hypothesis_test' | 'model_training'
    code_git_hash                  TEXT NOT NULL,
    config_json                       TEXT NOT NULL,
    metrics_json                        TEXT NOT NULL,
    dataset_snapshot_id                    TEXT,    -- free text until §40's dataset-versioning subsystem exists
    validation_standard_version              TEXT,  -- free text until §40's validation-standards subsystem exists
    random_seed                                 INTEGER,
    started_at                                     TIMESTAMPTZ,
    completed_at                                      TIMESTAMPTZ
);

-- Immutable identity. Never updated after insert.
CREATE TABLE registry_artifacts (
    artifact_id              TEXT PRIMARY KEY,
    artifact_type               TEXT NOT NULL,
    version                        TEXT NOT NULL,
    source_experiment_id              TEXT NOT NULL REFERENCES experiments(experiment_id),
    created_at                           TIMESTAMPTZ NOT NULL
);

-- Append-only transition log (ADR-0002). Current status for an artifact
-- = the row with the latest transitioned_at for that artifact_id.
CREATE TABLE registry_status_transitions (
    id                          BIGINT PRIMARY KEY DEFAULT nextval('registry_transitions_id_seq'),
    artifact_id                    TEXT NOT NULL REFERENCES registry_artifacts(artifact_id),
    status                            TEXT NOT NULL,
    transitioned_at                     TIMESTAMPTZ NOT NULL,
    promoted_by                            TEXT NOT NULL,
    promotion_checklist_snapshot              TEXT   -- JSON, nullable (RESEARCH's initial row has none)
);
```

**Append-only enforcement**, same mechanism as Subsystem 1 (repository-
layer method absence, not DB triggers): `registry_artifacts` and
`registry_status_transitions` repositories expose `insert`/read methods
only. `Registry.promote()` is the one place a new transition row gets
created, and it's gated by `_ALLOWED_TRANSITIONS` — the state-machine
validity check lives in `registry.py` (business logic), not in the
storage layer (which stays a dumb, honest leaf per the dependency graph,
ARCHITECTURE.md §6).

## 4. Test plan

- `register_artifact` creates exactly one `registry_artifacts` row and
  one `registry_status_transitions` row at `RESEARCH` — an artifact is
  never registered without an initial status.
- `promote` along a legal path (`research → shadow → paper → live →
  retired`) succeeds at each step; `current_status` reflects each change.
- `promote` to an illegal target (e.g. `research → live` directly, or any
  transition out of `retired`) raises `IllegalTransitionError` and
  **does not** write a transition row — a rejected promotion must leave
  zero trace of having been attempted as if it succeeded.
- `history` returns every transition in chronological order, including
  the initial `RESEARCH` row.
- `status_as_of`: given an artifact promoted `research → shadow → live`
  at three different times, querying a timestamp between the shadow and
  live transitions returns `SHADOW`, not `LIVE` or `RESEARCH` — this is
  the specific behavior ADR-0002 exists to make possible, so it gets its
  own explicit test, not just "current status works."
- `live_artifacts` returns only artifacts whose *current* status is
  `LIVE`, filtered by `artifact_type` when given.
- `registry_artifacts`/`registry_status_transitions` repositories expose
  no `update`/`delete`, same introspection-based assertion as Subsystem 1.
- `register_artifact` with a `source_experiment_id` that was never
  registered via `register_experiment` fails (the FK constraint) —
  Registry never lets an artifact cite a promotion basis that doesn't
  durably exist.

## 5-6. Implementation + verification

Built as specified: `trading_brain/registry.py`, migration
`0002_registry_schema.sql`, repository additions in
`trading_brain/storage/repository.py`
(`Experiment`/`RegistryArtifact`/`RegistryStatusTransition`
repositories). 11 new tests (`tests/test_registry.py`), all passing on
the first run against the implementation above.

One bug this subsystem's work surfaced in **Subsystem 1's own test
suite**, not in the new code: `test_storage.py::test_migrate_is_idempotent`
hardcoded `assert applied == [(1,)]` — true when only migration `0001`
existed, false the moment `0002_registry_schema.sql` landed and the full
suite ran (`262 passed, 1 failed`). The test was checking a fact about
the moment it was written rather than the actual property it was meant
to verify (idempotency: running `migrate()` twice produces no
duplicates). Fixed to compare applied-versions-before vs.
applied-versions-after and assert no duplicates, which stays true
regardless of how many migrations exist by the time a future subsystem
adds another one. Recorded here rather than as a silent diff, since it's
exactly the kind of test-quality issue "no subsystem skips verification"
is meant to catch before it becomes a recurring false alarm on every
future migration.

Full suite: 252 → 263, zero regressions elsewhere.

## 7. Documentation

This spec doc plus `docs/adr/0002-registry-status-history-is-append-only.md`
are the documentation, same convention as Subsystem 1 — module docstrings
in `registry.py` carry the "why," this doc records what shipped and what
was deliberately deferred (§1's scope boundaries stand as written; none
of them were resolved during implementation, they remain open for a
later subsystem).
