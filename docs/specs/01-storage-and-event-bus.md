# Subsystem 1: Storage Layer + Event Bus

Follows the 7-step process from `docs/ARCHITECTURE.md`'s governance
section. Steps 1-4 (spec, interfaces, data contracts, test plan) are
written here before implementation. Steps 5-7 (implementation,
verification, documentation) are tracked at the bottom once done.

## 1. Technical specification

**Why this subsystem, first, per the ADD's own build order** (Part I §28
step 1): every other subsystem needs somewhere to persist and a
consistent way to publish/subscribe to events. Nothing downstream can be
built correctly without this existing first.

**Scope of this increment, deliberately bounded:**

- The `EventBus` protocol + its in-memory implementation (ADD §4).
- The **core operational schema only** (ADD §18): `signals`, `trades`,
  `regime_history`, `settings_audit_log`, `account_snapshots`, plus a
  `schema_migrations` table to track applied migrations.
- Append-only enforcement (ADD §41) on `signals`, `trades`,
  `settings_audit_log` from the start, not retrofitted later.
- DuckDB as the engine, per ADR-0001.

**Explicitly out of scope for this increment** (separate subsystems per
the ADD's build order, each gets its own 7-step cycle):

- The research schema (`features`, `experiments`, `registry`, `findings`,
  etc. — ADD §32, §39, §40) — Subsystem 7+.
- Wiring the existing `broker/`, `service/` code to publish onto this
  EventBus instead of its current direct-callback wiring
  (`PaperBroker.subscribe_bars`, `AppState.wire_broker`,
  `ConnectionManager`) — that's a real coupling change to already-tested
  code and deserves its own spec/test-plan/verification cycle, not a
  silent bundle into "build storage." Building it now would violate the
  pre-implementation checklist's own question 2 (does this increase
  coupling) by rushing two subsystems into one changeset.
- Dataset snapshotting (ADD §40) — depends on the research schema existing first.

**Design decision: the bus is synchronous, not asyncio-based**, despite
ADD §4 sketching an `asyncio`-based implementation. Reasoning against the
checklist: the pure-domain code this event bus will eventually carry
events *about* (`strategy.py`, `backtest.py`, `risk.py`, `scoring.py`) is
entirely synchronous by design — no `async def` anywhere in
`trading_brain/`'s domain layer. Making the bus asyncio-only would force
every future publisher in that layer to either become async for no
domain reason, or wrap every `publish()` call in a sync-to-async bridge.
A synchronous bus is strictly simpler (checklist Q7), works from both
sync and async callers (a coroutine can call a sync function; the
reverse requires an event loop), and `service/`'s existing async code
(FastAPI handlers) can already call synchronous functions freely. This
is a deliberate, checklist-motivated deviation from the ADD's sketch, not
an oversight — recorded here since the ADD's own sketch said otherwise.

## 2. Public interfaces

```python
# trading_brain/events.py

class Event(Protocol):
    event_id: str
    occurred_at: datetime

class EventBus(ABC):
    def publish(self, event: Event) -> None: ...
    def subscribe(self, event_type: Type[Event], handler: Callable[[Event], None]) -> None: ...

class InMemoryEventBus(EventBus):
    ...  # the only implementation that exists yet; ADD §4's swap-later seam
```

```python
# trading_brain/storage/db.py

class Storage:
    def __init__(self, path: str | Path): ...
    def connection(self) -> duckdb.DuckDBPyConnection: ...
    def migrate(self) -> None: ...  # applies migrations/*.sql in order, idempotent
```

```python
# trading_brain/storage/repository.py
# One repository per table. Each exposes ONLY the operations that table's
# role (append-only vs. mutable) allows -- see Data Contracts below.

class SignalRepository:
    def insert(self, signal: SignalRecord) -> None: ...
    def get(self, trade_id: str) -> Optional[SignalRecord]: ...
    def recent(self, symbol: Optional[str] = None, limit: int = 100) -> List[SignalRecord]: ...
    # no update(), no delete() -- append-only per ADD §41

class TradeRepository:
    def insert(self, trade: TradeRecord) -> None: ...
    def record_exit(self, exit: TradeExitRecord) -> None: ...  # INSERT of a correction row, see contracts
    def get(self, trade_id: str) -> Optional[TradeRecord]: ...
    # no update(), no delete()

class RegimeHistoryRepository:
    def insert(self, entry: RegimeHistoryRecord) -> None: ...
    def latest(self, symbol: str) -> Optional[RegimeHistoryRecord]: ...

class SettingsAuditRepository:
    def insert(self, entry: SettingsAuditRecord) -> None: ...
    def history(self, field: Optional[str] = None, limit: int = 100) -> List[SettingsAuditRecord]: ...

class AccountSnapshotRepository:
    def insert(self, snapshot: AccountSnapshotRecord) -> None: ...
    def latest(self, account_mode: str) -> Optional[AccountSnapshotRecord]: ...
    def equity_curve(self, account_mode: str, since: Optional[datetime] = None) -> List[AccountSnapshotRecord]: ...
```

## 3. Data contracts

Schema (DuckDB dialect), per ADD §18 with the append-only decision made
explicit per-table:

```sql
-- schema_migrations: tracks which numbered migration files have run.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version      INTEGER PRIMARY KEY,
    applied_at   TIMESTAMP NOT NULL
);

-- APPEND-ONLY. One row per candidate a strategy produced, filled or not.
CREATE TABLE signals (
    trade_id             TEXT PRIMARY KEY,
    symbol                TEXT NOT NULL,
    strategy_name           TEXT NOT NULL,
    generated_at               TIMESTAMP NOT NULL,
    direction                    TEXT NOT NULL,
    entry, stop_loss,
    take_profit, invalidation_price  DOUBLE NOT NULL,
    tier                                TEXT NOT NULL,
    checklist_json                        TEXT NOT NULL,
    ai_win_probability                       DOUBLE,
    ai_rationale                                TEXT,
    ai_model_version                               TEXT,
    regime_at_signal                                 TEXT,
    risk_decision                                       TEXT NOT NULL,
    risk_reason                                            TEXT,
    portfolio_decision                                        TEXT,
    account_mode                                                 TEXT NOT NULL
);

-- APPEND-ONLY (fills are new rows; see record_exit's contract below).
-- One row per fill event -- a trade that re-enters after a prior exit on
-- the same symbol/strategy gets a new trade_id, never a mutated old row.
CREATE TABLE trades (
    trade_id         TEXT PRIMARY KEY REFERENCES signals(trade_id),
    broker_order_id    TEXT,
    filled_at             TIMESTAMP,
    fill_price               DOUBLE,
    quantity                    INTEGER,
    exit_index                     INTEGER,
    exit_price                        DOUBLE,
    exit_at                              TIMESTAMP,
    outcome                                 TEXT,     -- win | loss | invalidated | open
    realized_r                                 DOUBLE
);

-- Append-only in spirit (regime labels are a time series, never corrected
-- in place -- a reclassification is a new row with a later as_of).
CREATE TABLE regime_history (
    id           BIGINT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    regime         TEXT NOT NULL,
    confidence      DOUBLE NOT NULL,
    as_of             TIMESTAMP NOT NULL
);

-- APPEND-ONLY by definition -- an audit log that could be edited isn't one.
CREATE TABLE settings_audit_log (
    id           BIGINT PRIMARY KEY,
    field         TEXT NOT NULL,
    old_value      TEXT,
    new_value       TEXT,
    changed_by        TEXT NOT NULL,
    changed_at          TIMESTAMP NOT NULL
);

-- Append-only time series, one row per snapshot -- never mutated.
CREATE TABLE account_snapshots (
    id          BIGINT PRIMARY KEY,
    account_mode TEXT NOT NULL,
    equity        DOUBLE NOT NULL,
    open_positions INTEGER NOT NULL,
    as_of            TIMESTAMP NOT NULL
);
```

**Append-only enforcement mechanism (ADD §41):** enforced at the
repository layer, not by DuckDB triggers. Rationale against the
checklist: DuckDB's trigger support is limited/version-dependent, while
"the repository class for an append-only table simply has no `update`
or `delete` method, and nothing outside `trading_brain/storage/` is
permitted to hold a raw connection" is a boundary Python already enforces
completely, with zero extra moving parts. `trades.record_exit()` is the
one operation that looks like a mutation (a trade's exit fields get
filled in after it opens) — modeled explicitly as `UPDATE ... WHERE
trade_id = ? AND exit_at IS NULL` restricted to *only* the exit columns,
which is the one legitimate lifecycle transition this table has (open →
closed happens exactly once per trade_id) rather than a general-purpose
mutation path. This is documented here precisely so it doesn't read as
an inconsistency later: `trades` has exactly one narrow, named,
single-use mutation; every other table has none.

## 4. Test plan

- `EventBus`: publish with no subscribers is a no-op; a subscriber only
  receives events of the type it subscribed to; multiple subscribers to
  the same type all receive the event; a handler raising an exception
  does not prevent other handlers from running (isolation).
- `Storage.migrate()`: running it twice is idempotent (no error, no
  duplicate schema); `schema_migrations` records exactly the applied
  versions.
- Each repository: insert-then-get round-trips every field without loss;
  `signals`/`settings_audit_log` repositories expose no update/delete
  method at all (asserted via introspection, not just "we didn't call
  it" — a real test that the capability doesn't exist); `trades.
  record_exit()` only succeeds once per `trade_id` (a second call is a
  no-op or raises, not a silent second write) and only touches the exit
  columns.
- Integration: a `SignalCandidateEvent` published on the bus, with a
  subscriber that writes it via `SignalRepository.insert`, produces
  exactly one row queryable back out — the smallest possible proof the
  "publish → persisted synchronously" rule (ADD §16) actually holds.

## 5-6. Implementation + verification

Built as specified above: `trading_brain/events.py`,
`trading_brain/storage/{db,repository}.py`,
`trading_brain/storage/migrations/0001_core_schema.sql`. 17 new tests
(`tests/test_events.py`, `tests/test_storage.py`), full suite
235 → 252 passing, zero regressions. `pyproject.toml` gained `duckdb>=1.0`
per ADR-0001.

Two real bugs caught during implementation, worth recording rather than
letting the fix disappear into the diff:

1. **`ExceptionGroup` is Python 3.11+ only.** First draft of
   `InMemoryEventBus.publish`'s handler-isolation logic used the builtin
   `ExceptionGroup` to report multiple failed handlers. `pyproject.toml`
   targets `>=3.9`, and this session has direct evidence the project
   actually runs on 3.9 (the Mac's own traceback, from the live-feed
   debugging earlier this conversation, showed
   `Python3.framework/Versions/3.9`). That would have been a `NameError`
   the first time two handlers failed on the same event, on the one
   machine this code actually needs to run on, undetectable by this
   sandbox's Python 3.11 test run. Fixed with a small 3.9-compatible
   `HandlerErrors` exception instead. Recorded here because it's exactly
   the kind of gap the governance checklist's "could this become
   technical debt" question is meant to catch, and it did — before the
   code shipped, not after.
2. **DuckDB's `TIMESTAMP` silently drops timezone info.** Every record
   dataclass here uses timezone-aware `datetime`s (correct practice), but
   the first migration draft used plain `TIMESTAMP` columns, which
   round-tripped every timestamp back as naive, breaking the very
   round-trip test the spec's own test plan called for
   (`SignalRepository` insert-then-get). Verified DuckDB's `TIMESTAMPTZ`
   round-trips exactly (tested directly against duckdb 1.5.5 rather than
   assumed from another database's convention) and migrated the schema
   before writing the rest of the tests. Caught by actually running the
   test the spec demanded, not by inspection — the concrete case for why
   step 6 (verification) is its own step, not implied by step 5.

## 7. Documentation

This spec doc *is* the documentation, kept in sync with what shipped
(this section written after implementation, not before). Module-level
docstrings in `events.py`/`storage/db.py`/`storage/repository.py` carry
the "why," matching this codebase's existing convention (see e.g.
`backtest.py`'s or `strategy.py`'s module docstrings) rather than
duplicating it in a separate doc. `docs/ARCHITECTURE.md` is unchanged —
this subsystem implements what §4/§15/§18/§41 already specified, with
one recorded deviation (the synchronous, not asyncio, bus — see §1
above) and one recorded scope boundary (research schema deferred to a
later subsystem) — neither rose to the level of needing its own ADR,
since neither weakens a boundary the ADD actually drew, but both are
written down here rather than silently decided.
