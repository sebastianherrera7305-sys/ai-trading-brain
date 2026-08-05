"""Tests for quant_research.core — returns algebra, rolling ops, EWMA."""

import math

import numpy as np
import pytest

from quant_research import core


def test_simple_returns():
    r = core.simple_returns(np.array([100.0, 110.0, 121.0]))
    assert np.isnan(r[0])
    np.testing.assert_allclose(r[1:], [0.1, 0.1])


def test_log_returns():
    r = core.log_returns(np.array([100.0, 110.0, 121.0]))
    assert np.isnan(r[0])
    np.testing.assert_allclose(r[1:], [math.log(1.1), math.log(1.1)])


def test_cumulative_returns():
    g = core.cumulative_returns(np.array([0.1, 0.1]))
    np.testing.assert_allclose(g, [1.1, 1.21])


def test_cumulative_returns_handles_nan():
    g = core.cumulative_returns(np.array([np.nan, 0.1]))
    np.testing.assert_allclose(g, [1.0, 1.1])


def test_prices_from_returns_is_inverse_of_simple_returns():
    prices = np.array([100.0, 98.5, 105.2, 103.1])
    rebuilt = core.prices_from_returns(core.simple_returns(prices), start_price=100.0)
    np.testing.assert_allclose(rebuilt, prices, rtol=1e-12)


def test_drawdown_prices():
    dd = core.drawdown_prices(np.array([100.0, 120.0, 90.0]))
    np.testing.assert_allclose(dd, [0.0, 0.0, -0.25])


def test_z_score():
    np.testing.assert_allclose(core.z_score(np.array([1.0, 2.0, 3.0])), [-1.0, 0.0, 1.0])


def test_z_score_constant_input_is_nan():
    assert np.all(np.isnan(core.z_score(np.array([2.0, 2.0, 2.0]))))


def test_rolling_mean():
    out = core.rolling_mean(np.array([1.0, 2.0, 3.0, 4.0]), 2)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [1.5, 2.5, 3.5])


def test_rolling_mean_window_one_is_identity():
    np.testing.assert_allclose(
        core.rolling_mean(np.array([1.0, 2.0, 3.0]), 1), [1.0, 2.0, 3.0]
    )


def test_rolling_mean_window_larger_than_input_is_nan():
    assert np.all(np.isnan(core.rolling_mean(np.array([1.0, 2.0]), 5)))


def test_rolling_std():
    out = core.rolling_std(np.array([1.0, 2.0, 3.0, 4.0]), 2)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [math.sqrt(0.5)] * 3)


def test_rolling_sum():
    out = core.rolling_sum(np.array([1.0, 2.0, 3.0, 4.0]), 2)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [3.0, 5.0, 7.0])


def test_rolling_z_score():
    out = core.rolling_z_score(np.array([1.0, 2.0, 3.0, 4.0]), 2)
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [math.sqrt(0.5)] * 3)


def test_rolling_z_score_zero_variance_window_is_nan():
    out = core.rolling_z_score(np.array([1.0, 1.0, 2.0, 3.0]), 2)
    assert np.isnan(out[1])
    assert not np.isnan(out[2])


def test_rolling_correlation_self_is_one():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = core.rolling_correlation(x, x, 3)
    np.testing.assert_allclose(out[2:], [1.0, 1.0, 1.0])


def test_rolling_correlation_inverse_is_minus_one():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = core.rolling_correlation(x, -x, 3)
    np.testing.assert_allclose(out[2:], [-1.0, -1.0, -1.0])


def test_ewma_constant_series():
    np.testing.assert_allclose(core.ewma(np.array([1.0, 1.0, 1.0]), 3), [1.0, 1.0, 1.0])


def test_ewma_span_one_is_identity():
    np.testing.assert_allclose(
        core.ewma(np.array([1.0, 5.0, 2.0]), 1), [1.0, 5.0, 2.0]
    )


def test_ewma_span_two_reference():
    out = core.ewma(np.array([0.0, 6.0, 12.0]), 2)
    alpha = 2.0 / 3.0
    np.testing.assert_allclose(out, [0.0, alpha * 6.0, alpha * 12.0 + (1 - alpha) * 4.0])


def test_ewma_volatility_constant_returns():
    vol = core.ewma_volatility(np.array([0.01] * 50), span=10, periods=252)
    np.testing.assert_allclose(vol, [math.sqrt(0.0001 * 252)] * 50, rtol=1e-12)


def test_centered_smooth():
    out = core.centered_smooth(np.array([1.0, 2.0, 3.0, 4.0, 5.0]), 3)
    assert np.isnan(out[0]) and np.isnan(out[-1])
    np.testing.assert_allclose(out[1:-1], [2.0, 3.0, 4.0])


def test_centered_smooth_rejects_even_window():
    with pytest.raises(ValueError):
        core.centered_smooth(np.array([1.0, 2.0, 3.0]), 2)


def test_safe_divide_default_nan():
    out = core.safe_divide(np.array([1.0, 2.0, 3.0]), np.array([0.0, 1.0, 2.0]))
    assert np.isnan(out[0])
    np.testing.assert_allclose(out[1:], [2.0, 1.5])


def test_safe_divide_custom_default():
    out = core.safe_divide(np.array([1.0, 2.0]), np.array([0.0, 1.0]), default=0.0)
    np.testing.assert_allclose(out, [0.0, 2.0])


def test_drop_nan():
    np.testing.assert_allclose(core.drop_nan(np.array([1.0, np.nan, np.inf, 2.0])), [1.0, 2.0])


def test_required_length_raises():
    with pytest.raises(ValueError):
        core.required_length("x", np.array([1.0, np.nan]), 3)
