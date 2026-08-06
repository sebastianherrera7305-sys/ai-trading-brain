"""Benchmark: Buy & Hold the index (no signals).

Daily P&L = close-to-close return of every day; a unit of capital is
always fully invested. No parameters, no randomness.
"""

import numpy as np

from _common import ann_sharpe, daily_close_returns, load_ohlc, max_drawdown, total_return


def run(ctx):
    ohlc, _ = load_ohlc(ctx)
    rets = daily_close_returns(ohlc[:, 3])
    return {
        "metrics": {
            "n_days": float(ohlc.shape[0]),
            "total_return": total_return(rets),
            "ann_sharpe": ann_sharpe(rets),
            "max_drawdown": max_drawdown(rets),
            "mean_daily_return": float(np.nanmean(rets)),
            "volatility": float(np.nanstd(rets, ddof=1) * np.sqrt(252.0)),
        },
        "tests": [{
            "name": "buy_hold_definition",
            "statistic": float(ohlc.shape[0]),
            "p_value": None,
            "conclusion": "fully invested close-to-close; no costs",
        }],
        "artifacts": {"daily_returns": rets},
        "logs": ["buy & hold benchmark on %d days" % ohlc.shape[0]],
    }
