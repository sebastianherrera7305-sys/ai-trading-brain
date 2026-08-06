# Overnight Gap Continuation on E-mini S&P 500 futures (ES) — Study Report

**Study ID:** gap-continuation-v1
**Author:** sebastian
**Date:** 2026-08-06
**Verdict:** **REJECTED** — no evidence of a tradeable edge after data-snooping adjustment.

## 1. Hypothesis

> After an overnight opening gap in daily ES futures of magnitude ≥ `threshold_pct`,
> the holding-period return (open-to-close over `hold_days`) continues in the gap
> direction: gap up → long, gap down → short. The edge survives transaction costs.

## 2. Data & pipeline

| Item | Value |
|---|---|
| Instrument | CME E-mini S&P 500 futures (ES), continuous front month |
| Source | `data/ES_F_10y.csv` (daily OHLC) |
| Bars | 2,513 (2016-08-04 → 2026-08-04) |
| Prepared dataset | `es-f-10y-ohlc-v1`, id `8d2a7d6b…9a84`, sha256 `b3159e9d…24276`, 101,024 B |
| Pipeline | `prepare_dataset.py`: raw CSV → float64 OHLC + epoch-day dates; no imputation, no adjustment; registered in the research store (`/tmp/research-study`) |
| Trial matrix dataset | `es-gap-trial-matrix-v1`, id `3dec8c36…c535a2`, sha256 `519cb85d…1a00520`, 105,979 B |

All statistics are computed by `quant_research` (frozen v0.3.0, numpy-only, seeded).
No volume column exists in the data; volume-based analysis was excluded by design.

## 3. Experiment design

- **Search grid (36 cells × 3 seeds = 108 runs):** `threshold_pct ∈ {0.3, 0.5, 0.7, 1.0}`, `hold_days ∈ {1, 2, 3}`, `direction ∈ {up, down, both}`, cost 0 bps.
- **Cost robustness (216 runs):** the same 36 cells at 2.5 and 5.0 bps round-trip cost.
- **Trades:** non-overlapping (next entry only after previous exit); long after up-gaps, short after down-gaps; exposure-accurate daily P&L.
- **Per-run statistical battery (quant_research):** permutation test of entry-day selection vs the signed pool of all possible trades (`permutation_test_signal`, 3,000 perms), Welch t vs the same pool (`two_sample_t_test`), moving-block bootstrap 95% CI on mean trade return (1,000 draws), Bayesian P(win rate > 50%) with uniform prior (`probability_edge_above`), Wald SPRT of 50% vs 55% win rate (`sprt_bernoulli`), per-year and EWMA-volatility-tercile breakdowns. Cells with < 3 trades are excluded from statistics.
- **Benchmarks (16 runs):** buy & hold; random non-overlapping entries (p=0.05, 3 seeds); SMA crossovers (5/50, 10/100, 20/200); EMA crossovers (5/50, 10/100, 20/200) — all long-only, one-day signal lag, same daily-P&L basis.
- **Meta-validation (3 seeds):** over the 36-trial matrix — Deflated Sharpe Ratio (Bailey–López de Prado), White's Reality Check (block bootstrap, block 21, 1,500 draws), and Welch t of the best trial's daily P&L vs each benchmark.
- **Configs:** generated deterministically by `generate_configs.py` (38 JSON configs, committed).

## 4. Results

### 4.1 Strategy search

Best cell by annualized Sharpe: **threshold 0.3%, hold 1 day, up only, cost 0 bps**.

| Metric | Best-by-Sharpe cell | Best-by-mean cell |
|---|---|---|
| Cell | thr 0.3%, h=1, up | thr 0.3%, h=2, up |
| n trades | 111 | 109 |
| Mean trade return | +0.22% | +0.32% |
| Win rate | 59.5% | — |
| Annualized Sharpe | 0.52 | 0.51 |
| Total return (10y) | +26.3% | +39.4% |
| Permutation p (entry days) | **0.027** | **0.014** |
| Welch t vs signed pool | t=1.51, p=0.133 | t=1.68, p=0.095 |
| Bootstrap 95% CI (mean/trade) | [−0.013%, +0.51%] | [0.00%, +0.69%] |
| P(win rate > 50%) | 0.977 | 0.948 |
| SPRT (50% vs 55%) | continue | continue |

Only the permutation gate is nominally significant; the Welch test, bootstrap CI
(includes 0), and SPRT (no decision after 111 trades) do not confirm an edge.
Across the whole search grid, only **5 of 36 cells (14%)** are nominally significant
at 5% — consistent with chance under multiple testing — and 13 of 36 (36%) have
positive Sharpe.

### 4.2 Cost robustness (best cell)

| Cost | Mean/trade | Win rate | Sharpe |
|---|---|---|---|
| 0 bps | +0.220% | 59.5% | 0.52 |
| 2.5 bps | +0.195% | 58.6% | 0.52 |
| 5.0 bps | +0.170% | 58.6% | 0.52 |

The edge candidate survives the cost ladder (still positive at 5 bps), so costs do
not explain the result.

### 4.3 Benchmarks

| Benchmark | Sharpe | Total return | Exposure |
|---|---|---|---|
| Buy & hold | 0.79 | +254% | 100% |
| Random entries h=1 | −0.03 | — | — |
| Random entries h=2 | 0.06 | — | — |
| Random entries h=3 | 0.22 | — | — |
| SMA(5,50) / (10,100) / (20,200) | 0.77 / 0.86 / 0.77 | +116–154% | ~0.7 |
| EMA(5,50) / (10,100) / (20,200) | 0.80 / **0.89** / 0.72 | +127–164% | ~0.8 |

Every trend-following benchmark beats the best gap cell (Sharpe 0.52). Buy & hold
(+254%) also dominates the best cell's +26–39% over the same window.

### 4.4 Meta-validation (the decisive test)

Search set: 36 strategy cells (cost 0). Optimization statistic: mean daily return.

| Test | Statistic | Result |
|---|---|---|
| **Deflated Sharpe Ratio** | DSR p = **0.285** | not significant at 5% |
| **White's Reality Check** | p = **0.370–0.395** (3 seeds) | not significant at 5% |
| Best trial vs random entries | mean 0.00014 vs 0.00006/day, p=0.375 | not significant |
| Best trial vs buy & hold | mean 0.00014 vs 0.00057/day, p=0.080 | not significant |
| Best trial vs best SMA | p=0.162 | not significant |
| Best trial vs best EMA | p=0.111 | not significant |

Once the 36-cell search is accounted for, the best cell is statistically
indistinguishable from random entries and from the null of no edge. Its mean daily
return is lower than buy & hold's (0.014% vs 0.057%).

## 5. Reproducibility

| Commit | Content | Reproduced at | Result |
|---|---|---|---|
| `eafdf3d` (C1) | study code + configs + prepared dataset | best cell, buy & hold | **matched** (61 and 6 metrics, exact) |
| `fe4828c` (C2) | trial matrix dataset (from registry artifacts) | — | — |
| `c407039` (C3) | gap_meta import fix | meta-validation seed 0 | **matched** (26 metrics, exact) |

Every reproduction ran with the module checksum and dataset sha256 verified, on a
clean tree. The framework correctly refused to verify the first meta run (recorded
from a dirty tree) and the smoke-phase failures (6 records, all root-caused and
fixed before production runs; zero production failures). Environment: CPython 3.9.6,
numpy 2.0.2, macOS arm64.

### Platform questions answered via `research compare`

- `best` (ann_sharpe): top of everything searched = EMA(10,100) crossover (≈0.89), then buy & hold (0.75–0.79); best gap cell ≈0.52.
- `robustness` (ann_sharpe > 0 by threshold_pct): pass rate 33–44% across the grid — no threshold is robust.
- `significance` (hold 1 vs hold 2, both-direction cells): p=0.0054, Cohen's d=1.04 — hold-1 cells differ from hold-2 cells internally (irrelevant to the verdict).
- `failures`: 6 records, all from module bring-up (import order, pool slice alignment, datetime casting); none in production runs.

## 6. Conclusion

**Verdict: REJECTED.** The overnight gap continuation hypothesis does not hold on
daily ES futures (2016–2026):

1. The best of 36 searched cells shows a nominally significant permutation p-value
   (0.014–0.027) but fails every confirmatory test (Welch p > 0.09, bootstrap CI
   includes 0, SPRT undecided).
2. Data-snooping-adjusted tests reject it: DSR p = 0.285, White's Reality Check
   p ≈ 0.39. The "edge" is the expected artifact of searching 36 variants.
3. All simple benchmarks (buy & hold, SMA/EMA crossovers) dominate the best cell on
   Sharpe and total return; the best trial is indistinguishable from random entries.

## 7. Limitations & follow-ups

- Single instrument (ES) and single timeframe (daily); the result does not generalize by construction.
- Continuous front-month contract; roll handling is the data provider's.
- Gap defined versus prior close only; no overnight-session, volume, or intraday information (not in the data).
- Non-overlapping trade constraint shrinks the sample (111 trades over 10y) and caps sensitivity.
- Data window extends to 2026-08 (environment clock); the last months are OOS with respect to any real 2025 trading.
- Follow-ups if this thread is ever revisited: intraday data for true open-gap fills, gap-fading (opposite) hypothesis, per-symbol panel across CL/GC/EURUSD, and regime-conditional splits.

## 8. Artifacts

- Study code: `research_studies/gap_continuation/` (`gap_strategy.py`, `gap_meta.py`, `buy_hold.py`, `random_entries.py`, `sma_crossover.py`, `ema_crossover.py`, `_common.py`, `prepare_dataset.py`, `assemble_trial_matrix.py`, `generate_configs.py`, 38 configs).
- Registry: `/tmp/research-study` (340 production runs + 6 bring-up failures + reproductions).
- Data: `data/ES_F_10y.csv` (raw), `data/es_f_10y_ohlc_v1.npz` (prepared), `data/es_gap_trial_matrix_v1.npz` (trial matrix).
