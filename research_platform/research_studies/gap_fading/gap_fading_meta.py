"""Meta-validation experiment for the Gap Fading study (Campaign C002).

Consumes the assembled fade trial matrix (registered as a dataset by the
study's assembly script) and applies the data-snooping-adjusted tests
from quant_research — the canonical math engine:

    - deflated_sharpe_ratio: Bailey & Lopez de Prado (2014). Is the
      best fade trial Sharpe still significantly positive once the
      number of searched trials is accounted for? Per-observation
      (daily) Sharpes, n_obs = number of finite days.
    - reality_check_p_value: White (2000). Block-bootstrap p-value for
      "even the best of these fade trials has no edge", computed on the
      (n_trials, n_obs) matrix of daily strategy P&L.
    - two_sample_t_test (Welch): best-trial daily P&L vs each benchmark
      (random entries pool, buy & hold, best SMA crossover, best EMA
      crossover) and vs the C001 best cell (paired C001-vs-C002
      comparison, spec §9.8).
    - pearson_correlation: overnight vs intraday leg of the gap
      decomposition (F-GAP-COMP — descriptive context only).

The trial matrix itself is assembled from registry artifacts by the
study's assembly script (data engineering, no statistics).
"""

import numpy as np

from _common import qr  # noqa: E402  (bootstraps the quant_research import path)

N_BOOT = 1500


def _clean(matrix: np.ndarray) -> np.ndarray:
    """Drop any column that is non-finite in any row."""
    mask = np.isfinite(matrix).all(axis=0)
    return matrix[:, mask]


def run(ctx):
    data = ctx.dataset["data"]
    trials = np.asarray(data["strategy_trials"], dtype=np.float64)
    thresholds = np.asarray(data["trial_threshold"], dtype=np.float64)
    holds = np.asarray(data["trial_hold"], dtype=np.float64)
    directions = np.asarray(data["trial_direction"], dtype=np.bytes_).astype("U")
    random_series = np.asarray(data["random_series"], dtype=np.float64)
    buyhold = np.asarray(data["buyhold_series"], dtype=np.float64)
    sma_series = np.asarray(data["sma_series"], dtype=np.float64)
    ema_series = np.asarray(data["ema_series"], dtype=np.float64)
    c001_best = np.asarray(data["c001_best_series"], dtype=np.float64)
    seed = ctx.seed

    trials = _clean(trials)
    n_trials, n_obs = trials.shape
    assert n_trials >= 2 and n_obs >= 10

    trial_means = trials.mean(axis=1)
    trial_sharpes = trials.mean(axis=1) / (trials.std(axis=1, ddof=1) + 1e-12)
    best_idx = int(np.argmax(trial_means))
    best_series = trials[best_idx]
    best_sharpe = float(trial_sharpes[best_idx])
    best_mean = float(trial_means[best_idx])

    skew = qr.statistics.skewness(best_series)
    kurt = qr.statistics.excess_kurtosis(best_series)
    dsr = qr.resampling.deflated_sharpe_ratio(
        best_sharpe, trial_sharpes, n_obs, skewness=skew, kurtosis=kurt
    )
    rc_p = qr.resampling.reality_check_p_value(
        trials, block_size=21, n_bootstrap=N_BOOT, seed=seed
    )

    metrics = {
        "n_trials": float(n_trials),
        "n_days": float(n_obs),
        "best_trial_idx": float(best_idx),
        "best_trial_threshold_pct": float(thresholds[best_idx]),
        "best_trial_hold": float(holds[best_idx]),
        "best_trial_direction": float({"up": 0, "down": 1, "both": 2}[directions[best_idx]]),
        "best_trial_mean_daily": best_mean,
        "best_trial_sharpe": best_sharpe,
        "dsr_p": float(dsr),
        "rc_p": float(rc_p),
        "best_skew": float(skew),
        "best_kurt": float(kurt),
    }

    tests = [{
        "name": "best_trial_identity",
        "statistic": float(best_idx),
        "p_value": None,
        "conclusion": ("threshold=%.2f%% hold=%d direction=%s"
                       % (thresholds[best_idx], int(holds[best_idx]),
                          directions[best_idx])),
    }, {
        "name": "deflated_sharpe_ratio",
        "statistic": best_sharpe,
        "p_value": float(dsr),
        "conclusion": ("P(DSR > 0) = %.4f (%d trials, %d obs, skew=%.3f, kurt=%.3f); "
                       % (dsr, n_trials, n_obs, skew, kurt)
                       + ("significant at 5%" if dsr < 0.05 else "not significant at 5%")),
    }, {
        "name": "whites_reality_check",
        "statistic": float(rc_p),
        "p_value": float(rc_p),
        "conclusion": ("p = %.4f; " % rc_p
                       + ("null of no-edge rejected at 5%" if rc_p < 0.05
                          else "null of no-edge NOT rejected at 5%")),
    }]

    # ---- Benchmark comparisons (Welch t on daily P&L) ----
    rnd = _clean(random_series)
    bh = _clean(buyhold)
    sma = _clean(sma_series)
    ema = _clean(ema_series)
    c1 = _clean(c001_best.reshape(1, -1))[0]

    random_pool = rnd.reshape(-1)
    bh_row = bh[0]
    sma_best_idx = int(np.argmax(sma.mean(axis=1)))
    ema_best_idx = int(np.argmax(ema.mean(axis=1)))

    def compare(name, other, other_label):
        t, df, p = qr.statistics.two_sample_t_test(best_series, other)
        metrics["t_vs_%s" % name] = float(t)
        metrics["p_vs_%s" % name] = float(p)
        tests.append({
            "name": "welch_vs_%s" % name,
            "statistic": float(t),
            "p_value": float(p),
            "conclusion": ("best fade trial mean %.5f vs %s mean %.5f: p=%.4f "
                           % (best_mean, other_label, float(np.mean(other)), p)
                           + ("significant at 5%" if p < 0.05 else "not significant at 5%")),
        })

    compare("random", random_pool, "random-entries pool")
    compare("buyhold", bh_row, "buy & hold")
    compare("sma", sma[sma_best_idx], "best SMA crossover")
    compare("ema", ema[ema_best_idx], "best EMA crossover")

    # ---- Paired C001-vs-C002 best-cell comparison (spec §9.8) ----
    c001_sharpe = float(
        c1.mean() / (c1.std(ddof=1) + 1e-12)
    ) if c1.size > 1 else 0.0
    metrics["c001_best_sharpe"] = c001_sharpe
    metrics["c001_best_beat"] = float(1.0) if best_sharpe > c001_sharpe else float(0.0)
    t_c, df_c, p_c = qr.statistics.two_sample_t_test(best_series, c1)
    metrics["t_vs_c001_best"] = float(t_c)
    metrics["p_vs_c001_best"] = float(p_c)
    tests.append({
        "name": "paired_c001_vs_c002_best_cell",
        "statistic": float(t_c),
        "p_value": float(p_c),
        "conclusion": ("C002 best Sharpe %.3f vs C001 best %.3f: Welch p=%.4f "
                       % (best_sharpe, c001_sharpe, p_c)
                       + ("; C002 beats C001" if best_sharpe > c001_sharpe
                          else "; C002 <= C001")),
    })

    metrics["random_pool_mean"] = float(random_pool.mean())
    metrics["buyhold_mean"] = float(bh_row.mean())
    metrics["best_sma_mean"] = float(sma[sma_best_idx].mean())
    metrics["best_ema_mean"] = float(ema[ema_best_idx].mean())
    metrics["random_pool_sharpe"] = float(
        random_pool.mean() / (random_pool.std(ddof=1) + 1e-12))
    metrics["buyhold_sharpe"] = float(bh_row.mean() / (bh_row.std(ddof=1) + 1e-12))

    # ---- F-GAP-COMP decomposition (descriptive; closing-analysis
    # deliverable, NOT a strategy signal) ----
    overnight = np.asarray(data["overnight_ret"], dtype=np.float64)
    intraday = np.asarray(data["intraday_ret"], dtype=np.float64)
    cum_on = np.asarray(data["cum_overnight"], dtype=np.float64)
    cum_id = np.asarray(data["cum_intraday"], dtype=np.float64)
    mean_on = float(np.nanmean(overnight[1:]))
    mean_id = float(np.nanmean(intraday))
    corr = qr.statistics.pearson_correlation(overnight, intraday)
    total_drift = float(cum_on[-1] + cum_id[-1])
    on_share = float(cum_on[-1] / total_drift) if total_drift != 0.0 else 0.0
    metrics.update({
        "mean_overnight_ret": mean_on,
        "mean_intraday_ret": mean_id,
        "corr_overnight_intraday": float(corr),
        "cum_overnight_drift": float(cum_on[-1]),
        "cum_intraday_drift": float(cum_id[-1]),
        "total_drift": total_drift,
        "overnight_drift_share": on_share,
    })
    tests.append({
        "name": "gap_decomposition",
        "statistic": float(corr),
        "p_value": None,
        "conclusion": ("overnight mean %.5f vs intraday mean %.5f; corr=%.3f; "
                       "cum drift on %.4f / id %.4f (overnight share %.2f%%)"
                       % (mean_on, mean_id, corr, cum_on[-1], cum_id[-1],
                          100 * on_share)),
    })

    return {
        "metrics": metrics,
        "tests": tests,
        "artifacts": {
            "best_trial_series": best_series,
            "trial_means": trial_means,
        },
        "logs": [
            "meta-validation: %d trials x %d obs; best=#%d (thr=%.2f%%, hold=%d, %s)"
            % (n_trials, n_obs, best_idx, thresholds[best_idx], int(holds[best_idx]),
               directions[best_idx]),
            "DSR p=%.4f, Reality Check p=%.4f (seed=%d)" % (dsr, rc_p, seed),
        ],
    }
