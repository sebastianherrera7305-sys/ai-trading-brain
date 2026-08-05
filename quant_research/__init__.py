"""Quantitative Research package — AI Trading Brain.

Independent statistical toolkit for institutional-grade edge validation.
See docs/research/01-06 for the research mandate this package serves.

Phase status (per the research mandate's phase plan):

- Phase 1  Core Mathematics ......... DELIVERED (core, statistics,
  probability utilities, timeseries)
- Phase 2  Statistical Validation ... drafted (resampling, SPRT,
  Bayesian updating); formal completion pending: FDR/Benjamini-
  Hochberg correction and the SPA test
- Phase 3  Risk & Performance ....... planned (ratios)
- Phase 4  Simulation ............... planned (montecarlo)
- Phase 5  Market Regime Research ... planned (edge)
- Phase 6  Benchmark Framework ...... planned
- Phase 7  Research Dataset Schema .. docs/research/04 (spec only)

Design constraints (frozen):

- numpy-only. No scipy, no pandas, no platform imports. Every
  statistical primitive scipy would provide (student-t CDF, chi2 CDF,
  incomplete beta, incomplete gamma) is implemented here so the package
  runs anywhere numpy runs — including the Python 3.9 baseline.
- Python 3.9 compatible. No match statements, no PEP 604 union syntax
  at runtime, only typing-module annotations.
- Pure. No I/O, no network, no DuckDB, no brokers, no FastAPI. Inputs
  are numpy arrays; outputs are numbers/dicts. The platform
  (trading_brain) can integrate later through its own adapter layer;
  this package does not know it exists.
- Deterministic. Every stochastic function takes a seed (default 0) and
  documents its generator policy.
- Heavily unit-tested against closed-form references and known table
  values (see tests/test_quant_research_*.py).

Module map:

- _input:     package input contract (PRIVATE): array-like coercion,
              NaN/Inf/empty policy, determinism — every public function
              follows it
- core:       returns/prices algebra, rolling ops, EWMA, z-scores
- statistics: normal/t/chi2 distributions (CDF, inverse, p-values),
              confidence intervals, t-tests, Jarque-Bera, correlations,
              covariance, descriptive statistics
- probability: binomial math, expected value, Bayesian Beta-Bernoulli
               updating, credible intervals, Kelly criterion, Brier
               score, Wald SPRT
- resampling: block/stationary bootstrap, bootstrap CIs, permutation
              tests, White's Reality Check, deflated Sharpe ratio
- timeseries: autocorrelation, Hurst exponent, variance-ratio test,
              lagged feature matrix
"""

from . import core
from . import statistics
from . import probability
from . import resampling
from . import timeseries

__version__ = "0.2.0"

__all__ = [
    "core",
    "statistics",
    "probability",
    "resampling",
    "timeseries",
]
