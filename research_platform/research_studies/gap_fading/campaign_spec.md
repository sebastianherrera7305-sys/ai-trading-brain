# Campaign C002 — Gap Fading (H-MS-01) — Pre-Registered Research Protocol

**Role:** Director of Quantitative Research.
**Status:** SPECIFICATION ONLY — awaiting approval. No experiments have been
executed. No infrastructure has been modified.
**Date:** 2026-08-06. **Platform:** existing research platform, used exactly
as it exists (no new frameworks).

Scientific hypothesis (H-GAP-FADING): *"Do overnight gaps tend to partially
or fully mean revert during the following session after controlling for
costs, benchmarks, and multiple testing?"*

Canonical catalog ID: **H-MS-01** (catalog.md §1). This document is the
pre-registered protocol for Campaign C002; any deviation requires a
meta-research entry and a spec amendment before continuing.

---

## 1. Research question

Does the *opposite sign* of the C001 rule carry a post-cost edge on ES daily:
after an overnight gap exceeding `threshold_pct`, does the holding-period
open→close move reverse the gap (gap up → short, gap down → long)?

C001 tested gap *continuation* and was rejected (E-0001: DSR p=0.285, RC
p≈0.39). C002 determines whether the opposite-sign hypothesis survives. The
two verdicts jointly close the gap family on ES daily: "no continuation" +
"no fade" = gap dimension exhausted; "fade edge" = first edge candidate.

## 2. Null hypothesis

**H0 (no fade edge):** after controlling for costs, benchmarks, and multiple
testing, the fade rule has no statistically significant edge — the best
searched fade cell is indistinguishable from its construction-matched null
and does not beat the benchmarks; formally, DSR p ≥ 0.05 or best cell ≤ C001
best cell or all benchmark comparisons not significant.

## 3. Alternative hypothesis

**H1 (fade edge):** gaps partially or fully revert within the holding
window; the directional fade rule has a positive post-cost edge that
survives multiplicity correction and beats the C001 best cell and at least
one benchmark on the identical basis.

## 4. Required datasets

| Dataset | ID | Grade | Use |
|---|---|---|---|
| ES daily OHLC 10y | `es-f-10y-ohlc-v1` (`8d2a7d6b…9a84`) | A | Primary; identical window to C001 (2016-08 → 2026-08, 2,513 bars) — required for the paired C001-vs-C002 comparison |

- Integrity gate at launch: checksum re-verified
  (`b3159e9d…24276` = `data/es_f_10y_ohlc_v1.npz`); runner re-verifies the
  blob per run (`verify_dataset`).
- Multi-market (CL/GC/EURUSD) is NOT part of this campaign: per the decision
  framework, an ES-only inconclusive/insufficient result routes to the
  REQUIRES_MORE_DATA follow-up (multi-market C002 extension) — the datasets
  are Grade B/C and registered only at that follow-up.

## 5. Required features

| Feature | Status | Use |
|---|---|---|
| F-GAP | `verified` (C001) | Overnight gap definition + threshold filter (core signal) |
| F-GAP-COMP | `planned (P0, C002)` | Gap/intraday decomposition in the closing analysis (deliverable; NOT consumed by the strategy cells) |

F-GAP-COMP must be implemented and verified as the campaign's first
in-campaign step (roadmap.md pledge: "C002 … F-GAP-COMP verified"), before
the decomposition analysis. The 36-cell matrix itself depends on F-GAP only.

## 6. Feature definitions

All returns are computed from the registered OHLC npz (float64, epoch-days):

- **Gap (F-GAP):** `gap_pct_t = open_t / close_{t-1} − 1` (daily basis).
  A gap day qualifies when `|gap_pct_t| > threshold_pct` (threshold ∈
  {0.3, 0.5, 0.7, 1.0} percent, identical grid to C001).
  - Up gap: `gap_pct_t > +threshold`; Down gap: `gap_pct_t < −threshold`.
- **Fade position (sign flip of C001):** up gap → short from `open_t`;
  down gap → long from `open_t`. Exit at `close_{t+hold-1}` (hold ∈
  {1, 2, 3} days). Direction variants: `up` (short only), `down` (long
  only), `both` (pooled).
- **Fade return:** `(close_{t+hold-1} / open_t − 1)` with sign flipped
  relative to C001's continuation convention (identical construction).
- **F-GAP-COMP (closing analysis only):** overnight return
  `= open_t/close_{t-1} − 1`; intraday return `= close_t/open_t − 1`;
  decomposition of drift components and their correlation — descriptive
  context for the verdict, not a strategy signal.
- **Market context (subgroup decomposition, NOT strategy variants):**
  - Trend regime: sign of `close_t − EMA(100)` (consistent with the EMA
    benchmark family).
  - Volatility regime: EWMA(20)-vol tercile of the day (identical
    construction to C001's regime breakdown).

## 7. Experimental variants

**Principle: parameter variations are experiments, not hypotheses.** The
hypothesis is evaluated over the grid as a family; per-cell results are
descriptive and never the basis of the verdict (NK-0002).

### 7.1 Primary matrix — mirror of C001 (sign flip only)

36 cells = thresholds {0.3, 0.5, 0.7, 1.0} × hold {1, 2, 3} × direction
{up, down, both}, each × seeds {0, 1, 2}.

- 0 bps: 36 × 3 = **108 runs**
- Cost ladder: same 36 cells × 3 seeds @ 2.5 and 5 bps: **216 runs**

The grid, modules, and cost model are C001's exactly, with the position
sign inverted — this is what makes the paired meta-comparison valid.

### 7.2 Gap-size classification (descriptive)

| Class | Threshold range |
|---|---|
| Small | 0.3% |
| Medium | 0.5–0.7% |
| Large | 1.0% |

Classification is for subgroup reporting (does any fade effect concentrate
in large gaps?); it adds no cells.

### 7.3 Direction

Up / down / both as in C001 — reports whether any fade effect is
directional or pooled.

### 7.4 Market context (subgroup decomposition of primary cells)

- Trend regime split (bull vs bear vs flat) and vol-regime split
  (low/med/high EWMA-vol tercile) are computed on the primary cells'
  trade series — C001's per-year/regime robustness pattern. Regime
  *conditional claims* require their own multiplicity statement; the
  campaign verdict never rests on a subgroup.
- Per-year breakdown (2016–2026) mandatory (C001 showed 2023/2026
  negative for continuation).

### 7.5 Execution layer (robustness, secondary)

| Variant | Construction | Status in the verdict |
|---|---|---|
| Open entry (primary) | Fill at day-t open (as C001) | Verdict input |
| Delayed entry | Same 36 cells × 3 seeds, entry at day-t close (no open fill), 0 bps: **108 runs** | Robustness/tradability check — cannot resurrect a rejected primary verdict; tests the untested C001 assumption "tradeable open fill" |
| Realistic costs | 0/2.5/5 bps ladder on the primary matrix | Verdict input (acceptance requires survival at 0 bps; ladder reported as robustness) |

Total planned runs: 108 + 216 + 108 (delayed) + meta runs + launch
reproductions (Gate F).

## 8. Benchmark strategies

All on the identical basis (same daily bars, window, cost handling):

| Benchmark | Reference | Role |
|---|---|---|
| Buy & hold | E-0002 recorded (Sharpe 0.79) | Acceptance requires ≥1 benchmark beaten |
| EMA(10,100) | E-0002 recorded (Sharpe 0.89) | Acceptance requires ≥1 benchmark beaten |
| Random entries (seed 0) | E-0002 recorded (−0.03…+0.22 by hold) | Null-basis sanity check |
| C001 best cell | E-0001 recorded (Sharpe 0.52) | **Paired meta-comparison** (C001 vs C002 best cell) |

C001's 16 benchmark runs (E-0002) are reused from the store — same dataset,
window, and construction (no rerun needed); a spot reproduction of the 4
headline benchmarks at launch doubles as the Gate F reproducibility proof.

## 9. Statistical methodology

Identical battery to C001 (all statistics via `quant_research` v0.3.0,
frozen; version recorded per run):

1. **Permutation nullity gate** — **vs signed pool** (the C001 pool-alignment
   lesson: a directional fade rule is tested against same-construction
   signed trades, never an unsigned pool).
2. **Welch t** vs construction-matched pool (all possible trades) — per cell
   and vs random entries / buy & hold / best SMA / best EMA (C001 mirror:
   best-trial Welch vs benchmarks).
3. **Block bootstrap CI** on mean/trade.
4. **Bayesian win-rate**.
5. **Wald SPRT** (sequential; C001 left it undecided after 111 trades —
   expected here too; sample-size caveat reported).
6. **Per-year and vol-regime breakdowns** (§7.4).
7. **gap_description** (descriptive: gap counts, size distribution, fade
   event counts by direction/hold).
8. **Meta stage (gap_fading_meta):** paired C001-vs-C002 best-cell
   comparison; DSR/RC over the C002 grid; trial-matrix assembly
   (`assemble_trial_matrix` pattern of C001, hypothesis H-MS-01).

Test parameters (n_permutations, iterations, CI method) are recorded in the
report appendix (platform cannot persist them yet — N3).

## 10. Multiple testing correction

- **DSR (deflated Sharpe) + White's Reality Check over the 36-cell grid ×
  3 seeds** — mandatory, per NK-0002 (the single-test permutation gate is a
  pre-screen only).
- Calibration reference: E-0003 (5/36 cells ≈ 14% nominal significant ≈
  chance in C001) — any C002 nominal-significance rate near 14% is expected
  under H0.
- The delayed-entry layer (7.5) is a separate 36-cell search; it is
  reported with its own DSR/RC as a robustness fact, not a verdict input.

## 11. Cost assumptions

Inherited verbatim from C001 modules (sign flip only):
- Round-trip cost `cost_bps` ∈ {0, 2.5, 5} bps, applied on the daily basis
  exactly as C001's verified implementation (E-0001 robustness).
- C001 result to expect: Sharpe insensitive to 5 bps; mean/trade decays
  (0.22% → 0.17% in C001) — report both metrics at every cost.
- No slippage/partial-fill modeling (assumption recorded: daily open vs
  true auction open untested in C001; the delayed-entry layer probes it).

## 12. Acceptance criteria (ACCEPTED)

All of:
1. DSR p < 0.05 after multiplicity correction over the grid;
2. Best cell Sharpe > C001 best cell (0.52) on the identical cost basis;
3. ≥ 1 benchmark beaten (buy & hold 0.79 or EMA(10,100) 0.89) at 0 bps;
4. Robustness consistency: positive per-year sign in ≥ 9 of 11 years for
   the headline cell, stable across seeds {0,1,2}, and the fade effect
   survives the cost ladder directionally (mean/trade positive at 5 bps);
5. F-GAP-COMP verified and decomposition analysis delivered (roadmap
   deliverable) in the closing report.

## 13. Rejection criteria (REJECTED)

Any of:
1. DSR p ≥ 0.05; or
2. Best cell ≤ C001 best cell (0.52) on the identical basis; or
3. All benchmark comparisons not significant (best-trial Welch p ≥ 0.05 vs
   buy & hold and vs EMA(10,100) at 0 bps).

**INCONCLUSIVE** — evidence ambiguous: SPRT undecided AND bootstrap CI
straddles 0 AND subgroups conflict (e.g., fade in down-gaps only, weak
pooled) with no corrected significance; recorded as edge verdict
`inconclusive` with limitations.

**REQUIRES_MORE_DATA** — fade event count inadequate on ES daily (e.g.,
large-gap cells < 50 trades per seed) or window conflicts with C001's
per-year instability; recorded as edge verdict `inconclusive` + limitation,
and the follow-up is the multi-market C002 extension (CL/GC/EURUSD
registered first), catalog status `blocked-data` until then.

## 14. Expected information value

**High / S** — the cheapest experiment with the highest incremental
information:
- REJECTED: closes the entire gap family on ES daily ("no continuation" +
  "no fade" = dimension exhausted; roadmap rank 1 rationale); H-MS-01 →
  negative knowledge with reinvestigation triggers.
- ACCEPTED: the laboratory's first edge candidate (subject to the same
  battery at every later campaign).
- Either way: second DSR/RC calibration point (after E-0003), F-GAP-COMP
  verified, and the delayed-entry layer resolves the C001 "tradeable open
  fill" assumption.

---

## Registry alignment & execution plan (post-approval)

- Configs: mirror C001's `config_scan_*`, `config_cost_*` (hypothesis
  `H-MS-01`, module `gap_fading`); delayed entry: `config_delayed_*`
  (entry at close). Config validation enforces the canonical ID (B2).
- Experiment records: `hypothesis=H-MS-01`, seeds {0,1,2}, config_hash +
  module_checksum + git_commit recorded; clean tree required (B3 —
  UNVERIFIABLE_REPRODUCTION otherwise).
- Module `gap_fading.py` = `gap_strategy.py` with position sign inverted;
  `gap_fading_meta.py` = `gap_meta.py` mirror (H-MS-01 trial matrix).
- Launch gates: `research/C002_LAUNCH_CHECKLIST.md` (A–F before execution,
  G at closure). Precondition P1: F-GAP-COMP implemented + verified first.
- Closure: campaign report (README §6), Edge DB entry E-00xx, catalog
  status update, NK entry if rejected, graph + dashboard regenerated, one
  closure commit.
- Decision recorded per §12/§13; the four decision categories
  (ACCEPTED | REJECTED | INCONCLUSIVE | REQUIRES_MORE_DATA) map to edge
  verdicts as defined in campaigns.md (B1 governance).
