"""Edge-case contract tests for quant_research (package input contract,
see quant_research/_input.py).

Pins the documented behaviors for: empty inputs, single-element inputs,
NaN/Inf handling, integer vs float inputs, lists/tuples/ranges/
generators, and scalar/2-D/string rejection.
"""

import math

import numpy as np
import pytest

from quant_research import core, probability, resampling, statistics, timeseries


# ---------------------------------------------------------------------------
# Coercion: array-like in, float64 out
# ---------------------------------------------------------------------------

def test_list_input_works_and_outputs_float64():
    out = core.simple_returns([100, 110, 121])
    assert out.dtype == np.float64
    np.testing.assert_allclose(out[1:], [0.1, 0.1])


def test_tuple_input_works():
    assert statistics.variance((1.0, 2.0, 3.0, 4.0, 5.0)) == pytest.approx(2.5)


def test_range_input_works():
    assert statistics.variance(range(1, 6)) == pytest.approx(2.5)


def test_generator_input_consumed_once():
    assert statistics.variance(x for x in (1.0, 2.0, 3.0, 4.0, 5.0)) == pytest.approx(2.5)


def test_int_input_behaves_like_float():
    np.testing.assert_allclose(
        core.rolling_mean(np.array([1, 2, 3, 4]), 2)[1:], [1.5, 2.5, 3.5]
    )


@pytest.mark.parametrize(
    "func,args",
    [
        (core.simple_returns, (5.0,)),
        (core.cumulative_returns, (5.0,)),
        (core.z_score, (5.0,)),
        (core.ewma, (5.0, 3)),
        (core.safe_divide, (1.0, 2.0)),
        (statistics.variance, (5.0,)),
        (statistics.empirical_cdf, (5.0, np.array([1.0]))),
        (probability.brier_score, (np.array([0.5]), 1.0)),
    ],
)
def test_scalar_inputs_raise_valueerror(func, args):
    with pytest.raises(ValueError):
        func(*args)


def test_string_input_raises_typeerror():
    with pytest.raises(TypeError):
        core.simple_returns("not a series")


def test_2d_input_raises_valueerror():
    with pytest.raises(ValueError):
        statistics.variance(np.ones((3, 2)))


def test_covariance_matrix_accepts_2d_and_1d():
    x = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
    assert statistics.covariance_matrix(x).shape == (2, 2)
    assert statistics.covariance_matrix(np.array([1.0, 2.0, 3.0])).shape == (1, 1)
    with pytest.raises(ValueError):
        statistics.covariance_matrix(np.ones((2, 2, 2)))


# ---------------------------------------------------------------------------
# Empty inputs: algebra returns empty, statistics raise
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "func,args",
    [
        (core.simple_returns, (np.array([]),)),
        (core.log_returns, (np.array([]),)),
        (core.cumulative_returns, (np.array([]),)),
        (core.prices_from_returns, (np.array([]),)),
        (core.drawdown_prices, (np.array([]),)),
        (core.rolling_mean, (np.array([]), 3)),
        (core.rolling_std, (np.array([]), 3)),
        (core.rolling_sum, (np.array([]), 3)),
        (core.rolling_z_score, (np.array([]), 3)),
        (core.ewma, (np.array([]), 3)),
        (core.ewma_volatility, (np.array([]), 3)),
        (core.centered_smooth, (np.array([]), 3)),
        (core.safe_divide, (np.array([]), np.array([]))),
        (core.drop_nan, (np.array([]),)),
    ],
)
def test_algebra_functions_return_empty_on_empty_input(func, args):
    out = func(*args)
    assert isinstance(out, np.ndarray)
    assert out.shape == (0,)


def test_rolling_correlation_empty_input():
    out = core.rolling_correlation(np.array([]), np.array([]), 3)
    assert out.shape == (0,)


def test_lagged_features_empty_input():
    out = timeseries.lagged_features(np.array([]), 2)
    assert out.shape == (0, 3)


@pytest.mark.parametrize(
    "func,args",
    [
        (core.z_score, (np.array([]),)),
        (statistics.variance, (np.array([]),)),
        (statistics.covariance, (np.array([]), np.array([]))),
        (statistics.coefficient_of_variation, (np.array([]),)),
        (statistics.empirical_cdf, (np.array([]), np.array([1.0]))),
        (statistics.mean_confidence_interval, (np.array([]),)),
        (statistics.two_sample_t_test, (np.array([]), np.array([1.0, 2.0]))),
        (statistics.paired_t_test, (np.array([]), np.array([]))),
        (statistics.skewness, (np.array([]),)),
        (statistics.excess_kurtosis, (np.array([]),)),
        (statistics.jarque_bera, (np.array([]),)),
        (statistics.pearson_correlation, (np.array([]), np.array([]))),
        (statistics.spearman_correlation, (np.array([]), np.array([]))),
        (probability.brier_score, (np.array([]), np.array([]))),
        (probability.brier_skill_score, (np.array([]), np.array([]))),
        (resampling.block_bootstrap, (np.array([]), 3)),
        (resampling.stationary_bootstrap, (np.array([]), 3.0)),
        (resampling.bootstrap_confidence_interval, (np.array([]),)),
        (resampling.permutation_test_two_sample, (np.array([]), np.array([1.0, 2.0]))),
        (timeseries.autocorrelation, (np.array([]),)),
        (timeseries.hurst_exponent, (np.array([]),)),
        (timeseries.variance_ratio, (np.array([]), 4)),
    ],
)
def test_statistics_raise_on_empty_input(func, args):
    with pytest.raises(ValueError):
        func(*args)


def test_permutation_test_signal_empty_signals_raises():
    with pytest.raises(ValueError):
        resampling.permutation_test_signal(np.array([]), np.array([]))


# ---------------------------------------------------------------------------
# Single-element inputs
# ---------------------------------------------------------------------------

def test_single_element_statistics_raise_or_nan():
    with pytest.raises(ValueError):
        statistics.variance(np.array([5.0]))
    assert statistics.skewness(np.array([5.0])) != statistics.skewness(np.array([5.0]))
    assert statistics.excess_kurtosis(np.array([5.0, 6.0])) != statistics.excess_kurtosis(
        np.array([5.0, 6.0])
    )


def test_single_element_algebra_works():
    r = core.simple_returns(np.array([100.0]))
    assert np.isnan(r[0])
    np.testing.assert_allclose(core.cumulative_returns(np.array([0.1])), [1.1])


def test_single_element_ewma_identity():
    np.testing.assert_allclose(core.ewma(np.array([7.0]), 3), [7.0])


# ---------------------------------------------------------------------------
# NaN / Inf policy
# ---------------------------------------------------------------------------

def test_statistics_drop_nan_and_inf():
    clean = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    dirty = np.array([1.0, np.nan, 2.0, np.inf, 3.0, -np.inf, 4.0, np.nan, 5.0])
    assert statistics.variance(dirty) == pytest.approx(statistics.variance(clean))
    assert statistics.mean_confidence_interval(dirty)[0] == pytest.approx(3.0)


def test_statistics_all_nan_raise():
    with pytest.raises(ValueError):
        statistics.variance(np.array([np.nan, np.nan, np.nan]))


def test_z_score_position_aligned_nan():
    x = np.array([1.0, np.nan, 3.0])
    z = core.z_score(x)
    assert np.isnan(z[1])
    np.testing.assert_allclose(z[[0, 2]], [-1.0 / math.sqrt(2.0), 1.0 / math.sqrt(2.0)])


def test_returns_converters_keep_nan_positions():
    prices = np.array([100.0, np.nan, 110.0])
    r = core.simple_returns(prices)
    assert np.isnan(r[0]) and np.isnan(r[1]) and np.isnan(r[2])
    lr = core.log_returns(np.array([100.0, 110.0, np.nan]))
    assert np.isnan(lr[0]) and np.isnan(lr[2])


def test_rolling_window_with_nan_propagates():
    out = core.rolling_mean(np.array([1.0, np.nan, 3.0, 4.0]), 2)
    assert np.isnan(out[1]) and np.isnan(out[2])
    assert out[3] == pytest.approx(3.5)


def test_cumulative_returns_treats_nan_as_zero():
    np.testing.assert_allclose(
        core.cumulative_returns(np.array([np.nan, 0.1, np.nan])), [1.0, 1.1, 1.1]
    )


def test_autocorrelation_drops_nan_pairs():
    x = np.array([1.0, np.nan, 2.0, 3.0])
    assert timeseries.autocorrelation(x) == pytest.approx(
        timeseries.autocorrelation(np.array([1.0, 2.0, 3.0]))
    )


def test_covariance_uses_jointly_finite_pairs():
    a = np.array([1.0, np.nan, 2.0, 3.0])
    b = np.array([1.0, 1.0, np.nan, 3.0])
    assert statistics.covariance(a, b) == pytest.approx(
        statistics.covariance(np.array([1.0, 3.0]), np.array([1.0, 3.0]))
    )


# ---------------------------------------------------------------------------
# Window/parameter validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "func,args",
    [
        (core.rolling_mean, (np.array([1.0, 2.0]), 0)),
        (core.rolling_std, (np.array([1.0, 2.0]), -1)),
        (core.rolling_sum, (np.array([1.0, 2.0]), 0)),
        (core.centered_smooth, (np.array([1.0, 2.0]), 2)),
        (core.ewma, (np.array([1.0, 2.0]), 0.0)),
        (timeseries.autocorrelation, (np.array([1.0, 2.0, 3.0]), 0)),
        (timeseries.autocorrelation_series, (np.array([1.0, 2.0, 3.0]), 0)),
        (timeseries.variance_ratio, (np.arange(1.0, 30.0), 1)),
        (timeseries.lagged_features, (np.array([1.0, 2.0]), 0)),
    ],
)
def test_invalid_parameters_raise(func, args):
    with pytest.raises(ValueError):
        func(*args)


def test_rolling_correlation_length_mismatch_raises():
    with pytest.raises(ValueError):
        core.rolling_correlation(np.array([1.0, 2.0]), np.array([1.0]), 2)


def test_two_sample_t_test_nonbinary_rejections():
    with pytest.raises(ValueError):
        probability.brier_score(np.array([0.5, 0.5]), np.array([0.0, 2.0]))
    with pytest.raises(ValueError):
        probability.sprt_bernoulli(np.array([0.0, 1.0, 2.0]), 0.4, 0.6)
    with pytest.raises(ValueError):
        probability.sprt_bernoulli(np.array([0.0, 1.0]), 0.6, 0.4)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_stochastic_functions_deterministic_on_seed():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 1.0, 50)
    a = resampling.block_bootstrap(x, 5, n_bootstrap=100, seed=0)
    b = resampling.block_bootstrap(x, 5, n_bootstrap=100, seed=0)
    np.testing.assert_array_equal(a, b)


def test_stochastic_functions_differ_on_seed():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 1.0, 50)
    a = resampling.block_bootstrap(x, 5, n_bootstrap=100, seed=0)
    b = resampling.block_bootstrap(x, 5, n_bootstrap=100, seed=1)
    assert not np.array_equal(a, b)
