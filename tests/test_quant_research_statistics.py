"""Tests for quant_research.statistics — distributions, tests, descriptives.

Reference values are published table values (student-t, chi2) or closed
forms; any drift of the kernels breaks these tests.
"""

import math

import numpy as np
import pytest

from quant_research import statistics as st


def test_normal_cdf_known_points():
    assert st.normal_cdf(0.0) == pytest.approx(0.5, abs=1e-12)
    assert st.normal_cdf(1.959964) == pytest.approx(0.975, abs=1e-5)
    assert st.normal_sf(1.959964) == pytest.approx(0.025, abs=1e-5)


def test_normal_inv_cdf_known_points():
    assert st.normal_inv_cdf(0.5) == pytest.approx(0.0, abs=1e-9)
    assert st.normal_inv_cdf(0.975) == pytest.approx(1.959964, abs=1e-4)
    assert st.normal_z_score(0.05) == pytest.approx(1.959964, abs=1e-4)


def test_normal_roundtrip():
    for p in (0.01, 0.25, 0.75, 0.99):
        assert st.normal_cdf(st.normal_inv_cdf(p)) == pytest.approx(p, abs=1e-6)


def test_student_t_cdf_table_values_df10():
    assert st.student_t_cdf(0.0, 10) == pytest.approx(0.5, abs=1e-9)
    assert st.student_t_cdf(1.372, 10) == pytest.approx(0.90, abs=1e-4)
    assert st.student_t_cdf(1.812, 10) == pytest.approx(0.95, abs=1e-4)
    assert st.student_t_cdf(2.228, 10) == pytest.approx(0.975, abs=1e-4)
    assert st.student_t_cdf(3.169, 10) == pytest.approx(0.995, abs=1e-4)
    assert st.student_t_cdf(-1.812, 10) == pytest.approx(0.05, abs=1e-4)


def test_student_t_inv_cdf_known_points():
    assert st.student_t_inv_cdf(0.90, 10) == pytest.approx(1.372, abs=1e-3)
    assert st.student_t_inv_cdf(0.95, 10) == pytest.approx(1.812, abs=1e-3)
    assert st.student_t_inv_cdf(0.975, 10) == pytest.approx(2.228, abs=1e-3)


def test_student_t_inv_cdf_heavy_tail_extreme():
    assert st.student_t_inv_cdf(0.995, 1) == pytest.approx(63.657, abs=1e-2)


def test_chi2_cdf_table_values():
    assert st.chi2_cdf(3.8415, 1) == pytest.approx(0.95, abs=1e-4)
    assert st.chi2_cdf(9.488, 4) == pytest.approx(0.95, abs=1e-4)
    assert st.chi2_cdf(15.507, 8) == pytest.approx(0.95, abs=1e-4)
    assert st.chi2_p_value(3.8415, 1) == pytest.approx(0.05, abs=1e-4)


def test_chi2_inv_cdf_roundtrip():
    for df in (1, 4, 8, 30):
        x = st.chi2_inv_cdf(0.95, df)
        assert st.chi2_cdf(x, df) == pytest.approx(0.95, abs=1e-6)


def test_incomplete_beta_reference_points():
    assert st.regularized_incomplete_beta(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    assert st.regularized_incomplete_beta(0.3, 1, 1) == pytest.approx(0.3, abs=1e-9)
    assert st.regularized_incomplete_beta(0.0, 2, 2) == pytest.approx(0.0, abs=1e-12)
    assert st.regularized_incomplete_beta(1.0, 2, 2) == pytest.approx(1.0, abs=1e-12)
    assert st.regularized_incomplete_beta(0.8, 2, 5) == pytest.approx(0.9984, abs=1e-9)
    assert st.regularized_incomplete_beta(0.2, 5, 2) == pytest.approx(0.0016, abs=1e-9)
    assert st.regularized_incomplete_beta(0.8, 2, 5) == pytest.approx(
        1.0 - st.regularized_incomplete_beta(0.2, 5, 2), abs=1e-9
    )


def test_variance():
    assert st.variance(np.array([1.0, 2.0, 3.0, 4.0, 5.0])) == pytest.approx(2.5)


def test_covariance():
    x = np.array([1.0, 2.0, 3.0])
    assert st.covariance(x, x) == pytest.approx(1.0)
    assert st.covariance(x, -x) == pytest.approx(-1.0)


def test_covariance_matrix():
    x = np.array([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]])
    m = st.covariance_matrix(x)
    np.testing.assert_allclose(m, [[1.0, 1.0], [1.0, 1.0]])


def test_coefficient_of_variation():
    assert st.coefficient_of_variation(np.array([2.0, 4.0, 6.0])) == pytest.approx(0.5)


def test_normal_pdf():
    assert st.normal_pdf(0.0) == pytest.approx(0.3989422804, abs=1e-9)
    assert st.normal_pdf(0.0, mu=0.0, sigma=2.0) == pytest.approx(0.1994711402, abs=1e-9)


def test_empirical_cdf():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert st.empirical_cdf(x, np.array([3.0]))[0] == pytest.approx(0.6)
    ties = np.array([1.0, 1.0, 2.0, 2.0])
    assert st.empirical_cdf(ties, np.array([1.0]))[0] == pytest.approx(0.5)


def test_mean_confidence_interval():
    x = np.arange(1.0, 11.0)
    mean, lo, hi = st.mean_confidence_interval(x, confidence=0.95)
    assert mean == pytest.approx(5.5)
    t = st.student_t_inv_cdf(0.975, 9)
    half = t * np.std(x, ddof=1) / math.sqrt(10)
    assert lo == pytest.approx(5.5 - half, rel=1e-12)
    assert hi == pytest.approx(5.5 + half, rel=1e-12)
    assert lo < 5.5 < hi


def test_two_sample_t_test_zero_variance_second():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([1.0, 1.0, 1.0, 1.0, 1.0])
    t, df, p = st.two_sample_t_test(a, b)
    assert t == pytest.approx(2.8284271, abs=1e-4)
    assert df == pytest.approx(4.0, abs=1e-9)
    assert 0.04 < p < 0.06


def test_two_sample_t_test_equal_means():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([2.0, 1.0, 3.0])
    t, df, p = st.two_sample_t_test(a, b)
    assert t == pytest.approx(0.0, abs=1e-12)
    assert p == pytest.approx(1.0, abs=1e-9)


def test_paired_t_test_reference():
    a = np.array([2.0, 3.0, 4.0])
    b = np.array([1.0, 1.0, 1.0])
    t, p = st.paired_t_test(a, b)
    assert t == pytest.approx(2.0 * math.sqrt(3.0), abs=1e-4)
    assert 0.06 < p < 0.09


def test_skewness_symmetric_is_zero():
    assert st.skewness(np.array([1.0, 2.0, 3.0, 4.0, 5.0])) == pytest.approx(0.0, abs=1e-12)


def test_skewness_positive_skew():
    s = st.skewness(np.array([1.0, 1.0, 1.0, 10.0, 10.0]))
    assert s == pytest.approx(0.60857, abs=1e-3)


def test_excess_kurtosis_normal_approx_zero():
    rng = np.random.default_rng(42)
    k = st.excess_kurtosis(rng.normal(0.0, 1.0, 5000))
    assert abs(k) < 0.3


def test_jarque_bera_normal_data():
    rng = np.random.default_rng(42)
    jb, p = st.jarque_bera(rng.normal(0.0, 1.0, 500))
    assert p > 0.05


def test_jarque_bera_rejects_exponential():
    rng = np.random.default_rng(42)
    jb, p = st.jarque_bera(rng.exponential(1.0, 500))
    assert p < 0.01


def test_pearson_correlation():
    x = np.arange(1.0, 11.0)
    assert st.pearson_correlation(x, x) == pytest.approx(1.0)
    assert st.pearson_correlation(x, -x) == pytest.approx(-1.0)
    rng = np.random.default_rng(1)
    uncorrelated = st.pearson_correlation(
        rng.normal(0, 1, 2000), rng.normal(0, 1, 2000)
    )
    assert abs(uncorrelated) < 0.1


def test_spearman_correlation_monotone_is_one():
    x = np.arange(1.0, 11.0)
    assert st.spearman_correlation(x, x ** 2) == pytest.approx(1.0)


def test_sharpe_standard_error_lo():
    se = st.sharpe_standard_error(0.5, 100)
    assert se == pytest.approx(math.sqrt(1.125 / 100.0), abs=1e-9)
