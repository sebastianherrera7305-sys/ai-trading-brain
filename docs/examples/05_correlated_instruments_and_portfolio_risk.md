# Example 05 — Correlated Instruments: Portfolio Variance and Hedging

## Problem

A portfolio holds E-mini S&P 500 futures (ES) and E-mini Nasdaq futures
(NQ). They share a common factor but have their own idiosyncratic risk.

* How correlated are the two daily return series — and how much of the
  pairwise risk is shared?
* What is the variance of a 50/50 position, and how much does
  diversification actually buy?
* If we hedge NQ exposure with ES, what hedge ratio minimizes variance?
* How robust are the estimates to a single corrupted observation?

Why this matters: correlation drives position limits, margin
requirements, and hedging programs. Overestimating correlation
understates risk (a "diversified" book that is really one factor);
underestimating it produces unnecessary hedge costs. The covariance
matrix is the input to every risk model the platform will build in later
phases, and the rank-based check is the first line of defense against
corrupted data in the feed.

## Dataset

2,000 daily returns for each of two index futures, ES and NQ, generated
from a one-factor model (seed 99): a common market factor
N(0, 1), NQ = factor + N(0, 0.4), ES = 0.8 * factor + N(0, 0.4). The
construction makes the true ES-NQ correlation ~0.88 known in advance.
A later step deliberately corrupts a single observation (a -40-sigma
tick) to test estimator robustness to feed errors.

## Method

* **Pearson correlation** measures linear co-movement
  `rho = Cov(a, b) / (sd(a) * sd(b))`.
* **Spearman correlation** is the Pearson correlation of the *ranks*:
  it measures monotone (not just linear) association and is nearly
  immune to single outlying observations.
* **Covariance matrix** `Sigma` collects all pairwise covariances; a
  position vector `w` has variance `w' Sigma w`, which quantifies
  diversification: `w' Sigma w < sum_i w_i^2 var_i` whenever the assets
  are not perfectly correlated.
* **Minimum-variance hedge ratio**: hedging asset 2 with asset 1 at
  `h* = Cov(2,1) / Var(1)` minimizes the hedged variance
  `Var(2 - h* 1) = Var(2) (1 - rho^2)`.

## Code

```python
import numpy as np
from quant_research import statistics

rng = np.random.default_rng(99)
factor = rng.normal(0.0, 1.0, 2000)                  # shared market factor
nq = factor + rng.normal(0.0, 0.4, 2000)             # NQ: market + noise
es = 0.8 * factor + rng.normal(0.0, 0.4, 2000)       # ES: 0.8 market + noise
```

```python
# --- 1. Pairwise measures ------------------------------------------------
rho_p = statistics.pearson_correlation(nq, es)
rho_s = statistics.spearman_correlation(nq, es)
cov = statistics.covariance(nq, es)
assert abs(rho_p - 0.8267) < 1e-3 and abs(rho_s - 0.8178) < 1e-3
assert abs(cov - 0.7833) < 1e-3
print(f"Pearson {rho_p:.4f} | Spearman {rho_s:.4f} | covariance {cov:.4f}")
print(f"shared variance: {rho_p**2:.1%}  (R^2 of the linear relationship)")

# --- 2. Portfolio variance from the covariance matrix --------------------
covmat = statistics.covariance_matrix(np.column_stack([nq, es]))
assert covmat.shape == (2, 2)
assert abs(covmat[0, 0] - 1.1426) < 1e-3 and abs(covmat[1, 1] - 0.7858) < 1e-3
w = np.array([0.5, 0.5])
portfolio_var = float(w @ covmat @ w)
weighted_avg_var = float(np.array([0.5, 0.5]) @ np.diag(covmat))
print(f"50/50 portfolio variance: {portfolio_var:.4f} "
      f"(vs {weighted_avg_var:.4f} if no diversification)")
assert portfolio_var < weighted_avg_var          # diversification works
print(f"diversification benefit: {100 * (1 - portfolio_var / weighted_avg_var):.1f}% "
      f"variance reduction")

# --- 3. Minimum-variance hedge -------------------------------------------
h = statistics.covariance(es, nq) / statistics.variance(nq)
hedged = es - h * nq
var_es = statistics.variance(es)
var_hedged = statistics.variance(hedged)
assert abs(h - 0.6855) < 1e-3
assert var_hedged < 0.35 * var_es
print(f"hedge ratio h* = {h:.4f}  |  var(ES) {var_es:.4f} -> "
      f"var(ES - h* NQ) {var_hedged:.4f}  ({100 * (1 - var_hedged / var_es):.0f}% risk reduction)")
```

```python
# --- 4. Robustness: one corrupted observation ----------------------------
corrupt = nq.copy()
corrupt[1500] -= 40.0                              # bad tick (40 sigma)
rho_p_c = statistics.pearson_correlation(corrupt, es)
rho_s_c = statistics.spearman_correlation(corrupt, es)
print(f"after 1 corrupt tick: Pearson {rho_p_c:.4f}  Spearman {rho_s_c:.4f}")
assert abs(rho_s_c - rho_s) < 1e-3                 # ranks barely move
assert abs(rho_p_c - rho_p) > 0.1                  # Pearson badly biased
```

## Interpretation

* The pair is strongly, but not perfectly, correlated: R^2 = 68%. A
  naive "they're the same trade" assumption would ignore the 32% of
  variance that is idiosyncratic — and a naive "they're independent"
  assumption would miss the 68% shared factor.
* A 50/50 position has variance 0.874 vs 0.964 without diversification:
  a 9% variance reduction. Real diversification here is modest *because*
  the correlation is 0.83 — this is the honest number risk committees
  need when deciding whether two legs of a book can be netted.
* The minimum-variance hedge ratio is 0.685 NQ-contracts per ES-contract
  and removes 68% of the ES variance. The residual (32%) is the
  idiosyncratic risk that no linear hedge can remove — it is the lower
  bound on what any hedging program can achieve with this instrument
  pair.
* One 40-sigma corrupt tick shifts Pearson from 0.83 to 0.64 (−23%!),
  while Spearman is unchanged to three decimals. In production, rank
  correlation is the *default* sanity check on a pair, and Pearson is
  used only after cleaning; `drop_nan` / outlier guards (Example 03)
  run before any Pearson number is quoted.

## Limitations

* Correlation is not constant: it rises in crises (the "correlation
  goes to one" effect), so a historical 0.83 underestimates
  stress-period co-movement. Re-estimate on rolling windows
  (Example 02) and stress-test with the crisis regimes.
* The covariance matrix here is a plain sample estimate; for wider
  universes the sample matrix is noisy and needs shrinkage — a Phase 3
  concern, but the API (`covariance_matrix`) is already the stable input.
* Spearman robustness protects against *single* gross errors; it does
  not protect against systematic mispricing or missing observations.
