# Feature Registry

Every feature is an independently documented research object. IDs match
`features.md` (the roadmap); this file documents the **implemented** subset as
verified in Campaign 001, plus the planned P0 items. All math lives in
`quant_research` (qr-0.3.0, frozen) or in the shared study helpers (`_common.py`).

Validation status: `verified` = exercised and reproduced in C001;
`library-tested` = frozen-library doctest/unit tested, not yet campaign-used;
`planned` = roadmap item, not yet implemented.

---

## Implemented features

### F-RET — returns family — `verified`
- **Definition:** simple return r_t = x_t/x_{t−1} − 1; log return ln(x_t/x_{t−1});
  cumulative wealth W_T = Π(1+r_t); drawdown path D_t = min(W_t − 1, D_{t−1}).
- **Inputs:** price series → aligned output, index 0 = NaN (simple/log).
- **Lag:** causal, no lag. **Look-ahead safety:** none.
- **Complexity:** O(n) time, O(n) memory.
- **Failure modes:** NaN handling — consumers must use finite-only stats;
  dividing by zero for zero/negative prices.

### F-MA — rolling mean — `verified`
- **Definition:** m_t = mean(x_{t−w+1}..x_t); first w−1 positions NaN.
- **Inputs:** series + window w → series. **Lag:** causal, trailing window.
- **Look-ahead safety:** none. **Complexity:** O(n·w), O(n+w) memory.
- **Failure modes:** NaN inside window propagates; small-window noise.

### F-EMA — exponential moving average — `verified`
- **Definition:** e_t = α·x_t + (1−α)·e_{t−1}, α = 2/(span+1), warm-up = span.
- **Inputs:** series + span (float > 0). **Lag:** causal.
- **Look-ahead safety:** none. **Complexity:** O(n).
- **Failure modes:** span ≤ 0 raises; warm-up period depends on span.

### F-RVOL — EWMA volatility — `verified`
- **Definition:** σ_t from EWMA of squared returns with `span`, annualized by
  `periods` (C001 used span=32, periods=252).
- **Inputs:** return series + span + periods → volatility series.
- **Lag:** causal; NaN during warm-up.
- **Look-ahead safety:** none. **Complexity:** O(n).
- **Failure modes:** regime labels derived from in-sample percentiles
  (F-REGIME) leak if used as a *filter* — future campaigns must use trailing
  quantiles.

### F-ZSCORE — rolling z-score — `library-tested`
- **Definition:** z_t = (x_t − mean_w)/std_w(ddof). 
- **Inputs:** series + window (+ ddof) → series. **Lag:** causal.
- **Look-ahead safety:** none. **Complexity:** O(n·w).
- **Failure modes:** constant windows → zero std; ddof choice.

### F-CORR — rolling correlation — `library-tested`
- **Definition:** Pearson correlation over trailing window of two series.
- **Inputs:** two series + window → series. **Lag:** causal.
- **Failure modes:** minimum-overlap/constant-input handling — verify per call
  before campaign use.

### F-SMOOTH — centered smooth — `library-tested`
- **Definition:** centered moving average (value at t uses neighbors on both
  sides).
- **Lag:** **NON-CAUSAL** — value at t uses x_{t±k}.
- **Look-ahead safety:** **VIOLATES causality** — usable only for display or
  with an explicit shift when the decision uses a lagged copy.
- **Failure modes:** must never enter a signal without lagging by the
  half-window.

### F-GAP — overnight gap — `verified`
- **Definition:** g_t = open_t/close_{t−1} − 1; index 0 NaN.
- **Inputs:** OHLC → series (C001: gap built inside gap_strategy).
- **Lag:** causal (uses t and t−1 only).
- **Complexity:** O(n).
- **Failure modes:** roll-day price jumps masquerade as gaps (DS-001 caveat).

### F-GAP-COMP — gap/intraday decomposition — `planned (P0, C002)`
- **Definition:** overnight component o_t = open_t/close_{t−1} − 1; intraday
  i_t = close_t/open_t − 1; plus cumulative series of each.
- **Inputs:** OHLC. **Lag:** causal.
- **Unlocks:** H-TOD-01, H-MS-01 (C002).

### F-SHARPE / F-DD / F-CR / F-YEAR — `_common` helpers — `verified`
- ann_sharpe: mean/std × √252 of finite daily P&L; max_drawdown via
  cumulative_returns+drawdown_prices; total_return = Π(1+r)−1; entry_year:
  epoch-day → calendar year.
- **Failure modes:** ann_sharpe returns 0.0 when std = 0 or n < 2 (silent);
  total_return is path-dependent on non-overlapping vs overlapping legs.

### F-POOL — construction-matched signed pool — `verified`
- **Definition:** pool of ALL possible hold-day open→close returns under the
  strategy's own construction (signed by gap direction), pool[t] = trade
  entered day t+1.
- **Purpose:** nullity gate + Welch reference for directional rules.
- **Failure modes:** must be signed for directional strategies (unsigned pool
  tests "special days", not the rule — C001 bug history, see negative
  knowledge NK-0002).

### F-REGIME — EWMA-vol tercile regime — `verified`
- **Definition:** labels {low, mid, high} from percentiles of F-RVOL.
- **C001 usage:** per-regime trade breakdowns.
- **Failure modes:** in-sample percentiles — see F-RVOL.

### F-TRIAL — trial-matrix assembly — `verified`
- **Definition:** (n_trials × n_days) daily-P&L matrix from registry artifacts,
  with parallel param arrays (threshold/hold/direction).
- **Purpose:** input to DSR / White's Reality Check.
- **Failure modes:** row order must match param arrays; seed-0 rows only for
  deterministic strategies.

## Planned P0 batch (implement with C002 — details in features.md §2)

| ID | Feature | Status | Unlocks |
|---|---|---|---|
| F-CAL | weekday/month/turn-of-month | planned | H-SESS-01/02 |
| F-DON | rolling extremes (Donchian) | planned | H-TF-01, H-LIQ-01 |
| F-MOM | multi-day momentum | planned | H-TF-02, H-IMK-01 |
| F-RANGE / F-ATR / F-POSITION | range, ATR, close position | planned | H-MS-02, H-AMT-01 |
| F-STREAK | streak counter | planned | H-MR-02 |
| F-SWEEP | failed-break proxy | planned | H-LIQ-01 |
| F-FVG | fair-value-gap detection | planned | H-FVG-01 |
| F-ALIGN / F-IMK-LAG | multi-market alignment + lags | planned | H-IMK-01/02 |

## Counts

- Implemented and `verified` in campaigns: **10** (F-RET, F-MA, F-EMA, F-RVOL,
  F-GAP, F-SHARPE, F-DD, F-CR, F-YEAR, F-POOL, F-REGIME, F-TRIAL → 12).
- `library-tested`, not yet campaign-used: 3 (F-ZSCORE, F-CORR, F-SMOOTH).
- `planned` (P0): 11.

## Registry rules

1. A campaign may use a feature only if it is `verified` or `library-tested`
  (planned features require implementation + validation inside the campaign).
2. Any deviation from a documented definition is a new feature version
  (ID + suffix), never a silent change.
3. New features are added to both `features.md` (roadmap) and this registry
  (definition) at implementation time.
