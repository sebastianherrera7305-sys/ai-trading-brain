"""resampling — block/stationary bootstrap, bootstrap confidence
intervals, permutation tests, White's Reality Check.

The empirical-null machinery (docs/research/05 sections 2.2-2.4):
answers to "would random data do at least this well?" that make no
parametric assumptions about trade returns.

Determinism policy: every function takes a seed and uses numpy's
default_rng. Tests pin exact results for fixed seeds.
"""

from typing import Callable, Optional

import math

import numpy as np

from .core import required_length
from .statistics import normal_cdf, normal_inv_cdf


def _mean_diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(a) - np.mean(b))


def _mean_of_selected(returns: np.ndarray, signals: np.ndarray) -> float:
    sel = returns[signals == 1]
    if len(sel) == 0:
        return 0.0
    return float(np.mean(sel))


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

def _blocks(n: int, block_size: int, rng: np.random.Generator, n_draws: int) -> np.ndarray:
    """n_draws starting indices for (possibly overlapping) blocks of
    length block_size."""
    max_start = n - block_size + 1
    return rng.integers(0, max_start, size=n_draws)


def block_bootstrap(
    data: np.ndarray,
    block_size: int,
    n_bootstrap: int = 1000,
    seed: int = 0,
    statistic: Callable[[np.ndarray], float] = np.mean,
) -> np.ndarray:
    """Moving-block bootstrap (Kunsch): resample contiguous blocks of
    length block_size with replacement and concatenate until each
    bootstrap sample matches the original length (last partial block
    truncated). Returns the n_bootstrap statistic values.

    Blocking preserves short-horizon serial dependence in returns —
    plain resampling of individual trades would destroy autocorrelation
    and overstate confidence (the classic bootstrap failure mode for
    strategies that trade the same regime repeatedly)."""
    data = np.asarray(data, dtype=float)
    data = data[np.isfinite(data)]
    n = len(data)
    required_length("block_bootstrap", data, 2)
    if block_size <= 0 or block_size > n:
        raise ValueError("block_size must be in [1, len(data)]")
    rng = np.random.default_rng(seed)
    out = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample = np.empty(n)
        filled = 0
        while filled < n:
            start = int(rng.integers(0, n - block_size + 1))
            take = min(block_size, n - filled)
            sample[filled:filled + take] = data[start:start + take]
            filled += take
        out[i] = statistic(sample)
    return out


def stationary_bootstrap(
    data: np.ndarray,
    mean_block_length: float,
    n_bootstrap: int = 1000,
    seed: int = 0,
    statistic: Callable[[np.ndarray], float] = np.mean,
) -> np.ndarray:
    """Stationary bootstrap (Politis & Romano): block lengths are
    geometric with mean mean_block_length, so each bootstrap series is
    weakly stationary. Preferred over fixed-block when dependence is at
    unknown scales."""
    data = np.asarray(data, dtype=float)
    data = data[np.isfinite(data)]
    n = len(data)
    required_length("stationary_bootstrap", data, 2)
    if mean_block_length <= 0:
        raise ValueError("mean_block_length must be > 0")
    p = 1.0 / mean_block_length
    rng = np.random.default_rng(seed)
    out = np.empty(n_bootstrap)
    for i in range(n_bootstrap):
        sample = np.empty(n)
        filled = 0
        pos = int(rng.integers(0, n))
        while filled < n:
            length = int(rng.geometric(p))
            for _ in range(length):
                if filled >= n:
                    break
                sample[filled] = data[pos]
                filled += 1
                pos = (pos + 1) % n
            pos = int(rng.integers(0, n))
        out[i] = statistic(sample)
    return out


def bootstrap_ci(
    data: np.ndarray,
    block_size: int = 5,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 0,
    statistic: Callable[[np.ndarray], float] = np.mean,
) -> tuple:
    """Percentile bootstrap confidence interval (block bootstrap) for
    `statistic(data)`. Returns (estimate, lower, upper)."""
    data = np.asarray(data, dtype=float)
    est = statistic(data[np.isfinite(data)])
    dist = block_bootstrap(data, block_size, n_bootstrap, seed, statistic)
    tail = (1.0 - confidence) / 2.0
    return est, float(np.percentile(dist, 100 * tail)), float(np.percentile(dist, 100 * (1.0 - tail)))


# ---------------------------------------------------------------------------
# Permutation tests
# ---------------------------------------------------------------------------

def permutation_test_two_sample(
    a: np.ndarray,
    b: np.ndarray,
    n_permutations: int = 5000,
    seed: int = 0,
    statistic: Callable[[np.ndarray, np.ndarray], float] = _mean_diff,
) -> float:
    """Two-sample permutation test of "no difference": pool a and b,
    shuffle group labels, recompute the statistic. Returns the two-sided
    p-value (fraction of permutations at least as extreme as observed,
    using the +1/+1 Monte-Carlo convention)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    required_length("permutation_test_two_sample", a, 2)
    required_length("permutation_test_two_sample", b, 2)
    pooled = np.concatenate([a, b])
    na = len(a)
    rng = np.random.default_rng(seed)
    observed = statistic(a, b)
    count = 0
    for _ in range(n_permutations):
        idx = rng.permutation(len(pooled))
        perm_stat = statistic(pooled[idx[:na]], pooled[idx[na:]])
        if abs(perm_stat) >= abs(observed):
            count += 1
    return (count + 1) / (n_permutations + 1)


def permutation_test_signal(
    returns: np.ndarray,
    signals: np.ndarray,
    n_permutations: int = 5000,
    seed: int = 0,
    statistic: Callable[[np.ndarray, np.ndarray], float] = _mean_of_selected,
) -> float:
    """Permutation test of "signal has no edge": observed performance of
    the selected trades (returns where signal == 1) vs the null where
    signal assignments are shuffled across returns. Returns the one-sided
    p-value: fraction of permutations whose selected-performance >= the
    observed one. This is the nullity gate required for every backtest
    result in docs/research/05 section 2.3."""
    returns = np.asarray(returns, dtype=float)
    signals = np.asarray(signals, dtype=float)
    if len(returns) != len(signals):
        raise ValueError("returns and signals must have equal length")
    valid = np.isfinite(returns)
    r = returns[valid]
    s = signals[valid]
    if not np.any(s == 1):
        raise ValueError("signals must contain at least one 1")
    rng = np.random.default_rng(seed)
    observed = statistic(r, s)
    count = 0
    for _ in range(n_permutations):
        shuffled = rng.permutation(r)
        if statistic(shuffled, s) >= observed:
            count += 1
    return (count + 1) / (n_permutations + 1)


# ---------------------------------------------------------------------------
# White's Reality Check — data-snooping-adjusted p-value
# (docs/research/05 section 2.4)
# ---------------------------------------------------------------------------

def reality_check_pvalue(
    trial_performances: np.ndarray,
    block_size: int = 5,
    n_bootstrap: int = 2000,
    seed: int = 0,
) -> float:
    """White's Reality Check (1997), block-bootstrap implementation.

    trial_performances: (n_trials, n_obs) matrix of per-observation
    performance of every candidate strategy tried (each row = one
    parameter set / rule). The statistic is the best (max) mean across
    trials — the classic "we tried 500 variants, the best one looks
    great" situation.

    Procedure: recenter every row by its own mean (so the null is "no
    strategy has edge"), resample observation indices jointly across all
    rows (preserving cross-trial dependence), recompute the max of the
    trial means, and return the fraction of bootstrap maxima >= the
    observed max mean. A small p-value means even the best of many
    trials is unlikely under the null of universal no-edge.

    This is the honest p-value for a tuned strategy's reported backtest
    — the plain walk-forward p-value ignores that the parameter grid was
    searched.
    """
    m = np.asarray(trial_performances, dtype=float)
    if m.ndim != 2:
        raise ValueError("trial_performances must be 2-D (n_trials, n_obs)")
    valid = np.all(np.isfinite(m), axis=1)
    if not np.any(valid):
        raise ValueError("no fully-finite trial rows")
    m = m[valid]
    n_trials, n_obs = m.shape
    if block_size <= 0 or block_size > n_obs:
        raise ValueError("block_size must be in [1, n_obs]")
    required_length("reality_check_pvalue", np.ones(n_trials), 2)

    means = m.mean(axis=1)
    observed = float(means.max())
    centered = m - means[:, None]

    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(n_bootstrap):
        sample = np.empty((n_trials, n_obs))
        filled = 0
        while filled < n_obs:
            start = int(rng.integers(0, n_obs - block_size + 1))
            take = min(block_size, n_obs - filled)
            sample[:, filled:filled + take] = centered[:, start:start + take]
            filled += take
        if float(sample.mean(axis=1).max()) >= observed:
            count += 1
    return (count + 1) / (n_bootstrap + 1)


def deflated_sharpe_ratio(
    sharpe_best: float,
    trial_sharpes: np.ndarray,
    n_obs: int,
    skewness: Optional[float] = None,
    kurtosis: Optional[float] = None,
) -> float:
    """Bailey & López de Prado (2014, "The Deflated Sharpe Ratio")
    data-snooping-adjusted Sharpe significance.

    Inputs (all Sharpe values are NON-annualized, per-observation):
    - sharpe_best: the best Sharpe observed across the trials
    - trial_sharpes: the Sharpe of EVERY candidate tried (the whole
      search distribution, not just the winner)
    - n_obs: number of observations per trial
    - skewness/kurtosis of the returns (optional; if omitted the
      distribution is assumed normal, i.e. the standard error reduces
      to sqrt(1/n))

    Returns P(DSR > 0): the probability that the true post-selection
    Sharpe exceeds zero once the number of trials is accounted for.

    Procedure (AFML ch. 14): the null maximum Sharpe is
    E[max] = sqrt(V[max]) * [(1-gamma)*Z^-1(1-1/N) +
    gamma*Z^-1(1-1/(N*e))], with V[max] = variance of the trial Sharpes,
    N = number of trials, gamma = Euler-Mascheroni. The DSR is then a
    one-sided normal tail probability of the distance between the
    observed best and E[max], corrected for skew/kurtosis.
    """
    trials = np.asarray(trial_sharpes, dtype=float)
    trials = trials[np.isfinite(trials)]
    if len(trials) < 2:
        raise ValueError("trial_sharpes needs >= 2 finite values")
    if n_obs < 2:
        raise ValueError("n_obs must be >= 2")
    if (skewness is None) != (kurtosis is None):
        raise ValueError("skewness and kurtosis must be provided together")

    n = len(trials)
    gamma_e = 0.5772156649015329
    vmax = float(np.var(trials, ddof=1))
    if vmax == 0.0:
        e_max = 0.0
    else:
        z1 = normal_inv_cdf(1.0 - 1.0 / n)
        z2 = normal_inv_cdf(1.0 - 1.0 / (n * math.e))
        e_max = math.sqrt(vmax) * ((1.0 - gamma_e) * z1 + gamma_e * z2)

    numerator = (sharpe_best - e_max) * math.sqrt(n_obs - 1.0)
    if skewness is None:
        denominator = 1.0
    else:
        denominator = math.sqrt(
            1.0 - skewness * sharpe_best + (kurtosis - 1.0) / 4.0 * sharpe_best ** 2
        )
        if denominator <= 0.0:
            return float("nan")
    return float(normal_cdf(numerator / denominator))
