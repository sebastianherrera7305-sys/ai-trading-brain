"""Benchmark: random entries (same holding convention as the strategy).

Entry days are drawn uniformly at random (seeded per run via ctx.seed),
trades are non-overlapping, holding is `hold_days` open->close. This is
the null-entry benchmark: it isolates the value of *which* days the
strategy selects versus *how* trades are constructed.

Randomness is part of this experiment by design; each seed is a fresh
sample of the same null process, which is exactly what the platform's
seed/repeat mechanism is for.
"""

import numpy as np

from _common import ann_sharpe, load_ohlc, max_drawdown, total_return


def run(ctx):
    ohlc, _ = load_ohlc(ctx)
    hold = int(ctx.params["hold_days"])
    rng = ctx.rng
    n = ohlc.shape[0]
    open_ = ohlc[:, 0]
    close = ohlc[:, 3]

    trade_rets = []
    pnl = np.zeros(n)
    i = 1
    while i < n - hold:
        if rng.random() < ctx.params.get("entry_prob", 0.05):
            exit_day = min(i + hold - 1, n - 1)
            r = close[exit_day] / open_[i] - 1.0
            trade_rets.append(r)
            pnl[i] = close[i] / open_[i] - 1.0
            for k in range(i + 1, exit_day + 1):
                pnl[k] = close[k] / close[k - 1] - 1.0
            i = exit_day + 1
        else:
            i += 1
    trade_rets = np.asarray(trade_rets, dtype=np.float64)
    wins = int(np.sum(trade_rets > 0.0))
    return {
        "metrics": {
            "hold_days": float(hold),
            "n_trades": float(trade_rets.size),
            "win_rate": float(wins / trade_rets.size) if trade_rets.size else 0.0,
            "mean_trade_return": float(np.mean(trade_rets)) if trade_rets.size else 0.0,
            "total_return": total_return(pnl),
            "ann_sharpe": ann_sharpe(pnl),
            "max_drawdown": max_drawdown(pnl),
        },
        "tests": [{
            "name": "random_entries_definition",
            "statistic": float(trade_rets.size),
            "p_value": None,
            "conclusion": "uniform random entry days, hold=%d days, non-overlapping" % hold,
        }],
        "artifacts": {"daily_returns": pnl, "trade_returns": trade_rets},
        "logs": ["random entries: %d trades, seed=%d" % (trade_rets.size, ctx.seed)],
    }
