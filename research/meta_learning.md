# Meta-Learning

Analysis of the laboratory's entire research history, aimed at improving the
research strategy itself. Where `meta_research.md` logs what each campaign
learned (process + market), this document extracts cross-campaign patterns and
issues explicit recommendations. Update after every campaign closure and at
each quarterly review.

## 1. Current evidence base

- Campaigns completed: **1** (C001 gap continuation — rejected).
- Hypotheses tested: 1 (rejected). Hypotheses accepted: 0.
- Experiments: 354 registered (348 completed, 6 bring-up failures).
- Datasets: 4 markets × 10y daily (ES/CL/GC/EURUSD), 2 registered.
- Evidence class: **n = 1 campaign**. All patterns below are provisional and
  each must be re-tested as evidence accumulates.

## 2. Patterns (provisional, n=1)

### P1 — Searched grids over-produce nominal significance
5 of 36 cells (14%) passed the single-test gate at 5% — consistent with
chance; DSR (0.285) and White's RC (≈0.39) reversed the headline. Pattern:
single-test gates are pre-screens only; grid verdicts come from the
multiplicity-corrected layer.

### P2 — Trend-class benchmarks dominate ES daily
EMA(10,100) 0.89 > SMA(10,100) 0.86 > buy & hold 0.79 > best searched cell
0.52. The benchmark suite itself carried most of the "alpha" on this window
(2.5× index rise). Implication: on ES daily, any directional hypothesis must
outperform trend-class benchmarks, which is a high bar; long-biased
hypotheses must also beat buy & hold.

### P3 — Market drift is the largest measurable component
Buy & hold (+254%) swamped all searched gap cells (+26–39%). Daily-return
magnitude work (H-MS-02, H-TOD-01) will quantify how much of returns is
overnight vs intraday, but the drift dominance is already visible.

### P4 — Gap-family strategies are implicit vol bets
Gap entries clustered in high-EWMA-vol states (79/135 trades in the top
tercile in the reference cell). Any future gap/gap-fade test should treat
vol-state conditioning as a first-class dimension, not an afterthought.

### P5 — Single-market, single-window results are the weakest evidence class
The only tested hypothesis was ES-only, one window, one continuous series.
All conclusions carry the "market/window" qualifier until C003/C004/C007
replicate across markets.

### P6 — Implementation effort concentrates where the tests are
The battery (permutation, Welch, bootstrap, Bayesian, SPRT, DSR, RC) is ~50%
of campaign effort but produced the decisive evidence. Feature engineering
was ~15%. Effort allocation is roughly right; keep it.

## 3. Recommendations

- **R1 (research sequence):** Run C002 (gap fading) next — it completes the
  gap family at near-zero marginal cost and converts "no continuation edge"
  into "no gap edge" or "opposite edge".
- **R2 (standard benchmark suite):** Every daily campaign must include
  buy & hold, random entries (3 seeds), SMA(10,100), EMA(10,100) on the same
  daily-P&L basis. This makes cross-campaign comparisons valid and answers
  "which benchmarks are hardest to outperform" (P2: trend-class so far).
- **R3 (multi-market as default):** From C003 onward, hypotheses are tested
  on ≥2 markets; single-market results are labeled provisional.
- **R4 (multiplicity discipline):** Any search over >4 cells carries DSR/RC;
  the single-test gate is never the decision layer (P1).
- **R5 (vol conditioning):** Vol-state (F-REGIME, trailing quantiles) is a
  standard filter dimension in directional campaigns (P4).
- **R6 (feature library before C003):** Implement the P0 feature batch
  (features.md §2) before the multi-market campaigns so all campaigns share
  identical feature code; otherwise cross-market comparability suffers.
- **R7 (data roadmap):** The two highest-leverage acquisitions are VIX daily
  (trivial, unlocks H-ALT-01) and intraday ES (unlocks 8+ catalog hypotheses);
  do them when the daily campaign queue is exhausted or blocked.
- **R8 (ML benchmark discipline):** When C010 (ML) runs, its model/feature
  search is a grid like any other — DSR/RC-style multiplicity control and
  purged time-series CV are mandatory; an ML result that doesn't beat the
  standard benchmark suite is a rejection.

## 4. Standing questions — current answers

| Question | Answer (as of 2026-08-06) |
|---|---|
| Which domains consistently fail? | Only 1 tested: gap/continuation (MS). Insufficient data; gap family resolves at C002 |
| Which features appear in strong results? | Trend-class (MA/EMA exposure) carried the benchmarks; gap-day selection was weakly special |
| Which markets are easiest to model? | Unknown — ES only so far; C003/C004/C007 will answer |
| Which benchmarks are hardest to beat? | Trend-class crossovers (P2) |
| Which tests reject the most? | DSR/RC (rejected the only grid tested); single-test gates rejected 86% of cells but 5 false positives |
| Where does effort give the most information? | The validation layer (P6); not the sweep breadth |
