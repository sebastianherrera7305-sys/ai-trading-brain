"""Tests for quant_research.timeseries — autocorrelation, Hurst,
variance ratio, lagged features."""

import numpy as np
import pytest

from quant_research import timeseries as ts


def _ar1(n, rho, seed=0, sigma=1.0):
    rng = np.random.default_rng(seed)
    eps = rng.normal(0.0, sigma, n)
    out = np.zeros(n)
    for t in range(1, n):
        out[t] = rho * out[t - 1] + eps[t]
    return out


def test_autocorrelation_trend_is_one():
    x = np.arange(1.0, 101.0)
    assert ts.autocorrelation(x, lag=1) == pytest.approx(1.0, abs=1e-6)


def test_autocorrelation_alternating_is_minus_one():
    x = np.tile(np.array([1.0, -1.0]), 50)
    assert ts.autocorrelation(x, lag=1) == pytest.approx(-1.0)


def test_autocorrelation_white_noise_near_zero():
    rng = np.random.default_rng(0)
    x = rng.normal(0.0, 1.0, 2000)
    assert abs(ts.autocorrelation(x, lag=1)) < 0.1


def test_autocorrelation_series_length():
    rng = np.random.default_rng(0)
    corrs = ts.autocorrelation_series(rng.normal(0.0, 1.0, 500), max_lag=3)
    assert len(corrs) == 3
    assert all(np.isfinite(corrs))


def test_hurst_white_noise_around_half():
    rng = np.random.default_rng(0)
    noise = rng.normal(0.0, 1.0, 2000)
    h = ts.hurst_exponent(noise)
    assert abs(h - 0.5) < 0.1


def test_hurst_linear_trend_is_one():
    h = ts.hurst_exponent(np.arange(2000.0))
    assert h == pytest.approx(1.0, abs=0.05)


def test_hurst_random_walk_levels_saturate():
    rng = np.random.default_rng(0)
    walk = np.cumsum(rng.normal(0.0, 1.0, 2000))
    h = ts.hurst_exponent(walk)
    assert h > 0.9


def test_hurst_persistence_above_half():
    x = _ar1(2000, rho=0.9, seed=3)
    h = ts.hurst_exponent(x)
    assert h > 0.6


def test_hurst_mean_reversion_below_half():
    x = _ar1(2000, rho=-0.9, seed=3)
    h = ts.hurst_exponent(x)
    assert h < 0.45


def test_variance_ratio_random_walk_is_one():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0, 1.0, 5000)
    vr = ts.variance_ratio(returns, q=2)
    assert abs(vr - 1.0) < 0.15


def test_variance_ratio_trending_above_one():
    returns = _ar1(4000, rho=0.5, seed=1)
    assert ts.variance_ratio(returns, q=2) > 1.05


def test_variance_ratio_mean_reverting_below_one():
    returns = _ar1(4000, rho=-0.5, seed=1)
    assert ts.variance_ratio(returns, q=2) < 0.95


def test_variance_ratio_z_score_random_walk():
    rng = np.random.default_rng(0)
    returns = rng.normal(0.0, 1.0, 5000)
    assert abs(ts.variance_ratio_z_score(returns, q=2)) < 2.0


def test_lagged_features_layout():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    out = ts.lagged_features(x, lags=2)
    assert out.shape == (5, 3)
    np.testing.assert_allclose(out[:, 0], x)
    np.testing.assert_allclose(out[:, 1], [np.nan, 1.0, 2.0, 3.0, 4.0])
    np.testing.assert_allclose(out[:, 2], [np.nan, np.nan, 1.0, 2.0, 3.0])
