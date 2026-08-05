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
  t_{0.995}(10)=3.169
  chi2_{0.95}(1)=3.8415, chi2_{0.95}(4)=9.488, chi2_{0.95}(8)=15.507
  Z_{0.975}=1.959964
"""

import math
from typing import Tuple

import numpy as np

from .core import required_length

_MIN_FLOAT = 1e-300


# ---------------------------------------------------------------------------
# Normal distribution
# ---------------------------------------------------------------------------

def normal_cdf(x: float) -> float:
    """P(Z <= x) for Z ~ N(0, 1)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def normal_sf(x: float) -> float:
    """P(Z > x) for Z ~ N(0, 1)."""
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def normal_inv_cdf(p: float) -> float:
    """Quantile function of N(0,1). Acklam's rational approximation
    (error < 1.15e-9 over the full range)."""
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

    if p < 0.02425:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )
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
    """Z such that P(|Z| >= z) = p (two-sided significance cutoff)."""
    return normal_inv_cdf(1.0 - two_sided_p / 2.0)


# ---------------------------------------------------------------------------
# Incomplete beta and Student-t
# ---------------------------------------------------------------------------

def regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """I_x(a, b) — regularized incomplete beta function (CDF of the
    Beta(a, b) distribution).

    Implementation: the hypergeometric identity
    I_x(a, b) = x^a/(a B(a,b)) * 2F1(a, 1-b; a+1; x),
    evaluated by its (terminating for integer b) power series, with the
    symmetry I_x(a,b) = 1 - I_{1-x}(b,a) used whenever x > 0.5 so the
    series argument never exceeds 0.5 (geometric convergence, no
    continued fractions needed).

    Exactness note: for integer a, b (the binomial CI use case) the
    series terminates, so results are exact to machine precision.
    """
    if a <= 0 or b <= 0:
        raise ValueError("a and b must be > 0")
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    if x <= 0.5:
        lnbt = (
            math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
            + a * math.log(x)
        )
        return math.exp(lnbt) * _hypergeometric_series(x, a, b) / a
    y = 1.0 - x
    lnbt = (
        math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
        + b * math.log(y)
    )
    return 1.0 - math.exp(lnbt) * _hypergeometric_series(y, b, a) / b


def _hypergeometric_series(x: float, a: float, b: float, max_iter: int = 5000) -> float:
    """Partial sum of 2F1(a, 1-b; a+1; x). Term ratio
    (a+n)(1-b+n) / ((a+1+n)(n+1)) * x; for integer b the series
    terminates exactly at n = b-1."""
    total = 1.0
    term = 1.0
    for n in range(max_iter):
        term *= (a + n) * (1.0 - b + n) / ((a + 1.0 + n) * (n + 1.0)) * x
        total += term
        if abs(term) <= abs(total) * 1e-15:
            break
    return total


def student_t_cdf(t: float, df: int) -> float:
    """P(T <= t) for T ~ Student-t with df degrees of freedom. Uses the
    beta identity: F(t) = 1 - 0.5 * I_{df/(df+t^2)}(df/2, 1/2), t >= 0."""
    if df <= 0:
        raise ValueError("df must be >= 1")
    if t == 0.0:
        return 0.5
    if t < 0.0:
        return 1.0 - student_t_cdf(-t, df)
    x = df / (df + t * t)
    return 1.0 - 0.5 * regularized_incomplete_beta(x, df / 2.0, 0.5)


def student_t_inv_cdf(p: float, df: int) -> float:
    """Quantile of Student-t (one-sided, lower tail). Deterministic
    bisection on student_t_cdf — with 200 halvings the bracket width is
    below float precision. The bracket widens exponentially, because
    heavy tails make fixed [-40, 40] wrong at extremes (df=1:
    t_{0.995} = 63.66)."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
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
    """P(X <= x) for X ~ chi2 with df degrees of freedom. chi2_df =
    Gamma(shape=df/2, scale=2), hence the x/2 argument — a missing
    factor of two here is the classic wrong-CDF bug."""
    if df < 1:
        raise ValueError("df must be >= 1")
    return _lower_incomplete_gamma(df / 2.0, x / 2.0)


def chi2_p_value(x: float, df: int) -> float:
    """Upper-tail p-value of a chi2 statistic: P(X >= x)."""
    return 1.0 - chi2_cdf(x, df)


def chi2_inv_cdf(p: float, df: int) -> float:
    """Quantile of chi2. Bisection, same policy as student_t_inv_cdf."""
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
    """Sample variance of x (NaN entries dropped)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    required_length("variance", x, 2)
    return float(np.var(x, ddof=ddof))


def covariance(a: np.ndarray, b: np.ndarray, ddof: int = 1) -> float:
    """Sample covariance of two aligned series."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    m = np.isfinite(a) & np.isfinite(b)
    required_length("covariance", a[m], 2)
    return float(np.cov(a[m], b[m], ddof=ddof)[0, 1])


def covariance_matrix(x: np.ndarray, ddof: int = 1) -> np.ndarray:
    """Sample covariance matrix of a (n_obs, n_vars) array — one
    variable per COLUMN (the convention financial data naturally uses:
    each column a return series)."""
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    if x.ndim != 2:
        raise ValueError("x must be 1-D or 2-D (n_obs, n_vars)")
    return np.cov(x, rowvar=False, ddof=ddof)


def coefficient_of_variation(x: np.ndarray) -> float:
    """std/mean — dimensionless dispersion, meaningful only for
    strictly positive means. NaN otherwise."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    required_length("coefficient_of_variation", x, 2)
    m = float(np.mean(x))
    if m == 0.0 or not np.isfinite(m):
        return float("nan")
    return float(np.std(x, ddof=1) / abs(m))


def normal_pdf(x: float, mu: float = 0.0, sigma: float = 1.0) -> float:
    """Density of N(mu, sigma^2)."""
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    z = (x - mu) / sigma
    return math.exp(-0.5 * z * z) / (sigma * math.sqrt(2.0 * math.pi))


def empirical_cdf(x: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Empirical CDF: F(v) = fraction of observations <= v, evaluated
    at each requested value. The model-free distribution check — what
    the data itself says before any parametric assumption."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    required_length("empirical_cdf", x, 1)
    values = np.asarray(values, dtype=float)
    sorted_x = np.sort(x)
    return np.searchsorted(sorted_x, values, side="right").astype(float) / len(sorted_x)


def mean_confidence_interval(
    x: np.ndarray, confidence: float = 0.95
) -> Tuple[float, float, float]:
    """(mean, lower, upper) t-based confidence interval for the mean of x.
    t-distributed because small samples are the norm in edge research."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    required_length("mean_confidence_interval", x, 2)
    m = float(np.mean(x))
    s = float(np.std(x, ddof=1))
    if s == 0.0:
        return m, m, m
    t = student_t_inv_cdf(0.5 + confidence / 2.0, n - 1)
    half = t * s / math.sqrt(n)
    return m, m - half, m + half


def two_sample_t_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float, float]:
    """Welch's two-sample t-test (unequal variances): returns
    (t, df, two-sided p)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    required_length("two_sample_t_test", a, 2)
    required_length("two_sample_t_test", b, 2)
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
    p = 2.0 * student_t_sf(abs(t), int(round(df)))
    return t, df, p


def paired_t_test(a: np.ndarray, b: np.ndarray) -> Tuple[float, float]:
    """Paired (two-sided) t-test on differences d = a - b: (t, p)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    d = (a - b)[np.isfinite(a - b)]
    required_length("paired_t_test", d, 2)
    n = len(d)
    md = float(np.mean(d))
    sd = float(np.std(d, ddof=1))
    if sd == 0.0:
        return 0.0, 1.0
    t = md / (sd / math.sqrt(n))
    p = 2.0 * student_t_sf(abs(t), n - 1)
    return t, p


def student_t_sf(t: float, df: int) -> float:
    """P(T > t) one-sided upper tail."""
    return 1.0 - student_t_cdf(t, df)


def skewness(x: np.ndarray) -> float:
    """Sample skewness (unbiased correction: g1 * sqrt(n(n-1))/(n-2)
    for n >= 3, else NaN)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return float("nan")
    m2 = float(np.mean((x - np.mean(x)) ** 2))
    m3 = float(np.mean((x - np.mean(x)) ** 3))
    if m2 == 0.0:
        return float("nan")
    g1 = m3 / m2 ** 1.5
    return g1 * math.sqrt(n * (n - 1)) / (n - 2)


def excess_kurtosis(x: np.ndarray) -> float:
    """Sample excess kurtosis (normal distribution => 0)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 4:
        return float("nan")
    m2 = float(np.mean((x - np.mean(x)) ** 2))
    m4 = float(np.mean((x - np.mean(x)) ** 4))
    if m2 == 0.0:
        return float("nan")
    g2 = m4 / m2 ** 2 - 3.0
    return (n - 1) / ((n - 2) * (n - 3)) * ((n + 1) * g2 + 6.0)


def jarque_bera(x: np.ndarray) -> Tuple[float, float]:
    """(JB statistic, p-value) normality test. JB = n/6 * (S^2 +
    (K-3)^2/4), asymptotically chi2(2)."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    required_length("jarque_bera", x, 4)
    n = len(x)
    s = skewness(x)
    k = excess_kurtosis(x)
    if s != s or k != k:
        return float("nan"), float("nan")
    jb = n / 6.0 * (s * s + (k * k) / 4.0)
    return jb, chi2_p_value(jb, 2)


def pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation coefficient of two aligned series."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    sa = float(np.std(a, ddof=1))
    sb = float(np.std(b, ddof=1))
    if sa == 0.0 or sb == 0.0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def spearman_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation: Pearson correlation of the ranks
    (average ranks for ties)."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if len(a) != len(b):
        raise ValueError("a and b must have equal length")
    return pearson_correlation(_ranks(a), _ranks(b))


def _ranks(x: np.ndarray) -> np.ndarray:
    """Average ranks (1-based) with ties averaged."""
    order = np.argsort(np.argsort(x))
    return order.astype(float) + 1.0


def sharpe_standard_error(sharpe: float, n: int) -> float:
    """Lo (2002) asymptotic standard error of an estimated Sharpe ratio:
    sqrt((1 + 0.5*S^2) / n). The tool behind "is this Sharpe just
    noise?" on small samples."""
    if n < 2:
        raise ValueError("n must be >= 2")
    return math.sqrt((1.0 + 0.5 * sharpe * sharpe) / n)
