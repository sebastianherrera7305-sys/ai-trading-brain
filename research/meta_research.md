# Meta-Research

Research on the research itself: periodically analyze all completed
experiments to improve the process. The goal is not more experiments but
better experiments, and efficient elimination of false ideas.

## Cadence

- After every campaign closure: append to §2 (first iteration below).
- Quarterly: full review of the Edge Database + catalog statuses; re-rank the
  backlog in `campaigns.md` with written justification.

## Standing questions

1. Which research domains consistently fail? (→ prune or re-specify)
2. Which features appear repeatedly in successful hypotheses?
3. Which markets are most responsive? (→ prioritize them)
4. Which validation tests reject the highest proportion of strategies?
   (→ trust them most)
5. Which benchmarks are hardest to outperform? (→ always include them)
6. What was the measured false-discovery rate of our pipelines?
7. Did any accepted result come from a single seed or single window?
8. Which hypotheses did we avoid testing, and why? (selection-bias audit)

## Instrumentation

- Trial-level facts come from the registry (`research compare`, store
  queries).
- Verdict-level facts come from the Edge Database.
- Every campaign report must state which standing question it advanced.

---

## 1. Iteration — post-C001 (2026-08-06)

### What we learned about the markets
- On ES daily (2016–2026), gap continuation has no post-selection edge
  (E-0001). The measured mean open→close return after gaps was consistent
  with the signed pool: gap-day selection itself was weakly special (raw
  permutation p≈0.02 pre-adjustment), but the *directional* rule was not.
- Simple trend crossovers and buy & hold dominated every searched gap cell
  (E-0002). On this window the market's drift and trend response are far
  larger than overnight-gap structure effects.
- Per-year gap performance was unstable (negative 2023, 2026); regime
  breakdown showed entries cluster in high-vol states (79 of 135 trades in the
  top EWMA-vol tercile in the reference cell) — gap strategies are implicitly
  a vol-timing bet.

### What we learned about the process
- **Single-test gates are insufficient for grids:** the permutation nullity
  gate called 5 of 36 cells (14%) significant — consistent with chance. DSR +
  White's Reality Check overturned the headline result. Rule for the lab: any
  multi-cell search is decided by DSR/RC, never by the best cell's raw p.
- **Signed nullity pools matter:** comparing a directional rule against an
  unsigned pool produces a test of "special days", not of the rule. C001's
  pool bug (fixed in-session) was caught by cross-checking module output
  against an independent re-implementation. Rule: independent recomputation of
  headline statistics is part of acceptance.
- **Dirty-tree discipline works:** the framework refused to verify a
  reproduction recorded from an uncommitted tree; committing the fix produced
  exact matches. Rule: no runs on dirty trees; reproduce at the recorded
  commit.
- **Import-order pitfall:** experiment modules importing `quant_research`
  before the `_common` bootstrap fail outside the framework's cwd. Standardize
  on `from _common import qr, ...` (now the lab convention).
- **Cost ladder cheap insurance:** Sharpe was insensitive to 5 bps (daily
  basis), but mean/trade visibly decayed; report both.

### Backlog implications
- The opposite-sign test (gap fading, C002) is now the single most
  information-dense experiment: it converts "no continuation edge" into
  "no gap edge" or "opposite edge".
- Multi-market trend/reversion campaigns (C003/C004) will measure whether the
  ES drift/trend dominance is a market property or a window property.
- C005 (calendar) will provide the next false-discovery calibration point.
- No new single-market gap variant should be proposed until C002 closes:
  gap-continuation variants would be re-treading E-0001.

## 2. Log of process improvements

| When | Improvement | Originating observation |
|---|---|---|
| C001 | Signed nullity pool for directional rules | permutation gate measured "special days", not the rule |
| C001 | DSR/RC mandatory for any searched grid | 14% nominal significance ≈ chance in 36-cell search |
| C001 | Independent recomputation of headline stats | pool alignment bug survived code review |
| C001 | Commit-before-run discipline | dirty-tree reproduction refused by framework |
| C001 | Report both Sharpe and mean/trade at each cost | Sharpe hid cost decay at 5 bps |
| C001 | `from _common import qr, ...` as module standard | import-order failure outside framework cwd |
| 2026-08-06 | Laboratory architecture FROZEN (`architecture_freeze.md`) | final integration layer complete: knowledge graph, consistency checks, queries, dashboard integration |
| 2026-08-06 | Knowledge graph generator (`research/graph.py`) | deterministic view over canonical registries; 16 automated checks; never hand-edited |
| 2026-08-06 | `reproduce` documented to require `--cwd research_studies/<campaign>` | 3 of 7 reproduction attempts unverifiable due to wrong working directory |
