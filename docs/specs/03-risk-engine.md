# Subsystem 3: Risk Engine

Follows the same 7-step process as Subsystems 1-2.

## 1. Technical specification

**Why this subsystem, third, per the approved build order** (ARCHITECTURE.md
§28 step 3): formalizes the ad hoc risk checks already scattered inline in
`engine_runner.py._look_for_candidate` (`settings.trading_allowed()`,
`is_instrument_enabled()`, `meets_min_tier()`, `position_size()`) into the
composable validator pipeline §11 specifies — "risk management must always
override every strategy," enforced by short-circuiting on the first
rejection rather than by convention.

**What already exists and gets reused, not rebuilt:** `risk.py`'s
`position_size()` (fixed-fractional sizing) is the arithmetic core of
`PositionSizeValidator` below. `risk.py`'s `validate_trade_risk()`/
`TradePlan` is a *different* concern — trade-geometry validation (is the
stop beyond real structure, is RR positive) already folded into
`strategy.py`'s checklist scoring at candidate-generation time. This
subsystem is account-level gating that runs *after* a candidate already
cleared that bar, not a duplicate of it.

**A dependency-graph decision made before writing any code:**
ARCHITECTURE.md §6's diagram draws `RISK2` (risk engine) with no edge
to/from `BROKER2` — they're independent, both feeding `ENGINE`
(engine_runner). `BotSettings` (`broker/settings.py`) currently holds the
risk-relevant configuration (`risk_percent`, `max_contracts`, `min_tier`,
`daily_drawdown_limit_percent`), but it lives in the `broker` package.
Having `risk_engine` import `BotSettings` directly would invert that
independence — `risk_engine` would depend on `broker`, which the ADD's own
graph says shouldn't happen. Resolution: `risk_engine` defines its own
`RiskPolicy` dataclass, self-contained, with the fields it actually needs
(including two the ADD calls for that `BotSettings` doesn't have yet:
weekly loss limit, max concurrent positions). Reconciling `BotSettings`
and `RiskPolicy` — where the risk-relevant fields ultimately live, and how
one maps to the other — is wiring work for a later increment (same
deferral pattern as Subsystem 1's broker/service rewiring), not resolved
here. This isn't a deviation needing an ADR — it's the graph already in
the frozen ADD, just followed literally instead of by accident.

**A correction, not a new decision:** §11 lists nine pipeline items,
numbered 1-9, with item 9 (`TrailingStopValidator`) parenthetically noted
as "net-new, intra-trade rather than pre-trade." That's a self-contradiction
in the frozen text — everything else in that pipeline evaluates a
*candidate* before entry; a trailing stop manages an *open position*.
Listing it as pipeline step 9 implies a shape it doesn't have. Correction:
`TrailingStopValidator` does not belong in this Risk Engine's pre-trade
pipeline at all — it's position-management, which is
`ExecutionEngine`/`LiveEngine`'s domain (§13), already has a bracket/
invalidation mechanism there, and gets extended when that subsystem's
turn comes. Not building a wrong-shaped validator for the sake of hitting
a list item.

**Scope of this increment:**

- `RiskPolicy`, `AccountState`, `RiskCheckResult` — the pipeline's data contracts.
- Validators: `KillSwitchValidator`, `InstrumentEnabledValidator`,
  `TierFloorValidator`, `PositionSizeValidator`, `DailyLossLimitValidator`,
  `WeeklyLossLimitValidator` (net-new), `MaxConcurrentPositionsValidator`
  (net-new), `AccountRulesValidator` with one implementation
  (`NoOpAccountRules`, for a personal, non-funded account).
- `RiskEngine.evaluate()` — runs every validator in order, **short-circuits
  on the first `REJECT`**, but returns the full list of results run so
  far (§11: "every validator's decision, including approvals, is logged").

**Explicitly out of scope:**

- `TopstepAccountRules` — porting the EOD-trailing-drawdown/consistency-
  rule logic already built and tested in `trading-bot/bot/propfirm/
  calculator.py`'s `_floor_for()`. That's a cross-repo port of real,
  already-validated logic; it deserves its own careful parity check
  against the source, not a rushed inline reimplementation bundled into
  this increment. `AccountRulesValidator` is defined as pluggable
  specifically so this slots in later without touching the pipeline.
- Wiring `engine_runner.py` to actually call `RiskEngine.evaluate()`
  instead of its current inline checks — a coupling change to
  already-tested code, same deferral rationale as every prior subsystem.
- Persisting `RiskCheckResult` to the `signals` table (Subsystem 1's
  schema already has `risk_decision`/`risk_reason` columns for this) —
  deferred because a full `signals` row also needs `ai_win_probability`
  etc. from the not-yet-built AI Decision Engine; `RiskEngine` stays
  storage-agnostic (returns plain results, doesn't persist them itself),
  matching `strategy.py`'s own precedent of not touching storage.

## 2. Public interfaces

```python
# trading_brain/risk_engine/pipeline.py

class RiskCheckStatus(str, Enum):
    APPROVE = "approve"
    RESIZE = "resize"
    REJECT = "reject"

@dataclass(frozen=True)
class RiskCheckResult:
    validator_name: str
    status: RiskCheckStatus
    reason: str
    resized_quantity: Optional[int] = None

@dataclass(frozen=True)
class RiskPolicy:
    risk_percent: float
    max_contracts: int
    min_tier: Tier
    daily_loss_limit_percent: float
    weekly_loss_limit_percent: float
    max_concurrent_positions: int

@dataclass(frozen=True)
class AccountState:
    equity: float
    open_positions_count: int
    daily_loss_limit_breached: bool
    weekly_loss_limit_breached: bool
    kill_switch_active: bool
    instrument_enabled: bool

class RiskValidator(ABC):
    name: str
    def check(
        self, candidate: TradeCandidate, policy: RiskPolicy, account: AccountState,
        unit_value_per_point: float = 1.0,
    ) -> RiskCheckResult: ...

class RiskEngine:
    def __init__(self, validators: Optional[List[RiskValidator]] = None): ...
    def evaluate(
        self, candidate: TradeCandidate, policy: RiskPolicy, account: AccountState,
        unit_value_per_point: float = 1.0,
    ) -> List[RiskCheckResult]:
        """Runs validators in order, stops at the first REJECT."""

# Reading the outcome: NOT results[-1] -- a REJECT is always last (the
# pipeline stops there), but a RESIZE is not terminal (later validators,
# e.g. account rules, still run against it), so a later APPROVE must not
# bury an earlier RESIZE. Caught during implementation by the pipeline's
# own test suite, not by inspection -- see step 5-6 below. The real
# contract is two small pure functions over the whole result list:

def overall_status(results: List[RiskCheckResult]) -> RiskCheckStatus:
    """REJECT if any result rejected; else RESIZE if any result resized;
    else APPROVE."""

def effective_quantity(results: List[RiskCheckResult]) -> Optional[int]:
    """The last RESIZE's (or resize-carrying APPROVE's) resized_quantity,
    or None if nothing set one."""
```

```python
# trading_brain/risk_engine/account_rules.py

class AccountRulesValidator(RiskValidator):
    """Pluggable per-account-type rules (ARCHITECTURE.md §7, §11) --
    personal account is a no-op today; a funded (Topstep) account's
    EOD-trailing/consistency rules plug in here later without changing
    the pipeline shape."""

class NoOpAccountRules(AccountRulesValidator):
    ...  # always APPROVE -- the only implementation this increment ships
```

## 3. Data contracts

No new storage schema this increment — `RiskCheckResult` is an in-memory
return value, not a table (see §1's scope boundary on persistence).
`RiskPolicy`/`AccountState` are plain dataclasses, not stored directly;
whatever assembles them (a later wiring increment) is responsible for
reading `BotSettings`/broker state and mapping into these shapes.

**The one invariant worth stating as a contract, since it's the whole
point of "risk always overrides strategy":** `RiskEngine.evaluate()`
never raises for a rejected candidate — rejection is a normal, expected
`RiskCheckResult`, not an exception. Exceptions are reserved for
programmer errors (a validator raising on malformed input), not for "the
answer is no," matching `Registry.promote()`'s precedent of raising only
for `IllegalTransitionError`/`UnknownArtifactError` (genuine misuse), not
for ordinary decision outcomes.

## 4. Test plan

- Each validator in isolation: `KillSwitchValidator` rejects iff
  `account.kill_switch_active`; `InstrumentEnabledValidator` rejects iff
  `not account.instrument_enabled`; `TierFloorValidator` rejects a
  candidate below `policy.min_tier` and approves at/above it (covering
  the tier-rank ordering, not just equality); `PositionSizeValidator`
  computes a quantity via `risk.position_size()`, resizes down to
  `policy.max_contracts` when the computed size exceeds it, and rejects
  (not resizes to zero) when the computed size rounds below 1;
  `DailyLossLimitValidator`/`WeeklyLossLimitValidator` each reject iff
  their respective `account.*_breached` flag is set;
  `MaxConcurrentPositionsValidator` rejects iff
  `account.open_positions_count >= policy.max_concurrent_positions`;
  `NoOpAccountRules` always approves.
- `RiskEngine.evaluate()`: with all-approving validators, returns one
  result per validator, all `APPROVE`/`RESIZE`; with one validator
  rejecting midway, returns results only up to and including that
  rejection — later validators must not run at all (asserted via a
  validator that raises if called, not just "the result list is short").
- Order independence is NOT assumed — the pipeline's stated order
  (cheapest/most-restrictive first, §11) is asserted directly: a test
  constructs `RiskEngine()` with its default validator list and checks
  `KillSwitchValidator` is first.
- Integration-shaped test: a candidate that would pass every check except
  `PositionSizeValidator`'s resize (computed size exceeds `max_contracts`)
  ends the pipeline in `RESIZE`, not silently coerced to `APPROVE` with
  the original size.

## 5-6. Implementation + verification

Built as specified: `trading_brain/risk_engine/{pipeline,validators,
account_rules}.py`. 16 new tests (`tests/test_risk_engine.py`).

**One real design bug this subsystem's own test plan caught before it
shipped**, not after: §3's data contract originally said "callers read
`results[-1].status` to know the overall verdict." That's wrong.
`PositionSizeValidator` isn't the last validator in the default order
(account-rules runs after it), so a mid-pipeline `RESIZE` gets followed
by a later `APPROVE` — reading only the last result silently buries the
resize. Writing the integration test this spec's own §4 called for
("ends the pipeline in RESIZE, not silently coerced to APPROVE")
surfaced the bug immediately: the test failed against the first
implementation, not because the test was wrong. Fixed by adding two pure
functions, `overall_status()` (REJECT wins if any result rejected, else
RESIZE if any resized, else APPROVE) and `effective_quantity()` (the
last resize-carrying result), and rewriting the contract in both
`pipeline.py` and this doc to match. This is the concrete case for why
step 4 (test plan) gets written before step 5 (implementation) rather
than after: the flawed contract was written down, in this document,
before any code existed, and the test plan derived from it is what
caught the flaw once real code had to satisfy it.

Also promoted `_TIER_RANK` — duplicated privately in both `strategy.py`
and `walk_forward.py` (the latter's copy dead code, unused) — to a
public `TIER_RANK`/`meets_tier_floor()` in `scoring.py`, since
`TierFloorValidator` needed the same ranking a third time. Fixing the
duplication rather than adding a third private copy.

Full suite: 263 → 279, zero regressions.

## 7. Documentation

This spec doc is the documentation. Module docstrings in `pipeline.py`,
`validators.py`, and `account_rules.py` carry the "why," matching this
codebase's established convention. `docs/ARCHITECTURE.md` §11 stands as
written; this doc records where the implementation corrected it (the
mis-scoped `TrailingStopValidator`, §1 above) and where it caught a flaw
in the ADD's own contract sketch before code depended on it.

## Amendment (2026-08-05, during Subsystem 4)

**`MaxConcurrentPositionsValidator` has been removed from this
subsystem.** Starting Portfolio Engine (Subsystem 4) surfaced that §11
and §12 assign the same concept — a platform-wide cap on open positions
— to two different modules; §2's own module boundary table resolves it
in Portfolio Engine's favor ("Risk Engine... never picks which trade to
take among several"). See `docs/adr/0003-max-concurrent-positions-belongs-to-portfolio-not-risk.md`
for the full reasoning. `RiskPolicy.max_concurrent_positions` and
`AccountState.open_positions_count` no longer exist; everything else
above (§1-§7) is unchanged and still describes what shipped. This
section is appended, not folded into the sections above, for the same
reason the ADD itself isn't silently rewritten after freezing — the
original decision and its correction should both stay visible.
