"""Shared, numpy-only research features (features.md P0 batch).

Versioned with the repo; campaign modules import them (same pattern as
study `_common`). No third-party dependencies, no statistics beyond
descriptive component correlation (all inference lives in
`quant_research`).

F-GAP-COMP — gap/intraday decomposition (C002 closing-analysis
deliverable; NOT a strategy signal):
    overnight_t = open_t / close_{t-1} - 1        (index 0 = NaN; == F-GAP)
    intraday_t  = close_t / open_t - 1            (index 0 valid)
    cumulative drift of each component (cumulative sum)
    Pearson correlation overnight vs intraday (NaN pairs dropped)

Verification (2026-08-06): overnight_ret must reproduce C001's
gap_series exactly (gap_strategy.py artifacts) — checked at validation.
"""

import numpy as np

__all__ = ["overnight_gap", "gap_decomposition"]


def overnight_gap(ohlc: np.ndarray) -> np.ndarray:
    """F-GAP: overnight gap series g_t = open_t/close_{t-1} - 1.

    Index 0 is NaN (no prior close). Causal (uses t and t-1 only).
    """
    gap = np.full(ohlc.shape[0], np.nan, dtype=np.float64)
    gap[1:] = ohlc[1:, 0] / ohlc[:-1, 3] - 1.0
    return gap


def gap_decomposition(ohlc: np.ndarray) -> dict:
    """F-GAP-COMP: decompose each day into overnight and intraday legs.

    Returns aligned series plus cumulative drift components and the
    Pearson correlation between the two legs (descriptive only).
    """
    overnight = overnight_gap(ohlc)
    intraday = ohlc[:, 3] / ohlc[:, 0] - 1.0
    cum_overnight = np.cumsum(np.nan_to_num(overnight))
    cum_intraday = np.cumsum(np.nan_to_num(intraday))
    mask = np.isfinite(overnight) & np.isfinite(intraday)
    if np.count_nonzero(mask) >= 2 and float(np.std(overnight[mask])) > 0.0:
        corr = float(np.corrcoef(overnight[mask], intraday[mask])[0, 1])
    else:
        corr = 0.0
    return {
        "overnight_ret": overnight,
        "intraday_ret": intraday,
        "cum_overnight": cum_overnight,
        "cum_intraday": cum_intraday,
        "corr_overnight_intraday": corr,
    }
