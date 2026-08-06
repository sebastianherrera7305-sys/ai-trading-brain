"""Benchmark: simple moving-average crossover.

Position is long when SMA(fast) > SMA(slow), flat otherwise (no
shorting). Signals are applied with a one-day lag (signal computed on
day t-1 drives day t's position), so there is no lookahead. Daily P&L =
position * close-to-close return. Both SMAs are computed with
quant_research.core.rolling_mean.
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

    fast_ma = qr.core.rolling_mean(close, fast)
    slow_ma = qr.core.rolling_mean(close, slow)
    signal = np.where(fast_ma > slow_ma, 1.0, 0.0)
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
            "name": "sma_crossover_definition",
            "statistic": exposure,
            "p_value": None,
            "conclusion": "long when SMA(%d) > SMA(%d), 1-day signal lag" % (fast, slow),
        }],
        "artifacts": {"daily_returns": pnl},
        "logs": ["SMA(%d,%d) crossover, exposure=%.3f" % (fast, slow, exposure)],
    }
