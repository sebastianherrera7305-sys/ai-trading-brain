"""Property-based tests for quant_research: mathematical invariants that
must hold for ANY input, with fixed seeds for determinism.

Every test here checks an identity (Cov(X,X) = Var(X), Phi(x) + Phi(-x)
= 1, total probability of the binomial, ...) that a regression in any
kernel would break. No external property-testing library: deterministic
loops over seeded random draws.
"""

import math

import numpy as np
import pytest

from quant_research import core, probability, resampling, statistics, timeseries


SEEDS = (0, 1, 2, 3, 4)


def _noisy(n=200, seed=0, mu=0.0, sigma=1.0):
    return np.random.default_rng(seed).normal(mu, sigma, n)


# ---------------------------------------------------------------------------
# Statistics invariants
# ---------------------------------------------------------------------------

def test_covariance_of_x_with_itself_is_variance():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        assert statistics.covariance(x, x) == pytest.approx(
            statistics.variance(x), rel=1e-12
        )


def test_variance_nonnegative_and_affine_invariant():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        assert statistics.variance(x) >= 0.0
        assert statistics.variance(x + 100.0) == pytest.approx(
            statistics.variance(x), rel=1e-12
        )
        assert statistics.variance(3.0 * x) == pytest.approx(
            9.0 * statistics.variance(x), rel=1e-12
        )


def test_mean_is_translation_covariant():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        assert float(np.mean(x + 7.5)) == pytest.approx(
            float(np.mean(x)) + 7.5, rel=1e-12
        )


@pytest.mark.parametrize(
    "corr", [statistics.pearson_correlation, statistics.spearman_correlation]
)
def test_correlation_symmetry_and_self(corr):
    for seed in SEEDS:
        x, y = _noisy(seed=seed), _noisy(seed=seed + 10)
        assert corr(x, y) == pytest.approx(corr(y, x), abs=1e-12)
        assert corr(x, x) == pytest.approx(1.0, abs=1e-12)
        assert corr(x, -x) == pytest.approx(-1.0, abs=1e-12)


def test_pearson_correlation_affine_invariant():
    for seed in SEEDS:
        x, y = _noisy(seed=seed), _noisy(seed=seed + 10)
        r = statistics.pearson_correlation(x, y)
        assert statistics.pearson_correlation(x, 2.0 * y + 5.0) == pytest.approx(
            r, abs=1e-12
        )
        assert statistics.pearson_correlation(x, -1.0 * y) == pytest.approx(
            -r, abs=1e-12
        )


def test_spearman_correlation_of_monotone_transform_is_one():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        assert statistics.spearman_correlation(x, np.exp(x)) == pytest.approx(
            1.0, abs=1e-12
        )


def test_skewness_sign_flips_with_x():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        s = statistics.skewness(x)
        assert statistics.skewness(-x) == pytest.approx(-s, abs=1e-12)


def test_kurtosis_invariant_to_translation_and_scaling():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        k = statistics.excess_kurtosis(x)
        assert statistics.excess_kurtosis(x + 42.0) == pytest.approx(k, abs=1e-9)
        assert statistics.excess_kurtosis(3.0 * x) == pytest.approx(k, abs=1e-9)


def test_z_score_has_zero_mean_unit_std():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        z = core.z_score(x)
        assert float(np.mean(z)) == pytest.approx(0.0, abs=1e-12)
        assert float(np.std(z, ddof=1)) == pytest.approx(1.0, abs=1e-12)


def test_empirical_cdf_monotone_and_bounded():
    x = _noisy(n=1000, seed=1)
    values = np.array([-3.0, -1.0, 0.0, 0.5, 1.0, 3.0])
    f = statistics.empirical_cdf(x, values)
    assert np.all(np.diff(f) >= -1e-15)
    assert 0.0 <= f.min() and f.max() <= 1.0


def test_mean_confidence_interval_contains_mean():
    for seed in SEEDS:
        x = _noisy(seed=seed)
        m, lo, hi = statistics.mean_confidence_interval(x)
        assert lo <= m <= hi
        assert m == pytest.approx(float(np.mean(x)), rel=1e-12)


def test_two_sample_t_test_identical_distributions_symmetric():
    rng = np.random.default_rng(3)
    for _ in range(5):
        a = rng.normal(0.0, 1.0, 50)
        b = rng.normal(0.0, 1.0, 50)
        t_ab, _, p_ab = statistics.two_sample_t_test(a, b)
        t_ba, _, p_ba = statistics.two_sample_t_test(b, a)
        assert t_ab == pytest.approx(-t_ba, abs=1e-12)
        assert p_ab == pytest.approx(p_ba, abs=1e-12)


# ---------------------------------------------------------------------------
# Distribution identities
# ---------------------------------------------------------------------------

def test_normal_cdf_antisymmetry():
    for x in np.linspace(-5.0, 5.0, 21):
        assert statistics.normal_cdf(x) + statistics.normal_cdf(-x) == pytest.approx(
            1.0, abs=1e-12
        )


def test_normal_inv_cdf_roundtrip():
    for p in (0.001, 0.05, 0.25, 0.5, 0.75, 0.95, 0.999):
        assert statistics.normal_cdf(statistics.normal_inv_cdf(p)) == pytest.approx(
            p, abs=1e-9
        )


def test_student_t_cdf_symmetry():
    for df in (1, 5, 10, 30):
        for t in np.linspace(0.1, 20.0, 8):
            assert statistics.student_t_cdf(t, df) + statistics.student_t_cdf(
                -t, df
            ) == pytest.approx(1.0, abs=1e-9)


def test_student_t_inv_cdf_roundtrip():
    for df in (1, 2, 10, 100):
        for p in (0.01, 0.1, 0.5, 0.9, 0.99):
            assert statistics.student_t_cdf(
                statistics.student_t_inv_cdf(p, df), df
            ) == pytest.approx(p, abs=1e-6)


def test_chi2_cdf_monotone_in_x():
    for df in (1, 4, 10):
        xs = np.linspace(0.0, 3.0 * df, 30)
        cdfs = [statistics.chi2_cdf(x, df) for x in xs]
        assert np.all(np.diff(cdfs) >= -1e-12)
        assert cdfs[0] == pytest.approx(0.0, abs=1e-12)


def test_chi2_inv_cdf_roundtrip():
    for df in (1, 2, 8, 40):
        for p in (0.01, 0.5, 0.95):
            assert statistics.chi2_cdf(statistics.chi2_inv_cdf(p, df), df) == pytest.approx(
                p, abs=1e-6
            )


def test_beta_cdf_boundaries_and_symmetry():
    for (a, b) in [(0.5, 0.5), (1.0, 1.0), (2.0, 5.0), (9.0, 3.0)]:
        assert probability.beta_cdf(0.0, a, b) == pytest.approx(0.0, abs=1e-12)
        assert probability.beta_cdf(1.0, a, b) == pytest.approx(1.0, abs=1e-12)
        for x in (0.1, 0.3, 0.7, 0.9):
            assert probability.beta_cdf(x, a, b) == pytest.approx(
                1.0 - probability.beta_cdf(1.0 - x, b, a), abs=1e-9
            )


def test_beta_inv_cdf_roundtrip():
    for (a, b) in [(0.5, 0.5), (2.0, 2.0), (3.0, 9.0)]:
        for p in (0.01, 0.5, 0.99):
            assert probability.beta_cdf(
                probability.beta_inv_cdf(p, a, b), a, b
            ) == pytest.approx(p, abs=1e-6)


def test_binomial_pmf_sums_to_one():
    for (n, p) in [(5, 0.3), (10, 0.5), (20, 0.8), (50, 0.05), (50, 0.95)]:
        total = sum(probability.binomial_pmf(k, n, p) for k in range(n + 1))
        assert total == pytest.approx(1.0, abs=1e-12)


def test_binomial_cdf_consistent_with_pmf():
    n, p = 12, 0.4
    partial = 0.0
    for k in range(n + 1):
        partial += probability.binomial_pmf(k, n, p)
        assert probability.binomial_cdf(k, n, p) == pytest.approx(partial, abs=1e-12)


def test_binomial_ci_contains_sample_fraction():
    for (k, n) in [(0, 10), (3, 10), (5, 10), (8, 10), (10, 10)]:
        lo, hi = probability.binomial_ci(k, n)
        assert lo <= k / n <= hi


def test_binomial_ci_tightens_with_n():
    lo10, hi10 = probability.binomial_ci(5, 10)
    lo100, hi100 = probability.binomial_ci(50, 100)
    assert (hi100 - lo100) < (hi10 - lo10)


# ---------------------------------------------------------------------------
# Kelly / decision theory
# ---------------------------------------------------------------------------

def test_kelly_maximizes_expected_log_growth():
    for (p, b) in [(0.55, 2.0), (0.6, 1.0), (0.7, 0.5)]:
        f_star = probability.kelly_fraction(p, b)
        g_at_star = probability.kelly_expected_growth(p, b, f_star)
        for f in np.linspace(0.05, 0.95, 20):
            if f == f_star:
                continue
            assert g_at_star >= probability.kelly_expected_growth(
                p, b, float(f)
            ) - 1e-12


def test_kelly_positive_edge_only():
    assert probability.kelly_fraction(0.6, 1.0) > 0.0
    assert probability.kelly_fraction(0.4, 1.0) == pytest.approx(0.0)


def test_probability_edge_above_monotone_in_successes():
    probs = [
        probability.probability_edge_above(k, 10 - k)
        for k in range(11)
    ]
    assert np.all(np.diff(probs) > 0.0)
    assert probs[-1] > 0.9
    assert probs[0] < 0.1


def test_brier_skill_score_base_rate_scores_zero():
    rng = np.random.default_rng(5)
    y = (rng.uniform(0.0, 1.0, 300) > 0.6).astype(float)
    base = float(np.mean(y))
    assert probability.brier_skill_score(
        np.full_like(y, base), y
    ) == pytest.approx(0.0, abs=1e-12)


def test_sprt_final_llr_grows_with_wins():
    rng = np.random.default_rng(8)
    out = rng.binomial(1, 0.5, 30).astype(float)
    r1 = probability.sprt_bernoulli(out, 0.4, 0.6)
    r2 = probability.sprt_bernoulli(np.concatenate([out, [1.0]]), 0.4, 0.6)
    assert r2["final_llr"] > r1["final_llr"]
    r3 = probability.sprt_bernoulli(np.concatenate([out, [0.0]]), 0.4, 0.6)
    assert r3["final_llr"] < r1["final_llr"]


def test_sprt_bounds_are_wald_constants():
    r = probability.sprt_bernoulli(np.array([1.0]), 0.4, 0.6)
    assert r["upper_bound"] == pytest.approx(math.log(19.0), rel=1e-12)
    assert r["lower_bound"] == pytest.approx(math.log(1.0 / 19.0), rel=1e-12)


# ---------------------------------------------------------------------------
# Core algebra invariants
# ---------------------------------------------------------------------------

def test_prices_returns_roundtrip_random_paths():
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        steps = rng.normal(0.0, 0.01, 300)
        prices = np.empty(len(steps) + 1)
        prices[0] = 100.0
        prices[1:] = 100.0 * np.cumprod(1.0 + steps)
        rebuilt = core.prices_from_returns(core.simple_returns(prices), 100.0)
        np.testing.assert_allclose(rebuilt, prices, rtol=1e-10)


def test_log_returns_sum_to_log_growth():
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        prices = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, 200))
        lr = core.log_returns(prices)
        assert float(np.nansum(lr)) == pytest.approx(
            math.log(prices[-1] / prices[0]), rel=1e-12
        )


def test_cumulative_returns_recurrence():
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        r = rng.normal(0.0, 0.01, 100)
        g = core.cumulative_returns(r)
        for t in range(1, len(g)):
            assert g[t] == pytest.approx(g[t - 1] * (1.0 + r[t]), rel=1e-12)


def test_drawdown_never_positive_and_zero_at_highs():
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        prices = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, 300))
        dd = core.drawdown_prices(prices)
        assert np.all(dd <= 1e-12)
        assert dd[np.argmax(prices)] == pytest.approx(0.0, abs=1e-12)


def test_rolling_mean_of_constant_is_constant():
    x = np.full(50, 3.0)
    out = core.rolling_mean(x, 7)
    np.testing.assert_allclose(out[6:], [3.0] * 44)
    assert np.all(np.isnan(out[:6]))


def test_ewma_of_constant_is_constant():
    for span in (2.0, 10.0, 50.0):
        np.testing.assert_allclose(core.ewma(np.full(20, 5.0), span), np.full(20, 5.0))


def test_rolling_z_score_mean_of_valid_part_near_zero():
    rng = np.random.default_rng(4)
    x = rng.normal(0.0, 1.0, 500)
    z = core.rolling_z_score(x, 50)
    assert abs(float(np.nanmean(z))) < 0.1
    assert abs(float(np.nanstd(z, ddof=1)) - 1.0) < 0.2


# ---------------------------------------------------------------------------
# Resampling invariants (fixed seeds)
# ---------------------------------------------------------------------------

def test_permutation_test_identical_samples_gives_one():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    p = resampling.permutation_test_two_sample(a, a, n_permutations=1000, seed=0)
    assert p == pytest.approx(1.0)


def test_permutation_test_different_means_detectable():
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    b = np.array([11.0, 12.0, 13.0, 14.0, 15.0, 16.0])
    p = resampling.permutation_test_two_sample(a, b, n_permutations=2000, seed=0)
    assert p < 0.05


def test_bootstrap_means_centered_on_sample_mean():
    x = _noisy(n=200, seed=11)
    dist = resampling.block_bootstrap(x, 10, n_bootstrap=2000, seed=3)
    assert float(np.mean(dist)) == pytest.approx(float(np.mean(x)), abs=0.15)


def test_bootstrap_ci_contains_estimate():
    x = _noisy(n=200, seed=11)
    est, lo, hi = resampling.bootstrap_confidence_interval(x, block_size=5, n_bootstrap=1000, seed=1)
    assert lo <= est <= hi


def _ar1(n=500, seed=11, phi=0.8):
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, 1.0, n)
    x = np.empty(n)
    x[0] = e[0]
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x


def test_bootstrap_ci_reflects_serial_dependence():
    # On dependent data, single-value resampling destroys the
    # dependence and OVERSTATES confidence (narrow CI); block
    # resampling must produce an honestly wider interval.
    x = _ar1()
    _, lo1, hi1 = resampling.bootstrap_confidence_interval(
        x, block_size=1, n_bootstrap=1000, seed=1
    )
    _, lo40, hi40 = resampling.bootstrap_confidence_interval(
        x, block_size=40, n_bootstrap=1000, seed=1
    )
    assert (hi40 - lo40) > (hi1 - lo1)


def test_reality_check_no_edge_has_large_pvalue():
    rng = np.random.default_rng(11)
    trials = rng.normal(0.0, 1.0, (20, 100))
    p = resampling.reality_check_p_value(trials, block_size=5, n_bootstrap=1000, seed=2)
    assert p > 0.05


def test_reality_check_one_lucky_trial_still_honest():
    rng = np.random.default_rng(12)
    trials = rng.normal(0.0, 1.0, (20, 100))
    trials[0, :] += 0.5
    p = resampling.reality_check_p_value(trials, block_size=5, n_bootstrap=2000, seed=2)
    assert p < 0.2


# ---------------------------------------------------------------------------
# Time-series invariants
# ---------------------------------------------------------------------------

def test_autocorrelation_of_iid_is_small():
    for seed in SEEDS:
        x = _noisy(n=2000, seed=seed)
        assert abs(timeseries.autocorrelation(x)) < 0.15
        assert abs(timeseries.autocorrelation(x, lag=2)) < 0.15


def test_autocorrelation_of_positive_trend_is_positive():
    x = np.arange(1.0, 501.0)
    assert timeseries.autocorrelation(x) > 0.99


def test_autocorrelation_series_length():
    ac = timeseries.autocorrelation_series(_noisy(n=1000, seed=5), 10)
    assert ac.shape == (10,)


def test_variance_ratio_of_iid_near_one():
    for seed in SEEDS:
        x = _noisy(n=2000, seed=seed)
        vr = timeseries.variance_ratio(x, 4)
        assert abs(vr - 1.0) < 0.3


def test_variance_ratio_of_positive_autocorrelation_above_one():
    rng = np.random.default_rng(7)
    trend = 0.1 + 0.9 * np.cumsum(rng.normal(0.0, 1.0, 1000))
    vr = timeseries.variance_ratio(trend, 4)
    assert vr > 1.2


def test_hurst_of_iid_near_half():
    for seed in (0, 1, 2):
        x = _noisy(n=2000, seed=seed)
        h = timeseries.hurst_exponent(x)
        assert 0.3 < h < 0.7


def test_lagged_features_reconstruction():
    x = _noisy(n=50, seed=2)
    X = timeseries.lagged_features(x, 2)
    np.testing.assert_allclose(X[:, 0], x)
    np.testing.assert_allclose(X[1:, 1], x[:-1])
    np.testing.assert_allclose(X[2:, 2], x[:-2])
    assert np.isnan(X[0, 1])
    assert np.all(np.isnan(X[:2, 2]))
