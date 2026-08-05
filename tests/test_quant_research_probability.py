"""Tests for quant_research.probability — binomial, EV, Kelly, Bayesian
updating, Brier, SPRT, power."""

import math

import numpy as np
import pytest

from quant_research import probability as pr


def test_binomial_pmf_exact():
    assert pr.binomial_pmf(5, 10, 0.5) == pytest.approx(252.0 / 1024.0)
    assert pr.binomial_pmf(0, 10, 0.5) == pytest.approx(1.0 / 1024.0)
    assert pr.binomial_pmf(7, 5, 0.5) == 0.0


def test_binomial_cdf_exact():
    assert pr.binomial_cdf(5, 10, 0.5) == pytest.approx(638.0 / 1024.0)
    assert pr.binomial_cdf(10, 10, 0.5) == pytest.approx(1.0)
    assert pr.binomial_cdf(-1, 10, 0.5) == 0.0


def test_binomial_ci_clopper_pearson_5_of_10():
    lo, hi = pr.binomial_ci(5, 10, confidence=0.95)
    assert lo == pytest.approx(0.18709, abs=1e-3)
    assert hi == pytest.approx(0.81291, abs=1e-3)


def test_binomial_ci_zero_successes():
    lo, hi = pr.binomial_ci(0, 10, confidence=0.95)
    assert lo == 0.0
    assert hi == pytest.approx(0.308497, abs=1e-3)


def test_beta_reference_points():
    assert pr.beta_cdf(0.3, 1, 1) == pytest.approx(0.3, abs=1e-9)
    assert pr.beta_cdf(0.5, 2, 2) == pytest.approx(0.5, abs=1e-9)
    assert pr.beta_inv_cdf(1.0 / 3.0, 0.5, 0.5) == pytest.approx(0.25, abs=1e-6)
    assert pr.beta_mean(2, 2) == pytest.approx(0.5)
    assert pr.beta_var(2, 2) == pytest.approx(0.05)


def test_beta_posterior_conjugate_update():
    a, b = pr.beta_posterior(1.0, 1.0, 8, 2)
    assert (a, b) == (9.0, 3.0)
    assert pr.beta_mean(a, b) == pytest.approx(0.75)


def test_probability_edge_above_closed_form():
    p = pr.probability_edge_above(8, 2, threshold=0.5, prior_alpha=1.0, prior_beta=1.0)
    assert p == pytest.approx(1981.0 / 2048.0, abs=1e-6)


def test_probability_edge_above_no_evidence():
    p = pr.probability_edge_above(0, 0, threshold=0.5)
    assert p == pytest.approx(0.5, abs=1e-9)


def test_expected_value():
    assert pr.expected_value(0.5, 2.0, 1.0) == pytest.approx(0.5)
    assert pr.expected_value(0.5, 1.0, 1.0) == pytest.approx(0.0)
    assert pr.expected_value(0.6, 1.0, 0.5) == pytest.approx(0.4)


def test_kelly_fraction():
    assert pr.kelly_fraction(0.6, 1.0) == pytest.approx(0.2)
    assert pr.kelly_fraction(0.5, 2.0) == pytest.approx(0.25)
    assert pr.kelly_fraction(0.3, 1.0) == pytest.approx(0.0)
    assert pr.kelly_fraction(0.2, 4.0) == pytest.approx(0.0)


def test_fractional_kelly():
    assert pr.fractional_kelly(0.6, 1.0, 0.25) == pytest.approx(0.05)


def test_kelly_maximizes_expected_growth():
    g_full = pr.kelly_expected_growth(0.6, 1.0, 0.2)
    g_over = pr.kelly_expected_growth(0.6, 1.0, 0.3)
    g_way_over = pr.kelly_expected_growth(0.6, 1.0, 0.5)
    assert g_full > g_over > g_way_over
    assert g_way_over < 0.0


def test_brier_score():
    assert pr.brier_score(np.array([0.5, 0.5]), np.array([0.0, 1.0])) == pytest.approx(0.25)
    assert pr.brier_score(np.array([1.0, 0.0]), np.array([1.0, 0.0])) == pytest.approx(0.0)


def test_brier_skill_score():
    p = np.array([1.0, 0.0])
    y = np.array([1.0, 0.0])
    assert pr.brier_skill_score(p, y, climatology=0.5) == pytest.approx(1.0)
    assert pr.brier_skill_score(
        np.array([0.5, 0.5]), np.array([0.0, 1.0]), climatology=0.5
    ) == pytest.approx(0.0)


def test_sprt_all_wins_accepts_edge():
    res = pr.sprt_bernoulli(np.ones(25), p0=0.5, p1=0.6, alpha=0.05, beta=0.05)
    assert res["decision"] == "accept_edge"
    assert res["upper_bound"] == pytest.approx(math.log(19.0), abs=1e-12)
    assert res["final_llr"] > res["upper_bound"]


def test_sprt_all_losses_rejects_edge():
    res = pr.sprt_bernoulli(np.zeros(15), p0=0.5, p1=0.6, alpha=0.05, beta=0.05)
    assert res["decision"] == "reject_edge"
    assert res["final_llr"] < res["lower_bound"]


def test_sprt_short_sample_continues():
    res = pr.sprt_bernoulli(np.array([1.0] * 6 + [0.0] * 4), p0=0.5, p1=0.6)
    assert res["decision"] == "continue"


def test_sprt_path_is_cumulative_llr():
    outcomes = np.array([1.0, 0.0, 1.0])
    res = pr.sprt_bernoulli(outcomes, p0=0.5, p1=0.6)
    expected = np.cumsum(
        np.where(outcomes == 1, math.log(0.6 / 0.5), math.log(0.4 / 0.5))
    )
    np.testing.assert_allclose(res["llr_path"], expected)


def test_sprt_expected_sample_size():
    e = pr.sprt_expected_sample_size(0.6, p0=0.5, p1=0.6, alpha=0.05, beta=0.05)
    assert e == pytest.approx(131.65, abs=0.5)


def test_normal_power_simple():
    power = pr.normal_power_simple(effect=0.2, sigma=1.0, n=100, alpha=0.05)
    assert power == pytest.approx(0.51595, abs=1e-3)
    big = pr.normal_power_simple(effect=0.5, sigma=1.0, n=100, alpha=0.05)
    assert big > 0.99
