"""statistics — distribution functions and hypothesis tests, scipy-free.

Implements the distributions this package needs with their own kernels
(Numerical-Recipes-style algorithms, verified against published table
values in the test suite):

- normal CDF via math.erf; inverse via Acklam's rational approximation
- Student-t CDF via the regularized incomplete beta function
- chi2 CDF via the regularized lower incomplete gamma function
- inverse CDFs via deterministic bisection on the CDFs above

Everything is numpy-only; scalars in, floats out. Reference points used
by tests (all standard published values):

  t_{0.90}(10)=1.372, t_{0.95}(10)=1.812, t_{0.975}(10)=2.228,
  t_{0.995}(10)=3.169, t_{0.995}(1)=63.657
  chi2_{0.95}(1)=3.8415, chi2_{0.95}(4)=9.488, chi2_{0.95}(8)=15.507
  Z_{0.975}=1.959964
"""

import math
from typing import Tuple

import numpy as np

from ._input import as_float_array, check_min, finite_only

__all__ = [
    "normal_cdf",
    "normal_sf",
    "normal_inv_cdf",
    "normal_z_score",
    "normal_pdf",
    "regularized_incomplete_beta",
    "student_t_cdf",
    "student_t_sf",
    "student_t_inv_cdf",
    "chi2_cdf",
    "chi2_p_value",
    "chi2_inv_cdf",
    "variance",
    "covariance",
    "covariance_matrix",
    "coefficient_of_variation",
    "empirical_cdf",
    "mean_confidence_interval",
    "two_sample_t_test",
    "paired_t_test",
    "skewness",
    "excess_kurtosis",
    "jarque_bera",
    "pearson_correlation",
    "spearman_correlation",
    "sharpe_standard_error",
]

_MIN_FLOAT = 1e-300


# ---------------------------------------------------------------------------
# Normal distribution
# ---------------------------------------------------------------------------

def normal_cdf(x: float) -> float:
    """CDF of the standard normal: P(Z <= x), Z ~ N(0, 1).

    Definition
        Phi(x) = 0.5 * (1 + erf(x / sqrt(2))), computed with
        math.erf (full double precision, no approximation).

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Complexity
        O(1).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions,
        eq. 7.1.1-7.1.2.

    Examples
        >>> normal_cdf(0.0)
        0.5
        >>> round(normal_cdf(1.959964), 5)
        0.975
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_sf(x: float) -> float:
    """Survival function of the standard normal: P(Z > x).

    Definition
        1 - Phi(x) computed directly via erfc for tail accuracy
        (subtracting Phi(x) from 1 loses precision in the far tail).

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Complexity
        O(1).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.2.

    Examples
        >>> round(normal_sf(1.959964), 5)
        0.025
    """
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def normal_inv_cdf(p: float) -> float:
    """Quantile function of N(0, 1): x with Phi(x) = p.

    Definition
        Acklam's rational approximation (absolute error < 1.15e-9 over
        the full range), exact enough for every statistical cutoff this
        package produces; not a substitute for a high-precision inverse
        in the extreme tails.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if p is not in (0, 1).

    Complexity
        O(1).

    References
        P. Acklam (2003), "An algorithm for computing the inverse
        normal cumulative distribution function" (published online).

    Examples
        >>> round(normal_inv_cdf(0.5), 9)
        0.0
        >>> round(normal_inv_cdf(0.975), 4)
        1.96
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    if p < 0.5:
        return -_normal_inv_body(1.0 - p)
    return _normal_inv_body(p)


def _normal_inv_body(p: float) -> float:
    """Acklam's body for p >= 0.5 (returns positive quantile)."""
    a = (-3.969683028665376e+01, 2.209460984245205e+02,
         -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02,
         -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01,
         -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00)
    d = (7.784695709041462e-03, 3.224671290700398e-01,
         2.445134137142996e+00, 3.754408661907416e+00)

    if p > 0.97575:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )

    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (
        ((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0
    )


def normal_z_score(two_sided_p: float) -> float:
    """Two-sided significance cutoff of the standard normal.

    Definition
        z such that P(|Z| >= z) = p, i.e. z = Phi^-1(1 - p/2).
        z = 1.96 for p = 0.05.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Complexity
        O(1).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.2.

    Examples
        >>> round(normal_z_score(0.05), 4)
        1.96
    """
    return normal_inv_cdf(1.0 - two_sided_p / 2.0)


def normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Density of N(mu, sigma^2).

    Definition
        f(x) = exp(-0.5 z^2) / (sigma sqrt(2 pi)), z = (x - mu)/sigma.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if sigma <= 0.

    Complexity
        O(1).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.2.

    Examples
        >>> round(normal_pdf(0.0), 9)
        0.39894228
        >>> round(normal_pdf(0.0, sigma=2.0), 9)
        0.19947114
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


# ---------------------------------------------------------------------------
# Incomplete beta and Student-t
# ---------------------------------------------------------------------------

def regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b) — regularized incomplete beta function (CDF of the
    Beta(a, b) distribution).

    Definition
        I_x(a,b) = int_0^x t^(a-1) (1-t)^(b-1) dt / B(a,b).

    Implementation
        Numerical-Recipes betai: bt = x^a (1-x)^b / (a B(a,b)) times
        the continued fraction betacf, with the symmetry
        I_x(a,b) = 1 - I_{1-x}(b,a) used whenever
        x > (a+1)/(a+b+2) so the continued fraction always converges
        rapidly (Lentz's method, ~O(sqrt(b)) iterations). The
        continued fraction is stable for ALL parameter ranges — the
        hypergeometric power series this function previously used
        terminates exactly for integer b but cancels catastrophically
        for large b (a real bug: I_0.134(37, 164) came out > 1).

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if a <= 0 or b <= 0.

    Complexity
        O(max_iter) scalar continued-fraction iterations (default
        max_iter = 5000; practically a few dozen to a few hundred).

    References
        Press et al., Numerical Recipes 3rd ed., §6.4.1-6.4.3 (betai
        and betacf); Abramowitz & Stegun eq. 26.5.8.

    Examples
        >>> round(regularized_incomplete_beta(0.5, 2, 2), 9)
        0.5
        >>> round(regularized_incomplete_beta(0.8, 2, 5), 6)
        0.9984
    """
    if a <= 0 or b <= 0:
        raise ValueError("a and b must be > 0")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + a * math.log(x) + b * math.log1p(-x)
    )
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _beta_continued_fraction(a, b, x) / a
    return 1.0 - bt * _beta_continued_fraction(b, a, 1.0 - x) / b


def _beta_continued_fraction(a: float, b: float, x: float, max_iter: int = 5000) -> float:
    """NR 6.4.5 continued fraction for I_x(a, b), evaluated with
    Lentz's method. Returns the fraction whose convergence is fastest
    when x is on the low side of (a+1)/(a+b+2)."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    d = _MIN_FLOAT if abs(d) < _MIN_FLOAT else d
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = _MIN_FLOAT if abs(d) < _MIN_FLOAT else d
        c = 1.0 + aa / c
        c = _MIN_FLOAT if abs(c) < _MIN_FLOAT else c
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = _MIN_FLOAT if abs(d) < _MIN_FLOAT else d
        c = 1.0 + aa / c
        c = _MIN_FLOAT if abs(c) < _MIN_FLOAT else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return h


def student_t_cdf(t: float, df: float) -> float:
    """CDF of Student's t: P(T <= t), T ~ t(df).

    Definition
        F(t) = 1 - 0.5 * I_{df/(df+t^2)}(df/2, 1/2) for t >= 0 (beta
        identity, A&S 26.7.1), with symmetry F(-t) = 1 - F(t). df
        may be fractional (Welch's t-test produces non-integer
        degrees of freedom; the beta kernel accepts any df > 0).

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if df <= 0.

    Complexity
        O(max_iter) on the beta continued-fraction kernel.

    References
        Abramowitz & Stegun (1964), eq. 26.7.1.

    Examples
        >>> round(student_t_cdf(0.0, 10), 9)
        0.5
        >>> round(student_t_cdf(1.812, 10), 4)
        0.95
        >>> round(student_t_cdf(-1.812, 10), 4)
        0.05
    """
    if df <= 0:
        raise ValueError("df must be >= 1")
    if t == 0.0:
        return 0.5
    if t < 0.0:
        return 1.0 - student_t_cdf(-t, df)
    x = df / (df + t * t)
    return 1.0 - 0.5 * regularized_incomplete_beta(x, df / 2.0, 0.5)


def student_t_sf(t: float, df: float) -> float:
    """Survival function of Student's t: P(T > t).

    Definition
        1 - student_t_cdf(t, df) — the one-sided upper tail used by
        the t-tests in this module. df may be fractional.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Complexity
        O(max_iter).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.7.

    Examples
        >>> round(student_t_sf(1.812, 10), 4)
        0.05
    """
    return 1.0 - student_t_cdf(t, df)


def student_t_inv_cdf(p: float, df: float) -> float:
    """Quantile of Student's t (one-sided, lower tail).

    Definition
        Deterministic bisection on student_t_cdf — with 200 halvings
        the bracket width is below float precision. The bracket
        widens exponentially, because heavy tails make fixed
        [-40, 40] wrong at extremes (df=1: t_{0.995} = 63.66).
        df may be fractional.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if p not in (0, 1) or df <= 0.

    Complexity
        O(200) CDF evaluations.

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.7.

    Examples
        >>> round(student_t_inv_cdf(0.95, 10), 3)
        1.812
        >>> round(student_t_inv_cdf(0.995, 1), 2)
        63.66
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    if df <= 0:
        raise ValueError("df must be >= 1")
    if p == 0.5:
        return 0.0
    lo, hi = -40.0, 40.0
    while student_t_cdf(hi, df) < p:
        hi *= 2.0
    while student_t_cdf(lo, df) > p:
        lo *= 2.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if student_t_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Incomplete gamma and chi2
# ---------------------------------------------------------------------------

def _lower_incomplete_gamma(a: float, x: float, max_iter: int = 300) -> float:
    """gamma(a, x)/Gamma(a) — regularized lower incomplete gamma via
    the NR series (for x < a+1) and continued fraction otherwise."""
    if x <= 0.0:
        return 0.0
    if a <= 0:
        raise ValueError("a must be > 0")
    if x < a + 1.0:
        # series
        ap = a
        total = 1.0 / a
        delta = total
        for n in range(max_iter):
            ap += 1.0
            delta *= x / ap
            total += delta
            if abs(delta) < abs(total) * 1e-14:
                break
        return total * math.exp(-x + a * math.log(x) - math.lgamma(a))
    # continued fraction (Lentz)
    b = x + 1.0 - a
    c = 1.0 / _MIN_FLOAT
    d = 1.0 / b if b != 0.0 else _MIN_FLOAT
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = _MIN_FLOAT if abs(d) < _MIN_FLOAT else d
        c = b + an / c
        c = _MIN_FLOAT if abs(c) < _MIN_FLOAT else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-14:
            break
    return 1.0 - math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_cdf(x: float, df: int) -> float:
    """CDF of the chi-squared distribution: P(X <= x), X ~ chi2(df).

    Definition
        chi2(df) = Gamma(shape=df/2, scale=2), hence the x/2 argument —
        a missing factor of two here is the classic wrong-CDF bug.
        df is an integer >= 1.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if df < 1.

    Complexity
        O(max_iter) on the incomplete-gamma kernel (300 iterations,
        usually converging in a few dozen).

    References
        Abramowitz & Stegun (1964), eq. 26.4.1.

    Examples
        >>> round(chi2_cdf(3.8415, 1), 4)
        0.95
        >>> round(chi2_cdf(9.488, 4), 4)
        0.95
        >>> round(chi2_cdf(15.507, 8), 4)
        0.95
    """
    if df < 1:
        raise ValueError("df must be >= 1")
    return _lower_incomplete_gamma(df / 2.0, x / 2.0)


def chi2_p_value(x: float, df: int) -> float:
    """Upper-tail p-value of a chi2 statistic: P(X >= x).

    Definition
        1 - chi2_cdf(x, df) — the tail used by the Jarque-Bera test.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Complexity
        O(max_iter).

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.4.

    Examples
        >>> round(chi2_p_value(3.8415, 1), 4)
        0.05
    """
    return 1.0 - chi2_cdf(x, df)


def chi2_inv_cdf(p: float, df: int) -> float:
    """Quantile of chi2: x with P(X <= x) = p.

    Definition
        Deterministic bisection on chi2_cdf, same policy as
        student_t_inv_cdf, with the upper bracket scaled to the mean
        plus ~20 standard deviations so even extreme quantiles are
        bracketed.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if p not in (0, 1) or df < 1.

    Complexity
        O(300) CDF evaluations.

    References
        Abramowitz & Stegun (1964), Handbook of Mathematical Functions, §26.4.

    Examples
        >>> round(chi2_inv_cdf(0.95, 4), 3)
        9.488
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    lo, hi = 0.0, max(100.0, df + 20.0 * math.sqrt(2.0 * df) + 100.0)
    if chi2_cdf(hi, df) < p:
        hi *= 4.0
    for _ in range(300):
        mid = 0.5 * (lo + hi)
        if chi2_cdf(mid, df) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def variance(x: np.ndarray, ddof: int = 1) -> float:
    """Sample variance of x (NaN/Inf entries dropped).

    Definition
        s^2 = sum((x - mean)^2) / (n - ddof) over finite observations.
        ddof=1 (default) gives the unbiased estimator.

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if fewer than 2 finite observations.

    Complexity
        O(n) time, O(n) memory.

    References
        Casella & Berger (2002), Statistical Inference, 2nd ed. (sample moments).

    Examples
        >>> import numpy as np
        >>> variance(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        2.5
    """
    x = finite_only(x, "x")
    check_min(x, 2, "variance")
    return float(np.var(x, ddof=ddof))


def covariance(a: np.ndarray, b: np.ndarray, ddof: int = 1) -> float:
    """Sample covariance of two aligned series.

    Definition
        cov(a, b) over the pairs where both entries are finite.
        ddof=1 (default) gives the unbiased estimator.

    NaN policy
        Observations where either input is non-finite are dropped pairwise; the documented minimum finite pair count is enforced (ValueError otherwise).

    Raises
        ValueError if a and b differ in length, or fewer than 2
        jointly-finite pairs.

    Complexity
        O(n) time, O(n) memory.

    References
        Casella & Berger (2002), Statistical Inference, 2nd ed. (sample moments).

    Examples
        >>> import numpy as np
        >>> x = np.array([1.0, 2.0, 3.0])
        >>> covariance(x, x)
        1.0
        >>> covariance(x, -x)
        -1.0
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    m = np.isfinite(a) & np.isfinite(b)
    check_min(a[m], 2, "covariance")
    return float(np.cov(a[m], b[m], ddof=ddof)[0, 1])


def covariance_matrix(x: np.ndarray, ddof: int = 1) -> np.ndarray:
    """Sample covariance matrix of a (n_obs, n_vars) array.

    Definition
        One variable per COLUMN (the convention financial data
        naturally uses: each column a return series). A 1-D input is
        treated as a single variable and returns a 1x1 matrix.

    NaN policy
        NaN entries propagate into the covariance matrix (numpy cov semantics) — drop or impute columns before calling.

    Raises
        ValueError if x is neither 1-D nor 2-D.

    Complexity
        O(n * k^2) time for n observations and k variables.

    References
        Casella & Berger (2002), Statistical Inference, 2nd ed. (sample moments).

    Examples
        >>> import numpy as np
        >>> m = covariance_matrix(np.array([[1.0, 1.0],
        ...                                 [2.0, 2.0],
        ...                                 [3.0, 3.0]]))
        >>> np.testing.assert_allclose(m, [[1.0, 1.0], [1.0, 1.0]])
    """
    arr = np.asarray(x, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    elif arr.ndim != 2:
        raise ValueError("x must be 1-D or 2-D (n_obs, n_vars)")
    cov = np.cov(arr, rowvar=False, ddof=ddof)
    return np.atleast_2d(cov)


def coefficient_of_variation(x: np.ndarray) -> float:
    """Coefficient of variation: sample std / |mean|.

    Definition
        CV = s / |mean| — dimensionless dispersion, meaningful only
        for strictly positive means; returns NaN when the mean is zero
        or non-finite. ddof=1 both moments.

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if fewer than 2 finite observations.

    Complexity
        O(n) time, O(n) memory.

    References
        Casella & Berger (2002), Statistical Inference, 2nd ed. (sample moments).

    Examples
        >>> import numpy as np
        >>> coefficient_of_variation(np.array([2.0, 4.0, 6.0]))
        0.5
    """
    x = finite_only(x, "x")
    check_min(x, 2, "coefficient_of_variation")
    m = float(np.mean(x))
    if m == 0.0 or not np.isfinite(m):
        return float("nan")
    return float(np.std(x, ddof=1) / abs(m))


def empirical_cdf(x: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Empirical CDF of the data at requested points.

    Definition
        F(v) = (# observations <= v) / n evaluated at each entry of
        `values` (ties counted, hence <=). The model-free distribution
        check — what the data itself says before any parametric
        assumption.

    NaN policy
        NaN/Inf in the data are dropped before building the ECDF; a NaN query value returns 0.0 (no finite observation is <= NaN).

    Raises
        ValueError if x has no finite observations.

    Complexity
        O(n log n) sort + O(k log n) lookups.

    References
        van der Vaart (1998), Asymptotic Statistics, Ch. 19 (empirical distribution function).

    Examples
        >>> import numpy as np
        >>> empirical_cdf(np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
        ...               np.array([3.0]))
        array([0.6])
    """
    x = finite_only(x, "x")
    check_min(x, 1, "empirical_cdf")
    values = as_float_array(values, "values")
    sorted_x = np.sort(x)
    return np.searchsorted(sorted_x, values, side="right").astype(float) / len(sorted_x)


def mean_confidence_interval(
    x: np.ndarray, confidence: float = 0.95
) -> Tuple[float, float, float]:
    """(mean, lower, upper) t-based confidence interval for the mean.

    Definition
        mean +- t_{1-alpha/2, n-1} * s / sqrt(n) — t-distributed
        because small samples are the norm in edge research. A
        zero-variance sample returns (m, m, m).

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if fewer than 2 finite observations.

    Complexity
        O(n) time, O(n) memory.

    References
        NIST/SEMATECH e-Handbook of Statistical Methods, §1.3.5.2.

    Examples
        >>> import numpy as np
        >>> m, lo, hi = mean_confidence_interval(np.arange(1.0, 11.0))
        >>> round(m, 1)
        5.5
        >>> lo < 5.5 < hi
        True
    """
    x = finite_only(x, "x")
    n = len(x)
    check_min(x, 2, "mean_confidence_interval")
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    if s == 0.0:
        return m, m, m
    t = student_t_inv_cdf(0.5 + confidence / 2.0, n - 1)
    half = t * s / math.sqrt(n)
    return m, m - half, m + half


def two_sample_t_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float, float]:
    """Welch's two-sample t-test (unequal variances).

    Definition
        t = (mean_a - mean_b) / sqrt(s_a^2/n_a + s_b^2/n_b) with
        Welch-Satterthwaite degrees of freedom; returns (t, df,
        two-sided p). When both samples are constant the test is
        degenerate and returns (0.0, n_a + n_b - 2, 1.0).

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if either sample has fewer than 2 finite
        observations.

    Complexity
        O(n_a + n_b) time, O(n) memory.

    References
        B. L. Welch (1947), "The generalization of Student's problem",
        Biometrika 34.

    Examples
        >>> import numpy as np
        >>> t, df, p = two_sample_t_test(np.arange(1.0, 6.0),
        ...                              np.array([1.0] * 5))
        >>> round(t, 4)
        2.8284
    """
    a = finite_only(a, "a")
    b = finite_only(b, "b")
    check_min(a, 2, "two_sample_t_test")
    check_min(b, 2, "two_sample_t_test")
    na, nb = len(a), len(b)
    ma, mb = float(np.mean(a)), float(np.mean(b))
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    if va == 0.0 and vb == 0.0:
        return 0.0, float(na + nb - 2), 1.0
    se = math.sqrt(va / na + vb / nb)
    t = (ma - mb) / se
    df = (va / na + vb / nb) ** 2 / (
        (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    )
    p = 2.0 * student_t_sf(abs(t), df)
    return t, df, p


def paired_t_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Paired (two-sided) t-test on differences d = a - b.

    Definition
        t = mean(d) / (s_d / sqrt(n)) on the finite pairwise
        differences; returns (t, p). A zero-variance difference series
        returns (0.0, 1.0).

    NaN policy
        Observations where either input is non-finite are dropped pairwise; the documented minimum finite pair count is enforced (ValueError otherwise).

    Raises
        ValueError if a and b differ in length, or fewer than 2 finite
        pairs.

    Complexity
        O(n) time, O(n) memory.

    References
        Casella & Berger (2002), Statistical Inference, 2nd ed. (matched-pairs t-test).

    Examples
        >>> import numpy as np
        >>> t, p = paired_t_test(np.array([2.0, 3.0, 4.0]),
        ...                      np.array([1.0, 1.0, 1.0]))
        >>> round(t, 4)
        3.4641
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    d = (a - b)[np.isfinite(a - b)]
    check_min(d, 2, "paired_t_test")
    n = len(d)
    md = float(np.mean(d))
    sd = float(np.std(d, ddof=1))
    if sd == 0.0:
        return 0.0, 1.0
    t = md / (sd / math.sqrt(n))
    p = 2.0 * student_t_sf(abs(t), n - 1)
    return t, p


def skewness(x: np.ndarray) -> float:
    """Sample skewness with the small-sample bias correction.

    Definition
        g1 * sqrt(n(n-1))/(n-2) where g1 = m3/m2^1.5 (Joanes & Gill
        G1, "adjusted Fisher-Pearson"). NaN for n < 3 or zero
        variance; 0 for any symmetric distribution.

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if x has no finite observations. NaN for n < 3 or
        zero variance.

    Complexity
        O(n) time, O(n) memory.

    References
        Joanes & Gill (1998), "Comparing measures of sample skewness
        and kurtosis", The Statistician 47.

    Examples
        >>> import numpy as np
        >>> skewness(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
        0.0
    """
    x = finite_only(x, "x")
    n = len(x)
    check_min(x, 1, "skewness")
    if n < 3:
        return float("nan")
    m2 = float(np.mean((x - np.mean(x)) ** 2))
    m3 = float(np.mean((x - np.mean(x)) ** 3))
    if m2 == 0.0:
        return float("nan")
    g1 = m3 / m2 ** 1.5
    return g1 * math.sqrt(n * (n - 1)) / (n - 2)


def excess_kurtosis(x: np.ndarray) -> float:
    """Sample excess kurtosis (normal distribution => 0).

    Definition
        (n-1)/((n-2)(n-3)) * ((n+1) g2 + 6) where g2 = m4/m2^2 - 3
        (Joanes & Gill G2). NaN for n < 4 or zero variance.

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if x has no finite observations. NaN for n < 4 or
        zero variance.

    Complexity
        O(n) time, O(n) memory.

    References
        Joanes & Gill (1998), "Comparing measures of sample skewness
        and kurtosis", The Statistician 47.

    Examples
        >>> import numpy as np
        >>> abs(excess_kurtosis(np.arange(1.0, 9.0))) < 1.5
        True
    """
    x = finite_only(x, "x")
    n = len(x)
    check_min(x, 1, "excess_kurtosis")
    if n < 4:
        return float("nan")
    m2 = float(np.mean((x - np.mean(x)) ** 2))
    m4 = float(np.mean((x - np.mean(x)) ** 4))
    if m2 == 0.0:
        return float("nan")
    g2 = m4 / m2 ** 2 - 3.0
    return (n - 1) / ((n - 2) * (n - 3)) * ((n + 1) * g2 + 6.0)


def jarque_bera(x: np.ndarray) -> Tuple[float, float]:
    """Jarque-Bera normality test: (JB statistic, p-value).

    Definition
        JB = n/6 * (S^2 + (K-3)^2/4) with the RAW (uncorrected) third
        and fourth central moments S = m3/m2^1.5 and K = m4/m2^2 —
        the textbook definition (Jarque & Bera 1980) and the one scipy
        validates against. Note the test statistic uses raw moments
        even though this module's public skewness/excess_kurtosis
        apply the small-sample corrections; the difference matters
        only for tiny samples, where JB is asymptotic anyway.
        Returns (nan, nan) when the sample is too small for the
        moments.

    NaN policy
        NaN/Inf entries are dropped before computation; the documented minimum finite count is enforced (ValueError otherwise).

    Raises
        ValueError if fewer than 4 finite observations.

    Complexity
        O(n) time, O(n) memory.

    References
        Jarque & Bera (1980), "Efficient tests for normality,
        homoscedasticity and serial independence", Economics Letters 6.

    Examples
        >>> import numpy as np
        >>> jb, p = jarque_bera(np.array([1.0, 2.0, 3.0, 4.0, 5.0,
        ...                               6.0, 7.0, 8.0, 9.0, 10.0]))
        >>> p > 0.05
        True
    """
    x = finite_only(x, "x")
    check_min(x, 4, "jarque_bera")
    n = len(x)
    m2 = float(np.mean((x - np.mean(x)) ** 2))
    m3 = float(np.mean((x - np.mean(x)) ** 3))
    m4 = float(np.mean((x - np.mean(x)) ** 4))
    if m2 == 0.0:
        return float("nan"), float("nan")
    s = m3 / m2 ** 1.5
    k = m4 / m2 ** 2
    jb = n / 6.0 * (s * s + (k - 3.0) ** 2 / 4.0)
    return jb, chi2_p_value(jb, 2)


def pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation coefficient of two aligned series.

    Definition
        cov(a, b) / (s_a s_b) over the jointly finite pairs. Returns
        NaN when either series has zero variance (correlation is
        undefined). Note: this function does NOT rank — for monotone
        association use spearman_correlation.

    NaN policy
        Observations where either input is non-finite are dropped pairwise; the documented minimum finite pair count is enforced (ValueError otherwise).

    Raises
        ValueError if a and b differ in length, or fewer than 2
        jointly-finite pairs.

    Complexity
        O(n) time, O(n) memory.

    References
        K. Pearson (1895), "Notes on regression and inheritance",
        Proc. R. Soc. 58.

    Examples
        >>> import numpy as np
        >>> x = np.arange(1.0, 11.0)
        >>> round(pearson_correlation(x, x), 12)
        1.0
        >>> round(pearson_correlation(x, -x), 12)
        -1.0
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    m = np.isfinite(a) & np.isfinite(b)
    check_min(a[m], 2, "pearson_correlation")
    a = a[m]
    b = b[m]
    sa = float(np.std(a, ddof=1))
    sb = float(np.std(b, ddof=1))
    if sa == 0.0 or sb == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spearman_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation: Pearson correlation of the ranks.

    Definition
        rho = pearson(rank(a), rank(b)) with average ranks for ties —
        a measure of monotone association that is robust to outliers
        and nonlinearity.

    NaN policy
        Observations where either input is non-finite are dropped pairwise; the documented minimum finite pair count is enforced (ValueError otherwise).

    Raises
        ValueError if a and b differ in length, or fewer than 2
        jointly-finite pairs.

    Complexity
        O(n log n) time (two sorts), O(n) memory.

    References
        C. Spearman (1904), "The proof and measurement of association
        between two things", American Journal of Psychology 15.

    References
        Gibbons & Chakraborti (2003), Nonparametric Statistical Inference, 4th ed. (rank correlation).

    Examples
        >>> import numpy as np
        >>> x = np.arange(1.0, 11.0)
        >>> round(spearman_correlation(x, x ** 2), 12)
        1.0
    """
    a = as_float_array(a, "a")
    b = as_float_array(b, "b")
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    m = np.isfinite(a) & np.isfinite(b)
    check_min(a[m], 2, "spearman_correlation")
    return pearson_correlation(_ranks(a[m]), _ranks(b[m]))


def _ranks(x: np.ndarray) -> np.ndarray:
    """Average ranks (1-based) with ties averaged."""
    order = np.argsort(np.argsort(x))
    return order.astype(float) + 1.0


def sharpe_standard_error(sharpe: float, n: int) -> float:
    """Asymptotic standard error of an estimated Sharpe ratio.

    Definition
        sqrt((1 + 0.5 * S^2) / n) (Lo 2002): the scale of sampling
        noise in a Sharpe estimate from n observations. The tool behind
        "is this Sharpe just noise?" on small samples.

    NaN policy
        None — scalar math; NaN flows through the formulas unless caught by the documented range validation.

    Raises
        ValueError if n < 2.

    Complexity
        O(1).

    References
        A. Lo (2002), "The Statistics of Sharpe Ratios", Financial
        Analysts Journal 58(4), eq. 16.

    Examples
        >>> round(sharpe_standard_error(0.5, 100), 6)
        0.106066
    """
    if n < 2:
        raise ValueError("n must be >= 2")
    return math.sqrt((1.0 + 0.5 * sharpe * sharpe) / n)
