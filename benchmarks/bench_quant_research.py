"""Benchmarks for quant_research — run with:

    python3 benchmarks/bench_quant_research.py

Measures runtime scaling of the hot paths at increasing input sizes and
reports the empirical complexity exponent (log(runtime)/log(n)) against
the documented asymptotic complexity. Numbers are indicative on any
machine; the exponent is the stable readout.

The benchmarks deliberately use large n to be meaningful:
- the bisection-based inverse CDFs are O(200) scalar kernel calls and
  are benchmarked at fixed cost, not scaling.
"""

import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quant_research import core, probability, resampling, statistics, timeseries  # noqa: E402


def _timeit(fn, repeat=3):
    best = float("inf")
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - t0)
    return best


def _scaling(name, fn, sizes, repeat=3, expected=None):
    times = []
    for n in sizes:
        times.append(_timeit(lambda: fn(n), repeat=repeat))
    xs = [math.log(n) for n in sizes]
    ys = [math.log(max(t, 1e-9)) for t in times]
    exponent = None
    if len(sizes) >= 4 and all(t > 0 for t in times):
        exponent = float(np.polyfit(xs, ys, 1)[0])
    verdict = ""
    if expected is not None and exponent is not None:
        ratio = exponent / expected
        if 0.6 < ratio < 1.5:
            verdict = "OK"
        else:
            verdict = "CHECK: measured %.2f vs documented %.2f" % (exponent, expected)
    line = "%-38s n=%7d  %8.1f ms" % (name, sizes[-1], times[-1] * 1e3)
    if exponent is not None:
        line += "   exponent=%.2f" % exponent
    if verdict:
        line += "   [%s]" % verdict
    print(line)
    return times


def main():
    # Vectorized sections need sizes beyond cache residency for the
    # measured exponent to reflect true asymptotic scaling.
    sizes = [2_000, 16_000, 128_000, 1_000_000]
    rng = np.random.default_rng(0)

    print("=== core: documented O(n) ===")
    data = {n: rng.normal(0.0, 0.01, n) for n in sizes}

    def _cum(n):
        core.cumulative_returns(data[n])

    def _roll(n):
        core.rolling_mean(data[n], 20)

    def _rollcorr(n):
        core.rolling_correlation(data[n], data[n][::-1], 20)

    def _ewma(n):
        core.ewma(data[n], 10.0)

    _scaling("cumulative_returns", _cum, sizes, expected=1.0)
    _scaling("rolling_mean w=20", _roll, sizes, expected=1.0)
    _scaling("rolling_correlation w=20", _rollcorr, sizes, expected=1.0)
    _scaling("ewma (python loop)", _ewma, sizes, expected=1.0)

    print("\n=== statistics: documented O(n) ===")
    def _var(n):
        statistics.variance(data[n])

    def _corr(n):
        statistics.pearson_correlation(data[n], data[n][::-1])

    def _jb(n):
        statistics.jarque_bera(data[n])

    _scaling("variance", _var, sizes, expected=1.0)
    _scaling("pearson_correlation", _corr, sizes, expected=1.0)
    _scaling("jarque_bera", _jb, sizes, expected=1.0)

    print("\n=== timeseries ===")
    def _ac(n):
        timeseries.autocorrelation(data[n])

    def _hur(n):
        timeseries.hurst_exponent(data[n])

    def _vr(n):
        timeseries.variance_ratio(data[n], 20)

    _scaling("autocorrelation lag=1", _ac, sizes, expected=1.0)
    _scaling("variance_ratio q=20", _vr, sizes, expected=1.0)
    _scaling("hurst_exponent (O(n log n))", _hur, sizes, expected=1.0)

    print("\n=== resampling: O(n_bootstrap * n) at fixed n_bootstrap ===")
    rs_sizes = [1_000, 4_000, 16_000, 64_000]
    rs_data = {n: rng.normal(0.0, 1.0, n) for n in rs_sizes}

    def _block(n):
        resampling.block_bootstrap(rs_data[n], 10, n_bootstrap=200, seed=0)

    def _perm(n):
        resampling.permutation_test_signal(
            rs_data[n], rng.integers(0, 2, n).astype(float),
            n_permutations=500, seed=0,
        )

    _scaling("block_bootstrap b=10, B=200", _block, rs_sizes, expected=1.0)
    _scaling("permutation_test_signal P=500", _perm, rs_sizes, expected=1.0)

    print("\n=== probability: fixed-cost kernels (single call each) ===")
    t = _timeit(lambda: statistics.student_t_inv_cdf(0.975, 200))
    print("%-38s %8.3f ms" % ("student_t_inv_cdf (200 bisections)", t * 1e3))
    t = _timeit(lambda: probability.binomial_ci(37, 200))
    print("%-38s %8.3f ms" % ("binomial_ci(37, 200) (2 inverses)", t * 1e3))
    t = _timeit(lambda: probability.beta_cdf(0.134, 37.0, 164.0))
    print("%-38s %8.3f ms" % ("beta_cdf(0.134, 37, 164)", t * 1e3))


if __name__ == "__main__":
    main()
