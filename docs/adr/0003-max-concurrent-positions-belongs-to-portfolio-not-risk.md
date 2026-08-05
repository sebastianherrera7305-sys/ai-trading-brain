# ADR-0003: MaxConcurrentPositionsValidator moves from Risk Engine to Portfolio Engine

**Status:** Accepted
**Date:** 2026-08-05

## Context

Starting Subsystem 4 (Portfolio Engine) surfaced a duplication that was
already in the frozen ADD's own Part I text, not introduced by Parts II
or III: §11 lists `MaxConcurrentPositionsValidator` as item 7 of the Risk
Engine's pipeline ("net-new"). §12 independently states Portfolio Engine
"Enforces `max_simultaneous_positions` platform-wide, not per-symbol."
Same concept — a platform-wide cap on how many positions can be open at
once — named and assigned to two different modules in two different
sections of the same original document.

§2's own module boundary table already draws the line that resolves
this: Risk Engine "Never picks which trade to take among several — only
accepts, rejects, or resizes what it's given," while Portfolio Engine
"arbitrates when several approved trades compete for capital/exposure
budget." A platform-wide position count is inherently a cross-instrument,
whole-portfolio fact — Risk Engine's own `AccountState` (Subsystem 3)
only carries `open_positions_count` as an opaque number with no
per-symbol or correlation awareness, which is a portfolio-level view
smuggled into a per-trade validator, not a per-trade risk rule.

Built as `RiskEngine.MaxConcurrentPositionsValidator` in Subsystem 3
(already shipped, `origin/main` at `fd00b5a`) before this was caught.
Recorded as a real ADR, not a quiet fix, because it changes already-
merged, tested code.

## The eight questions

1. **Module boundaries** — this IS the fix to a boundary violation; removing it restores the §2 table's own line.
2. **Coupling** — reduces it. Risk Engine currently has to be told a portfolio-level fact (`open_positions_count`) it has no way to compute or reason about correctly (no correlation grouping, no distinction between "3 positions in the same asset class" and "3 positions spread across uncorrelated instruments") — that dependency on portfolio-level truth belongs where the portfolio-level logic actually lives.
3. **Maintainability** — improves it. One place decides "how many positions can be open," not two, with no mechanism to keep them in agreement if the policy ever changes (e.g., raising the cap would require remembering to update it in two places).
4. **Reproducibility** — neutral.
5. **Auditability** — improves it slightly: a rejection for "too many open positions" will have one clear owner in the decision log instead of a duplicate check that could theoretically disagree with itself.
6. **Determinism** — neutral.
7. **Unnecessary complexity** — removes complexity (one fewer redundant validator) rather than adding it.
8. **Technical debt in two years** — the debt is the duplication itself: two independently-maintained caps for the same concept, with no test today asserting they must agree in size, tier-scoping, or resize logic. Left alone, either both are always kept in lockstep by hand forever, or they silently drift and produce a support-desk-style bug ("why did it accept this trade, Risk Engine said we were under the cap, but we clearly weren't").

## Decision

Remove `MaxConcurrentPositionsValidator` from `risk_engine` entirely.
`RiskPolicy`/`AccountState` lose `max_concurrent_positions`/(the
concurrent-position-relevant meaning of) `open_positions_count` is no
longer Risk Engine's concern. Portfolio Engine (Subsystem 4) is the sole
owner of `max_simultaneous_positions`, matching §12 and the §2 module
table's own stated boundary.

## Alternatives considered

- **Keep both, treat Risk Engine's version as a fast/cheap pre-check and
  Portfolio Engine's as the authoritative, correlation-aware one.**
  Rejected: the ADD's own module boundary table doesn't describe a
  fast-path/slow-path relationship anywhere else in the pipeline (every
  other validator has exactly one owner), and inventing one here just to
  keep both would be rationalizing the duplication after the fact rather
  than fixing it.
- **Leave Risk Engine's copy alone since it already shipped, and just
  make sure Portfolio Engine's check runs too.** Rejected per the eight
  questions — this is exactly the "two independently-maintained caps"
  debt scenario question 8 warns about, kept alive specifically to avoid
  touching already-merged code, which is the wrong reason to keep a
  known-wrong design.

## Consequences

- `trading_brain/risk_engine/validators.py`, `pipeline.py`'s
  `RiskPolicy`/`AccountState`, `__init__.py`'s `DEFAULT_VALIDATORS`, and
  `tests/test_risk_engine.py` all drop the concurrent-positions
  validator and its fields.
- `docs/specs/03-risk-engine.md` gets a short amendment note pointing
  here, not a silent rewrite of what was actually decided/shipped at the
  time (same policy as the ADD itself post-freeze).
- Portfolio Engine (Subsystem 4) is now unambiguously where
  `max_simultaneous_positions` lives, including any future correlation-
  group refinement.
