"""Benchmark: exponential moving-average crossover.

Identical construction to the SMA crossover benchmark but with
quant_research.core.ewma (span-based) instead of a simple mean.
Long when EMA(fast) > EMA(slow), flat otherwise, one-day signal lag.
"""

import numpy as np

from _common import (  # noqa: E402  (bootstraps the quant_research import path)
    qr,
    ann_sharpe,
    daily_close_returns,
    load_ohlc,
    max_drawdown,
    total_return,
)


def run(ctx):
    ohlc, _ = load_ohlc(ctx)
    fast = int(ctx.params["fast"])
    slow = int(ctx.params["slow"])
    close = ohlc[:, 3]
    rets = daily_close_returns(close)

    fast_ema = qr.core.ewma(close, float(fast))
    slow_ema = qr.core.ewma(close, float(slow))
    signal = np.where(fast_ema > slow_ema, 1.0, 0.0)
    signal = np.concatenate([[0.0], signal[:-1]])  # one-day lag: no lookahead

    pnl = np.full(rets.size, np.nan)
    pnl[1:] = signal[1:] * rets[1:]
    exposure = float(np.nanmean(signal[1:]))
    return {
        "metrics": {
            "fast": float(fast),
            "slow": float(slow),
            "total_return": total_return(pnl),
            "ann_sharpe": ann_sharpe(pnl),
            "max_drawdown": max_drawdown(pnl),
            "exposure": exposure,
        },
        "tests": [{
            "name": "ema_crossover_definition",
            "statistic": exposure,
            "p_value": None,
            "conclusion": "long when EMA(%d) > EMA(%d), 1-day signal lag" % (fast, slow),
        }],
        "artifacts": {"daily_returns": pnl},
        "logs": ["EMA(%d,%d) crossover, exposure=%.3f" % (fast, slow, exposure)],
    }
