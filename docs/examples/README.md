# quant_research — Research Examples

Reproducible walkthroughs showing the intended use of the package in
realistic quantitative research workflows. Each file follows the same
research-report template: **Problem** (the question and why it matters),
**Dataset** (what data was used and how it was generated),
**Method** (the mathematical approach), **Code** (the executable
demonstration), **Interpretation** (how to read the results), and
**Limitations** (what the method does not claim).

Every python code block in these files is executed as a regression test
(`tests/test_quant_research_examples.py`): the examples are the contract.
If a future change breaks the behavior documented here, the suite fails.

| File | Problem | Functions demonstrated |
|------|-------------------|------------------------|
| [01_trading_expectancy_and_position_sizing.md](01_trading_expectancy_and_position_sizing.md) | Is the expectancy positive and how big should positions be? | expected_value, kelly_fraction, fractional_kelly, kelly_expected_growth, binomial_pmf, binomial_cdf, binomial_ci, normal_power, normal_z_score, beta_posterior, beta_mean, beta_var, probability_edge_above |
| [02_market_regime_detection.md](02_market_regime_detection.md) | Is the market trending, mean-reverting, or a random walk? | rolling_mean, rolling_std, rolling_sum, rolling_z_score, z_score, centered_smooth, ewma, ewma_volatility, rolling_correlation, autocorrelation, autocorrelation_series, variance_ratio, variance_ratio_z_score, hurst_exponent, lagged_features, simple_returns |
| [03_equity_curve_and_drawdown_analytics.md](03_equity_curve_and_drawdown_analytics.md) | What was the realized Sharpe, worst drawdown, and return distribution? | simple_returns, log_returns, cumulative_returns, prices_from_returns, drawdown_prices, safe_divide, drop_nan, required_length, variance, coefficient_of_variation, skewness, excess_kurtosis, jarque_bera, empirical_cdf, mean_confidence_interval, sharpe_standard_error, bootstrap_confidence_interval |
| [04_validating_a_trading_edge.md](04_validating_a_trading_edge.md) | Is the observed edge real or noise — and can it be monitored live? | two_sample_t_test, paired_t_test, permutation_test_two_sample, permutation_test_signal, sprt_bernoulli, sprt_expected_sample_size, chi2_cdf, chi2_p_value, chi2_inv_cdf, regularized_incomplete_beta, beta_cdf, beta_inv_cdf, normal_cdf, normal_pdf, normal_inv_cdf, normal_sf, student_t_cdf, student_t_sf, student_t_inv_cdf, brier_score, brier_skill_score |
| [05_correlated_instruments_and_portfolio_risk.md](05_correlated_instruments_and_portfolio_risk.md) | How correlated are two futures, and what does the hedge buy? | covariance, covariance_matrix, pearson_correlation, spearman_correlation |
| [06_backtest_robustness_resampling.md](06_backtest_robustness_resampling.md) | How much of the best backtest is luck after 40 trials? | block_bootstrap, stationary_bootstrap, bootstrap_confidence_interval, reality_check_p_value, deflated_sharpe_ratio |

All examples are deterministic (fixed seeds) and self-verifying
(assertions inside the code blocks).
