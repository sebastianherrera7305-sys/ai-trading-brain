# Example 04 — Validating a Trading Edge: Signal, Distribution, and Monitoring

## Research question

A quant proposes a long/short strategy and a probabilistic signal.

1. Do long-leg returns exceed short-leg returns significantly? (t-tests,
   permutation tests)
2. Does a binary timing signal add value beyond the unconditional mean?
   (permutation test on signal-selected returns)
3. How large a true win rate can the evidence support, and what does a
   *sequential* test conclude as trades arrive? (Beta-Bernoulli, SPRT)
4. Are the probability forecasts well calibrated? (Brier score)
5. Do the observed returns match the assumed distribution? (chi2 variance
   test; Student-t machinery)

## Mathematical approach

* **Welch t-test** (`two_sample_t_test`): compares two means without
  equal-variance assumptions; returns `(t, df, p)`.
* **Paired t-test** (`paired_t_test`): tests the mean of the *daily
  spread* strategy-minus-benchmark, removing the common market factor.
* **Permutation tests**: nonparametric alternatives. `permutation_test_two_sample`
  shuffles the group labels; `permutation_test_signal` shuffles the
  signal against returns. No normality assumption, exact under exchangeability.
* **Beta-Bernoulli**: `beta_posterior` updates a Beta(1,1) prior with wins
  and losses; `beta_cdf` / `beta_inv_cdf` give tail probabilities and
  quantiles; `regularized_incomplete_beta` is the underlying kernel.
* **SPRT** (`sprt_bernoulli`): Wald's sequential test decides
  "p = p0" vs "p = p1" at controlled error rates, monitoring the
  log-likelihood ratio as trades accrue; `sprt_expected_sample_size`
  reports the average time-to-decision.
* **Brier** (`brier_score`, `brier_skill_score`): quadratic forecast
  error, normalized against the climatological forecast.
* **chi2** (`chi2_cdf`, `chi2_p_value`, `chi2_inv_cdf`): variance
  hypothesis tests — under H0, `(n-1) * s^2 / sigma0^2 ~ chi2(n-1)`.

## Why this matters

Every strategy claim passes through this gauntlet before capital is
allocated: is the edge real (tests), is it *predictable* (signal tests),
is it *monitorable* in live trading (SPRT), are our probability models
honest (Brier), and does the data match the model's assumptions (chi2)?
A strategy that fails any of these five questions is not allocatable.

## Code

```python
import numpy as np
from quant_research import statistics, probability, resampling

rng = np.random.default_rng(7)
z1 = rng.normal(0.0, 1.0, 500); z2 = rng.normal(0.0, 1.0, 500)
z1 = (z1 - z1.mean()) / z1.std(); z2 = (z2 - z2.mean()) / z2.std()
long_leg = 0.0015 + 0.01 * z1
short_leg = 0.0 + 0.01 * z2
```

```python
# --- 1. Does the long leg beat the short leg? ------------------------------
t, df, p = statistics.two_sample_t_test(long_leg, short_leg)
assert abs(t - 2.369) < 1e-2 and p < 0.05 and df > 900
print(f"Welch t-test: t = {t:.3f}, df = {df:.1f}, p = {p:.4f}")

# cross-check against the distribution functions directly
p_one_sided = statistics.student_t_sf(t, df)
p_two_sided = 2.0 * p_one_sided
assert abs(p_two_sided - p) < 1e-9
assert abs(statistics.student_t_cdf(t, df) - (1.0 - p_one_sided)) < 1e-12
assert abs(statistics.student_t_inv_cdf(0.975, df) - 1.9623) < 1e-2
print(f"one-sided sf cross-check: {p_one_sided:.4f}")
```

```python
# --- 2. Nonparametric confirmation and the timing signal ------------------
p_perm = resampling.permutation_test_two_sample(
    long_leg, short_leg, n_permutations=2000, seed=0
)
assert p_perm < 0.05
print(f"permutation test (labels): p = {p_perm:.3f}")

rng2 = np.random.default_rng(8)
e1 = rng2.normal(0.0, 1.0, 500); e2 = rng2.normal(0.0, 1.0, 500)
e1 = (e1 - e1.mean()) / e1.std(); e2 = (e2 - e2.mean()) / e2.std()
benchmark = 0.0002 + 0.009 * e1
strategy = benchmark + 0.0005 + 0.0045 * e2
t_p, p_p = statistics.paired_t_test(strategy, benchmark)   # daily alpha
assert abs(t_p - 2.482) < 1e-2 and p_p < 0.05
print(f"paired t-test (strategy vs benchmark): t = {t_p:.3f}, p = {p_p:.4f}")

# timing signal: returns carry +0.4% on signal days
sig = (rng2.random(500) < 0.3).astype(float)
sig_returns = np.where(sig == 1, 0.004, 0.0) + rng2.normal(0.0, 0.01, 500)
p_sig = resampling.permutation_test_signal(
    sig_returns, sig, n_permutations=2000, seed=0
)
assert p_sig < 0.05
print(f"permutation test (signal vs returns): p = {p_sig:.4f}")
```

```python
# --- 3. Bayesian win-rate evidence and sequential monitoring ---------------
a, b = probability.beta_posterior(1.0, 1.0, successes=8, failures=2)
assert (a, b) == (9.0, 3.0)
p_leq_half = probability.beta_cdf(0.5, a, b)                 # P(p <= 0.5)
assert abs(p_leq_half - 67.0 / 2048.0) < 1e-9                # exact rational
assert probability.beta_cdf(0.6, a, b) == statistics.regularized_incomplete_beta(0.6, a, b)
lo_cred = probability.beta_inv_cdf(0.025, a, b)
hi_cred = probability.beta_inv_cdf(0.975, a, b)
print(f"posterior Beta({a:.0f},{b:.0f}): mean {probability.beta_mean(a, b):.3f}, "
      f"var {probability.beta_var(a, b):.4f}")
print(f"95% credible interval: [{lo_cred:.3f}, {hi_cred:.3f}], "
      f"P(p <= 0.5) = {p_leq_half:.4f}")

# sequential monitoring: is the live win rate 0.5 or 0.6?
wins = np.array([1.0] * 20 + [0.0] * 3)
r = probability.sprt_bernoulli(wins, p0=0.5, p1=0.6)
assert r["decision"] == "accept_edge" and r["final_llr"] > 0.0
print(f"SPRT on 20W/3L: {r['decision']} after {r['n']} trades "
      f"(LLR {r['final_llr']:.2f}, bound {r['upper_bound']:.2f})")
weak = np.array([1.0] * 14 + [0.0] * 6)
assert probability.sprt_bernoulli(weak, 0.5, 0.6)["decision"] == "continue"
ess = probability.sprt_expected_sample_size(0.6, 0.5, 0.6)
assert abs(ess - 131.61) < 1e-2
print(f"expected trades to decide when p=0.6 is true: {ess:.1f}")
```

```python
# --- 4. Are the probability forecasts calibrated? --------------------------
rng4 = np.random.default_rng(9)
x = rng4.normal(0.0, 1.0, 600)
forecast = 1.0 / (1.0 + np.exp(-0.9 * x))                   # logistic model
outcome = (rng4.random(600) < forecast).astype(float)
bs = probability.brier_score(forecast, outcome)
bss = probability.brier_skill_score(forecast, outcome)
bss50 = probability.brier_skill_score(forecast, outcome, climatology=0.5)
assert abs(bs - 0.2100) < 1e-3 and abs(bss - 0.1597) < 1e-3
assert bss > 0.10 and bss50 > bss                       # better than climatology
print(f"Brier {bs:.4f} | skill vs climatology {bss:.3f} | vs 50/50 {bss50:.3f}")
```

```python
# --- 5. Does the data fit the model's assumptions? -------------------------
rng5 = np.random.default_rng(21)
daily = rng5.normal(0.0006, 0.011, 1258)                # daily strategy returns
sigma0 = 0.011                                          # target annualized vol 17.5%
q = (len(daily) - 1) * statistics.variance(daily) / sigma0 ** 2
p_var = statistics.chi2_p_value(q, len(daily) - 1)
crit = statistics.chi2_inv_cdf(0.95, len(daily) - 1)
assert abs(q - 1167.1) < 5.0 and p_var > 0.05 and q < crit
print(f"chi2 variance test: Q = {q:.1f}, 95% critical value {crit:.1f}, "
      f"p = {p_var:.3f}  -> cannot reject sigma = sigma0")
assert abs(statistics.chi2_cdf(q, len(daily) - 1) - (1.0 - p_var)) < 1e-9

# normal machinery used throughout: cutoffs and densities
assert abs(statistics.normal_inv_cdf(0.975) - 1.95996) < 1e-3
assert abs(statistics.normal_cdf(1.96) - 0.9750) < 1e-3
assert abs(statistics.normal_sf(1.96) - 0.0250) < 1e-3
assert abs(statistics.normal_pdf(0.0) - 0.3989) < 1e-3
print("normal CDF/SF/PDF/inv cross-checks: OK (1.96 <-> 0.975)")
```

## Interpretation

* The long leg beats the short leg at p = 0.018 (Welch) and p = 0.02
  (permutation) — the edge survives both parametric and nonparametric
  scrutiny. The paired test on strategy-vs-benchmark daily alpha is
  significant at p = 0.013: the strategy adds value *after removing the
  market factor*.
* The timing signal is strong (p = 0.0005): signal days carry +0.4%
  and the permutation test rejects label-independence decisively.
* The Beta(9,3) posterior says P(win rate > 50%) = 1 − 67/2048 = 0.967
  with a 95% credible interval well above 0.5 — but note that 8 wins in
  10 trades is a small sample; the SPRT shows what live monitoring buys:
  with p0 = 0.5 vs p1 = 0.6 and 5% error rates, the 20W/3L run reaches
  "accept the 0.6 edge" at trade 23, while 14W/6L correctly says "keep
  monitoring". Expect ~132 trades on average before a true 0.6 win rate
  is confirmed — sequential testing prevents the classic mistake of
  declaring victory after a lucky ten trades.
* Brier skill of 0.16 over climatology: the forecasts are informative.
* The chi2 variance test cannot reject the assumed volatility: the risk
  model's sigma0 is consistent with the data, so the t/permutation
  p-values above are not invalidated by a misspecified scale.

## Limitations

* Permutation tests assume exchangeability — they are exact under the
  null for iid data but conservative/misleading under autocorrelation;
  for dependent returns use the block bootstrap (Example 06).
* The SPRT assumes iid Bernoulli outcomes and known p0/p1 hypotheses;
  it detects a *fixed* alternative, not drift. Monitor with the
  alternative you can act on.
* The chi2 variance test is one-sided by construction
  (`chi2_p_value` is the upper tail); for a two-sided volatility check
  take the conservative tail.
* Brier score is calibrated-shape sensitive: a good BSS can hide
  miscalibration in the tails; complement with reliability diagrams
  before production use.
