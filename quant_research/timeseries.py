"""timeseries — time-series utilities: autocorrelation, Hurst exponent,
variance-ratio test, smoothing.

Phase 1 (Core Mathematics) time-series layer. Everything is numpy-only,
deterministic and operates on 1-D arrays ordered oldest-first.

What these tools answer in the research pipeline (docs/research/05):

- autocorrelation: does the edge persist from one bar to the next?
- Hurst exponent: is the series trending (H > 0.5), mean-reverting
  (H < 0.5) or a random walk (H ~ 0.5)?
- variance-ratio test: a formal test of the random-walk null;
  VR > 1 suggests positive serial dependence (trend), VR < 1 suggests
  negative dependence (mean reversion).
"""

import math
from typing import List

import numpy as np

from .core import drop_nan, required_length, rolling_sum
from .statistics import pearson_correlation


def autocorrelation(x: np.ndarray, lag: int = 1) -> float:
    """Pearson correlation of x[t] with x[t-lag]. The lag-1 value is the
    most common serial-dependence readout for return series."""
    x = drop_nan(x)
    required_length("autocorrelation", x, 2)
    if lag <= 0:
        raise ValueError("lag must be >= 1")
    if len(x) <= lag:
        return float("nan")
    return pearson_correlation(x[:-lag], x[lag:])


def autocorrelation_series(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Autocorrelations at lags 1..max_lag (correlogram)."""
    if max_lag < 1:
        raise ValueError("max_lag must be >= 1")
    return np.array([autocorrelation(x, lag) for lag in range(1, max_lag + 1)])


def hurst_exponent(x: np.ndarray, min_lag: int = 10, max_lag: int = 0) -> float:
    """Rescaled-range (R/S) Hurst exponent.

    For each lag L, split the series into non-overlapping chunks of
    length L, compute R/S per chunk (R = range of cumulative deviations
    from the chunk mean, S = chunk std), average, and regress
    log(R/S) ~ log(L). The slope is the Hurst exponent.

    Interpretation: H ~ 0.5 random walk; H > 0.5 persistent/trending;
    H < 0.5 anti-persistent/mean-reverting. For a pure linear trend the
    slope converges to 1.0.

    Numerical notes: lags are spaced geometrically between min_lag and
    n/2 so the regression covers decades of scale; chunks with S == 0
    (constant chunks) are dropped, and a lag is used only if at least
    two valid chunks remain.
    """
    x = drop_nan(x)
    n = len(x)
    required_length("hurst_exponent", x, 20)
    if min_lag < 4:
        raise ValueError("min_lag must be >= 4")
    if max_lag == 0:
        max_lag = n // 2
    if max_lag < min_lag:
        return float("nan")

    lags = sorted(set(int(round(l)) for l in np.geomspace(min_lag, max_lag, 24)))
    lags = [l for l in lags if n // l >= 2]

    log_lags: List[float] = []
    log_rs: List[float] = []
    for lag in lags:
        n_chunks = n // lag
        values = x[: n_chunks * lag].reshape(n_chunks, lag)
        deviations = np.cumsum(values - values.mean(axis=1, keepdims=True), axis=1)
        r = deviations.max(axis=1) - deviations.min(axis=1)
        s = values.std(axis=1, ddof=1)
        valid = s > 0.0
        if valid.sum() < 2:
            continue
        rs_mean = float(np.mean(r[valid] / s[valid]))
        if rs_mean <= 0.0 or not math.isfinite(rs_mean):
            continue
        log_lags.append(math.log(lag))
        log_rs.append(math.log(rs_mean))

    if len(log_lags) < 3:
        return float("nan")
    slope = np.polyfit(log_lags, log_rs, 1)[0]
    return float(slope)


def variance_ratio(returns: np.ndarray, q: int) -> float:
    """Lo-MacKinlay variance ratio: Var of q-period returns / (q * Var
    of 1-period returns). Under the random-walk null the ratio is 1;
    positive serial dependence pushes it above 1, negative below.
    Requires at least 2*q+2 observations to be meaningful."""
    returns = drop_nan(returns)
    n = len(returns)
    required_length("variance_ratio", returns, 2 * q + 2)
    if q < 2:
        raise ValueError("q must be >= 2")
    var_1 = float(np.var(returns, ddof=1))
    if var_1 == 0.0:
        return float("nan")
    q_returns = rolling_sum(returns, q)[q - 1:]
    var_q = float(np.var(q_returns, ddof=1))
    return var_q / (q * var_1)


def variance_ratio_zstat(returns: np.ndarray, q: int) -> float:
    """Homoskedastic z-statistic of the variance ratio (Lo-MacKinlay
    1988): z = (VR - 1) / sqrt(2(2q-1)(q-1) / (3q n)). |z| > 1.96
    rejects the random walk at 5%."""
    returns = drop_nan(returns)
    n = len(returns)
    vr = variance_ratio(returns, q)
    if vr != vr:
        return float("nan")
    se = math.sqrt(2.0 * (2.0 * q - 1.0) * (q - 1.0) / (3.0 * q * n))
    return (vr - 1.0) / se


def lagged_features(x: np.ndarray, lags: int) -> np.ndarray:
    """(n, lags+1) design matrix: column 0 is x[t], column k is x[t-k]
    (NaN-padded on the leading rows where the lag does not exist). The
    standard input layout for autocorrelation-based models."""
    x = np.asarray(x, dtype=float)
    if lags < 1:
        raise ValueError("lags must be >= 1")
    n = len(x)
    out = np.full((n, lags + 1), np.nan)
    out[:, 0] = x
    for k in range(1, lags + 1):
        out[k:, k] = x[:-k]
    return out
