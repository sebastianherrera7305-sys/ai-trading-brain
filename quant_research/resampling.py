"""resampling — block/stationary bootstrap, bootstrap confidence
intervals, permutation tests, White's Reality Check.

The empirical-null machinery (docs/research/05 sections 2.2-2.4):
answers to "would random data do at least this well?" that make no
parametric assumptions about trade returns.

Determinism policy: every function takes a seed and uses numpy's
default_rng(seed). Tests pin exact results for fixed seeds.
"""

from typing import Callable, Optional, Tuple

import math

import numpy as np

from ._input import as_float_array, check_min, finite_only
from .statistics import normal_cdf, normal_inv_cdf

__all__ = [
    "block_bootstrap",
    "stationary_bootstrap",
    "bootstrap_confidence_interval",
    "permutation_test_two_sample",
    "permutation_test_signal",
    "reality_check_p_value",
    "deflated_sharpe_ratio",
]


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

def block_bootstrap(
    data: np.ndarray,
    block_size: int,
    n_bootstrap: int = 1000,
    seed: int = 0,
    statistic: Callable[[np.ndarray], float] = np.mean,
) -> np.ndarray:
    """Moving-block bootstrap (Kunsch) of a statistic.

    Definition
        Resample contiguous blocks of length block_size with
        replacement and concatenate until each bootstrap sample matches
        the original length (last partial block truncated); recompute
        `statistic` per sample. Returns the n_bootstrap values.

        Blocking preserves short-horizon serial dependence in returns —
        plain resampling of individual trades would destroy
        autocorrelation and overstate confidence (the classic bootstrap
        failure mode for strategies that trade the same regime
        repeatedly).

    Raises
        ValueError if fewer than 2 finite observations, or block_size
        outside [1, n].

    Complexity
        O(n_bootstrap * n) time; O(n) memory.

    References
        H. Künsch (1989), "The jackknife and the bootstrap for general
        stationary observations", Annals of Statistics 17.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(7)
        >>> x = rng.normal(0.0, 1.0, 50)
        >>> out = block_bootstrap(x, 5, n_bootstrap=200, seed=3)
        >>> out.shape
        (200,)
        >>> abs(float(np.mean(out)) - float(np.mean(x))) < 0.5
        True
    """
    data = finite_only(data, "data")
    n = len(data)
    check_min(data, 2, "block_bootstrap")
    if block_size <= 0 or block_size > n:
        raise ValueError("block_size must be in [1, len(data)]")
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be >= 1")
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
    """Stationary bootstrap (Politis & Romano) of a statistic.

    Definition
        Block lengths are drawn geometric with mean mean_block_length
        and the series wraps around, so each bootstrap series is weakly
        stationary. Preferred over fixed-block when dependence exists at
        unknown scales.

    Raises
        ValueError if fewer than 2 finite observations, or
        mean_block_length <= 0.

    Complexity
        O(n_bootstrap * n) time; O(n) memory.

    References
        D. Politis & J. Romano (1994), "The stationary bootstrap",
        Journal of the American Statistical Association 89.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(7)
        >>> x = rng.normal(0.0, 1.0, 50)
        >>> out = stationary_bootstrap(x, 4.0, n_bootstrap=200, seed=3)
        >>> out.shape
        (200,)
    """
    data = finite_only(data, "data")
    n = len(data)
    check_min(data, 2, "stationary_bootstrap")
    if mean_block_length <= 0:
        raise ValueError("mean_block_length must be > 0")
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be >= 1")
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


def bootstrap_confidence_interval(
    data: np.ndarray,
    block_size: int = 5,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int = 0,
    statistic: Callable[[np.ndarray], float] = np.mean,
) -> Tuple[float, float, float]:
    """Percentile block-bootstrap confidence interval for a statistic.

    Definition
        (estimate, lower, upper) where estimate = statistic(data) on
        the finite observations and the bounds are the percentile
        points of the block-bootstrap distribution (Efron's percentile
        interval). No parametric distributional assumption is made.

    Raises
        ValueError propagated from block_bootstrap (>= 2 finite
        observations, block_size in [1, n]).

    Complexity
        O(n_bootstrap * n) time; O(n) memory.

    References
        B. Efron (1981), "Nonparametric standard errors and confidence
        intervals", Canadian Journal of Statistics 9.

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(7)
        >>> x = rng.normal(0.0, 1.0, 100)
        >>> est, lo, hi = bootstrap_confidence_interval(x, block_size=5, n_bootstrap=500, seed=1)
        >>> lo <= est <= hi
        True
    """
    data = finite_only(data, "data")
    check_min(data, 2, "bootstrap_confidence_interval")
    est = float(statistic(data))
    dist = block_bootstrap(data, block_size, n_bootstrap, seed, statistic)
    tail = (1.0 - confidence) / 2.0
    return (
        est,
        float(np.percentile(dist, 100 * tail)),
        float(np.percentile(dist, 100 * (1.0 - tail))),
    )


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
    """Two-sample permutation test of "no difference".

    Definition
        Pool a and b, shuffle the group labels, recompute the
        statistic, and count how often the permuted statistic is at
        least as extreme as the observed one. Returns the two-sided
        p-value with the +1/+1 Monte-Carlo convention (an exact 0 is
        impossible and under-reports significance).

    Raises
        ValueError if either sample has fewer than 2 finite
        observations.

    Complexity
        O(n_permutations * (n_a + n_b)) time; O(n) memory.

    References
        E. Pitman (1937), "Significance tests which may be applied to
        samples from any populations", JRSS B 4.

    Examples
        >>> import numpy as np
        >>> p = permutation_test_two_sample(np.arange(1.0, 6.0),
        ...                                 np.arange(11.0, 16.0),
        ...                                 n_permutations=2000, seed=0)
        >>> p < 0.05
        True
    """
    a = finite_only(a, "a")
    b = finite_only(b, "b")
    check_min(a, 2, "permutation_test_two_sample")
    check_min(b, 2, "permutation_test_two_sample")
    if n_permutations < 1:
        raise ValueError("n_permutations must be >= 1")
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
    """Permutation test of "signal has no edge".

    Definition
        Observed performance of the selected trades (returns where
        signal == 1) vs the null where signal assignments are shuffled
        across returns. Returns the one-sided p-value: fraction of
        permutations whose selected-performance is >= the observed one
        (+1/+1 convention). This is the nullity gate required for every
        backtest result in docs/research/05 section 2.3.

    Raises
        ValueError if returns and signals differ in length, or signals
        contain no 1.

    Complexity
        O(n_permutations * n) time; O(n) memory.

    References
        E. Pitman (1937), "Significance tests which may be applied to
        samples from any populations", JRSS B 4.

    Examples
        >>> import numpy as np
        >>> p = permutation_test_signal(np.array([0.1, -0.05, 0.2, -0.02, 0.3,
        ...                                       0.01, -0.1, 0.05]),
        ...                             np.array([1.0, 0.0, 1.0, 0.0, 1.0,
        ...                                       0.0, 1.0, 1.0]),
        ...                             n_permutations=2000, seed=0)
        >>> p < 0.2
        True
    """
    returns = as_float_array(returns, "returns")
    signals = as_float_array(signals, "signals")
    if len(returns) != len(signals):
        raise ValueError("returns and signals must have equal length")
    if n_permutations < 1:
        raise ValueError("n_permutations must be >= 1")
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

def reality_check_p_value(
    trial_performances: np.ndarray,
    block_size: int = 5,
    n_bootstrap: int = 2000,
    seed: int = 0,
) -> float:
    """White's Reality Check (1997), block-bootstrap implementation.

    Definition
        trial_performances: (n_trials, n_obs) matrix of per-observation
        performance of every candidate strategy tried (each row = one
        parameter set / rule). The statistic is the best (max) mean
        across trials — the classic "we tried 500 variants, the best
        one looks great" situation.

        Procedure: recenter every row by its own mean (null: "no
        strategy has edge"), resample observation indices jointly
        across all rows (preserving cross-trial dependence), recompute
        the max of the trial means, and return the fraction of
        bootstrap maxima >= the observed max mean (+1/+1). A small
        p-value means even the best of many trials is unlikely under
        the null of universal no-edge.

        This is the honest p-value for a tuned strategy's reported
        backtest — the plain walk-forward p-value ignores that the
        parameter grid was searched.

    Raises
        ValueError if the input is not 2-D, has no fully-finite rows,
        or block_size outside [1, n_obs]. Needs >= 2 trial rows.

    Complexity
        O(n_bootstrap * n_trials * n_obs) time; O(n_trials * n_obs)
        memory.

    References
        H. White (2000), "A Reality Check for Data Snooping",
        Econometrica 68(5).

    Examples
        >>> import numpy as np
        >>> rng = np.random.default_rng(11)
        >>> trials = rng.normal(0.0, 1.0, (20, 100))
        >>> p = reality_check_p_value(trials, block_size=5,
        ...                          n_bootstrap=500, seed=2)
        >>> p > 0.05
        True
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
    check_min(np.ones(n_trials), 2, "reality_check_p_value")
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap must be >= 1")

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

    Definition
        Inputs (all Sharpe values are NON-annualized, per-observation):
        sharpe_best: the best Sharpe observed across the trials;
        trial_sharpes: the Sharpe of EVERY candidate tried (the whole
        search distribution, not just the winner); n_obs: observations
        per trial; skewness/kurtosis of the returns (optional; if
        omitted the distribution is assumed normal, i.e. the standard
        error reduces to sqrt(1/n)).

        Returns P(DSR > 0): the probability that the true
        post-selection Sharpe exceeds zero once the number of trials is
        accounted for.

        Procedure (AFML ch. 14): the null maximum Sharpe is
        E[max] = sqrt(V[max]) * [(1-gamma)*Z^-1(1-1/N) +
        gamma*Z^-1(1-1/(N*e))], with V[max] = variance of the trial
        Sharpes, N = number of trials, gamma = Euler-Mascheroni. The
        DSR is then a one-sided normal tail probability of the distance
        between the observed best and E[max], corrected for
        skew/kurtosis.

    Raises
        ValueError if fewer than 2 finite trial Sharpes, n_obs < 2, or
        exactly one of skewness/kurtosis is given.

    Complexity
        O(N) time, O(N) memory.

    References
        Bailey & López de Prado (2014), "The Deflated Sharpe Ratio:
        Correcting for Selection Bias, Backtest Overfitting and
        Non-Normality", Journal of Portfolio Management 40(5).

    Examples
        >>> import numpy as np
        >>> trial_sharpes = np.array([0.0, 0.05, 0.1, 0.15, 0.2])
        >>> round(deflated_sharpe_ratio(0.2, trial_sharpes, 250), 4)
        0.9524
    """
    trials = as_float_array(trial_sharpes, "trial_sharpes")
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
        radicand = (
            1.0 - skewness * sharpe_best
            + (kurtosis - 1.0) / 4.0 * sharpe_best ** 2
        )
        if radicand <= 0.0:
            return float("nan")
        denominator = math.sqrt(radicand)
    return float(normal_cdf(numerator / denominator))
