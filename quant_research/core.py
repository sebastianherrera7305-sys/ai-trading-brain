"""core — returns/prices algebra, rolling operations, EWMA, z-scores.

The base layer every other module builds on. All functions are
vectorized numpy and assume input arrays are 1-D float arrays ordered
oldest-first (index 0 = oldest). No NaNs are produced by these
helpers except where the window makes a value genuinely undefined.

Why rolling ops are implemented with sliding_window_view instead of
cumsum: cumsum-based rolling mean/std suffer catastrophic cancellation
on near-constant arrays (the whole point of this package is analyzing
trading returns, which hover near zero). sliding_window_view is exact,
memory-efficient and available since numpy 1.20.
"""

from typing import List, Optional

import numpy as np

from numpy.lib.stride_tricks import sliding_window_view


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """p_t / p_{t-1} - 1. First element is NaN (no previous price)."""
    prices = np.asarray(prices, dtype=float)
    out = np.empty_like(prices)
    out[0] = np.nan
    if len(prices) > 1:
        out[1:] = prices[1:] / prices[:-1] - 1.0
    return out


def log_returns(prices: np.ndarray) -> np.ndarray:
    """log(p_t / p_{t-1}). First element is NaN."""
    prices = np.asarray(prices, dtype=float)
    out = np.empty_like(prices)
    out[0] = np.nan
    if len(prices) > 1:
        np.log(prices[1:] / prices[:-1], out=out[1:])
    return out


def cumulative_returns(returns: np.ndarray, start_value: float = 1.0) -> np.ndarray:
    """Growth of a unit of capital given a series of returns: start_value *
    cumprod(1 + r_t). NaN entries (e.g. the leading NaN of returns
    converters) are treated as zero return."""
    returns = np.asarray(returns, dtype=float)
    r = np.nan_to_num(returns, nan=0.0)
    return start_value * np.cumprod(1.0 + r)


def prices_from_returns(returns: np.ndarray, start_price: float = 100.0) -> np.ndarray:
    """Inverse of simple_returns: reconstruct a price path from returns."""
    returns = np.asarray(returns, dtype=float)
    r = np.nan_to_num(returns, nan=0.0)
    return start_price * np.cumprod(1.0 + r)


def drawdown_prices(prices: np.ndarray) -> np.ndarray:
    """Underwater curve from a price path: p_t / running_max - 1
    (<= 0, reaching 0 exactly at each new high)."""
    prices = np.asarray(prices, dtype=float)
    running_max = np.maximum.accumulate(prices)
    return prices / running_max - 1.0


def zscore(x: np.ndarray, ddof: int = 1) -> np.ndarray:
    """Standardize: (x - mean) / std. NaN if std == 0 (constant input
    has no meaningful z-score)."""
    x = np.asarray(x, dtype=float)
    mean = np.mean(x)
    std = np.std(x, ddof=ddof)
    if std == 0.0:
        return np.full_like(x, np.nan)
    return (x - mean) / std


def rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling simple mean; first (window-1) elements are NaN."""
    x = np.asarray(x, dtype=float)
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.mean(axis=1)
    return out


def rolling_std(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling sample standard deviation; first (window-1) elements NaN."""
    x = np.asarray(x, dtype=float)
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.std(axis=1, ddof=ddof)
    return out


def rolling_sum(x: np.ndarray, window: int) -> np.ndarray:
    """Rolling sum; first (window-1) elements are NaN."""
    x = np.asarray(x, dtype=float)
    if window <= 0:
        raise ValueError("window must be >= 1")
    if len(x) < window:
        return np.full_like(x, np.nan)
    view = sliding_window_view(x, window)
    out = np.full(len(x), np.nan)
    out[window - 1:] = view.sum(axis=1)
    return out


def rolling_zscore(x: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Z-score of x against its own trailing window; NaN wherever the
    window (or the window's std) is undefined."""
    mean = rolling_mean(x, window)
    std = rolling_std(x, window, ddof=ddof)
    out = np.full_like(x, np.nan)
    valid = ~np.isnan(std) & (std != 0.0)
    out[valid] = (x[valid] - mean[valid]) / std[valid]
    return out


def rolling_correlation(a: np.ndarray, b: np.ndarray, window: int, ddof: int = 1) -> np.ndarray:
    """Rolling Pearson correlation between two aligned series; NaN where
    either window is incomplete or one of the rolling stds is zero."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
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
    """Exponential moving average with span (full same-length output,
    warm start on the first value)."""
    x = np.asarray(x, dtype=float)
    if span <= 0:
        raise ValueError("span must be > 0")
    if len(x) == 0:
        return np.array([])
    return _ema(x, span)


def ewma_volatility(returns: np.ndarray, span: float, periods: int = 252) -> np.ndarray:
    """Rolling exponentially-weighted volatility estimate: sqrt(EMA of
    squared returns * periods). The classic RiskMetrics-style vol proxy
    with no window burn-in."""
    returns = np.asarray(returns, dtype=float)
    if span <= 0:
        raise ValueError("span must be > 0")
    if len(returns) == 0:
        return np.array([])
    r = np.nan_to_num(returns, nan=0.0)
    ema_sq = _ema(r * r, span)
    return np.sqrt(ema_sq * periods)


def centered_smooth(x: np.ndarray, window: int) -> np.ndarray:
    """Centered moving average (window must be odd): smooth_t = mean of
    x[t-(w//2) : t+(w//2)+1]. Boundary elements are NaN."""
    x = np.asarray(x, dtype=float)
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
    """Element-wise a/b, substituting `default` where b == 0 (or NaN)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    out = np.full(np.broadcast(a, b).shape, default, dtype=float)
    np.divide(a, b, out=out, where=(b != 0.0) & ~np.isnan(b))
    return out


def drop_nan(x: np.ndarray) -> np.ndarray:
    """Drop NaN/Inf entries, preserving order."""
    x = np.asarray(x, dtype=float)
    return x[np.isfinite(x)]


def required_length(name: str, x: np.ndarray, minimum: int) -> None:
    """Shared validation: a function needs at least `minimum` finite
    observations of a series to mean anything. Raises ValueError."""
    n = int(np.isfinite(np.asarray(x, dtype=float)).sum())
    if n < minimum:
        raise ValueError(
            "%s needs >= %d finite observations, got %d" % (name, minimum, n)
        )
