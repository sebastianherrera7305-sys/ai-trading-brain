# Overnight Gap Fading on E-mini S&P 500 futures (ES) — Study Report

**Study ID:** gap-fading-v1
**Author:** sebastian
**Date:** 2026-08-06
**Verdict:** **REJECTED** — no evidence of a tradeable edge after data-snooping adjustment.

## 1. Hypothesis

> After an overnight opening gap in daily ES futures of magnitude ≥ `threshold_pct`,
> the holding-period return (open-to-close over `hold_days`) fades the gap: gap up →
> short, gap down → long. The edge survives transaction costs.

This is the exact sign-flip of the C001 (gap continuation) hypothesis
(catalog successor hypothesis H-MS-01), pre-registered before execution; no
parameter, methodology, or protocol change was made after registration.

## 2. Data & pipeline

| Item | Value |
|---|---|
| Instrument | CME E-mini S&P 500 futures (ES), continuous front month |
| Source | `data/ES_F_10y.csv` (daily OHLC) |
| Bars | 2,513 (2016-08-04 → 2026-08-04) |
| Prepared dataset | `es-f-10y-ohlc-v1`, id `8d2a7d6b…9a84`, sha256 `b3159e9d…24276`, 101,024 B |
| Pipeline | `prepare_dataset.py` (C001, unchanged): raw CSV → float64 OHLC + epoch-day dates; no imputation, no adjustment; registered in the research store |
| Trial matrix dataset | `es-gap-fade-trial-matrix-v1`, id `54fcd511…bba5`, sha256 `7862a5ae…83f7`, 211,673 B |
| Features | F-GAP-COMP (`overnight_gap`, `gap_decomposition`) — `research_studies/features/__init__.py`; reproduces C001's `gap_series` exactly (max diff 0.0) |

All statistics are computed by `quant_research` (frozen v0.3.0, numpy-only, seeded).
No volume column exists in the data; volume-based analysis was excluded by design.

**Storage incident (registered, not silent):** the original execution store
(`/tmp/research-study`) was deleted by the macOS periodic tmp cleanup after the
first execution pass; the assembled trial matrix NPZ and the prepared dataset NPZ
survived in `data/`. All 432 strategy runs were re-executed deterministically into
the persistent store (`~/.research`), and the re-executed seed-0 runs were verified
identical to the surviving matrix cell-by-cell (36/36 strategy, 36/36 delayed
`allclose`), so the evidence is fully reconstructed. The discarded first-pass runs
remain in the store, marked `git_dirty` (excluded by the B3 gate).

## 3. Experiment design

- **Search grid (36 cells × 3 seeds = 108 runs):** `threshold_pct ∈ {0.3, 0.5, 0.7, 1.0}`, `hold_days ∈ {1, 2, 3}`, `direction ∈ {up, down, both}`, cost 0 bps.
- **Cost robustness (216 runs):** the same 36 cells at 2.5 and 5.0 bps round-trip cost.
- **Delayed layer (108 runs, spec §7.5):** the 36 cells × 3 seeds at 0 bps with fills deferred to the following bar's close (robustness to fill slippage), a separate module (`gap_fading_delayed.py`), excluded from the DSR/RC search set.
- **Trades:** non-overlapping (next entry only after previous exit); short after up-gaps, long after down-gaps; exposure-accurate daily P&L.
- **Per-run statistical battery (quant_research):** permutation test of entry-day selection vs the signed pool of all possible trades (`permutation_test_signal`, 3,000 perms), Welch t vs the same pool (`two_sample_t_test`), moving-block bootstrap 95% CI on mean trade return (1,000 draws), Bayesian P(win rate > 50%) with uniform prior (`probability_edge_above`), Wald SPRT of 50% vs 55% win rate (`sprt_bernoulli`), per-year and EWMA-volatility-tercile breakdowns.
- **Benchmarks (16 runs, C001, unchanged, reused from the registry):** buy & hold; random non-overlapping entries (p=0.05, 3 seeds); SMA crossovers (5/50, 10/100, 20/200); EMA crossovers (5/50, 10/100, 20/200) — all long-only, one-day signal lag, same daily-P&L basis.
- **Meta-validation (3 seeds):** over the 36-trial fade matrix — Deflated Sharpe Ratio (Bailey–López de Prado), White's Reality Check (block bootstrap, block 21, 1,500 draws), Welch t of the best trial's daily P&L vs each benchmark, and the paired C001-vs-C002 best-cell comparison (spec §9.8).
- **Configs:** generated deterministically by `generate_configs.py` (38 JSON configs, committed; regeneration is byte-identical).

## 4. Results

### 4.1 Strategy search

Best cell by mean daily return: **threshold 0.5%, hold 3 days, both directions, cost 0 bps**.

| Metric | Best fade cell | C001 best cell (same battery, for reference) |
|---|---|---|
| Cell | thr 0.5%, h=3, both | thr 0.3%, h=1, up |
| n trades | 114 | 111 |
| Mean trade return | +0.525% | +0.220% |
| Win rate | 57.9% | 59.5% |
| Annualized Sharpe | 0.569 | 0.520 |
| Total return (10y) | +72.9% | +26.3% |
| Max drawdown | −19.8% | — |
| Permutation p (entry days) | **0.0007** | 0.027 |
| Welch t vs signed pool | t=2.36, p=0.0197 | t=1.51, p=0.133 |
| Bootstrap 95% CI (mean/trade) | [+0.066%, +0.949%] | [−0.013%, +0.51%] |
| P(win rate > 50%) | 0.954 | 0.977 |
| SPRT (50% vs 55%) | undecided | continue |

Across the whole search grid, **14 of 36 cells (39%)** are nominally significant
at 5% by the permutation gate and **23 of 36 (64%)** have positive annualized
Sharpe — a stronger raw picture than C001, but the nominal rate still sits inside
the false-discovery range of a 36-cell search (C001 calibration: 14%).

Per-year mean trade return of the best cell (n trades): 2016 −0.28% (3), 2017
−0.14% (3), 2018 +1.56% (9), 2019 +0.48% (10), 2020 +1.25% (22), 2021 +1.04% (3),
2022 −0.23% (14), 2023 +0.66% (7), 2024 −0.71% (7), 2025 −0.19% (23), 2026 +1.51%
(13). Five of eleven years are negative.

### 4.2 Cost robustness (best cell)

| Cost | Mean/trade | Win rate | Sharpe |
|---|---|---|---|
| 0 bps | +0.525% | 57.9% | 0.569 |
| 2.5 bps | +0.500% | 57.9% | 0.569 |
| 5.0 bps | +0.475% | 57.9% | 0.569 |

The edge candidate survives the cost ladder (still positive at 5 bps), so costs do
not explain the result.

### 4.3 Benchmarks

| Benchmark | Mean daily return | Daily Sharpe | vs best fade trial (Welch) |
|---|---|---|---|
| Best fade trial (0.5%, h=3, both) | +0.0240% | 0.0358 | — |
| Buy & hold | +0.0569% | 0.0499 | t=−1.24, p=0.214 |
| Random entries pool | +0.0061% | 0.0180 | t=1.32, p=0.188 |
| Best SMA crossover | +0.0403% | — | t=−0.76, p=0.445 |
| Best EMA crossover | +0.0414% | — | t=−0.87, p=0.383 |

The best fade trial is not distinguishable from any benchmark at 5%, and its mean
daily return is below buy & hold and both crossover families.

### 4.4 Meta-validation (the decisive test)

Search set: 36 strategy cells (cost 0). Optimization statistic: mean daily return.

| Test | Statistic | Result |
|---|---|---|
| **Deflated Sharpe Ratio** | DSR p = **0.370** | not significant at 5% |
| **White's Reality Check** | p = **0.083–0.101** (3 seeds: 0.084 / 0.101 / 0.083) | not significant at 5% |
| Best trial vs random entries | mean 0.000240 vs 0.000061/day, p=0.188 | not significant |
| Best trial vs buy & hold | mean 0.000240 vs 0.000569/day, p=0.214 | not significant |
| Best trial vs best SMA | p=0.445 | not significant |
| Best trial vs best EMA | p=0.383 | not significant |
| **Paired C001 vs C002** | C002 Sharpe 0.0358 vs C001 0.0327/day; t=0.98, p=0.328; beat=1 | not significant |

Once the 36-cell search is accounted for, the best fade cell is statistically
indistinguishable from the null of no edge and from C001's best continuation cell.
Despite stronger raw statistics than C001 (permutation p=0.0007, Welch p=0.020),
the corrected tests do not reach significance.

### 4.5 Delayed layer (fill robustness, spec §7.5)

Best cell delayed (0.5%, h=3, both, seed 0): 112 trades, win 52.7%, annualized
Sharpe **0.299** (vs 0.569 same-day fills), permutation p=0.061 (not significant).
Deferring fills to the following close materially degrades the edge candidate and
removes its raw significance — the result is not robust to fill timing.

### 4.6 F-GAP-COMP decomposition (descriptive)

| Component | Mean daily return | Cumulative drift (10y) |
|---|---|---|
| Overnight leg | −0.0080% | −0.2017 |
| Intraday leg | +0.0650% | +1.6337 |
| Correlation (overnight vs intraday) | −0.024 | — |

Overnight drift share: −14.1% of the total. On daily ES, the mean overnight
(gap) return is negative — consistent with the well-documented negative overnight
premium — yet the fade rule's raw edge does not survive the search-adjustment or
the delayed-fill check. The decomposition is descriptive context, not a strategy
signal.

## 5. Reproducibility

| Commit | Content | Reproduced at | Result |
|---|---|---|---|
| `bcfe4ed` | campaign pre-registration (spec, awaiting approval) | — | — |
| `6aeae2c` (C1) | study code, features, configs, R1 evidence-gated assembly, audit docs | — | — |
| `c4a4199` (C2) | meta paired-comparison input-shape fix (R2) + 3 regression tests | — | — |
| `eb0667c` | trial matrix artifact (sha256 7862a5ae…) | — | — |
| `(closure)` | this report, Edge DB, dashboard | — | — |

| Reproduction | Verdict |
|---|---|
| Best fade cell (0.5%, h=3, both, seed 0) at its commit | **matched** (re-executed; git/dataset/module checks pass) |
| Meta-validation seed 0 at its commit | **matched** (re-executed; git/dataset/module checks pass) |

All 432 production runs executed on a clean tree (verified per run), with
`hypothesis=H-MS-01`, `config_hash`, `module_checksum`, `seed`, git snapshot, and
`quant_research` version recorded in the persistent store `~/.research`. The
first-pass runs (dirty-tree) and the original smoke run are preserved in the store
but excluded by the B3 evidence gate (see §2 incident note).

**Registered deviations (none silent):** (1) storage incident of §2 — re-execution
with identity verification; (2) first re-execution pass recorded `git_dirty=1`
because the R2 fix was not yet committed — re-executed on a clean tree; (3) the
R2 fix itself (1 line, `gap_fading_meta.py:114`) surfaced only at runtime because
the meta consumer had never run against a real matrix (C001's meta experiment
never ran — it was rejected before the meta layer existed).

## 6. Conclusion

**Verdict: REJECTED.** The overnight gap fading hypothesis does not hold on daily
ES futures (2016–2026):

1. The best of 36 searched cells shows strong raw statistics (permutation
   p=0.0007, Welch p=0.020, bootstrap CI excluding 0) and survives the cost
   ladder, but the delayed-fill layer (p=0.061) and per-year stability (5 of 11
   years negative) are weak.
2. Data-snooping-adjusted tests reject it: DSR p = 0.370, White's Reality Check
   p ≈ 0.083–0.101. The "edge" is again the expected artifact of searching 36
   variants — consistent with the C001 calibration (NK-0002).
3. The best fade trial is not distinguishable from random entries (p=0.188) or
   from C001's best continuation cell (p=0.328), and its mean daily return is
   below buy & hold and both crossover families.

Both signs of the gap rule — continuation (C001) and fading (C002) — are now
rejected on this market/window with the same methodology: H-MS-01 (gap as signal)
is falsified in both directions.

## 7. Limitations & follow-ups

- Single instrument (ES) and single timeframe (daily); the result does not generalize by construction.
- Continuous front-month contract; roll handling is the data provider's.
- Gap defined versus prior close only; no overnight-session, volume, or intraday information (not in the data).
- Non-overlapping trade constraint shrinks the sample (114 trades over 10y).
- Same-day open fills are modeled; the delayed layer (next-close) is the only fill-slippage check — true auction-open fill data would be the definitive test.
- The overnight drift decomposition (−14% overnight share) is descriptive; it does not itself support a tradeable claim on this window.
- Data window extends to 2026-08 (environment clock); the last months are OOS with respect to any real 2025 trading.
- Follow-ups if this thread is ever revisited: intraday data for true fill modeling, per-symbol panel across CL/GC/EURUSD, and conditioning on overnight-session characteristics. The gap family on ES daily is now exhausted in both directions (see NK-0003).

## 8. Artifacts

- Study code: `research_studies/gap_fading/` (`gap_fading.py`, `gap_fading_delayed.py`, `gap_fading_meta.py`, `_common.py`, `assemble_trial_matrix.py`, `generate_configs.py`, 38 configs, `campaign_spec.md`, audit docs).
- Features: `research_studies/features/__init__.py` (F-GAP-COMP, verified).
- Registry: `~/.research` (432 clean production runs + 432 discarded dirty first-pass runs + 3 meta runs + reproductions; datasets `es-f-10y-ohlc-v1`, `es-gap-fade-trial-matrix-v1`).
- Data: `data/ES_F_10y.csv` (raw), `data/es_f_10y_ohlc_v1.npz` (prepared), `data/es_gap_fade_trial_matrix_v1.npz` (trial matrix, sha256 `7862a5ae…`).
- Evidence gate: B3 (clean-tree + full metadata) enforced by `assemble_trial_matrix.py`; exclusion reasons recorded per candidate (R1).
