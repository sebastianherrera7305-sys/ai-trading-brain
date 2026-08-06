"""Example experiment: momentum scan on synthetic data.

Deliberately deterministic: every random draw goes through
``ctx.rng``, which is seeded with ``ctx.seed`` by the runner, so the
same experiment always produces the same metrics.
"""

import numpy as np


def run(ctx):
    params = ctx.params
    n = params["n_points"]
    window = params["window"]
    rng = ctx.rng

    # Synthetic price path: drift + noise.
    returns = rng.normal(loc=params["drift"], scale=params["volatility"], size=n)
    prices = 100.0 * np.exp(np.cumsum(returns))

    # Momentum signal: sign of the trailing mean return.
    momentum = np.convolve(returns, np.ones(window) / window, mode="valid")
    position = np.sign(momentum)
    strat_returns = returns[window - 1:] * position
    strategy = np.cumsum(strat_returns)
    buy_hold = np.cumsum(returns[window - 1:])

    total = float(strategy[-1])
    bh = float(buy_hold[-1])
    sharpe = float(strategy.mean() / strategy.std()) if strategy.std() > 0 else 0.0

    # Two sanity checks on top of the statistical results.
    tests = [
        {
            "name": "sharpe_positive",
            "statistic": sharpe,
            "p_value": None,
            "conclusion": "pass" if sharpe > 0 else "fail",
        },
        {
            "name": "strategy_beats_buy_hold",
            "statistic": total - bh,
            "p_value": None,
            "conclusion": "pass" if total > bh else "fail",
        },
    ]

    return {
        "metrics": {
            "total_return": total,
            "buy_hold_return": bh,
            "sharpe": sharpe,
            "trades": int(np.count_nonzero(position)),
        },
        "tests": tests,
        "artifacts": {
            "equity_curve": strategy,
            "seed_summary": "seed=%d window=%d" % (ctx.seed, window),
        },
        "logs": ["momentum_scan completed for window=%d" % window],
    }
