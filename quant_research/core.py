"""core — returns/prices algebra, rolling operations, EWMA, z-scores.

The base layer every other module builds on. All functions are
vectorized numpy and follow the package input contract (see _input.py):
array-like in, 1-D float64 out, oldest-first ordering (index 0 =
oldest). Missing values (NaN/Inf) propagate through position-aligned
operations and are never invented; empty inputs to algebra functions
return empty arrays.

Why rolling ops are implemented with sliding_window_view instead of
cumsum: cumsum-based rolling mean/std suffer catastrophic cancellation
on near-constant arrays (the whole point of this package is analyzing
trading returns, which hover near zero). sliding_window_view is exact,
memory-efficient and available since numpy 1.20.
"""

from typing import Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ._input import as_float_array, check_min, finite_only

__all__ = [
    "simple_returns",
    "log_returns",
    "cumulative_returns",
    "prices_from_returns",
    "drawdown_prices",
    "z_score",
    "rolling_mean",
    "rolling_std",
    "rolling_sum",
    "rolling_z_score",
    "rolling_correlation",
    "ewma",
    "ewma_volatility",
    "centered_smooth",
    "safe_divide",
    "drop_nan",
    "required_length",
]


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """Simple (arithmetic) return series from a price path.

    Definition
        r_t = p_t / p_{t-1} - 1 for t >= 1; r_0 = NaN (no previous
        price). Prices are used as given: a zero or negative price
        yields inf/NaN, matching numpy's own conventions.

    Complexity
        O(n) time, O(n) memory; vectorized.

    Examples
        >>> import numpy as np
        >>> r = simple_returns(np.array([8.0, 4.0, 2.0]))
        >>> int(np.isnan(r[0]))
        1
        >>> float(r[1]), float(r[2])
        (-0.5, -0.5)
        >>> np.testing.assert_allclose(
        ...     simple_returns(np.array([100.0, 110.0, 121.0]))[1:], [0.1, 0.1],
        ...     rtol=1e-12,
        ... )
    """
    prices = as_float_array(prices, "prices")
    out = np.empty_like(prices)
    if len(prices) > 0:
        out[0] = np.nan
    if len(prices) > 1:
        out[1:] = prices[1:] / prices[:-1] - 1.0
    return out


def log_returns(prices: np.ndarray) -> np.ndarray:
    """Continuously-compounded return series: log(p_t / p_{t-1}).

    Definition
        r_t = log(p_t / p_{t-1}) for t >= 1; r_0 = NaN (no previous
        price). Preferred over simple_returns wherever returns are
        added across time (log returns compound by summation).

    Complexity
        O(n) time, O(n) memory; vectorized.

    Examples
        >>> import numpy as np
        >>> import math
        >>> r = log_returns(np.array([8.0, 4.0, 2.0]))
        >>> int(np.isnan(r[0]))
        1
        >>> float(r[1]) == -math.log(2.0)
        True
    """
    prices = as_float_array(prices, "prices")
    out = np.empty_like(prices)
    if len(prices) > 0:
        out[0] = np.nan
    if len(prices) > 1:
        np.log(prices[1:] / prices[:-1], out=out[1:])
    return out


def cumulative_returns(returns: np.ndarray, start_value: float = 1.0) -> np.ndarray:
    """Growth of one unit of capital over a return series.

    Definition
        g_t = start_value * prod_{i<=t} (1 + r_i). NaN entries (e.g. the
        leading NaN of the return converters) are treated as zero
        return, so the output length always equals the input length.

    Complexity
        O(n) time, O(n) memory; vectorized cumprod.

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(
        ...     cumulative_returns(np.array([0.1, 0.1])), [1.1, 1.21],
        ... )
        >>> np.testing.assert_allclose(
        ...     cumulative_returns(np.array([np.nan, 0.1])), [1.0, 1.1],
        ... )
    """
    returns = as_float_array(returns, "returns")
    r = np.nan_to_num(returns, nan=0.0)
    return start_value * np.cumprod(1.0 + r)


def prices_from_returns(returns: np.ndarray, start_price: float = 100.0) -> np.ndarray:
    """Reconstruct a price path from simple returns.

    Definition
        p_t = start_price * prod_{i<=t} (1 + r_i) with NaN returns
        treated as zero. Exact inverse of simple_returns for finite
        prices (see the round-trip test).

    Complexity
        O(n) time, O(n) memory.

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(
        ...     prices_from_returns(np.array([0.1, 0.1]), 100.0),
        ...     [110.0, 121.0],
        ... )
    """
    returns = as_float_array(returns, "returns")
    r = np.nan_to_num(returns, nan=0.0)
    return start_price * np.cumprod(1.0 + r)


def drawdown_prices(prices: np.ndarray) -> np.ndarray:
    """Underwater curve from a price path: p_t / running_max - 1.

    Definition
        d_t = p_t / max(p_0..p_t) - 1; always <= 0, touching exactly 0
        at each new high. The negative of this series is the drawdown
        from the peak.

    Complexity
        O(n) time, O(n) memory.

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(
        ...     drawdown_prices(np.array([100.0, 120.0, 90.0])),
        ...     [0.0, 0.0, -0.25],
        ... )
    """
    prices = as_float_array(prices, "prices")
    running_max = np.maximum.accumulate(prices)
    return prices / running_max - 1.0


def z_score(x: np.ndarray, ddof: int = 1) -> np.ndarray:
    """Standardize a series: (x - mean) / std, position-aligned.

    Definition
        z_t = (x_t - mean) / std computed on the finite observations;
        output positions of missing inputs stay NaN. If the standard
        deviation is zero (constant input) every output is NaN, because
        a constant series has no meaningful z-score.

    Complexity
        O(n) time, O(n) memory.

    Raises
        ValueError if fewer than 2 finite observations.

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(
        ...     z_score(np.array([1.0, 2.0, 3.0])), [-1.0, 0.0, 1.0],
        ... )
        >>> z = z_score(np.array([2.0, 2.0, 2.0]))
        >>> bool(np.all(np.isnan(z)))
        True
    """
    x = as_float_array(x, "x")
    check_min(x, 2, "z_score")
    finite = x[np.isfinite(x)]
    mean = float(np.mean(finite))
    std = float(np.std(finite, ddof=ddof))
    if std == 0.0:
        return np.full_like(x, np.nan)
    out = (x - mean) / std
    out[~np.isfinite(x)] = np.nan
    return out


def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling simple mean over a fixed window.

    Definition
        m_t = mean(x_{t-w+1}..x_t) for t >= w; the first w-1 positions
        are NaN (window not yet complete). Missing values inside a
        window propagate (the window mean is NaN).

    Complexity
        O(n*w) time in the window size, O(n + w) memory; implemented
        with sliding_window_view (exact, no cumsum cancellation).

    Raises
        ValueError if window < 1.

    Examples
        >>> import numpy as np
        >>> out = rolling_mean(np.array([1.0, 2.0, 3.0, 4.0]), 2)
        >>> int(np.isnan(out[0]))
        1
        >>> np.testing.assert_allclose(out[1:], [1.5, 2.5, 3.5])
    """
    x = as_float_array(x, "x")
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.mean(axis=1)
    return out


def rolling_std(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling sample standard deviation over a fixed window.

    Definition
        s_t = std(x_{t-w+1}..x_t) with the given ddof for t >= w; the
        first w-1 positions are NaN. With ddof=1 a one-point window has
        NaN std (undefined sample variance).

    Complexity
        O(n*w) time, O(n + w) memory.

    Raises
        ValueError if window < 1.

    Examples
        >>> import numpy as np
        >>> import math
        >>> out = rolling_std(np.array([1.0, 2.0, 3.0, 4.0]), 2)
        >>> int(np.isnan(out[0]))
        1
        >>> np.testing.assert_allclose(out[1:], [math.sqrt(0.5)] * 3)
    """
    x = as_float_array(x, "x")
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.std(axis=1, ddof=ddof)
    return out


def rolling_sum(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling sum over a fixed window (used by the variance-ratio test).

    Definition
        s_t = sum(x_{t-w+1}..x_t) for t >= w; first w-1 positions NaN.

    Complexity
        O(n*w) time, O(n + w) memory.

    Raises
        ValueError if window < 1.

    Examples
        >>> import numpy as np
        >>> out = rolling_sum(np.array([1.0, 2.0, 3.0, 4.0]), 2)
        >>> int(np.isnan(out[0]))
        1
        >>> np.testing.assert_allclose(out[1:], [3.0, 5.0, 7.0])
    """
    x = as_float_array(x, "x")
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.sum(axis=1)
    return out


def rolling_z_score(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Z-score of x against its own trailing window.

    Definition
        z_t = (x_t - mean_t) / std_t where mean_t/std_t are the trailing
        window statistics. NaN wherever the window is incomplete, the
        window std is zero, or x_t is missing.

    Complexity
        O(n*w) time, O(n + w) memory.

    Raises
        ValueError if window < 1.

    Examples
        >>> import numpy as np
        >>> out = rolling_z_score(np.array([1.0, 2.0, 3.0, 4.0]), 2)
        >>> int(np.isnan(out[0]))
        1
        >>> np.testing.assert_allclose(out[1:], [0.5 ** 0.5] * 3, rtol=1e-12)
    """
    mean = rolling_mean(x, window)
    std = rolling_std(x, window, ddof=ddof)
    out = np.full(len(mean), np.nan)
    valid = ~np.isnan(std) & (std != 0.0) & ~np.isnan(x)
    out[valid] = (x[valid] - mean[valid]) / std[valid]
    return out


def rolling_correlation(
    a: np.ndarray, b: np.ndarray, window: int, ddof: int = 1
) -> np.ndarray:
    """Rolling Pearson correlation between two aligned series.

    Definition
        corr_t = cov(a, b)_t / (std_a_t * std_b_t) over the trailing
        window. NaN where either window is incomplete, either std is
        zero, or a window contains missing values.

    Complexity
        O(n*w) time, O(n + w) memory.

    Raises
        ValueError if a and b differ in length, or window < 1.

    Examples
        >>> import numpy as np
        >>> x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        >>> np.testing.assert_allclose(
        ...     rolling_correlation(x, x, 3)[2:], [1.0, 1.0, 1.0],
        ... )
        >>> np.testing.assert_allclose(
        ...     rolling_correlation(x, -x, 3)[2:], [-1.0, -1.0, -1.0],
        ... )
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    if window <= 0:
        raise ValueError("window must be >= 1")
    n = len(a)
    if n < window:
        return np.full(n, np.nan)
    va = sliding_window_view(a, window)
    vb = sliding_window_view(b, window)
    ma = va.mean(axis=1)
    mb = vb.mean(axis=1)
    sa = va.std(axis=1, ddof=ddof)
    sb = vb.std(axis=1, ddof=ddof)
    cov = ((va - ma[:, None]) * (vb - mb[:, None])).sum(axis=1) / (window - ddof)
    out = np.full(n, np.nan)
    valid = (sa != 0.0) & (sb != 0.0) & ~np.isnan(cov)
    out[window - 1:] = np.where(valid, cov / (sa * sb), np.nan)
    return out


def _ema(x: np.ndarray, span: float) -> np.ndarray:
    """Exponential moving average (recursive, exact): e_t = a*x_t +
    (1-a)*e_{t-1} with a = 2/(span+1). Loop is O(n) in pure Python on
    purpose: a vectorized formulation is only stable via scipy-style
    convolution tricks that this package deliberately avoids."""
    alpha = 2.0 / (span + 1.0)
    out = np.empty(len(x))
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = alpha * x[i] + (1.0 - alpha) * out[i - 1]
    return out


def ewma(x: np.ndarray, span: float) -> np.ndarray:
    """Exponential moving average with span (RiskMetrics-style filter).

    Definition
        e_t = a * x_t + (1 - a) * e_{t-1}, a = 2/(span+1), warm-started
        at e_0 = x_0. Full same-length output; no burn-in window.
        span=1 is the identity filter.

    Complexity
        O(n) time, O(n) memory; single pass, exact recursion.

    Raises
        ValueError if span <= 0.

    References
        J.P. Morgan / Reuters (1996), RiskMetrics Technical Document,
        Section 5.2 (exponential weighting).

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(ewma(np.array([1.0, 1.0, 1.0]), 3),
        ...                            [1.0, 1.0, 1.0])
        >>> np.testing.assert_allclose(ewma(np.array([1.0, 5.0, 2.0]), 1),
        ...                            [1.0, 5.0, 2.0])
    """
    x = as_float_array(x, "x")
    if span <= 0:
        raise ValueError("span must be > 0")
    if len(x) == 0:
        return np.array([])
    return _ema(x, span)


def ewma_volatility(
    returns: np.ndarray, span: float, periods: int = 252
) -> np.ndarray:
    """Exponentially-weighted volatility estimate from a return series.

    Definition
        vol_t = sqrt(periods * EMA_t(r^2)) with span weighting — the
        classic RiskMetrics-style vol proxy with no window burn-in.
        Missing returns are treated as zero (no information).

    Complexity
        O(n) time, O(n) memory.

    Raises
        ValueError if span <= 0 or periods < 1.

    References
        J.P. Morgan / Reuters (1996), RiskMetrics Technical Document,
        Section 5.2.

    Examples
        >>> import numpy as np
        >>> v = ewma_volatility(np.array([0.01] * 50), span=10, periods=252)
        >>> np.testing.assert_allclose(v, [0.01 * 252 ** 0.5] * 50, rtol=1e-12)
    """
    returns = as_float_array(returns, "returns")
    if span <= 0:
        raise ValueError("span must be > 0")
    if periods < 1:
        raise ValueError("periods must be >= 1")
    if len(returns) == 0:
        return np.array([])
    r = np.nan_to_num(returns, nan=0.0)
    ema_sq = _ema(r * r, span)
    return np.sqrt(ema_sq * periods)


def centered_smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average (window must be odd).

    Definition
        smooth_t = mean(x[t-(w//2) : t+(w//2)+1]); boundary positions
        closer than (w-1)/2 to either end are NaN. A centered average
        does not lag the signal, unlike trailing filters.

    Complexity
        O(n*w) time, O(n + w) memory.

    Raises
        ValueError if window is not a positive odd integer.

    Examples
        >>> import numpy as np
        >>> out = centered_smooth(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
        >>> int(np.isnan(out[0])), int(np.isnan(out[-1]))
        (1, 1)
        >>> np.testing.assert_allclose(out[1:-1], [2.0, 3.0, 4.0])
    """
    x = as_float_array(x, "x")
    if window <= 0 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer")
    half = window // 2
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[half:len(x) - half] = view.mean(axis=1)
    return out


def safe_divide(a: np.ndarray, b: np.ndarray, default: float = np.nan) -> np.ndarray:
    """Element-wise a/b with a substituted default where b is 0 or NaN.

    Definition
        out_t = a_t / b_t where b_t != 0 and b_t is finite; default
        otherwise. Broadcast shapes are allowed (same rules as numpy's
        ufunc broadcasting).

    Complexity
        O(n) time, O(n) memory.

    Examples
        >>> import numpy as np
        >>> out = safe_divide(np.array([1.0, 2.0, 3.0]),
        ...                   np.array([0.0, 1.0, 2.0]))
        >>> int(np.isnan(out[0]))
        1
        >>> np.testing.assert_allclose(out[1:], [2.0, 1.5])
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    out = np.full(np.broadcast(a, b).shape, default, dtype=float)
    np.divide(a, b, out=out, where=(b != 0.0) & ~np.isnan(b))
    return out


def drop_nan(x: np.ndarray) -> np.ndarray:
    """Drop NaN/Inf entries, preserving order.

    Definition
        out = x[isfinite(x)]. The companion of required_length: every
        statistic in this package drops non-finite observations before
        validating the minimum count.

    Complexity
        O(n) time, O(n) memory.

    Examples
        >>> import numpy as np
        >>> np.testing.assert_allclose(
        ...     drop_nan(np.array([1.0, np.nan, np.inf, 2.0])), [1.0, 2.0],
        ... )
    """
    return finite_only(x)


def required_length(name: str, x: np.ndarray, minimum: int) -> None:
    """Raise ValueError unless x has at least `minimum` finite entries.

    Definition
        Shared validation gate: a statistic needs a documented minimum
        of finite observations to mean anything. The error message
        states the minimum, so callers never have to guess why a small
        sample was rejected.

    Raises
        ValueError with a message naming the function, the minimum and
        the actual count.

    Examples
        >>> import numpy as np
        >>> required_length("variance", np.array([1.0, np.nan]), 2)
        Traceback (most recent call last):
            ...
        ValueError: variance needs >= 2 finite observations, got 1
    """
    check_min(x, minimum, name)
