"""timeseries — time-series utilities: autocorrelation, Hurst exponent,
variance-ratio test, lagged features.

Phase 1 (Core Mathematics) time-series layer. Everything is numpy-only,
deterministic and operates on 1-D arrays ordered oldest-first (index 0
= oldest).

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

from ._input import as_float_array, check_min, finite_only
from .core import rolling_sum
from .statistics import pearson_correlation

__all__ = [
    "autocorrelation",
    "autocorrelation_series",
    "hurst_exponent",
    "variance_ratio",
    "variance_ratio_z_score",
    "lagged_features",
]


def autocorrelation(x: np.ndarray, lag: int = 1) -> float:
    """Autocorrelation of x at a given lag.

    Definition
        Pearson correlation of x[t] with x[t-lag] over the finite
        observations (shifted pairs). The lag-1 value is the most
        common serial-dependence readout for return series: positive =
        persistence, negative = reversal.

    Raises
        ValueError if fewer than 2 finite observations, or lag < 1.
        Returns NaN when the lag leaves fewer than 2 usable pairs.

    Complexity
        O(n) time, O(n) memory.

    References
        Box, Jenkins & Reinsel, Time Series Analysis (Pearson of
        shifted series; standard correlogram estimator).

    Examples
        >>> import numpy as np
        >>> round(autocorrelation(np.arange(1.0, 101.0)), 12)
        1.0
    """
    x = finite_only(x, "x")
    check_min(x, 2, "autocorrelation")
    if lag <= 0:
        raise ValueError("lag must be >= 1")
    if len(x) <= lag:
        return float("nan")
    return pearson_correlation(x[:-lag], x[lag:])


def autocorrelation_series(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Autocorrelations at lags 1..max_lag (the correlogram).

    Definition
        A vector of autocorrelation(x, lag) for lag in 1..max_lag —
        the quick visual check for structure before any formal test.

    Raises
        ValueError if max_lag < 1.

    Complexity
        O(max_lag * n) time, O(max_lag) memory.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(5)
        >>> ac = autocorrelation_series(rng.normal(0.0, 1.0, 1000), 3)
        >>> ac.shape
        (3,)
        >>> bool(np.all(np.abs(ac) < 0.15))
        True
    """
    if max_lag < 1:
        raise ValueError("max_lag must be >= 1")
    return np.array([autocorrelation(x, lag) for lag in range(1, max_lag + 1)])


def hurst_exponent(x: np.ndarray, min_lag: int = 10, max_lag: int = 0) -> float:
    """Rescaled-range (R/S) Hurst exponent.

    Definition
        For each lag L, split the series into non-overlapping chunks of
        length L, compute R/S per chunk (R = range of cumulative
        deviations from the chunk mean, S = chunk std), average, and
        regress log(R/S) ~ log(L). The slope is the Hurst exponent.

        Interpretation: H ~ 0.5 random walk; H > 0.5 persistent /
        trending; H < 0.5 anti-persistent / mean-reverting. For a pure
        linear trend the slope converges to 1.0.

        Numerical notes: lags are spaced geometrically between min_lag
        and max_lag (default n/2) so the regression covers decades of
        scale; chunks with S == 0 (constant chunks) are dropped, and a
        lag is used only if at least two valid chunks remain. Returns
        NaN if fewer than 3 valid lags remain. On random-walk level
        series the estimator saturates near 1 — feed stationary series
        (e.g. returns), not prices.

    Raises
        ValueError if fewer than 20 finite observations, or
        min_lag < 4.

    Complexity
        O(n * log(n)) time (geometric lag grid), O(n) memory.

    References
        H. Hurst (1951), "Long-term storage capacity of reservoirs",
        Trans. Amer. Soc. Civil Engineers 116.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(42)
        >>> h = hurst_exponent(rng.standard_normal(500))
        >>> 0.3 < h < 0.7
        True
    """
    x = finite_only(x, "x")
    n = len(x)
    check_min(x, 20, "hurst_exponent")
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
    """Lo-MacKinlay variance ratio.

    Definition
        VR(q) = Var(q-period returns) / (q * Var(1-period returns)).
        Under the random-walk null the ratio is 1; positive serial
        dependence pushes it above 1, negative below. The q-period
        returns use non-overlapping sums of length q.

    Raises
        ValueError if q < 2, or fewer than 2q+2 finite observations
        (the minimum the ratio can mean anything for).

    Complexity
        O(n) time, O(n) memory.

    References
        Lo & MacKinlay (1988), "Stock market prices do not follow
        random walks", Review of Financial Studies 1.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(9)
        >>> vr = variance_ratio(rng.normal(0.0, 1.0, 2000), 4)
        >>> abs(vr - 1.0) < 0.3
        True
    """
    returns = finite_only(returns, "returns")
    n = len(returns)
    if q < 2:
        raise ValueError("q must be >= 2")
    check_min(returns, 2 * q + 2, "variance_ratio")
    var_1 = float(np.var(returns, ddof=1))
    if var_1 == 0.0:
        return float("nan")
    q_returns = rolling_sum(returns, q)[q - 1:]
    var_q = float(np.var(q_returns, ddof=1))
    return var_q / (q * var_1)


def variance_ratio_z_score(returns: np.ndarray, q: int) -> float:
    """Homoskedastic z-statistic of the variance ratio.

    Definition
        z = (VR - 1) / sqrt(2(2q-1)(q-1) / (3q n)) under the
        homoskedastic random-walk null (Lo & MacKinlay 1988).
        |z| > 1.96 rejects the random walk at 5%.

    Raises
        ValueError propagated from variance_ratio.

    Complexity
        O(n) time, O(n) memory.

    References
        Lo & MacKinlay (1988), "Stock market prices do not follow
        random walks", Review of Financial Studies 1, eq. (10).

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(9)
        >>> z = variance_ratio_z_score(rng.normal(0.0, 1.0, 2000), 4)
        >>> abs(z) < 2.5
        True
    """
    returns = finite_only(returns, "returns")
    n = len(returns)
    vr = variance_ratio(returns, q)
    if vr != vr:
        return float("nan")
    se = math.sqrt(2.0 * (2.0 * q - 1.0) * (q - 1.0) / (3.0 * q * n))
    return (vr - 1.0) / se


def lagged_features(x: np.ndarray, lags: int) -> np.ndarray:
    """(n, lags+1) design matrix of x and its lags.

    Definition
        Column 0 is x[t], column k is x[t-k]; the leading rows where
        a lag does not exist are NaN-padded (oldest-first data, so
        missing history is at the START of each lag column). The
        standard input layout for autocorrelation-based models.

    Raises
        ValueError if lags < 1.

    Complexity
        O(n * lags) time, O(n * (lags+1)) memory.

    Examples
        >>> import numpy as np
        >>> X = lagged_features(np.array([1.0, 2.0, 3.0]), 1)
        >>> X.shape
        (3, 2)
        >>> np.testing.assert_allclose(X, [[1.0, np.nan],
        ...                                [2.0, 1.0],
        ...                                [3.0, 2.0]])
    """
    x = as_float_array(x, "x")
    if lags < 1:
        raise ValueError("lags must be >= 1")
    n = len(x)
    out = np.full((n, lags + 1), np.nan)
    out[:, 0] = x
    for k in range(1, lags + 1):
        out[k:, k] = x[:-k]
    return out
