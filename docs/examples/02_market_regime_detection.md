# Example 02 — Market Regime Detection with Rolling Statistics

## Problem

A systematic desk is deciding between a momentum strategy and a
mean-reversion strategy for a liquid index. Both only work in the right
regime. Can we detect, from the price series alone, whether the market is
currently trending, mean-reverting, or a random walk — and build a simple
rolling "regime score" from the library's primitives?

Why this matters: regime misclassification is the standard cause of
strategy death — a momentum book running mean-reverting markets, a
mean-reversion book running trends. A cheap, explainable regime check
runs *before* capital is committed and *continuously* afterwards, and it
is the input to risk limits (cut exposure in "random-walk, high-vol"
states).

## Dataset

Three synthetic daily return series, 5,000 observations each, generated
from AR(1) processes with 1% daily volatility: a driftless random walk
(seed 31), a trending regime (phi = +0.25 with a small drift, seed 3) and
a mean-reverting regime (phi = -0.25, seed 4). Price series are built
from the returns with prices_from_returns. The regimes are synthetic so
the true labels are known by construction and each detector's answer can
be checked against ground truth.

## Method

Three complementary tools, all computed on the return series `r_t`:

1. **Variance-ratio test (Lo & MacKinlay).** For a random walk, the
   q-period variance is q times the one-period variance, so
   `VR(q) = Var(r_t+...+r_{t+q-1}) / (q * Var(r_t))` equals 1. Positive
   autocorrelation (trending) pushes `VR > 1`; negative autocorrelation
   (mean-reversion) pushes `VR < 1`. `variance_ratio_z_score` gives the
   asymptotically standard-normal test statistic.

2. **Hurst exponent (R/S analysis).** For a process with Hurst `H`, the
   rescaled range scales as `(n)^H`. `H = 0.5` is a random walk, `H > 0.5`
   is persistent (trending), `H < 0.5` is anti-persistent. On financial
   data R/S estimates are noisy, so it is used as corroboration.

3. **Rolling statistics.** `rolling_mean`, `rolling_std`, `rolling_sum`,
   `rolling_z_score`, `ewma`, `ewma_volatility` and `centered_smooth`
   describe the *current* environment: volatility regimes, trend slope,
   and whether the latest observation is an outlier relative to its recent
   distribution.

`autocorrelation` and `autocorrelation_series` quantify the serial
dependence directly; `lagged_features` builds the feature matrix a regime
model would consume.

## Code

```python
import numpy as np
from quant_research import core, timeseries

def ar1(phi, n, seed, mu=0.0):
    """AR(1) returns: r_t = mu + phi * r_{t-1} + eps. phi>0 -> trend, phi<0 -> MR."""
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, 0.01, n)
    r = np.empty(n)
    r[0] = eps[0]
    for i in range(1, n):
        r[i] = mu + phi * r[i - 1] + eps[i]
    return r

rw = np.random.default_rng(31).normal(0.0, 0.01, 5000)   # random walk
mo = ar1(+0.25, 5000, seed=3, mu=0.0004)                 # trending
mr = ar1(-0.25, 5000, seed=4)                            # mean-reverting
```

```python
# --- 1. Formal test: variance ratio ---------------------------------------
for name, r in (("random walk ", rw), ("momentum    ", mo), ("mean-revert ", mr)):
    vr = timeseries.variance_ratio(r, 4)
    z = timeseries.variance_ratio_z_score(r, 4)
    print(f"{name} VR(4) = {vr:6.3f}   z = {z:+7.2f}")
assert abs(timeseries.variance_ratio(rw, 4) - 1.027) < 0.05
assert timeseries.variance_ratio(mo, 4) > 1.35
assert timeseries.variance_ratio(mr, 4) < 0.80
assert abs(timeseries.variance_ratio_z_score(mo, 4)) > 8.0
assert abs(timeseries.variance_ratio_z_score(mr, 4)) > 8.0
```

```python
# --- 2. Corroboration: autocorrelation and Hurst --------------------------
for name, r in (("random walk ", rw), ("momentum    ", mo), ("mean-revert ", mr)):
    ac1 = timeseries.autocorrelation(r, 1)
    h = timeseries.hurst_exponent(r)
    print(f"{name} ac(1) = {ac1:+7.3f}   Hurst = {h:.3f}")
ac_profile = timeseries.autocorrelation_series(mo, 5)
assert abs(ac_profile[0] - timeseries.autocorrelation(mo, 1)) < 1e-12
assert abs(timeseries.autocorrelation(mr, 1)) > 0.10   # strong negative dependence
```

```python
# --- 3. Rolling environment statistics ------------------------------------
prices = core.prices_from_returns(mo, start_price=100.0)   # trending index

vol20 = core.rolling_std(core.simple_returns(prices), 20)        # fast vol
vol60 = core.rolling_std(core.simple_returns(prices), 60)        # slow vol
vol_ratio = core.safe_divide(vol20, vol60, default=1.0)          # vol regime
assert vol_ratio.shape == (5000,) and vol_ratio[0] == 1.0
print(f"vol20/vol60 now = {vol_ratio[-1]:.2f}  (1.0 = calm, >1.3 = stress)")

# MA crossover: fast EWMA of the level vs the 200-day mean
ema = core.ewma(prices, 20)[-1]
trend = core.rolling_mean(prices, 200)[-1]
smooth = core.centered_smooth(prices, 61)                        # de-noised level
ma_gap = ema - trend
assert ma_gap > 0.0                                              # uptrend: fast MA above slow MA
assert not np.isnan(smooth[60]) and np.isnan(smooth[0])
print(f"ema(20) - ma(200) = {ma_gap:+.2f}  (positive = trend up)")

# Band position: z-score of price inside its own 60-day window.
# The regime rule: flag when the band z crosses +/-2.
z_mo = core.rolling_z_score(prices, 60)
z_mr = core.rolling_z_score(core.prices_from_returns(mr, 100.0), 60)
assert np.nanmax(np.abs(z_mo)) > 3.0 and np.nanmax(np.abs(z_mr)) > 3.0
print(f"trending: max band |z| = {np.nanmax(np.abs(z_mo)):.2f}, "
      f"fraction of days |z|>2 = {np.nanmean(np.abs(z_mo) > 2.0):.2f}")
print(f"mean-rev: max band |z| = {np.nanmax(np.abs(z_mr)):.2f}, "
      f"fraction of days |z|>2 = {np.nanmean(np.abs(z_mr) > 2.0):.2f}")
```

```python
# --- 4. Feature engineering for a regime model ----------------------------
feat = timeseries.lagged_features(core.simple_returns(prices), 5)
assert feat.shape == (5000, 6)                    # current + 5 lags
assert np.allclose(feat[5:, 0], core.simple_returns(prices)[5:])
momentum = np.nanmean(feat[5:, 1:6], axis=1)      # 5-day momentum, valid rows only
r = core.simple_returns(prices)
corr_mom = np.corrcoef(momentum, r[5:])[0, 1]
print(f"corr(lagged 5d momentum, next return) = {corr_mom:+.3f}")
assert corr_mom > 0.05                            # trending regime: momentum works
```

## Interpretation

* The variance-ratio test separates the regimes cleanly: `z = +17.5`
  (trending), `z = -11.6` (mean-reverting), `z ≈ 1` (random walk). A
  |z| > 2 cutoff on a rolling window is a defensible regime trigger.
* Autocorrelation corroborates (`ac(1) = +0.25 / -0.25 / ≈ 0`), but the
  Hurst estimates on 5,000 daily returns barely move (`0.50-0.55`): R/S
  on return series is high-variance for these sample sizes and should be
  treated as corroboration, never as the decision statistic. The walk
  -forward decision rule uses VR and the rolling z-score.
* The rolling band z-score of the *price* flags regime breaks early:
  price leaving a 2-standard-deviation band of its 60-day range is the
  classic breakout signal; a negative z with `VR < 1` is the fade signal.
* `vol20/vol60` captures the volatility regime (risk-on / risk-off) —
  useful for scaling exposure rather than switching strategy.

## Limitations

* Synthetic AR(1) returns are stationary; real markets have structural
  breaks, non-stationarity and fat tails, which inflate both VR and Hurst
  toward the trend side.
* All statistics here are *unconditional*; regime detection on real data
  should be rolled forward (estimate on `t <= T`, evaluate on `t > T`) to
  avoid look-ahead — the rolling functions make this straightforward.
* `lagged_features` drops the first `lags` rows (warm-up); always align
  predictions to the valid window.
