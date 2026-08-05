# 05 — Edge Detection: Statistical Methods for Confirming a Real Edge

The research layer of AI Trading Brain (doc 01 §integration) must never
promote a strategy to live trading purely on a backtest. This document
specifies the statistical machinery that separates real edge from noise —
and which pieces become part of the platform. Documentation only.

---

## 1. The core problem: multiple testing in a search space

A backtest engine generates thousands of candidate strategies (param
grids × instruments × regimes). At 95% confidence, ~5% of pure-noise
strategies will look significant by chance. Any single-test inference is
therefore meaningless until the search space is accounted for. This is the
**selection bias / data snooping** problem — the single most important
statistical issue in quant research.

## 2. Methods, ranked by role in the pipeline

### 2.1 Walk-forward analysis (already in trading-bot)
- Split the timeline into consecutive folds; optimize on each train window,
  validate strictly on the following OOS window; report only OOS folds.
- **In AI Trading Brain:** mandatory gate for every strategy before paper
  trading. Must include the beta benchmark and per-fold honesty that
  trading-bot's walk-forward currently lacks (pending hardening: benchmark,
  nullity test, robust selection metric).

### 2.2 Bootstrap (resampling) confidence
- Resample trade outcomes (block bootstrap — contiguous blocks to preserve
  serial dependence) → empirical distribution of performance (mean P&L,
  Sharpe, hit rate). Report percentile intervals, not point estimates.
- **Role:** quick sanity bounds on any metric, including after promotion.

### 2.3 Permutation test (nullity)
- Randomly permute entry/exit signals relative to returns (or shuffle
  trade ordering) to generate the distribution of performance under the
  null "no edge." If the real result is beyond the 95th-99th percentile of
  permutations → evidence of edge. Cheap, assumption-light, directly
  addresses "did this strategy outperform random timing?"
- **Role:** first-tier significance test; must accompany every backtest.

### 2.4 White's Reality Check (1997)
- A bootstrap procedure over the full family of candidate rules: tests
  whether the **best** candidate's OOS performance is distinguishable from
  the best achievable under the null (data-snooping-adjusted p-value).
- Computes the max of the standardized mean performances over all
  candidates, vs its bootstrap null.
- **Role:** the classic answer to "we tried 500 parameter sets — is the best
  one real?" Use when reporting the best of a grid.

### 2.5 Hansen's SPA test (2005)
- Supersedes White's Reality Check: uses the full distribution of candidate
  performances (not just the max) — better power, less prone to penalizing
  good candidates. Returns a data-snooping-adjusted p-value.
- **Role:** preferred upgrade of 2.4 in the promotion pipeline.

### 2.6 Cross-validation & time-series CV
- Rolling-origin (expanding-window) and blocked k-fold (contiguous blocks,
  non-overlapping — never shuffled k-fold on time series) to estimate
  generalization error.
- **Role:** model-level (AI Decision Engine) validation; complements
  walk-forward at the strategy level.

### 2.7 Bayesian updating
- Prior over strategy edge (weak, skeptical) → posterior updated per trade
  (or per day): `P(edge | data) ∝ P(data | edge) × P(edge)`. With binomial
  outcomes this is the Beta-Bernoulli conjugate: posterior Beta(α+k, β+n−k).
  A strategy only earns credibility by cumulative evidence, not by one
  lucky streak.
- **Role:** continuous, live performance monitoring (see 2.8/2.9); produces
  the "probability the edge is still alive" readout.

### 2.8 SPRT (Sequential Probability Ratio Test)
- Wald's sequential test of two hypotheses (edge ≥ θ vs edge ≤ 0): after
  each trade, accumulate the log-likelihood ratio; stop when it crosses
  accept/reject boundaries. Sequential design = the minimal expected sample
  to a decision; boundaries set the error rates (α, β).
- **Role:** live edge kill-switch — the Edge Monitor's decision rule for
  pausing/reversing a strategy (promote/demote with statistics instead of
  gut).

### 2.9 FDR (False Discovery Rate) control
- Benjamini-Hochberg: when testing many strategies/hypotheses at once,
  control the expected proportion of false positives among those declared
  significant (instead of per-test α). Keeps a research program honest when
  the Registry holds hundreds of claims.
- **Role:** portfolio-level filter across the strategy Registry.

### 2.10 Multiple-comparisons awareness (always)
- Deflated Sharpe ratio (Bailey & López de Prado) — the observed Sharpe
  adjusted for the number of trials performed; requires trials count N.
- **Role:** cheap sanity check, single number for a research summary.

## 3. Which methods become part of AI Trading Brain

| Method | Component | Priority |
|---|---|---|
| Walk-forward + beta benchmark + nullity | Research Data Platform (backtest engine) | P0 — fix trading-bot's pending hardening first |
| Bootstrap (block) | quant_research package | P0 |
| Permutation test | quant_research package | P0 |
| SPRT | Edge Monitoring | P1 (live kill-switch) |
| Bayesian updating (Beta-Binomial) | Edge Monitoring | P1 |
| FDR control (BH) | Registry / findings table | P1 |
| White's RC / SPA | promotion pipeline (decision) | P2 (research tool) |
| Deflated Sharpe | research summaries | P2 |
| Time-series CV | AI Decision Engine validation | P2 |

## 4. Promotion gates (the rules of the house)

1. **Backtest → Paper:** walk-forward OOS net of costs positive AND
   permutation p < 0.05 AND bootstrap CI for OOS Sharpe excludes 0.
2. **Paper → Live:** SPRT accept boundary crossed on live/paper trades
   (α=β=0.05) with minimum sample floor (e.g., ≥ 60 trades or ≥ 6 months),
   AND calibrated P(win) verified (reliability diagram within tolerance).
3. **Live → demotion/pause:** SPRT reject boundary, or realized performance
   below the Bayesian posterior credible bound for 2 consecutive review
   periods.
4. **Registry hygiene:** every claim enters the findings table with its
   full test battery; BH-FDR applied across the table each review cycle;
   claims that fail get lifecycle-transitioned (ADR-0002 style status flow).

## 5. Failure modes of this pipeline

- Overfitting the *validation procedure* itself (tuning test batteries on
  the same data — freeze procedures in the ADD before promoting anyone).
- SPRT boundaries too tight → premature demotion of genuinely edge-y
  strategies (regret asymmetry: prefer patience on live, strictness in
  backtest-to-paper).
- Survivorship/restatement bias in the raw data (doc 02: Yahoo restates
  silently; content-hashed snapshots mitigate).
- P-hacking via the permutation design (use fixed seeds, pre-registered
  procedures; the Registry is the pre-registration record).

## 6. Bottom line

The AI Trading Brain adopts **walk-forward + permutation + block bootstrap**
as the entry battery, **SPRT + Bayesian updating** as the live lifecycle
monitor, and **BH-FDR** as the portfolio-wide hygiene control. This is the
sequence that both protects capital and keeps the research loop honest —
and it directly upgrades trading-bot's existing walk-forward with the three
pending hardening items (beta benchmark, nullity test, robust selection
metric).
