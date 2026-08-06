"""Regression tests for the C002 meta-validation consumer (R2 fix).

The trial matrix stores c001_best_series as a flat 1-D series while
every other series is 2-D (n_rows, n_days).  _clean() assumes a 2-D
matrix; feeding it the 1-D c001 series turned the finite-column mask
into a scalar and numpy inserted a unit axis, yielding (n_days, 1)
and making quant_research's two_sample_t_test reject its 'b' input.
The fix reshapes the 1-D series to (1, n_days) before cleaning — the
same canonical shape the assembly writes for buyhold_series.
"""

import importlib.util
import pathlib
import sys
from types import SimpleNamespace

import numpy as np

_STUDIES = pathlib.Path(__file__).resolve().parents[1] / "research_studies"
sys.path.insert(0, str(_STUDIES))

_spec = importlib.util.spec_from_file_location(
    "c002_meta",
    _STUDIES / "gap_fading" / "gap_fading_meta.py",
)
meta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(meta)


def _matrix(rows, n_days, rng, nan_first_col=True):
    m = rng.normal(0.0, 1.0, size=(rows, n_days))
    if nan_first_col:
        m[:, 0] = np.nan
    return m


def _flat(n_days, rng, nan_first=True):
    v = rng.normal(0.0, 1.0, size=n_days)
    if nan_first:
        v[0] = np.nan
    return v


def _ctx(n_trials=4, n_days=30, seed=7):
    rng = np.random.default_rng(seed)
    data = {
        "strategy_trials": _matrix(n_trials, n_days, rng),
        "trial_threshold": np.asarray([0.3, 0.5, 0.7, 1.0][:n_trials], dtype=np.float64),
        "trial_hold": np.asarray([1, 2, 1, 2][:n_trials], dtype=np.float64),
        "trial_direction": np.asarray(
            [b"up", b"down", b"both", b"up"][:n_trials], dtype=np.bytes_
        ),
        "random_series": _matrix(3, n_days, rng),
        "buyhold_series": _matrix(1, n_days, rng),
        "sma_series": _matrix(3, n_days, rng),
        "ema_series": _matrix(3, n_days, rng),
        "c001_best_series": _flat(n_days, rng, nan_first=True),
        "overnight_ret": _flat(n_days, rng, nan_first=True),
        "intraday_ret": _flat(n_days, rng, nan_first=False),
        "cum_overnight": _flat(n_days, rng, nan_first=False),
        "cum_intraday": _flat(n_days, rng, nan_first=False),
    }
    return SimpleNamespace(dataset={"data": data}, seed=seed)


def test_meta_run_consumes_flat_c001_best_series():
    out = meta.run(_ctx())
    metrics = out["metrics"]
    assert "p_vs_c001_best" in metrics
    assert np.isfinite(metrics["p_vs_c001_best"])
    assert "dsr_p" in metrics and "rc_p" in metrics
    assert np.isfinite(metrics["dsr_p"]) and np.isfinite(metrics["rc_p"])


def test_meta_run_c001_series_without_nan():
    ctx = _ctx()
    ctx.dataset["data"]["c001_best_series"] = ctx.dataset["data"][
        "c001_best_series"
    ].copy()
    ctx.dataset["data"]["c001_best_series"][0] = 0.5
    out = meta.run(ctx)
    assert "p_vs_c001_best" in out["metrics"]


def test_meta_run_two_dimensional_like_real_assembly():
    ctx = _ctx()
    ctx.dataset["data"]["c001_best_series"] = ctx.dataset["data"][
        "c001_best_series"
    ].reshape(1, -1)
    out = meta.run(ctx)
    assert "p_vs_c001_best" in out["metrics"]
