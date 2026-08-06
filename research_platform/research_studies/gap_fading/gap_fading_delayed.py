"""Delayed-entry variant of the Gap Fading strategy (Campaign C002).

Robustness layer (spec §7.5): tests the C001 assumption of a
"tradeable open fill". The gap signal is identical to `gap_fading.py`
(same 36-cell grid, same thresholds/holds/directions), but the fill
happens at the **close** of the gap day instead of the open:

    - Entry: day t qualifies by the overnight gap (|gap| >= threshold,
      direction filter as in the primary rule).
    - Fill: at close[t] (no open fill — the gap-day open is NOT traded).
    - Exit: at close[t + hold_days] (hold = 1 is an overnight
      close-to-close hold; trade duration = hold days after entry).
    - Fade position: up gap -> short, down gap -> long (sign flip of
      C001, identical to the primary C002 rule).

Trade return (long): close[exit]/close[entry] - 1; short is the
inverse; `cost_bps` subtracted once per trade. The daily P&L series is
flat on the entry day (entered at the close) and carries the signed
close-to-close legs for days t+1..t+hold.

The delayed layer is a SEPARATE 36-cell search: it is reported with its
own DSR/White's Reality Check as a robustness fact, never as a verdict
input (spec §10). The permutation nullity gate uses the same
construction-matched signed fade pool as the primary rule.

All statistics via quant_research, seeded with ctx.seed (same battery
as gap_fading.py).
"""

import numpy as np

from _common import (  # noqa: E402  (bootstraps the quant_research import path)
    qr,
    ann_sharpe,
    daily_close_returns,
    entry_year,
    json_safe,
    load_ohlc,
    max_drawdown,
    total_return,
)

DIRECTIONS = {"up": 0, "down": 1, "both": 2}
N_PERM = 3000
N_BOOT = 1000


def _select_entries(gap: np.ndarray, threshold: float, direction: str) -> np.ndarray:
    if direction == "up":
        return gap >= threshold
    if direction == "down":
        return gap <= -threshold
    return np.abs(gap) >= threshold


def _build_trades(ohlc, gap, hold: int, threshold: float, direction: str,
                  cost_bps: float):
    """Non-overlapping delayed-entry fade trades.

    Entry day t is filled at close[t]; exit at close[t+hold]. Returns
    (trade_rets, pnl_daily, entries).
    """
    n = ohlc.shape[0]
    close = ohlc[:, 3]
    entries = _select_entries(gap, threshold, direction)
    trade_rets = []
    entry_days = []
    pnl = np.zeros(n)
    i = 1
    while i < n:
        if entries[i]:
            exit_day = min(i + hold, n - 1)
            # Fade: down gap -> long, up gap -> short (inverse of C001).
            is_long = gap[i] < 0
            gross = close[exit_day] / close[i] - 1.0
            if not is_long:
                gross = -gross
            cost = cost_bps / 1e4
            trade_rets.append(gross - cost)
            entry_days.append(i)
            for k in range(i + 1, exit_day + 1):
                leg = close[k] / close[k - 1] - 1.0
                pnl[k] = leg if is_long else -leg
            i = exit_day + 1
        else:
            i += 1
    return np.asarray(trade_rets, dtype=np.float64), pnl, np.asarray(entry_days, dtype=int)


def _pool_returns(ohlc, hold: int) -> np.ndarray:
    """All possible delayed-entry fade returns (length n - hold).

    pool[t] = close[t+hold]/close[t] - 1 — a trade entered at the close
    of day t (entry day d uses pool index d).
    """
    n = ohlc.shape[0]
    close = ohlc[:, 3]
    return close[hold:] / close[:n - hold] - 1.0


def run(ctx):
    ohlc, epoch_days = load_ohlc(ctx)
    params = ctx.params
    threshold = float(params["threshold_pct"]) / 100.0
    hold = int(params["hold_days"])
    direction = str(params["direction"])
    cost_bps = float(params.get("cost_bps", 0.0))
    seed = ctx.seed

    close = ohlc[:, 3]
    gap = np.full(ohlc.shape[0], np.nan)
    gap[1:] = ohlc[1:, 0] / close[:-1] - 1.0

    trade_rets, pnl_daily, entry_days = _build_trades(
        ohlc, gap, hold, threshold, direction, cost_bps
    )
    pool = _pool_returns(ohlc, hold)
    # Construction-matched signed fade pool (delayed convention): entry
    # day d uses pool index d; index 0 is NaN (no prior close) and is
    # dropped by the permutation test's NaN policy.
    signed_pool = -pool * np.sign(gap[:pool.size])
    n_trades = int(trade_rets.size)
    log = ctx.log

    metrics = {
        "threshold_pct": float(params["threshold_pct"]),
        "hold_days": float(hold),
        "direction": float(DIRECTIONS[direction]),
        "cost_bps": float(cost_bps),
        "entry": float(1.0),  # 0=open fill (primary), 1=close fill (delayed)
        "n_trades": float(n_trades),
        "total_return": total_return(pnl_daily),
        "ann_sharpe": ann_sharpe(pnl_daily),
        "max_drawdown": max_drawdown(pnl_daily),
    }

    tests = [{
        "name": "gap_description",
        "statistic": float(np.nanmean(np.abs(gap[1:]))),
        "p_value": None,
        "conclusion": "mean |overnight gap| = %.3f%%" % (100 * float(np.nanmean(np.abs(gap[1:])))),
    }]

    if n_trades < 3:
        log("insufficient trades (%d) for this cell; statistical tests skipped"
            % n_trades)
        metrics["win_rate"] = 0.0
        metrics["mean_trade_return"] = 0.0
        metrics["p_perm_signal"] = 0.0
        metrics["boot_lo"] = 0.0
        metrics["boot_hi"] = 0.0
        metrics["p_win_gt_50"] = 0.0
        metrics["spr_decision"] = 0.0
        tests.append({"name": "insufficient_trades", "statistic": float(n_trades),
                      "p_value": None,
                      "conclusion": "n_trades < 3; cell excluded from stats"})
    else:
        wins = int(np.sum(trade_rets > 0.0))
        win_rate = wins / n_trades
        metrics["win_rate"] = float(win_rate)
        metrics["mean_trade_return"] = float(np.mean(trade_rets))
        metrics["median_trade_return"] = float(np.median(trade_rets))
        metrics["trade_ret_std"] = float(np.std(trade_rets, ddof=1))

        signals = np.zeros(signed_pool.size, dtype=float)
        for d in entry_days:
            if 0 <= d < signed_pool.size:
                signals[d] = 1.0
        if float(np.sum(signals)) < 1:
            raise RuntimeError("no valid signals for permutation test")
        p_perm = qr.resampling.permutation_test_signal(
            signed_pool, signals, n_permutations=N_PERM, seed=seed
        )
        metrics["p_perm_signal"] = float(p_perm)
        t_welch, df_welch, p_welch = qr.statistics.two_sample_t_test(
            trade_rets, signed_pool)
        metrics["t_welch"] = float(t_welch)
        metrics["p_welch"] = float(p_welch)
        tests.append({
            "name": "permutation_signal_no_edge",
            "statistic": float(p_perm),
            "p_value": float(p_perm),
            "conclusion": "reject null at 5%%" if p_perm < 0.05 else "fail to reject null",
        })
        tests.append({
            "name": "welch_t_vs_all_possible_trades",
            "statistic": float(t_welch),
            "p_value": float(p_welch),
            "conclusion": "significant at 5%%" if p_welch < 0.05 else "not significant at 5%%",
        })

        est, lo, hi = qr.resampling.bootstrap_confidence_interval(
            trade_rets, block_size=1, n_bootstrap=N_BOOT,
            confidence=0.95, seed=seed,
        )
        metrics["boot_est"] = float(est)
        metrics["boot_lo"] = float(lo)
        metrics["boot_hi"] = float(hi)
        tests.append({
            "name": "bootstrap_mean_trade_return",
            "statistic": float(est),
            "p_value": None,
            "conclusion": "95%% CI [%.5f, %.5f]" % (lo, hi),
        })

        p_win_gt_50 = qr.probability.probability_edge_above(wins, n_trades - wins, 0.5)
        a_post, b_post = qr.probability.beta_posterior(1.0, 1.0, wins, n_trades - wins)
        metrics["p_win_gt_50"] = float(p_win_gt_50)
        metrics["beta_a"] = float(a_post)
        metrics["beta_b"] = float(b_post)
        tests.append({
            "name": "bayesian_win_rate",
            "statistic": float(win_rate),
            "p_value": None,
            "conclusion": ("P(win rate > 50%%) = %.3f (Beta(a=%.1f, b=%.1f))"
                           % (p_win_gt_50, a_post, b_post)),
        })

        outcomes = (trade_rets > 0.0).astype(float)
        spr = qr.probability.sprt_bernoulli(outcomes, p0=0.5, p1=0.55,
                                            alpha=0.05, beta=0.05)
        decision = spr["decision"]
        decision_code = {"accept_edge": 1.0, "reject_edge": 2.0, "continue": 0.0}[decision]
        metrics["spr_decision"] = decision_code
        tests.append({
            "name": "sprt_win_rate",
            "statistic": float(spr["n"]),
            "p_value": None,
            "conclusion": "decision=%s, n=%d" % (decision, int(spr["n"])),
        })

        year_map: dict = {}
        for d, r in zip(entry_days, trade_rets):
            y = entry_year(epoch_days, int(d))
            year_map.setdefault(y, []).append(r)
        for y in sorted(year_map):
            vals = year_map[y]
            metrics["yr_%d_n" % y] = float(len(vals))
            metrics["yr_%d_mean" % y] = float(np.mean(vals))
            metrics["yr_%d_win" % y] = float(np.mean(np.asarray(vals) > 0.0))
        tests.append({
            "name": "per_year_trades",
            "statistic": float(len(year_map)),
            "p_value": None,
            "conclusion": "; ".join(
                "%d:n=%d,mean=%.4f" % (y, len(v), np.mean(v))
                for y, v in sorted(year_map.items())
            ),
        })

        rets = daily_close_returns(close)
        vol = qr.core.ewma_volatility(rets, span=32, periods=252)
        valid_vol = vol[np.isfinite(vol)]
        if valid_vol.size >= 9:
            q1, q2 = np.percentile(valid_vol, [33.3, 66.7])
            regime = {}
            for d, r in zip(entry_days, trade_rets):
                v = vol[int(d)]
                if not np.isfinite(v):
                    continue
                key = "low" if v <= q1 else ("mid" if v <= q2 else "high")
                regime.setdefault(key, []).append(r)
            for key in ("low", "mid", "high"):
                vals = regime.get(key, [])
                metrics["vol_%s_n" % key] = float(len(vals))
                metrics["vol_%s_mean" % key] = float(np.mean(vals)) if vals else 0.0
            tests.append({
                "name": "volatility_regime_trades",
                "statistic": float(len(regime)),
                "p_value": None,
                "conclusion": "; ".join(
                    "%s:n=%d,mean=%.4f" % (k, len(v), (np.mean(v) if v else 0.0))
                    for k, v in sorted(regime.items())
                ),
            })

    return {
        "metrics": metrics,
        "tests": tests,
        "artifacts": {
            "daily_returns": pnl_daily,
            "trade_returns": trade_rets,
            "gap_series": gap,
        },
        "logs": [
            "delayed entry: gap threshold=%.2f%% hold=%d direction=%s cost=%.1fbps "
            "seed=%d -> %d trades"
            % (float(params["threshold_pct"]), hold, direction, cost_bps, seed, n_trades),
            json_safe(trade_rets[:20]),
        ],
    }
