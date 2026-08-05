"""Tests for quant_research.resampling — bootstrap, permutation tests,
Reality Check, deflated Sharpe."""

import numpy as np
import pytest

from quant_research import resampling as rs


def test_block_bootstrap_determinism():
    rng = np.random.default_rng(0)
    data = rng.normal(0.0, 1.0, 500)
    a = rs.block_bootstrap(data, block_size=20, n_bootstrap=200, seed=7)
    b = rs.block_bootstrap(data, block_size=20, n_bootstrap=200, seed=7)
    np.testing.assert_array_equal(a, b)


def test_block_bootstrap_mean_unbiased():
    rng = np.random.default_rng(0)
    data = rng.normal(0.05, 1.0, 2000)
    dist = rs.block_bootstrap(data, block_size=20, n_bootstrap=300, seed=1)
    assert float(np.mean(dist)) == pytest.approx(float(np.mean(data)), abs=0.05)


def test_bootstrap_ci_contains_estimate():
    rng = np.random.default_rng(0)
    data = rng.normal(0.1, 1.0, 1000)
    est, lo, hi = rs.bootstrap_confidence_interval(data, block_size=10, n_bootstrap=500, seed=3)
    assert est == pytest.approx(float(np.mean(data)))
    assert lo < est < hi


def test_bootstrap_ci_tight_for_low_variance():
    data = np.linspace(5.0, 5.001, 200)
    est, lo, hi = rs.bootstrap_confidence_interval(data, block_size=10, n_bootstrap=300, seed=3)
    assert hi - lo < 0.005


def test_stationary_bootstrap_determinism_and_mean():
    rng = np.random.default_rng(0)
    data = rng.normal(0.02, 1.0, 500)
    a = rs.stationary_bootstrap(data, mean_block_length=10, n_bootstrap=200, seed=9)
    b = rs.stationary_bootstrap(data, mean_block_length=10, n_bootstrap=200, seed=9)
    np.testing.assert_array_equal(a, b)
    assert float(np.mean(a)) == pytest.approx(float(np.mean(data)), abs=0.1)


def test_permutation_two_sample_edge_is_exact_min():
    a = np.ones(50)
    b = np.zeros(50)
    p = rs.permutation_test_two_sample(a, b, n_permutations=2000, seed=0)
    assert p == pytest.approx(1.0 / 2001.0)


def test_permutation_two_sample_equal_groups_p_is_one():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    p = rs.permutation_test_two_sample(a, a.copy(), n_permutations=200, seed=0)
    assert p == pytest.approx(1.0)


def test_permutation_signal_edge_is_exact_min():
    returns = np.linspace(0.0, 1.0, 100)
    signals = np.zeros(100)
    signals[-5:] = 1.0
    p = rs.permutation_test_signal(returns, signals, n_permutations=2000, seed=0)
    assert p == pytest.approx(1.0 / 2001.0)


def test_permutation_signal_no_edge_not_significant():
    rng = np.random.default_rng(7)
    returns = rng.normal(0.0, 1.0, 200)
    signals = np.where(rng.random(200) < 0.5, 1.0, 0.0)
    p = rs.permutation_test_signal(returns, signals, n_permutations=2000, seed=5)
    assert p > 0.01


def test_reality_check_one_great_trial():
    trials = np.vstack([np.ones(100), np.zeros(100)])
    p = rs.reality_check_p_value(trials, block_size=5, n_bootstrap=2000, seed=0)
    assert p == pytest.approx(1.0 / 2001.0)


def test_reality_check_null_is_one():
    trials = np.zeros((3, 100))
    p = rs.reality_check_p_value(trials, block_size=5, n_bootstrap=500, seed=0)
    assert p == pytest.approx(1.0)


def test_reality_check_requires_2d():
    with pytest.raises(ValueError):
        rs.reality_check_p_value(np.ones(50))


def test_deflated_sharpe_no_trial_variance():
    p = rs.deflated_sharpe_ratio(0.5, np.zeros(100), n_obs=252)
    assert p == pytest.approx(1.0, abs=1e-9)
    p0 = rs.deflated_sharpe_ratio(0.0, np.zeros(100), n_obs=252)
    assert p0 == pytest.approx(0.5, abs=1e-9)


def test_deflated_sharpe_many_trials_kills_weak_edge():
    rng = np.random.default_rng(0)
    trials = rng.normal(0.0, 1.0, 1000)
    p = rs.deflated_sharpe_ratio(0.2, trials, n_obs=252)
    assert p < 1e-6


def test_deflated_sharpe_validation():
    with pytest.raises(ValueError):
        rs.deflated_sharpe_ratio(0.5, np.zeros(100), n_obs=252, skewness=0.0)
    with pytest.raises(ValueError):
        rs.deflated_sharpe_ratio(0.5, np.array([0.1]), n_obs=252)
