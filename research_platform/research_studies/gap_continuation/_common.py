"""Shared helpers for the Gap Continuation study experiments.

Study code only — not framework infrastructure. Provides:
  - repo-root bootstrap so `quant_research` (the canonical math engine)
    is importable regardless of how the framework CLI was launched;
  - OHLC payload accessors;
  - a shared metrics vocabulary so strategy/benchmark/meta experiments
    emit comparable, numeric metrics.
"""

import os
import sys
from pathlib import Path

import numpy as np

STUDY_DIR = Path(__file__).resolve().parent
REPO_ROOT = STUDY_DIR.parents[2]


def ensure_quant_research() -> None:
    """Make the repo root importable so `import quant_research` works."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


ensure_quant_research()

import quant_research as qr  # noqa: E402  (needs the path bootstrap above)


def load_ohlc(ctx) -> tuple:
    """(ohlc (n,4), epoch_days (n,)) from the registered dataset payload."""
    data = ctx.dataset["data"]
    ohlc = np.asarray(data["ohlc"], dtype=np.float64)
    dates = np.asarray(data["dates"], dtype=np.int64)
    return ohlc, dates


def daily_close_returns(close: np.ndarray) -> np.ndarray:
    """close-to-close simple returns; index 0 = NaN."""
    ret = np.full(close.shape[0], np.nan)
    ret[1:] = close[1:] / close[:-1] - 1.0
    return ret


def ann_sharpe(daily_pnl: np.ndarray) -> float:
    """Annualized Sharpe of a daily P&L series (252 periods/yr)."""
    finite = daily_pnl[np.isfinite(daily_pnl)]
    if finite.size < 2 or float(np.std(finite, ddof=1)) == 0.0:
        return 0.0
    return float(finite.mean() / np.std(finite, ddof=1) * np.sqrt(252.0))


def total_return(daily_pnl: np.ndarray) -> float:
    finite = daily_pnl[np.isfinite(daily_pnl)]
    if finite.size == 0:
        return 0.0
    return float(np.prod(1.0 + finite) - 1.0)


def max_drawdown(daily_pnl: np.ndarray) -> float:
    """Worst underwater point (negative) of the P&L path."""
    finite = daily_pnl[np.isfinite(daily_pnl)]
    if finite.size == 0:
        return 0.0
    equity = qr.core.cumulative_returns(finite, start_value=1.0)
    dd = qr.core.drawdown_prices(equity)
    return float(np.nanmin(dd))


def entry_year(epoch_days: np.ndarray, day_index: int) -> int:
    """Calendar year of a given day index (epoch-day based)."""
    dt = np.datetime64(int(epoch_days[day_index]), "D")
    return int(dt.astype("datetime64[Y]").astype("int") + 1970)


def json_safe(x: np.ndarray) -> list:
    return [float(v) for v in x]
