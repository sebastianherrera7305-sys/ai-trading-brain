"""Validation-branch coverage tests for quant_research.

Pins every documented error path and degenerate branch (ValueError
messages, NaN returns, inf returns, boundary conventions) so the
package's failure contract is executable and coverage of the
validation branches is complete.
"""

import math

import numpy as np
import pytest

from quant_research import core, probability, resampling, statistics, timeseries
from quant_research._input import as_float_array as _as_float_array


# ---------------------------------------------------------------------------
# probability: scalar validation branches
# ---------------------------------------------------------------------------

def test_binomial_pmf_validation_branches():
    with pytest.raises(ValueError):
        probability.binomial_pmf(1, 10, 1.5)
    assert probability.binomial_pmf(0, 10, 0.0) == 1.0
    assert probability.binomial_pmf(1, 10, 0.0) == 0.0
    assert probability.binomial_pmf(10, 10, 1.0) == 1.0
    assert probability.binomial_pmf(9, 10, 1.0) == 0.0


def test_binomial_ci_validation_branches():
    with pytest.raises(ValueError):
        probability.binomial_ci(5, 10, confidence=0.0)
    with pytest.raises(ValueError):
        probability.binomial_ci(5, 0)
    lo, hi = probability.binomial_ci(0, 10)
    assert lo == 0.0
    lo, hi = probability.binomial_ci(10, 10)
    assert hi == 1.0


def test_beta_inv_cdf_boundary_branches():
    with pytest.raises(ValueError):
        probability.beta_inv_cdf(-0.1, 2.0, 2.0)
    assert probability.beta_inv_cdf(0.0, 2.0, 2.0) == 0.0
    assert probability.beta_inv_cdf(1.0, 2.0, 2.0) == 1.0


def test_expected_value_validation_branch():
    with pytest.raises(ValueError):
        probability.expected_value(1.5, 1.0, 1.0)


def test_kelly_validation_branches():
    with pytest.raises(ValueError):
        probability.kelly_fraction(0.0, 1.0)
    with pytest.raises(ValueError):
        probability.kelly_fraction(0.5, 0.0)
    with pytest.raises(ValueError):
        probability.fractional_kelly(0.6, 1.0, 0.0)
    with pytest.raises(ValueError):
        probability.fractional_kelly(0.6, 1.0, 1.5)
    with pytest.raises(ValueError):
        probability.kelly_expected_growth(1.5, 1.0, 0.2)
    with pytest.raises(ValueError):
        probability.kelly_expected_growth(0.6, 0.0, 0.2)
    with pytest.raises(ValueError):
        probability.kelly_expected_growth(0.6, 1.0, 0.0)
    assert probability.kelly_expected_growth(0.6, 1.0, 1.0) == float("-inf")
    assert probability.kelly_expected_growth(0.6, 0.2, 1.0) == float("-inf")


def test_brier_score_shape_validation_branch():
    with pytest.raises(ValueError):
        probability.brier_score(np.array([0.5, 0.5]), np.array([1.0]))


def test_brier_skill_score_shape_validation_branch():
    with pytest.raises(ValueError):
        probability.brier_skill_score(np.array([0.5]), np.array([1.0, 0.0]))


def test_brier_skill_score_custom_climatology_and_perfect():
    y = np.array([1.0, 1.0, 0.0])
    assert probability.brier_skill_score(np.array([1.0, 1.0, 0.0]), y) == pytest.approx(
        1.0
    )
    # A climate forecast with a custom base rate scores 0 by definition.
    assert probability.brier_skill_score(
        np.full(3, 0.7), y, climatology=0.7
    ) == pytest.approx(0.0)


def test_sprt_bernoulli_alpha_beta_validation():
    with pytest.raises(ValueError):
        probability.sprt_bernoulli(np.array([1.0]), 0.4, 0.6, alpha=1.5)
    with pytest.raises(ValueError):
        probability.sprt_bernoulli(np.array([1.0]), 0.4, 0.6, beta=0.0)


def test_sprt_bernoulli_empty_outcomes_continue():
    r = probability.sprt_bernoulli(np.array([]), 0.4, 0.6)
    assert r["decision"] == "continue"
    assert r["final_llr"] == 0.0
    assert r["n"] == 0


def test_sprt_expected_sample_size_branches():
    with pytest.raises(ValueError):
        probability.sprt_expected_sample_size(0.5, 0.6, 0.4)
    # p at the indifference point: no drift, E[n] = inf.
    assert probability.sprt_expected_sample_size(
        0.5, 0.4, 0.6
    ) == float("inf")


def test_normal_power_validation_branches():
    with pytest.raises(ValueError):
        probability.normal_power(0.2, 0.0, 100)
    with pytest.raises(ValueError):
        probability.normal_power(0.2, 1.0, 0)


# ---------------------------------------------------------------------------
# statistics: remaining validation branches
# ---------------------------------------------------------------------------

def test_normal_inv_cdf_validation():
    with pytest.raises(ValueError):
        statistics.normal_inv_cdf(0.0)
    with pytest.raises(ValueError):
        statistics.normal_inv_cdf(1.0)


def test_normal_pdf_validation():
    with pytest.raises(ValueError):
        statistics.normal_pdf(0.0, sigma=0.0)


def test_student_t_inv_cdf_validation():
    with pytest.raises(ValueError):
        statistics.student_t_inv_cdf(0.0, 10)
    with pytest.raises(ValueError):
        statistics.student_t_inv_cdf(0.5, 0)
    assert statistics.student_t_inv_cdf(0.5, 10) == 0.0


def test_regularized_incomplete_beta_validation():
    with pytest.raises(ValueError):
        statistics.regularized_incomplete_beta(0.5, 0.0, 2.0)
    with pytest.raises(ValueError):
        statistics.regularized_incomplete_beta(0.5, 2.0, -1.0)
    assert statistics.regularized_incomplete_beta(0.0, 2, 2) == 0.0
    assert statistics.regularized_incomplete_beta(1.0, 2, 2) == 1.0


def test_chi2_validation_branches():
    with pytest.raises(ValueError):
        statistics.chi2_cdf(1.0, 0)
    with pytest.raises(ValueError):
        statistics.chi2_inv_cdf(0.0, 4)
    with pytest.raises(ValueError):
        statistics.chi2_inv_cdf(1.5, 4)


def test_autocorrelation_returns_nan_when_lag_too_large():
    assert timeseries.autocorrelation(np.array([1.0, 2.0, 3.0]), lag=5) != timeseries.autocorrelation(
        np.array([1.0, 2.0, 3.0]), lag=5
    )


def test_variance_ratio_zero_variance_returns_nan():
    vr = timeseries.variance_ratio(np.full(30, 2.0), 4)
    assert vr != vr
    z = timeseries.variance_ratio_z_score(np.full(30, 2.0), 4)
    assert z != z


def test_hurst_min_lag_validation_and_max_lag_less_than_min():
    with pytest.raises(ValueError):
        timeseries.hurst_exponent(np.arange(1.0, 50.0), min_lag=2)
    assert timeseries.hurst_exponent(
        np.arange(1.0, 50.0), min_lag=20, max_lag=5
    ) != timeseries.hurst_exponent(np.arange(1.0, 50.0), min_lag=20, max_lag=5)


def test_pearson_correlation_zero_variance_nan():
    assert statistics.pearson_correlation(
        np.array([1.0, 1.0, 1.0]), np.arange(1.0, 4.0)
    ) != statistics.pearson_correlation(np.array([1.0, 1.0, 1.0]), np.arange(1.0, 4.0))


def test_coefficient_of_variation_zero_mean_nan():
    cv = statistics.coefficient_of_variation(np.array([-2.0, -1.0, 0.0, 1.0, 2.0]))
    assert cv != cv


def test_skewness_excess_kurtosis_small_sample_nan():
    assert statistics.skewness(np.array([1.0, 2.0])) != statistics.skewness(
        np.array([1.0, 2.0])
    )
    assert statistics.excess_kurtosis(np.array([1.0, 2.0, 3.0])) != statistics.excess_kurtosis(
        np.array([1.0, 2.0, 3.0])
    )
    assert statistics.skewness(np.array([1.0, 1.0, 1.0])) != statistics.skewness(
        np.array([1.0, 1.0, 1.0])
    )
    assert statistics.excess_kurtosis(np.array([1.0, 1.0, 1.0, 1.0])) != statistics.excess_kurtosis(
        np.array([1.0, 1.0, 1.0, 1.0])
    )


def test_jarque_bera_zero_variance_nan():
    jb, p = statistics.jarque_bera(np.array([1.0, 1.0, 1.0, 1.0, 1.0]))
    assert jb != jb and p != p


def test_sharpe_standard_error_validation():
    with pytest.raises(ValueError):
        statistics.sharpe_standard_error(0.5, 1)


def test_two_sample_t_test_both_constant_degenerate():
    a = np.array([1.0, 1.0, 1.0])
    b = np.array([2.0, 2.0, 2.0])
    t, df, p = statistics.two_sample_t_test(a, b)
    assert t == 0.0
    assert df == pytest.approx(4.0)
    assert p == pytest.approx(1.0)


def test_paired_t_test_zero_variance_degenerate():
    a = np.array([1.0, 2.0, 3.0])
    b = np.array([2.0, 3.0, 4.0])
    t, p = statistics.paired_t_test(a, b)
    assert t == 0.0 and p == pytest.approx(1.0)


def test_student_t_cdf_zero_t_is_half():
    assert statistics.student_t_cdf(0.0, 10) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# resampling: remaining validation branches
# ---------------------------------------------------------------------------

def test_resampling_n_bootstrap_validation():
    x = np.arange(1.0, 11.0)
    with pytest.raises(ValueError):
        resampling.block_bootstrap(x, 3, n_bootstrap=0)
    with pytest.raises(ValueError):
        resampling.stationary_bootstrap(x, 3.0, n_bootstrap=0)
    with pytest.raises(ValueError):
        resampling.permutation_test_two_sample(x[:4], x[4:], n_permutations=0)
    with pytest.raises(ValueError):
        resampling.permutation_test_signal(x, np.ones(10), n_permutations=0)


def test_reality_check_validation_branches():
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(np.array([1.0, 2.0, 3.0]))
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(np.full((3, 10), np.nan))
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(np.ones((3, 10)), block_size=0)
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(np.ones((1, 10)))


def test_reality_check_single_trial_row_rejected():
    trials = np.arange(1.0, 21.0).reshape(2, 10)
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(trials[:1])


def test_reality_check_drops_partial_nan_rows():
    rng = np.random.default_rng(0)
    trials = rng.normal(0.0, 1.0, (5, 50))
    trials[2, 3] = np.nan
    p = resampling.reality_check_p_value(trials, n_bootstrap=100, seed=0)
    assert 0.0 <= p <= 1.0


def test_deflated_sharpe_validation_branches():
    with pytest.raises(ValueError):
        resampling.deflated_sharpe_ratio(0.2, np.array([0.1]), 100)
    with pytest.raises(ValueError):
        resampling.deflated_sharpe_ratio(0.2, np.array([0.1, 0.2]), 1)
    with pytest.raises(ValueError):
        resampling.deflated_sharpe_ratio(0.2, np.array([0.1, 0.2]), 100, skewness=0.5)


def test_deflated_sharpe_zero_trial_variance():
    p = resampling.deflated_sharpe_ratio(0.3, np.array([0.1] * 5), 250)
    ref = statistics.normal_cdf(0.3 * math.sqrt(249.0))
    assert p == pytest.approx(ref, rel=1e-12)


def test_deflated_sharpe_bad_skew_denominator_nan():
    p = resampling.deflated_sharpe_ratio(
        10.0, np.array([0.0, 0.1, 0.2]), 100, skewness=5.0, kurtosis=1.0
    )
    assert p != p


def test_permutation_test_signal_shuffled_signal_semantics():
    # signals with exactly one 1: p is the tail of the shuffled mean —
    # deterministic structure check.
    returns = np.arange(1.0, 21.0)
    signals = np.zeros(20)
    signals[0] = 1.0
    p = resampling.permutation_test_signal(returns, signals, n_permutations=500, seed=0)
    assert 0.0 < p <= 1.0


# ---------------------------------------------------------------------------
# core: remaining branches
# ---------------------------------------------------------------------------

def test_centered_smooth_window_larger_than_input():
    out = core.centered_smooth(np.array([1.0, 2.0]), 5)
    assert np.all(np.isnan(out))


def test_z_score_missing_positions_are_nan_and_lengths_match():
    x = np.array([np.nan, 2.0, np.nan, 4.0])
    z = core.z_score(x)
    assert z.shape == (4,)
    assert np.isnan(z[0]) and np.isnan(z[2]) and not np.isnan(z[1])


def test_rolling_correlation_shorter_than_window():
    out = core.rolling_correlation(np.array([1.0, 2.0]), np.array([2.0, 1.0]), 5)
    assert np.all(np.isnan(out))


# ---------------------------------------------------------------------------
# second pass: remaining reachable branches
# ---------------------------------------------------------------------------

def test_zero_dimensional_ndarray_is_rejected():
    with pytest.raises(ValueError):
        _as_float_array(np.array(5.0))


def test_rolling_correlation_window_validation():
    with pytest.raises(ValueError):
        core.rolling_correlation(np.array([1.0, 2.0]), np.array([2.0, 1.0]), 0)


def test_ewma_volatility_validation():
    r = np.array([0.01] * 50)
    with pytest.raises(ValueError):
        core.ewma_volatility(r, span=0)
    with pytest.raises(ValueError):
        core.ewma_volatility(r, span=10, periods=0)


def test_brier_skill_score_zero_reference_brier():
    y = np.ones(5)
    assert probability.brier_skill_score(y, y) == 0.0


def test_sprt_expected_sample_size_negative_drift_branch():
    # p below the indifference point: the SPRT drifts toward rejection.
    ess = probability.sprt_expected_sample_size(0.3, 0.4, 0.6)
    assert ess > 0.0
    assert math.isfinite(ess)


def test_block_bootstrap_block_size_validation():
    with pytest.raises(ValueError):
        resampling.block_bootstrap(np.arange(1.0, 11.0), n_bootstrap=3, block_size=0)
    with pytest.raises(ValueError):
        resampling.block_bootstrap(np.arange(1.0, 11.0), n_bootstrap=3, block_size=100)


def test_stationary_bootstrap_mean_block_length_validation():
    with pytest.raises(ValueError):
        resampling.stationary_bootstrap(np.arange(1.0, 11.0), 0.0)


def test_permutation_test_signal_length_mismatch():
    with pytest.raises(ValueError):
        resampling.permutation_test_signal(np.ones(10), np.ones(9))


def test_reality_check_n_bootstrap_validation():
    trials = np.ones((3, 10))
    with pytest.raises(ValueError):
        resampling.reality_check_p_value(trials, n_bootstrap=0)


def test_deflated_sharpe_positive_radicand_with_skewness():
    p = resampling.deflated_sharpe_ratio(
        0.2, np.array([0.0, 0.1, 0.2]), 100, skewness=0.5, kurtosis=3.0
    )
    assert 0.0 < p <= 1.0


def test_normal_inv_cdf_acklam_upper_branch():
    # p=0.99 -> body(0.99) > 0.97575 exercises the extreme-tail
    # rational branch; p=0.005 -> -body(0.995) reaches it via symmetry.
    assert statistics.normal_inv_cdf(0.99) == pytest.approx(2.3263478740408408, abs=5e-9)
    assert statistics.normal_inv_cdf(0.005) == pytest.approx(-2.5758293035489004, abs=5e-9)


def test_student_t_cdf_sf_df_validation():
    with pytest.raises(ValueError):
        statistics.student_t_cdf(1.0, 0.0)
    with pytest.raises(ValueError):
        statistics.student_t_sf(1.0, 0.0)


def test_student_t_inv_cdf_lower_bracket_expansion():
    # df=1 is Cauchy: P(T < -40) ~ 0.008, so the lower bracket must expand.
    assert statistics.student_t_inv_cdf(0.001, 1) == pytest.approx(-318.308838985569, abs=1e-4)
    assert statistics.student_t_inv_cdf(0.999, 1) == pytest.approx(318.308838985569, abs=1e-4)


def test_lower_incomplete_gamma_direct_guard():
    with pytest.raises(ValueError):
        statistics._lower_incomplete_gamma(0.0, 1.0)
    assert statistics._lower_incomplete_gamma(2.0, -1.0) == 0.0


def test_equal_length_validations():
    with pytest.raises(ValueError):
        statistics.covariance(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        statistics.paired_t_test(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        statistics.pearson_correlation(np.array([1.0, 2.0]), np.array([1.0]))
    with pytest.raises(ValueError):
        statistics.spearman_correlation(np.array([1.0, 2.0]), np.array([1.0]))


def test_mean_confidence_interval_constant_series():
    assert statistics.mean_confidence_interval(np.full(5, 7.0)) == (7.0, 7.0, 7.0)


def test_hurst_constant_series_nan():
    assert timeseries.hurst_exponent(np.full(50, 3.0)) != timeseries.hurst_exponent(
        np.full(50, 3.0)
    )
