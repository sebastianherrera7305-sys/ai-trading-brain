# Negative Knowledge Database

Rejected research is permanent scientific knowledge. This database preserves
every rejected hypothesis with the conditions under which reinvestigation
would be justified, so the laboratory never wastes effort rediscovering
rejected ideas.

Rules:
- One entry per rejected hypothesis / failed idea, appended at decision time.
- Entries are never deleted; corrections add a new entry referencing the old.
- A hypothesis already here is not re-tested without a documented
  reinvestigation trigger (new data class, new market, materially different
  construction, or a new test methodology).

Schema:
```
NK-<NNNN>:
  hypothesis:
  reason_for_rejection:
  statistical_evidence:
  robustness_failures:
  benchmark_comparison:
  markets_tested:
  parameter_ranges_explored:
  assumptions_violated:
  reinvestigation_justified_when:
  related: (edge DB entries, reports)
```

---

## NK-0001 — Overnight gap continuation on ES daily

- **hypothesis:** After an overnight gap ≥ threshold_pct, the holding-period
  open→close return continues in the gap direction.
- **reason_for_rejection:** No edge survives data-snooping adjustment; the
  best searched cell was indistinguishable from random entries and below every
  benchmark.
- **statistical_evidence:** Best cell nominally significant pre-adjustment
  (permutation p=0.014–0.027), but Welch p ≥ 0.09, bootstrap 95% CI includes
  0, SPRT undecided after 111 trades. **Decisive:** DSR p=0.285, White's
  Reality Check p≈0.37–0.40; best-trial Welch vs random entries p=0.375,
  vs buy & hold p=0.080, vs best SMA p=0.162, vs best EMA p=0.111.
- **robustness_failures:** 14% of 36 cells nominally significant at 5%
  (≈ chance); only 36% of cells positive Sharpe; per-year instability
  (negative 2023, 2026); best cell survives the cost ladder (0.22% → 0.17%
  mean/trade at 5 bps) but never approaches benchmark levels.
- **benchmark_comparison:** best cell Sharpe 0.52 vs buy & hold 0.79,
  EMA(10,100) 0.89, SMA(10,100) 0.86; total return +26–39% vs buy & hold
  +254%.
- **markets_tested:** ES (E-mini S&P 500), daily, 2016-08 → 2026-08.
- **parameter_ranges_explored:** threshold_pct {0.3, 0.5, 0.7, 1.0} ×
  hold_days {1, 2, 3} × direction {up, down, both} × costs {0, 2.5, 5 bps} ×
  seeds {0, 1, 2}.
- **assumptions_violated:** "Gaps continue" — the directional rule's mean was
  negative for most cells; gap-day selection was weakly special in raw terms
  but not directionally exploitable; implicit assumption of tradeable open
  fills untested (daily open vs true auction open).
- **reinvestigation_justified_when:** (a) intraday data enables true auction-
  open fill modeling and/or session-specific gap definitions; (b) volume or
  order-flow data adds a conditioning dimension; (c) a materially different
  market family (e.g., CL/GC/EURUSD) is tested as a primary market — ES-only
  rejection does not transfer; (d) the opposite-sign rule (gap fading,
  H-MS-01) — which is NOT covered by this rejection and is Campaign C002.
- **related:** E-0001, E-0002, E-0003; gap_continuation/report.md.

## NK-0002 — Best-cell p-value as evidence in a searched grid (methodological)

- **hypothesis:** A single cell with p < 0.05 (permutation gate) constitutes
  evidence for a hypothesis when the cell was selected from a grid.
- **reason_for_rejection:** C001: 5 of 36 cells (14%) passed the gate — the
  measured false-discovery rate of the single-test gate in a 36-cell search is
  ≈ chance, and the grid's best cell failed both DSR and White's Reality
  Check.
- **statistical_evidence:** nominal p range 0.014–0.027 across best cells;
  corrected p range 0.285 (DSR) and 0.37–0.40 (RC).
- **robustness_failures:** the "significant" cells were not stable across
  seeds' statistical draws in ranking; per-year decomposition negative in 2 of
  11 years.
- **benchmark_comparison:** n/a (methodological).
- **markets_tested:** ES daily (calibration point; applies to any grid).
- **parameter_ranges_explored:** 36-cell grid × 3 seeds.
- **assumptions_violated:** independence of trials (trials share one price
  path); unadjusted multiple testing.
- **reinvestigation_justified_when:** Never as sole evidence. The corrected
  layer (DSR/RC) is mandatory for any grid result; the single-test gate
  remains only as a pre-screen.
- **related:** E-0003; meta_research.md §1.

## NK-0003 — Overnight gap fading on ES daily

- **hypothesis:** After an overnight gap ≥ threshold_pct, the holding-period
  open→close return fades the gap (gap up → short, gap down → long); the
  opposite-sign flip of NK-0001.
- **reason_for_rejection:** No edge survives data-snooping adjustment despite
  strong raw statistics; the best fade cell was indistinguishable from every
  benchmark and from C001's best continuation cell.
- **statistical_evidence:** Best cell (0.5%, h=3, both) raw: permutation
  p=0.0007, Welch p=0.020, bootstrap CI [+0.066%, +0.949%], P(win>50%)=0.954,
  but SPRT undecided and per-year means negative in 5 of 11 years. **Decisive:**
  DSR p=0.370, White's Reality Check p=0.083–0.101 (3 seeds); best-trial Welch
  vs random entries p=0.188, vs buy & hold p=0.214, vs best SMA p=0.445, vs
  best EMA p=0.383; paired vs C001 best cell p=0.328.
- **robustness_failures:** delayed-fill layer loses significance entirely
  (p=0.061; Sharpe 0.569 → 0.299); 39% of 36 cells nominally significant at 5%
  (inside the measured false-discovery band, NK-0002); cost ladder survives
  (+0.525% → +0.475% mean/trade at 5 bps) but does not rescue the verdict.
- **benchmark_comparison:** best fade cell mean +0.0240%/day vs buy & hold
  +0.0569%, best SMA +0.0403%, best EMA +0.0414%, random +0.0061% (daily).
- **markets_tested:** ES (E-mini S&P 500), daily, 2016-08 → 2026-08.
- **parameter_ranges_explored:** threshold_pct {0.3, 0.5, 0.7, 1.0} ×
  hold_days {1, 2, 3} × direction {up, down, both} × costs {0, 2.5, 5 bps} ×
  seeds {0, 1, 2} + delayed-fill layer (next-close).
- **assumptions_violated:** "Gaps revert" — the raw edge was real but the
  searched-best variant is not distinguishable from search noise; same-day open
  fills assumed tradeable; overnight negative drift (−14% share, F-GAP-COMP) is
  descriptive and does not transfer to a tradeable rule net of search
  adjustment and fill timing.
- **reinvestigation_justified_when:** (a) intraday data enables true auction-
  open fill modeling (the delayed-fill degradation is the strongest warning);
  (b) conditioning on overnight-session characteristics (e.g., gap within
  overnight range) becomes available; (c) a different market family is tested
  as primary — ES-only rejection does not transfer. The plain gap-fade rule on
  ES daily is **exhausted in both signs** (with NK-0001).
- **related:** E-0004; gap_fading/report.md; NK-0001 (opposite sign), NK-0002
  (calibration).

---

## Open negative space (candidate hypotheses already known to be weak — do not rush)

- Calendar/day-of-week effects on liquid modern futures (H-SESS-01/02):
  expected rejection class; cheap calibration value only — do not invest
  beyond Campaign C005 scope.
- Single-market, single-window daily strategy results (any family): the
  weakest evidence class per meta_learning.md §2 — never the basis for an
  acceptance without multi-market or out-of-window support.
