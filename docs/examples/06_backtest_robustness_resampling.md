# Example 06 — Backtest Robustness: Bootstrap, Reality Check, and Deflated Sharpe

## Research question

A quant desk searched 40 strategy variants on the same five years of data
(750 trades each) and the best one reports an annualized Sharpe of 1.9
(per-trade Sharpe 0.12). How much of that number is luck?

* What is the sampling distribution of the Sharpe ratio — a confidence
  interval that respects return dependence?
* Given that we *tried 40 variants*, is the best result still
  significant? (White's Reality Check)
* What is the probability that the best Sharpe is a false positive after
  correcting for both multiple trials *and* return non-normality?
  (Deflated Sharpe Ratio)

## Mathematical approach

* **Block bootstrap** (`block_bootstrap`, `bootstrap_confidence_interval`)
  resamples contiguous blocks of observations, preserving the
  autocorrelation structure that an iid bootstrap would destroy.
  `stationary_bootstrap` uses geometrically-sized blocks (Politis &
  Romano 1994). Both feed any statistic via the `statistic=` argument.
* **White's Reality Check** (`reality_check_p_value`): takes the
  (n_trials, n_obs) matrix of trial performances, recenters every trial
  by its own mean (the null: *no* trial has edge), resamples
  observation indices jointly across trials (preserving cross-trial
  dependence), and returns the fraction of resampled "best trial means"
  that reach the observed best. Small p-value = the best of many
  variants is unlikely to be luck.
* **Deflated Sharpe Ratio** (`deflated_sharpe_ratio`, Bailey & López de
  Prado 2014): `DSR = Phi((SR* - E[max SR]) * sqrt(T - 1) / sqrt(1 -
  gamma3*SR* + (gamma4 - 1)/4 * SR*^2))` — it discounts the best Sharpe
  by the *expected maximum* over the trial count and by the
  skewness/kurtosis of returns. Inputs are **per-period** Sharpe ratios
  and the per-period observation count.

## Why this matters

The expected best Sharpe of 40 pure-noise strategies is substantial:
`E[max]` grows with the number of trials, so "best of 40" is not
evidence. Every backtest report that ignores this overstates its edge by
construction — this is the single most common cause of allocator losses
in systematic strategies.

## Code

```python
import numpy as np
from quant_research import resampling

def ann_sharpe(x):
    return x.mean() / x.std(ddof=1) * np.sqrt(252) if x.std(ddof=1) > 0 else 0.0

rng = np.random.default_rng(21)
daily = rng.normal(0.0006, 0.011, 1258)            # 5y daily strategy returns
```

```python
# --- 1. Dependence-aware Sharpe distribution ------------------------------
bb = resampling.block_bootstrap(daily, block_size=21, n_bootstrap=500, seed=0, statistic=ann_sharpe)
sb = resampling.stationary_bootstrap(daily, mean_block_length=21.0, n_bootstrap=500, seed=0, statistic=ann_sharpe)
lo5, hi95 = np.percentile(bb, 5), np.percentile(bb, 95)
assert 1.0 < float(bb.mean()) < 1.6 and 0.4 < lo5 < hi95
print(f"block bootstrap of annualized Sharpe: mean {bb.mean():.2f}, "
      f"90% range [{lo5:.2f}, {hi95:.2f}]")
print(f"stationary bootstrap: mean {sb.mean():.2f}, "
      f"90% range [{np.percentile(sb, 5):.2f}, {np.percentile(sb, 95):.2f}]")
assert abs(float(sb.mean()) - float(bb.mean())) < 0.4   # similar center

bci_mean, bci_lo, bci_hi = resampling.bootstrap_confidence_interval(
    daily, block_size=21, n_bootstrap=500, seed=0, statistic=ann_sharpe
)
print(f"bootstrap 95% CI for annualized Sharpe: [{bci_lo:.2f}, {bci_hi:.2f}]")
assert bci_lo > 0.3 and bci_hi > 1.5
```

```python
# --- 2. The multiple-testing problem: 40 trials ---------------------------
T, n_trials = 750, 40

# Scenario A: 40 pure-noise strategies (no edge anywhere)
rng3 = np.random.default_rng(11)
noise = np.column_stack([rng3.normal(0.0, 0.006, T) for _ in range(n_trials)])
per_a = noise.mean(axis=0) / noise.std(axis=0)      # per-trade SRs
best_a = float(per_a.max())
p_a = resampling.reality_check_p_value(noise.T, block_size=1, n_bootstrap=500, seed=0)
dsr_a = resampling.deflated_sharpe_ratio(best_a, per_a, T)
assert best_a > 0.05 and p_a > 0.05 and dsr_a < 0.7
print(f"Scenario A (noise): best per-trade SR {best_a:.3f} | "
      f"Reality Check p = {p_a:.2f} | DSR = {dsr_a:.2f}")

# Scenario B: same, but one strategy has a genuine per-trade SR of 0.15
rng2 = np.random.default_rng(17)
noise_b = np.column_stack([rng2.normal(0.0, 0.006, T) for _ in range(n_trials - 1)])
z = rng2.normal(0.0, 1.0, T); z = (z - z.mean()) / z.std()
genuine = 0.0009 + 0.006 * z                        # exact per-trade SR 0.15
all_trials = np.column_stack([noise_b, genuine])
per_b = all_trials.mean(axis=0) / all_trials.std(axis=0)
best_b = float(per_b.max())
p_b = resampling.reality_check_p_value(all_trials.T, block_size=1, n_bootstrap=500, seed=0)
dsr_b = resampling.deflated_sharpe_ratio(best_b, per_b, T)
assert best_b > 0.1 and p_b < 0.05 and dsr_b > 0.85
print(f"Scenario B (genuine edge): best per-trade SR {best_b:.3f} | "
      f"Reality Check p = {p_b:.3f} | DSR = {dsr_b:.2f}")
```

```python
# --- 3. Confidence interval on the genuine strategy's per-trade mean ------
m, lo, hi = resampling.bootstrap_confidence_interval(
    genuine, block_size=1, n_bootstrap=500, seed=0
)
assert abs(m - 0.0009) < 1e-6 and lo < 0.0009 < hi
print(f"per-trade mean {m:.6f}, 95% CI [{lo:.6f}, {hi:.6f}]")
print(f"annualized equivalent: Sharpe CI "
      f"[{lo / genuine.std(ddof=1) * np.sqrt(750):.3f}, "
      f"{hi / genuine.std(ddof=1) * np.sqrt(750):.3f}] per year")
```

## Interpretation

* The block and stationary bootstraps give an honest 90% range for the
  annualized Sharpe — roughly [0.6, 2.1] — far wider than the naive
  `sharpe_standard_error` band (Example 03), because the block size 21
  preserves month-scale dependence. Never quote a Sharpe without its
  dependence-aware range.
* Scenario A is the punchline: the **best of 40 noise strategies** shows
  a per-trade Sharpe of 0.079 — it would look like a real 1.9 annualized
  Sharpe if reported alone. The Reality Check says p = 0.41 (consistent
  with pure luck) and the DSR is 0.49 (a coin flip). A desk quoting
  only the raw best-of-40 number is quoting noise.
* Scenario B: the genuine strategy (per-trade SR 0.15) survives the
  Reality Check (p = 0.002) and earns DSR = 0.91. Note that even a
  strong edge loses ~9% probability to the 40-trial deflation — the
  correction is expensive, and it should be: the search was expensive.
* `bootstrap_confidence_interval` on the per-trade mean confirms the
  edge is positive at the 95% level (CI [0.00045, 0.00132]).

## Limitations

* The Reality Check recenters *every* trial by its own mean; it tests
  "best is no better than the null", but a model family with many
  *correlated* variants inflates the null max more than the test's
  joint resampling fully captures. Report it together with the DSR.
* The DSR assumes the expected maximum is computable from the trial
  distribution (its `skewness`/`kurtosis` arguments let you adjust for
  non-normality; pass them when returns are fat-tailed). With no
  arguments it is the standard-normal version.
* Block size is a choice: too small ignores dependence (overstated
  significance), too large wastes power. For daily returns ~21 trading
  days is the usual starting point; for trade-level data use
  `block_size=1` when trades are approximately independent.
* Both methods answer "is the *best reported* number credible?" — they
  do not tell you which strategy is best, and they cannot rescue a
  strategy from a broken research design (look-ahead, survivorship).
