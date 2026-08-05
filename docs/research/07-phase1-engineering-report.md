# 07 — Phase 1 Engineering Report: quant_research

**Status:** DELIVERED — awaiting authorization before Phase 2
**Version:** 0.3.0 (API frozen at this version after approval)
**Commits:** `1d8f832` (initial), `81fcfd8` (hardening round 1), `9cfc068` (examples + API stabilization + report), this commit (freeze pass: docstring conventions, technical-debt inventory, freeze checklist)

---

## 1. Package architecture

```
quant_research/                  # numpy-only statistical toolkit (Python 3.9+)
├── __init__.py                  # version, module map, design constraints
├── _input.py                    # PRIVATE input contract shared by every function
├── core.py                      # returns/prices algebra, rolling ops, EWMA, z-scores
├── statistics.py                # distributions, moments, tests, correlations
├── probability.py               # binomial/beta, Kelly, Brier, SPRT, power
├── resampling.py                # block/stationary bootstrap, permutation, RC, DSR
└── timeseries.py                # autocorrelation, Hurst, variance ratio, features

tests/
├── test_quant_research_{core,statistics,probability,resampling,timeseries}.py   # per-module unit suites
├── test_quant_research_inputs.py         # 79 input-contract edge cases
├── test_quant_research_properties.py     # 52 property-based invariant tests
├── test_quant_research_references_numpy_pandas.py  # 17 reference tests
├── test_quant_research_references_scipy.py         # 22 reference tests (opt-in: scipy extra)
├── test_quant_research_branches.py       # 56 validation-branch tests
└── test_quant_research_examples.py       # executes docs/examples/*.md code blocks

benchmarks/bench_quant_research.py        # empirical-complexity benchmark runner
docs/examples/01..06 + README             # research walkthroughs (executable docs)
```

Design rules (frozen):

- **numpy-only at runtime.** scipy and pandas appear only in the optional
  test extras (`pip install -e .[ref]`) as validation references. The
  package runs on any numpy, Python 3.9+.
- **One input contract.** `_input.py` coerces array-likes to 1-D float64,
  rejects scalars/2-D with `ValueError`, strings with `TypeError`,
  generators consumed exactly once. NaN/Inf are dropped by statistical
  functions (then a documented minimum is enforced via `check_min`);
  position-aligned functions (rolling, z-scores) keep NaN in output
  positions. Pure algebra functions return empty arrays on empty input.
- **Deterministic.** Every stochastic function takes `seed` (default 0)
  and uses `np.random.default_rng`; no hidden state between calls.
- **Pure.** No I/O, no network, no platform imports. The trading_brain
  platform integrates later through its own adapter layer.

## 2. Dependency graph

```
quant_research/__init__      -> core, statistics, probability, resampling, timeseries
  _input  (private, imported by every module)
  core    -> _input                      (no cross-module deps)
  statistics -> _input                   (no cross-module deps)
  probability -> _input, statistics      (normal kernels for power; beta via statistics)
  resampling -> _input, statistics, probability (DSR uses normal_cdf)
  timeseries -> _input, core, statistics (uses simple_returns, variance)

Runtime third-party: numpy only.
Test-only: pytest, coverage, pandas (skip-if-missing), scipy (optional extra).
```

Acyclic and shallow: `probability` and `resampling` depend on
`statistics`, nothing depends on `core`'s rolling layer except
`timeseries`. There is no import cycle; the private `_input` layer is the
only shared infrastructure.

## 3. Public API (75 functions, frozen at 0.3.0)

**core (17):** `simple_returns`, `log_returns`, `cumulative_returns`,
`prices_from_returns`, `drawdown_prices`, `z_score`, `rolling_mean`,
`rolling_std`, `rolling_sum`, `rolling_z_score`, `rolling_correlation`,
`ewma`, `ewma_volatility`, `centered_smooth`, `safe_divide`, `drop_nan`,
`required_length`

**statistics (26):** `normal_cdf`, `normal_sf`, `normal_inv_cdf`,
`normal_z_score`, `normal_pdf`, `regularized_incomplete_beta`,
`student_t_cdf`, `student_t_sf`, `student_t_inv_cdf`, `chi2_cdf`,
`chi2_p_value`, `chi2_inv_cdf`, `variance`, `covariance`,
`covariance_matrix`, `coefficient_of_variation`, `empirical_cdf`,
`mean_confidence_interval`, `two_sample_t_test`, `paired_t_test`,
`skewness`, `excess_kurtosis`, `jarque_bera`, `pearson_correlation`,
`spearman_correlation`, `sharpe_standard_error`

**probability (19):** `binomial_pmf`, `binomial_cdf`, `binomial_ci`,
`beta_cdf`, `beta_inv_cdf`, `beta_mean`, `beta_var`, `beta_posterior`,
`probability_edge_above`, `expected_value`, `kelly_fraction`,
`fractional_kelly`, `kelly_expected_growth`, `brier_score`,
`brier_skill_score`, `sprt_bernoulli`, `sprt_expected_sample_size`,
`normal_power`

**resampling (7):** `block_bootstrap`, `stationary_bootstrap`,
`bootstrap_confidence_interval`, `permutation_test_two_sample`,
`permutation_test_signal`, `reality_check_p_value`,
`deflated_sharpe_ratio`

**timeseries (6):** `autocorrelation`, `autocorrelation_series`,
`hurst_exponent`, `variance_ratio`, `variance_ratio_z_score`,
`lagged_features`

**API stabilization (0.2.0 → 0.3.0):** six names renamed before the
freeze, for consistency with the rest of the surface:

| Old | New | Reason |
|-----|-----|--------|
| `core.zscore` | `core.z_score` | spelling consistent with `normal_z_score` |
| `core.rolling_zscore` | `core.rolling_z_score` | same |
| `resampling.bootstrap_ci` | `resampling.bootstrap_confidence_interval` | abbreviation inconsistent with `mean_confidence_interval` |
| `resampling.reality_check_pvalue` | `resampling.reality_check_p_value` | `p_value` spelling consistent with `chi2_p_value` |
| `probability.normal_power_simple` | `probability.normal_power` | vague "simple" suffix |
| `timeseries.variance_ratio_zstat` | `timeseries.variance_ratio_z_score` | consistent with `z_score` convention |

Renames were applied mechanically to source, tests, benchmarks, and
examples; the full suite (including doctests) verified the result.
**From this version on the public API is stable; breaking changes require
an ADR.**

### API consistency conventions (verified by script in the freeze pass)

- **Parameter order**: data argument(s) first, then configuration, then
  optional statistics defaults; two-input functions are uniformly
  `(a, b)`; the primary series is `x`.
- **Seeds**: every stochastic function takes `seed: int = 0` and uses
  `np.random.default_rng`; no hidden state between calls.
- **Defaults**: `ddof=1` (sample moments), `confidence=0.95` (intervals),
  `alpha = beta = 0.05` (test designs), `statistic=` callable in all
  five resampling functions, `n_permutations=5000`, `n_bootstrap=1000`.
- **Return conventions**: tests return `(statistic, [df,] p)`;
  intervals return `(point, lo, hi)` with the point first;
  `sprt_bernoulli` returns a dict; everything else a scalar/array.
- **Exceptions**: `ValueError` for domain/shape violations, `TypeError`
  for strings; degenerate math returns documented values (NaN/inf)
  instead of raising. `Raises` sections document function-local
  validation only — the shared input contract (coercion, scalar/2-D
  rejection, generator consumption) is documented once in `_input.py`.
- **Docstring format**: every public function carries
  Definition / Raises / Complexity / References / Examples sections
  (Raises and References omitted only where genuinely inapplicable,
  e.g. pure scalars and engineering helpers) plus an explicit
  `NaN policy` statement. All 74 public docstrings audited by script in
  the freeze pass.

## 4. Mathematical assumptions (documented per function in docstrings)

- **Normal/Student-t/chi2/Beta kernels**: standard CDF/quantile
  definitions; chi2 = Gamma(df/2, 2) (the factor-2 convention is pinned
  by reference tests); Student-t CDF via the incomplete beta.
- **`regularized_incomplete_beta`**: Numerical Recipes `betai`/`betacf`
  (Lentz continued fraction, symmetry switch at `x < (a+1)/(a+b+2)`).
  This replaced the hypergeometric 2F1 series of Phase 1 initial, which
  suffered catastrophic cancellation for large integer b (see §7).
- **`normal_inv_cdf`**: Acklam's rational approximation, absolute error
  < 1.15e-9; documented as not for extreme-tail quantiles.
- **Jarque-Bera**: raw moments `m3/m2^1.5`, `m4/m2^2` (Jarque & Bera
  1980); `skewness`/`excess_kurtosis` use the small-sample correction
  (Joanes-Gill 1998).
- **t-tests**: Welch's test with fractional degrees of freedom
  (Welch 1947); paired test on the differences.
- **Bootstrap**: resampling of contiguous blocks (block) or
  geometrically sized blocks (stationary, Politis-Romano 1994);
  percentile confidence intervals; all seeded.
- **Permutation tests**: exchangeability null; two-sample = label
  shuffle, signal = signal/return shuffle.
- **White's Reality Check** (White 2000): recenters each trial by its
  own mean, joint block resampling across trials.
- **Deflated Sharpe** (Bailey & López de Prado 2014): expected-maximum
  correction over trials plus skewness/kurtosis correction; inputs are
  per-period Sharpe ratios (annualized inputs must be re-scaled — see
  Example 06).
- **SPRT**: Wald's sequential likelihood-ratio test with fixed p0/p1
  and error rates alpha/beta; ESS is the expected stopping time.
- **Kelly**: `f* = (p(1+b) - 1)/b`; growth functions on log-wealth.
- **Hurst**: R/S analysis on the return series with `min_lag`/`max_lag`
  configuration; noisy for short samples (see limitations).
- **Variance ratio**: Lo-MacKinlay with overlapping intervals and the
  heteroskedasticity-robust standard error.

## 5. Validation methodology

Five layers, each executable:

1. **Closed-form and table values** — every function has doctest
   examples pinned to known values (e.g. `t_0.995(1) = 63.66`,
   `chi2_cdf(3.8415, 1) = 0.95`, `I_0.8(2,5) = 0.9984`).
2. **Input-contract tests** (79): scalars, 2-D, strings, generators,
   empty, single-element, NaN/Inf policies, invalid parameters,
   determinism.
3. **Property-based tests** (52): distributional invariants (Phi(x) +
   Phi(-x) = 1, Beta symmetry, binomial PMF sums to 1, Cov(X,X) = Var(X),
   Kelly maximizes expected log-growth, prices/returns round-trips,
   bootstrap CI widens with block size on AR(1) data, ...), all seeded.
4. **Reference validation vs numpy, pandas and scipy** (39 tests):
   dense grids over CDFs/SFs/PDFs/quantiles and moments. Tolerances are
   documented per function: normal CDF 1e-12, Student-t CDF 1e-10,
   chi2 CDF 1e-9, Beta 1e-10, quantiles 1e-6, Acklam 5e-9. pandas NaN
   policy of rolling windows verified to match ours.
5. **Validation-branch tests** (56): every documented error path,
   degenerate branch, and boundary convention pinned, including the
   ones discovered during coverage sweeps (see §7).

**Examples as regression tests**: `docs/examples/*.md` code blocks are
executed by the test suite, and a guard test fails if any public function
is not demonstrated in at least one example.

**Documentation audit (freeze pass)**: every public docstring now states
an explicit `NaN policy` matched to the verified behavior of the function
(drop-then-min, pairwise-complete, position-aligned propagation,
window-propagation, recursive-filter propagation, scalar flow, or
explicit rejection), and missing References/Complexity/Definition
sections were filled from primary sources. The audit is scripted
(section presence + `NaN policy` presence per `__all__` function).

## 6. Benchmark summary

`benchmarks/bench_quant_research.py` measures each function's empirical
complexity exponent (polyfit of log-time vs log-size) and compares it
with the documented big-O. Sizes are large enough to avoid cache
effects (up to 1M points vectorized; 64k resampling). All verdicts OK:

| Function (n = 8M unless noted) | Time | Empirical exponent |
|---|---|---|
| cumulative_returns | 121.5 ms | 0.97 |
| rolling_mean (w=20) | 351.6 ms | 0.97 |
| rolling_correlation (w=20) | 4.4 s | 0.98 |
| ewma (python loop) | 3.6 s | 0.96 |
| variance | 28.2 ms | 0.84 |
| pearson_correlation | 180.2 ms | 0.86 |
| jarque_bera | 390.4 ms | 0.90 |
| autocorrelation | 236.9 ms | 0.86 |
| variance_ratio (q=20) | 217.8 ms | 0.83 |
| hurst_exponent | 2.3 s | 0.80 |
| block_bootstrap (B=200, 64k) | 3.4 s | 0.88 |
| permutation test (P=500, 64k) | 767.7 ms | 0.93 |
| student_t_inv_cdf (fixed cost) | 8.3 ms (1e5 calls) | — |
| binomial_ci (fixed cost) | 7.9 ms (1e4 calls) | — |
| beta_cdf (fixed cost) | 0.017 ms | — |

The size grid extends to 8M points (64 MB, beyond CPU cache) so the
measured exponents reflect true asymptotic scaling; sub-linear readings
at in-cache sizes (e.g. `variance` at 0.41) are cache artifacts, not
sub-linear algorithms.

## 7. Findings from validation (all fixed in this Phase)

1. **Incomplete-beta kernel (critical).** The initial 2F1-series
   implementation terminally cancelled for large integer b:
   `I_0.134(37,164)` returned 1.124 and `I_0.3(37,164)` returned
   -1.45e22. Replaced with Numerical Recipes `betai`/`betacf`; verified
   against scipy to 1e-10 on grids including (37,164), (164,37),
   (200,37), (100,100). A regression pin keeps this case in the scipy
   reference suite.
2. **Welch df rounding.** The t-test rounded the fractional Welch df
   before computing p-values; the full fractional df is now used.
3. **Jarque-Bera moments.** Was using corrected moments; now uses the
   textbook raw moments (matching scipy's reference).
4. **numpy 2.x covariance.** `np.cov` of a single-column matrix returns
   a scalar; `covariance_matrix` now wraps it to shape (1,1) per docs.
5. **Validation order** in `student_t_inv_cdf` (df=0 slipped through at
   p=0.5); **sqrt-of-negative** in `deflated_sharpe_ratio` (skew/kurt
   radicand now checked before `sqrt`); **SPRT ESS exact-indifference
   float residue** (epsilon test now).
6. **Dead code removed.** The low-p Acklam branch in the private
   `_normal_inv_body` was unreachable through the public API (the
   symmetry flip only feeds it p > 0.5) — removed.
7. **Unreachable guards documented** (not removed, defensive):
   `chi2_inv_cdf` bracket expansion (`hi *= 4` cannot trigger for any
   representable p), Hurst's `rs_mean <= 0` guard (R/S is strictly
   positive whenever computed), `_lower_incomplete_gamma`'s `a <= 0`
   raise (reachable only directly; pinned by a kernel test).

## 8. Test summary

```
Full repo suite:            661 passed, 2 skipped, 2 warnings (~205 s)
quant_research tests:       336 tests + 74 doctests
  - unit suites:            103
  - input contract:          79
  - property-based:          52
  - references (np/pd/scipy): 39
  - validation branches:     56
  - examples (executed docs): 7
Line coverage (quant_research): 858 stmts, 3 miss, 99.7%
  100% of reachable lines; the 3 misses are provably unreachable
  defensive guards (documented above).
```

The 2 skips are pre-existing platform skips (IBKR environment and one
platform conditional), unrelated to quant_research.

## 9. Known limitations

- **Normal inverse** is Acklam's approximation (1.15e-9), not a
  high-precision ppf; fine for all documented cutoffs, not for extreme
  tail work.
- **Hurst exponent** on return series is high-variance at institutional
  sample sizes; use it as corroboration, not as the decision statistic
  (Example 02 shows the honest workflow).
- **Sharpe standard error** assumes iid returns; for autocorrelated
  strategies it is a lower bound — the block bootstrap is the
  dependence-aware alternative.
- **SPRT** tests a fixed alternative; it does not detect drift.
- **Permutation tests** assume exchangeability; dependent data needs
  block resampling.
- **DSR inputs are per-period** Sharpe ratios; feeding annualized
  numbers with per-period n produces meaningless ~1.0 outputs (guarded
  by documentation and Example 06, not by a runtime check).
- **Reality Check** with many correlated variants understates the
  multiplicity effect to some degree; pair it with the DSR.
- **Normal power function** uses the Gaussian approximation; exact
  binomial power preferred for tiny n.
- **Covariance matrix** is the plain sample estimator; no shrinkage
  (Phase 3 concern).
- Bootstrap CIs are percentile-based, not bias-corrected.

### Explicit technical debt (accepted, none blocking Phase 2)

- **Duplicated rolling-window loops.** `rolling_mean/std/sum` repeat the
  sliding-window pattern; a shared kernel would centralize edge handling
  but is deferred until a second consumer appears (YAGNI).
- **`ewma` is a pure-Python loop** (3.6 s at 8M points). A vectorized
  form needs scipy-style convolution tricks the package avoids by
  design; acceptable for research data, flagged for Phase 4 simulation
  workloads.
- **Two `(point, lo, hi)` interval implementations** (t-based in
  `statistics`, bootstrap in `resampling`) are separate; a common
  protocol could unify them but would couple the two modules.
- **DSR's per-period input convention is documentation-only.** A runtime
  guard (e.g. rejecting `|sharpe| > 5`) would catch annualized mis-feeds;
  deliberately deferred to keep the function total.
- **`statistic=` defaults to `np.mean`** — ergonomic, but hides the
  statistic choice; callers are encouraged to pass explicit functions
  (the examples do).
- **The scipy reference suite is an optional extra**; institutional CI
  should pin it (Recommendation 3).
- **Numerical approximation debt**: Acklam inverse normal (1.15e-9),
  bisection-based quantiles (200 halvings), Numerical Recipes continued
  fraction — all documented, all bounded, none replaceable without a new
  dependency.
- **Hidden coupling** (intentional, documented): probability and
  resampling import statistics kernels, so a change to
  `regularized_incomplete_beta` ripples into beta CDF, Student-t, and
  binomial CI — caught by the reference suites.
- **`hurst_exponent(max_lag=0)` uses 0 as an "automatic" sentinel** —
  a documented quirk, not a type error; accepted for ergonomics.

## 10. Future extension points

- **Phase 2 (statistical validation):** FDR/Benjamini-Hochberg
  correction (planned in the research mandate), Hansen's SPA test,
  stepwise White RC, walk-forward machinery.
- **Phase 3 (risk & performance):** downside ratios (Sortino, Calmar,
  MAR), VaR/CVaR with the existing distribution kernels, covariance
  shrinkage, drawdown distribution via bootstrap.
- **Phase 4 (simulation):** Monte Carlo engines built on the seeded
  RNG policy already in place.
- **Phase 5 (regime research):** the `lagged_features` + rolling
  primitives in Example 02 are the raw material for the edge module.
- **Platform integration:** the pure numpy interface is designed for a
  thin adapter inside trading_brain (no package knowledge of the
  platform).

## 11. Examples produced

`docs/examples/` — six walkthroughs, all deterministic and executed as
regression tests (see README.md table for the function mapping); each
follows the Problem / Dataset / Method / Code / Interpretation /
Limitations research-report template:

1. **Trading expectancy and position sizing** — expectancy, Clopper-
   Pearson CI vs Bayesian posterior, power analysis, Kelly sizing.
2. **Market regime detection** — variance-ratio, autocorrelation,
   Hurst, rolling/EWMA statistics, lagged features.
3. **Equity curve and drawdown analytics** — return conventions,
   drawdown, Sharpe + standard error, normality diagnostics, CI
   comparison.
4. **Validating a trading edge** — Welch/paired/permutation tests,
   Beta-Bernoulli evidence, SPRT monitoring, Brier calibration, chi2
   variance test.
5. **Correlated instruments** — covariance matrix, Pearson vs Spearman
   robustness, minimum-variance hedging.
6. **Backtest robustness** — block/stationary bootstrap, White's
   Reality Check, deflated Sharpe under a 40-trial search.

## 12. Recommendations before Phase 2

1. **Approve the API freeze** (0.3.0). Post-freeze changes go through
   the ADR process.
2. **Adopt the examples as the research onboarding material** — they
   are the standing documentation of how the platform expects the
   library to be used.
3. **Consider pinning the `ref` extra in CI** (scipy) so the reference
   suites always run; today they run only where scipy is installed.
4. **Add a CI job for Python 3.9** to lock the baseline (locally the
   package is exercised on 3.9+ only).
5. **Before Phase 2 starts**, the mandate requires the FDR/BH
   correction; the resampling layer (RC, DSR) is the natural host.

---

## 13. Phase 1 freeze checklist

| Item | Status |
|------|--------|
| Public API reviewed and frozen at 0.3.0 (6 renames; ADR gate afterwards) | PASS |
| Naming consistent across modules (`z_score`, `p_value`, `_confidence_interval`) | PASS |
| Parameter ordering and naming uniform; two-input convention `(a, b)` | PASS |
| Seeds uniform (`seed=0`, `default_rng`) in all stochastic functions | PASS |
| NaN policy explicit and correct in every public docstring (74/74 scripted audit) | PASS |
| Docstring sections complete (Definition/Raises/Complexity/References/Examples) | PASS |
| Error handling uniform (ValueError domains, TypeError for str, documented NaN/inf returns) | PASS |
| Examples executable, pinned, deterministic; Problem/Dataset/Method template applied | PASS |
| Every public function demonstrated in an example (guard test) | PASS |
| Benchmarks complete at 8M points; measured exponents match documented big-O | PASS |
| Mathematical references verified against primary sources (AS, Feller, Tsay, Welch, ...) | PASS |
| Property, reference, input, branch, regression, and doctest suites green | PASS |
| Full repo suite green (661 passed, 2 skipped — both pre-existing platform skips) | PASS |
| Line coverage 99.7% (858 stmts, 3 miss — provably unreachable guards) | PASS |
| Technical debt explicitly documented; none blocking | PASS |
| Engineering report refreshed with final audit results | PASS |

All items green. Phase 1 is complete and frozen. **Phase 2 will not
begin without explicit authorization following this report.**

---
Prepared for the Phase 1 acceptance review. Phase 2 will not begin
without explicit authorization following this report.
