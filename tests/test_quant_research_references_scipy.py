"""Reference-validation tests against scipy (optional dependency).

Every distribution kernel quant_research implements by hand (normal,
Student-t, chi2, beta, binomial) must agree with scipy.stats on dense
grids — the strongest possible check that the scipy-free implementations
are numerically correct. The whole file skips if scipy is not installed
(pytest.importorskip); the package itself never imports scipy.
"""

import math

import numpy as np
import pytest

scipy_stats = pytest.importorskip("scipy.stats")

from quant_research import probability, resampling, statistics, timeseries  # noqa: E402


# ---------------------------------------------------------------------------
# Normal
# ---------------------------------------------------------------------------

def test_normal_cdf_matches_scipy_grid():
    for x in np.linspace(-6.0, 6.0, 61):
        assert statistics.normal_cdf(x) == pytest.approx(
            float(scipy_stats.norm.cdf(x)), abs=1e-12
        )


def test_normal_sf_matches_scipy_grid():
    for x in np.linspace(-6.0, 6.0, 61):
        assert statistics.normal_sf(x) == pytest.approx(
            float(scipy_stats.norm.sf(x)), abs=1e-12
        )


def test_normal_inv_cdf_matches_scipy_grid():
    # Acklam's rational approximation documents max error 1.15e-9;
    # near its branch boundary (p ~ 0.025) the absolute error reaches
    # ~2e-9, so 5e-9 covers the full grid with margin — still 5
    # orders of magnitude below any use this package makes of it.
    for p in np.linspace(0.001, 0.999, 41):
        assert statistics.normal_inv_cdf(p) == pytest.approx(
            float(scipy_stats.norm.ppf(p)), abs=5e-9
        )


def test_normal_pdf_matches_scipy():
    for x in np.linspace(-4.0, 4.0, 33):
        assert statistics.normal_pdf(x) == pytest.approx(
            float(scipy_stats.norm.pdf(x)), rel=1e-12
        )
        assert statistics.normal_pdf(x, mu=2.0, sigma=0.5) == pytest.approx(
            float(scipy_stats.norm.pdf(x, loc=2.0, scale=0.5)), rel=1e-12
        )


# ---------------------------------------------------------------------------
# Student-t
# ---------------------------------------------------------------------------

def test_student_t_cdf_matches_scipy_grid():
    for df in (1, 2, 5, 10, 30, 100):
        for t in np.linspace(-15.0, 15.0, 61):
            assert statistics.student_t_cdf(t, df) == pytest.approx(
                float(scipy_stats.t.cdf(t, df)), abs=1e-10
            )


def test_student_t_inv_cdf_matches_scipy_grid():
    for df in (1, 2, 5, 10, 30):
        for p in (0.01, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 0.995):
            assert statistics.student_t_inv_cdf(p, df) == pytest.approx(
                float(scipy_stats.t.ppf(p, df)), abs=1e-6
            )


def test_student_t_sf_matches_scipy():
    for df in (1, 10):
        for t in (0.5, 2.0, 5.0):
            assert statistics.student_t_sf(t, df) == pytest.approx(
                float(scipy_stats.t.sf(t, df)), abs=1e-10
            )


# ---------------------------------------------------------------------------
# chi2
# ---------------------------------------------------------------------------

def test_chi2_cdf_matches_scipy_grid():
    for df in (1, 2, 4, 8, 30, 100):
        for x in np.linspace(0.1, 3.0 * df, 41):
            assert statistics.chi2_cdf(x, df) == pytest.approx(
                float(scipy_stats.chi2.cdf(x, df)), abs=1e-9
            )


def test_chi2_inv_cdf_matches_scipy_grid():
    for df in (1, 4, 8, 30):
        for p in (0.01, 0.05, 0.5, 0.95, 0.99):
            assert statistics.chi2_inv_cdf(p, df) == pytest.approx(
                float(scipy_stats.chi2.ppf(p, df)), abs=1e-6
            )


# ---------------------------------------------------------------------------
# Beta (and the Clopper-Pearson binomial CI it backs)
# ---------------------------------------------------------------------------

def test_beta_cdf_matches_scipy_grid():
    # Includes the large-parameter cases (37, 164), (200, 37) that
    # catastrophically failed under the old hypergeometric-series
    # kernel (I_0.134(37, 164) came out > 1) — regression pin.
    for (a, b) in [
        (0.5, 0.5),
        (1.0, 1.0),
        (2.0, 5.0),
        (5.0, 2.0),
        (9.0, 3.0),
        (37.0, 164.0),
        (164.0, 37.0),
        (200.0, 37.0),
        (100.0, 100.0),
    ]:
        for x in np.linspace(0.01, 0.99, 41):
            assert probability.beta_cdf(x, a, b) == pytest.approx(
                float(scipy_stats.beta.cdf(x, a, b)), abs=1e-10
            )


def test_beta_inv_cdf_matches_scipy_grid():
    for (a, b) in [(0.5, 0.5), (2.0, 5.0), (9.0, 3.0)]:
        for p in (0.01, 0.05, 0.5, 0.95, 0.99):
            assert probability.beta_inv_cdf(p, a, b) == pytest.approx(
                float(scipy_stats.beta.ppf(p, a, b)), abs=1e-6
            )


def test_binomial_ci_matches_clopper_pearson_formula():
    # The exact interval: [Beta^-1(alpha/2; k, n-k+1),
    # Beta^-1(1-alpha/2; k+1, n-k)] with the 0/1 boundary conventions.
    for (k, n) in [(0, 10), (2, 10), (5, 10), (8, 10), (10, 10), (37, 200)]:
        lo, hi = probability.binomial_ci(k, n, confidence=0.95)
        alpha = 0.025
        ref_lo = 0.0 if k == 0 else float(
            scipy_stats.beta.ppf(alpha, k, n - k + 1)
        )
        ref_hi = 1.0 if k == n else float(
            scipy_stats.beta.ppf(1.0 - alpha, k + 1, n - k)
        )
        assert lo == pytest.approx(ref_lo, abs=1e-9)
        assert hi == pytest.approx(ref_hi, abs=1e-9)


def test_binomial_pmf_cdf_match_scipy():
    for (n, p) in [(10, 0.3), (50, 0.5), (100, 0.9)]:
        for k in range(0, n + 1, max(1, n // 10)):
            assert probability.binomial_pmf(k, n, p) == pytest.approx(
                float(scipy_stats.binom.pmf(k, n, p)), rel=1e-12
            )
            assert probability.binomial_cdf(k, n, p) == pytest.approx(
                float(scipy_stats.binom.cdf(k, n, p)), abs=1e-12
            )


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def test_skewness_matches_scipy():
    rng = np.random.default_rng(3)
    x = rng.gamma(2.0, 1.0, 500)
    assert statistics.skewness(x) == pytest.approx(
        float(scipy_stats.skew(x, bias=False)), rel=1e-9
    )


def test_excess_kurtosis_matches_scipy():
    rng = np.random.default_rng(3)
    x = rng.gamma(2.0, 1.0, 500)
    assert statistics.excess_kurtosis(x) == pytest.approx(
        float(scipy_stats.kurtosis(x, fisher=True, bias=False)), rel=1e-9
    )


def test_coefficient_of_variation_matches_scipy():
    assert statistics.coefficient_of_variation(X := np.arange(1.0, 51.0)) == (
        pytest.approx(float(scipy_stats.variation(X, ddof=1)), rel=1e-12)
    )


def test_jarque_bera_matches_scipy():
    rng = np.random.default_rng(4)
    for x in (rng.normal(0.0, 1.0, 500), rng.exponential(1.0, 500)):
        jb, p = statistics.jarque_bera(x)
        ref = scipy_stats.jarque_bera(x)
        assert jb == pytest.approx(float(ref.statistic), rel=1e-6)
        assert p == pytest.approx(float(ref.pvalue), rel=1e-4)


def test_spearman_correlation_matches_scipy():
    rng = np.random.default_rng(5)
    x = rng.normal(0.0, 1.0, 200)
    y = x ** 3 + rng.normal(0.0, 0.5, 200)
    assert statistics.spearman_correlation(x, y) == pytest.approx(
        float(scipy_stats.spearmanr(x, y).statistic), rel=1e-12
    )


def test_mean_confidence_interval_matches_scipy_t_interval():
    rng = np.random.default_rng(6)
    x = rng.normal(0.0, 1.0, 25)
    m, lo, hi = statistics.mean_confidence_interval(x, confidence=0.95)
    ref_lo, ref_hi = scipy_stats.t.interval(
        0.95, len(x) - 1, loc=float(np.mean(x)), scale=float(np.std(x, ddof=1)) / math.sqrt(len(x))
    )
    assert lo == pytest.approx(ref_lo, rel=1e-9)
    assert hi == pytest.approx(ref_hi, rel=1e-9)


def test_two_sample_t_test_matches_scipy_welch():
    rng = np.random.default_rng(7)
    a = rng.normal(0.0, 1.0, 40)
    b = rng.normal(0.3, 1.5, 45)
    t, df, p = statistics.two_sample_t_test(a, b)
    ref = scipy_stats.ttest_ind(a, b, equal_var=False)
    assert t == pytest.approx(float(ref.statistic), rel=1e-9)
    assert df == pytest.approx(float(ref.df), rel=1e-9)
    assert p == pytest.approx(float(ref.pvalue), rel=1e-9)


def test_paired_t_test_matches_scipy():
    rng = np.random.default_rng(8)
    a = rng.normal(0.0, 1.0, 30)
    b = a + rng.normal(0.2, 0.5, 30)
    t, p = statistics.paired_t_test(a, b)
    ref = scipy_stats.ttest_rel(a, b)
    assert t == pytest.approx(float(ref.statistic), rel=1e-9)
    assert p == pytest.approx(float(ref.pvalue), rel=1e-9)


def test_normal_power_matches_scipy_derivation():
    # Reference: 1 - Phi(z_{1-alpha/2} - effect / SE) computed with
    # scipy's own normal (a pure scipy computation, not our kernels).
    for (effect, sigma, n) in [(0.2, 1.0, 100), (0.5, 1.0, 100), (0.1, 2.0, 50)]:
        se = sigma / math.sqrt(n)
        ref = 1.0 - scipy_stats.norm.cdf(
            scipy_stats.norm.ppf(0.975) - effect / se
        )
        assert probability.normal_power_simple(effect, sigma, n) == pytest.approx(
            float(ref), abs=1e-9
        )
