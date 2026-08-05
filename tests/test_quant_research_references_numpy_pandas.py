"""Reference-validation tests against numpy and pandas (always run).

Every quant_research function that has a numpy/pandas equivalent must
agree with it on the same data — this pins the package against silent
drift in the reference implementations' behavior, not just against
hand-written expected values. pandas is optional: the file skips its
pandas sections if pandas is missing (scipy references live in
test_quant_research_references_scipy.py).
"""

import math

import numpy as np
import pytest

from quant_research import core, probability, resampling, statistics, timeseries

pandas = pytest.importorskip("pandas")

RNG = np.random.default_rng(42)
X = RNG.normal(0.0, 1.0, 200)
Y = RNG.normal(0.0, 1.0, 200) + 0.3 * X


# ---------------------------------------------------------------------------
# numpy references
# ---------------------------------------------------------------------------

def test_variance_matches_numpy():
    assert statistics.variance(X) == pytest.approx(float(np.var(X, ddof=1)), rel=1e-12)
    assert statistics.variance(X, ddof=0) == pytest.approx(
        float(np.var(X, ddof=0)), rel=1e-12
    )


def test_covariance_matches_numpy():
    assert statistics.covariance(X, Y) == pytest.approx(
        float(np.cov(X, Y, ddof=1)[0, 1]), rel=1e-12
    )


def test_covariance_matrix_matches_numpy():
    M = np.column_stack([X, Y])
    np.testing.assert_allclose(
        statistics.covariance_matrix(M), np.cov(M, rowvar=False, ddof=1), rtol=1e-12
    )


def test_pearson_correlation_matches_numpy():
    assert statistics.pearson_correlation(X, Y) == pytest.approx(
        float(np.corrcoef(X, Y)[0, 1]), rel=1e-12
    )


def test_empirical_cdf_matches_manual_formula():
    v = np.array([-1.0, 0.0, 0.5, 2.0])
    manual = np.array(
        [float(np.sum(X <= q)) / len(X) for q in v]
    )
    np.testing.assert_allclose(statistics.empirical_cdf(X, v), manual, rtol=1e-12)


# ---------------------------------------------------------------------------
# pandas references (same convention checks)
# ---------------------------------------------------------------------------

def test_rolling_mean_matches_pandas():
    s = pandas.Series(X)
    ours = core.rolling_mean(X, 20)
    ref = s.rolling(20).mean().to_numpy()
    np.testing.assert_allclose(ours[19:], ref[19:], rtol=1e-12)
    assert np.all(np.isnan(ours[:19]))


def test_rolling_std_matches_pandas():
    s = pandas.Series(X)
    ours = core.rolling_std(X, 20, ddof=1)
    ref = s.rolling(20).std(ddof=1).to_numpy()
    np.testing.assert_allclose(ours[19:], ref[19:], rtol=1e-12)


def test_rolling_sum_matches_pandas():
    s = pandas.Series(X)
    ours = core.rolling_sum(X, 20)
    ref = s.rolling(20).sum().to_numpy()
    np.testing.assert_allclose(ours[19:], ref[19:], rtol=1e-12)


def test_ewma_matches_pandas_adjust_false():
    # pandas ewm(adjust=False) is exactly the recursive warm-start
    # filter implemented here.
    s = pandas.Series(X)
    ours = core.ewma(X, 12.0)
    ref = s.ewm(span=12.0, adjust=False).mean().to_numpy()
    np.testing.assert_allclose(ours, ref, rtol=1e-12)


def test_rolling_correlation_matches_pandas():
    ours = core.rolling_correlation(X, Y, 20)
    ref = (
        pandas.Series(X).rolling(20).corr(pandas.Series(Y)).to_numpy()
    )
    np.testing.assert_allclose(ours[19:], ref[19:], rtol=1e-12, atol=1e-12)


def test_autocorrelation_matches_pandas():
    assert timeseries.autocorrelation(X, lag=1) == pytest.approx(
        float(pandas.Series(X).autocorr(lag=1)), rel=1e-12
    )
    assert timeseries.autocorrelation(X, lag=3) == pytest.approx(
        float(pandas.Series(X).autocorr(lag=3)), rel=1e-12
    )


def test_autocorrelation_series_matches_pandas():
    max_lag = 10
    ours = timeseries.autocorrelation_series(X, max_lag)
    ref = np.array([pandas.Series(X).autocorr(lag=k) for k in range(1, max_lag + 1)])
    np.testing.assert_allclose(ours, ref, rtol=1e-12)


def test_skewness_matches_pandas():
    assert statistics.skewness(X) == pytest.approx(
        float(pandas.Series(X).skew()), rel=1e-12
    )


def test_excess_kurtosis_matches_pandas():
    assert statistics.excess_kurtosis(X) == pytest.approx(
        float(pandas.Series(X).kurt()), rel=1e-12
    )


def test_spearman_correlation_matches_pandas():
    # pandas method="spearman" requires scipy internally, so use the
    # equivalent rank + Pearson construction (pandas .rank() default
    # is average ranks, matching our _ranks).
    ref = float(
        pandas.Series(X).rank().corr(pandas.Series(Y).rank(), method="pearson")
    )
    assert statistics.spearman_correlation(X, Y) == pytest.approx(ref, rel=1e-12)


def test_drawdown_matches_pandas_cummax():
    prices = 100.0 * np.cumprod(1.0 + 0.01 * X + 0.001)
    ours = core.drawdown_prices(prices)
    ref = pandas.Series(prices).div(pandas.Series(prices).cummax()) - 1.0
    np.testing.assert_allclose(ours, ref.to_numpy(), rtol=1e-12)


# ---------------------------------------------------------------------------
# NaN policy alignment with pandas
# ---------------------------------------------------------------------------

def test_rolling_mean_nan_policy_matches_pandas():
    # Both propagate NaN through a window: the window mean is NaN when
    # any member is NaN. This pins the alignment so neither side can
    # silently drift.
    x = np.array([1.0, np.nan, 3.0, 4.0])
    ours = core.rolling_mean(x, 2)
    ref = pandas.Series(x).rolling(2).mean().to_numpy()
    np.testing.assert_allclose(ours, ref, rtol=1e-12, equal_nan=True)
