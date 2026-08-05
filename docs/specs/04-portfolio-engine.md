# Subsystem 4: Portfolio Engine

Follows the same 7-step process as Subsystems 1-3. Read
`docs/adr/0003-max-concurrent-positions-belongs-to-portfolio-not-risk.md`
first — this subsystem is partly a direct consequence of that ADR.

## 1. Technical specification

**Why this subsystem now:** it was the originally-stated step 2 of the
Part I build order (ARCHITECTURE.md §28), deferred when Registry (Part
II's step 8) got prioritized instead. Starting it surfaced ADR-0003 —
`RiskEngine`'s now-removed `MaxConcurrentPositionsValidator` needed a
portfolio-wide position count it had no legitimate way to compute
correctly (no correlation grouping, no per-symbol distinction). That gap
is this subsystem's actual job per §12: "Cross-instrument exposure,
correlation, capital allocation... arbitrates when several approved
trades compete for capital/exposure budget."

**A real, currently-live gap this closes, stated plainly (§12's own
words):** nothing in the system today stops four correlated positions
(e.g. GC=F, ES=F, CL=F, EURUSD=X all long into the same macro move) from
opening simultaneously, because each `LiveEngine` only knows about its
own symbol. This subsystem is the first code that has any cross-
instrument view at all.

**Scope of this increment:**

- `PortfolioState` — a snapshot of open + pending positions across every
  symbol. Deliberately a plain data snapshot, not something this module
  computes itself from a broker connection — `broker.get_positions()`
  already exists (`Broker` ABC); assembling a `PortfolioState` from it is
  the caller's job (engine_runner/service glue, deferred like every prior
  subsystem's wiring), keeping `portfolio.py` independent of `broker`
  exactly as ARCHITECTURE.md §6's dependency graph draws it (no edge
  between `BROKER2` and `PORTFOLIO`).
- `PortfolioPolicy` — `max_simultaneous_positions` (platform-wide, per
  §12's own words), a static `correlation_groups: Dict[symbol, group]`
  mapping, and `correlation_group_caps: Dict[group, max]`. §12's own
  text calls the crude correlation-group cap "a stated, honest v0" in
  place of real covariance estimation — this increment builds exactly
  that v0, not more.
- `PortfolioEngine.evaluate()` — three checks, in order: (1) does this
  symbol already have an open or pending position (a second position on
  the same symbol needs its own explicit policy decision this increment
  doesn't try to make — see below); (2) is the platform-wide cap already
  reached; (3) is the symbol's correlation group already at its cap.

**Explicitly out of scope:**

- Real covariance/correlation estimation from price history — §12 itself
  calls the static correlation-group cap "a stated, honest v0" in place
  of this; Part III §33/§42 separately defers full factor-model Risk
  Attribution for the same underlying reason (not enough instruments or
  history yet). Both point the same direction: stay at the group-cap v0
  here, don't build real covariance estimation on top of four instruments
  and ten years of daily bars.
- Capital allocation across strategies (Part III §42: explicitly v5,
  deferred until 3+ simultaneously-live strategies compete for one pool
  — this platform doesn't have a second strategy yet).
- Wiring `engine_runner.py`/`service/` to actually call
  `PortfolioEngine.evaluate()` and assemble real `PortfolioState` from
  `broker.get_positions()` — same deferral pattern as every prior
  subsystem's broker/service coupling change.
- A policy on whether a *second* position on the same symbol (e.g.
  adding to a winning trade) is ever allowed. Today's `LiveEngine` is
  strictly one-position-per-symbol by construction (its own state
  machine has no "add to position" state), so `PortfolioEngine` matching
  that constraint (reject a same-symbol overlap) is the honest default,
  not a new restriction — but the underlying policy question (should the
  platform ever pyramid a winner) is real and deliberately not decided
  here.

## 2. Public interfaces

```python
# trading_brain/portfolio.py

@dataclass(frozen=True)
class OpenPosition:
    symbol: str

@dataclass(frozen=True)
class PendingOrder:
    symbol: str

@dataclass(frozen=True)
class PortfolioState:
    open_positions: List[OpenPosition]
    pending_orders: List[PendingOrder]

    def all_symbols(self) -> Set[str]:
        """Every symbol with live exposure, open or pending -- both count
        toward every cap below, since a resting order is a real
        commitment of intended risk even before it fills."""

@dataclass(frozen=True)
class PortfolioPolicy:
    max_simultaneous_positions: int
    correlation_groups: Dict[str, str]     # symbol -> group name
    correlation_group_caps: Dict[str, int]  # group name -> max concurrent in that group

class PortfolioDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"

@dataclass(frozen=True)
class PortfolioCheckResult:
    decision: PortfolioDecision
    reason: str

class PortfolioEngine:
    def evaluate(self, symbol: str, state: PortfolioState, policy: PortfolioPolicy) -> PortfolioCheckResult:
        """Never raises for an ordinary rejection -- same precedent as
        Registry/RiskEngine: exceptions mean misuse, not 'the answer is
        no'."""
```

## 3. Data contracts

No new storage schema. `PortfolioState` is assembled by a caller from
`broker.get_positions()` (a later wiring increment) — this subsystem
doesn't read or write storage itself, matching `strategy.py`'s and
`risk_engine`'s precedent of staying storage-agnostic.

**A symbol not present in `policy.correlation_groups` is its own,
singleton group** (its group name defaults to the symbol itself) rather
than being rejected or silently exempted from group caps — an instrument
nobody has explicitly grouped yet should be the *most* conservative case
(assume no correlation benefit, cap it against itself), not the least.
**A group with no configured cap in `correlation_group_caps` defaults to
1** (one position at a time), for the same conservative reasoning —
absence of configuration must never read as absence of a limit.

## 4. Test plan

- A symbol with an existing open position is rejected even when every
  other cap has room — same-symbol overlap is checked first and
  independently of the numeric caps.
- A symbol with an existing *pending* (unfilled) order is rejected the
  same way as an open position — a resting order counts as exposure.
- `max_simultaneous_positions`: approved while under the cap (counting
  open + pending together across all symbols), rejected at the cap.
- Correlation group cap: two symbols mapped to the same group — first
  approved, second rejected once the group's own cap is reached, even
  while `max_simultaneous_positions` still has room (the group cap must
  bind independently, not only as a special case of the platform cap).
- A symbol not present in `correlation_groups` is treated as its own
  singleton group (capped against itself, not exempt).
- Order of checks: same-symbol overlap is asserted to run before the
  numeric caps (a test with an already-open position on the target
  symbol, but caps that would otherwise clearly approve, must still
  reject with the same-symbol reason, not a cap reason).
- `evaluate()` never raises for an ordinary rejection (same pattern as
  `RiskEngine`/`Registry`).

## 5-6. Implementation + verification

Built as specified: `trading_brain/portfolio.py`. 10 new tests
(`tests/test_portfolio.py`), all passing on the first run — no design
flaw surfaced this time (unlike Subsystems 1-3, each of which caught a
real bug during implementation or verification). One decision made
during implementation that wasn't pinned down in steps 1-4: an
unconfigured correlation group defaults to a cap of 1, not 0 or
unlimited — added to §3's data contracts after the fact rather than left
implicit, same discipline as documenting every other judgment call in
this project.

This subsystem is also where removing `MaxConcurrentPositionsValidator`
from Risk Engine (ADR-0003) actually landed in code — see
`docs/specs/03-risk-engine.md`'s Amendment section for that half of the
change.

Full suite: 279 → 288 (10 new, 1 removed from Subsystem 3's amendment),
zero regressions.

## 7. Documentation

This spec doc is the documentation, plus ADR-0003 for why this
subsystem's `max_simultaneous_positions` responsibility isn't shared
with Risk Engine. `docs/ARCHITECTURE.md` §12 stands as written and
matches what shipped — no correction needed here, unlike §11.
