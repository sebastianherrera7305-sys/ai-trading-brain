# Example 03 — Equity Curve, Return Distribution, and Drawdown Analytics

## Research question

A strategy produced five years of simulated daily P&L (1,258 trading days)
on a $100,000 book.

* What did the equity curve look like, and what was the worst drawdown?
* What are the annualized Sharpe ratio and its sampling error?
* Are the returns normal enough for mean-variance statistics to be
  trusted, or do fat tails matter?
* What is a defensible confidence interval for the average daily return?

## Mathematical approach

* **Return conventions.** `simple_returns` and `log_returns` convert a
  price series; `cumulative_returns` compounds daily returns into an
  equity curve; `prices_from_returns` converts back to a capital line.
* **Drawdown.** `drawdown_prices` computes the peak-to-trough decline as
  a fraction: `DD_t = (P_t - max_{s<=t} P_s) / max_{s<=t} P_s`. Maximum
  drawdown is the minimum of that path.
* **Sharpe ratio.** Per-period `mean / std` (annualized by sqrt(252));
  `sharpe_standard_error` gives the Lo (2002) sampling error
  `se = sqrt((1 + SR^2/2) / (n - 1))`.
* **Distribution diagnostics.** `skewness`, `excess_kurtosis` and the
  Jarque-Bera test check normality; `empirical_cdf` reads off tail
  probabilities directly; `variance` and `coefficient_of_variation`
  measure dispersion.
* **Confidence intervals.** `mean_confidence_interval` assumes normality
  (Student-t), while `bootstrap_confidence_interval` (block bootstrap)
  does not — the comparison tells us whether normality is a safe
  assumption for this return series.

## Why this matters

The drawdown number is what risk committees quote: "this strategy lost
X% at its worst". The Sharpe *estimate* is useless without its standard
error — a 0.44 Sharpe measured over five years is compatible with a very
different true Sharpe. And the normality check decides whether Gaussian
statistics (VaR, mean-variance) are even admissible for this book.

## Code

```python
import numpy as np
from quant_research import core, statistics, resampling

rng = np.random.default_rng(21)
daily = rng.normal(0.0006, 0.011, 1258)          # 5y of daily P&L (simulated)
core.required_length("daily", daily, 250)         # guard: need >= 1y
prices = core.prices_from_returns(daily, start_price=100_000.0)
```

```python
# --- 1. Equity curve and drawdown -----------------------------------------
equity = core.cumulative_returns(daily)
dd = core.drawdown_prices(equity)
max_dd = float(dd.min())
final_eq = float(equity[-1])
assert max_dd < -0.20 and final_eq > 2.0
print(f"5y growth factor: {final_eq:.2f}x   max drawdown: {max_dd:.1%}")
print(f"ending capital: ${prices[-1]:,.0f}")

# log vs simple returns: identical for small daily moves, differ in tails.
# Both return length-n arrays with r_0 = NaN (aligned to prices).
lr, sr = core.log_returns(prices), core.simple_returns(prices)
assert np.isnan(lr[0]) and np.isnan(sr[0])
max_gap = float(np.nanmax(np.abs(lr - sr)))
assert max_gap < 1e-3
print(f"max |log - simple| return gap: {max_gap:.2e} (daily scale: negligible)")
```

```python
# --- 2. Sharpe ratio and sampling error -----------------------------------
mean_d = float(daily.mean())
sd_d = np.sqrt(statistics.variance(daily))
sharpe_ann = (mean_d / sd_d) * np.sqrt(252)
se = statistics.sharpe_standard_error(sharpe_ann, len(daily))
assert 1.0 < sharpe_ann < 1.4 and 0.03 < se < 0.05
print(f"annualized Sharpe: {sharpe_ann:.2f}  +/- {se:.3f} (1 sd)")

# coefficient of variation: risk per unit of return (daily)
cv = statistics.coefficient_of_variation(daily)
assert cv > 10.0                                   # unit-return carries ~13x risk
print(f"daily coefficient of variation: {cv:.1f}")
```

```python
# --- 3. Distribution diagnostics ------------------------------------------
sk = statistics.skewness(daily)
ek = statistics.excess_kurtosis(daily)
jb, jb_p = statistics.jarque_bera(daily)
print(f"skewness {sk:+.3f}, excess kurtosis {ek:+.3f}, JB p-value {jb_p:.3f}")
assert abs(sk) < 0.15 and abs(ek) < 0.3 and jb_p > 0.05   # Gaussian-ish here

# Tail read-off: probability of a -2% day from the empirical distribution
p_neg2 = float(statistics.empirical_cdf(daily, np.array([-0.02]))[0])
p_norm = statistics.normal_cdf(-0.02 / 0.011)          # theoretical
print(f"P(day < -2%): empirical {p_neg2:.3f} vs normal {p_norm:.3f}")
```

```python
# --- 4. Confidence intervals: parametric vs bootstrap ---------------------
t_lo, t_hi = statistics.mean_confidence_interval(daily)[1:3]
b_lo, b_hi = resampling.bootstrap_confidence_interval(
    daily, block_size=10, n_bootstrap=300, seed=0
)[1:3]
print(f"t CI:        [{t_lo:+.5f}, {t_hi:+.5f}]")
print(f"bootstrap CI [{b_lo:+.5f}, {b_hi:+.5f}]")
assert abs(t_lo - 0.000214) < 5e-5 and abs(b_lo - 0.000243) < 5e-5
assert t_hi > 0.0013 and b_hi > 0.0013                       # mean is positive
```

```python
# --- 5. Utility helpers in a real pipeline --------------------------------
# drop_nan: a real data pipeline contains gaps (holidays, outages)
padded = np.array([np.nan, 0.0012, 0.0007, -0.0003])
clean = core.drop_nan(padded)
assert len(clean) == 3 and np.all(clean == padded[1:])
# safe_divide: annualized vol without division-by-zero blowups
vol_ann = core.safe_divide(np.array([sd_d]), np.array([1.0]))[0] * np.sqrt(252)
print(f"annualized vol (safe_divide): {vol_ann:.2%}")
```

## Interpretation

* Five years of a 1.20 Sharpe strategy grew capital 2.5x but gave back
  26.6% from peak to trough. The drawdown is the risk number: it implies
  the position sizing (Example 01) must survive a 27% equity shock, or
  the book is overlevered.
* The Sharpe standard error (±0.037) is small at this sample size — but
  that is the *sampling* error, not the model error. The estimate is
  stable *if* the regime persists (it rarely does).
* The returns are consistent with normality here (JB p = 0.83), so
  Gaussian CI and mean-variance tools are admissible for this series.
  Real strategy returns usually have fat tails — always re-run section 3
  before trusting Gaussian statistics.
* The bootstrap CI (block size 10, dependence-aware) agrees with the
  Student-t CI to the fourth decimal: for this series normality is not
  doing any work. When they disagree, the bootstrap wins.
* `drop_nan`, `safe_divide` and `required_length` are the pipeline glue:
  every production signal chain should validate and clean before any
  statistic is computed.

## Limitations

* Drawdown depends on the entire path, so its estimate is path-dependent
  and one sample long; a bootstrap over drawdown (block resampling of
  returns, then recompute) gives a range for the max drawdown.
* The Sharpe standard error assumes iid returns; daily momentum/vol
  clustering inflates the true error — `sharpe_standard_error` is a
  lower bound on uncertainty for autocorrelated strategies.
* All numbers here are on a single simulated path. The honest practice is
  to repeat the analysis across market regimes (Example 02) and to deflate
  the result for the number of strategies tried (Example 06).
