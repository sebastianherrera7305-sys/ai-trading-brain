# Feature Library — Inventory and Roadmap

Reusable research features, prioritized as building blocks (not
strategy-specific code). Features marked **available** are used directly from
`quant_research` (frozen v0.3.0) or from the shared study helper `_common.py`.
Features marked **to build** belong in a shared, numpy-only feature module
(location proposed: `research_platform/research_studies/features/`) so that
every campaign consumes the same code and can be reproduced from it.
Features marked **blocked** need data acquisition first.

Legend — priority: P0 = needed by the next campaigns (C002–C007), P1 = needed
shortly after, P2 = optional. Class A/B as in `catalog.md`.

## 1. Available today (quant_research.core + _common helpers)

| ID | Feature | Source | Unlocks |
|---|---|---|---|
| F-RET | simple/log returns, cumulative returns, drawdown | `core.simple_returns`, `log_returns`, `cumulative_returns`, `drawdown_prices` | all |
| F-MA | rolling mean / EWMA | `core.rolling_mean`, `core.ewma` | H-TF-01/02, H-MR-01 |
| F-ZSCORE | rolling z-score of close | `core.rolling_z_score`, `core.z_score` | H-MR-01 |
| F-RVOL | EWMA volatility / realized vol | `core.ewma_volatility`, `core.rolling_std` | H-VOL-01/02, H-IMK-02 |
| F-CORR | rolling correlation | `core.rolling_correlation` | H-IMK-02 |
| F-GAP | overnight gap series (open/prev close − 1) | study `_common`/C001 | H-MS-01, H-TOD-01, H-SESS-01 |
| F-TRADE | non-overlapping trade construction + exposure P&L | C001 pattern | all strategy campaigns |
| F-REGIME | EWMA-vol tercile/quantile regime labels | C001 pattern | H-VOL-01, filters |
| F-TEST | test battery (perm, Welch, bootstrap, Bayesian, SPRT, DSR, RC) | `quant_research` | all |

## 2. To build (P0 — unlocks C002–C007)

| ID | Feature | Definition | Inputs → Output | Unlocks | Effort |
|---|---|---|---|---|---|
| F-GAP-COMP | gap/intraday decomposition | per-day overnight return (close→open) and intraday return (open→close), plus cumulative series of each | OHLC → 2 aligned series | H-TOD-01, H-MS-01 | S |
| F-CAL | calendar features | weekday, month, turn-of-month flag, quarter | dates (epoch days) → int arrays | H-SESS-01/02 | S |
| F-DON | rolling extremes (Donchian) | rolling N-day max/min of close (and of high/low) | close/high/low → 2 arrays | H-TF-01, H-LIQ-01 | S |
| F-MOM | multi-day momentum | close_t / close_{t−k} − 1 for k-grid | close → matrix | H-TF-02, H-IMK-01 | S |
| F-RANGE | day range + range ratio | high−low; range / N-day average range (ATR-style) | OHLC → 2 arrays | H-MS-02, H-AMT-01 | S |
| F-ATR | average true range | N-day mean of true range | OHLC → series | H-AMT-01, H-OR-01 | S |
| F-POSITION | close position in day range | (close−low)/(high−low); N-day normalized variant | OHLC → series | H-MS-02 | S |
| F-STREAK | streak counter | consecutive same-direction closes (signed count) | close → int series | H-MR-02 | S |
| F-SWEEP | failed-break proxy | day high > prior N-day high but close below (and mirror) | OHLC + F-DON → event flags | H-LIQ-01 | S-M |
| F-FVG | fair value gap detection | gap between candle1.high and candle3.low (bullish/bearish), size, fill tracking | OHLC → events + fill stats | H-FVG-01 | M |
| F-ALIGN | multi-market alignment | align 4 markets on common trading dates, NaN for missing | 4 OHLC sets → aligned arrays + date mask | H-IMK-01/02 | S-M |
| F-IMK-LAG | lagged cross-market returns | prior-day (and k-day) returns of each other market, aligned | F-ALIGN + F-RET | H-IMK-01 | S |

## 3. To build (P1)

| ID | Feature | Definition | Unlocks | Effort |
|---|---|---|---|---|
| F-TREND-STRUCT | swing structure (fractal highs/lows, swing labels) | N-bar swing detection → direction labels | H-AMT-01, filters | M |
| F-SESSION | session phase labels | (needs intraday) first/mid/last hour, overnight | H-TOD-02 | S (once data) |
| F-PIVOT | prior session pivot levels | prior high/low/close projections | H-LIQ-02 | S (once data) |
| F-EXTVOL | VIX series intake | register VIX daily; level/change/term features | H-ALT-01, H-VOL | S-M (once data) |
| F-POS | CFTC positioning intake | net spec positioning, z-scored | H-ALT-02 | M (once data) |

## 4. Blocked on data (P1/P2 — acquisition spec)

| ID | Feature | Required data | Acquisition spec | Unlocks | Priority |
|---|---|---|---|---|---|
| F-OR | opening range | intraday ES 1m/5m, ≥2y | first N-minute [high,low] per day | H-OR-01 | P1 |
| F-IB | initial balance | same | first-hour (or first 30m) range + close | H-OR-01, H-AMT-02 | P1 |
| F-VWAP | cumulative VWAP | intraday OHLCV | price × volume / volume anchors | H-VWAP-01/02, H-OR-01 | P1 |
| F-VPROF | volume profile / POC / value area | intraday OHLCV | histogram → POC, VA bounds | H-VP-01 | P2 |
| F-SWEEP-I | intraday sweep detection | intraday (1m) | tick-through of pivot levels + reversal | H-LIQ-02 | P2 |
| F-DELTA | delta (buyer-initiated volume) | intraday with tick/volume direction | per-bar buy − sell volume | (catalog: order-flow family) | P2 |
| F-IMBALANCE | order-book imbalance | depth data | bid/ask volume ratio | (catalog: order-flow family) | P2 |
| F-TERM | term structure | multi-contract daily settles | spread series per market | H-FUT-01 | P2 |
| F-ROLL | roll dates | per-contract metadata | event flags | H-FUT-02 | P2 |
| F-OPT | option chain surface | ES option chains daily | P/C ratio, IV skew, term | H-OPT-01 | P2 |
| F-SENT | text/news sentiment | news corpus with timestamps | score series | H-ALT-02 | P2 |

## 5. Roadmap order

1. **P0 batch (ship with C002):** F-GAP-COMP, F-CAL, F-DON, F-MOM, F-RANGE,
   F-ATR, F-POSITION, F-STREAK, F-SWEEP, F-FVG, F-ALIGN, F-IMK-LAG — one
   shared module `research_platform/research_studies/features/`, numpy-only,
   unit-checked against C001 artifacts where applicable (F-GAP, F-RET must
   reproduce C001 numbers exactly).
2. **P0 data acquisition decision** (before or after C002–C007): VIX daily
   (F-EXTVOL) — trivial, unlocks H-ALT-01/H-OPT-adjacent work.
3. **P1:** F-TREND-STRUCT; intraday ES acquisition (F-OR/F-IB/F-VWAP) — the
   single highest-leverage acquisition, unlocks 5+ catalog hypotheses.
4. **P2:** volume/order-flow family; term structure; options.

Discipline: features live in one shared module and are versioned with the
repo; campaign modules import them (same pattern as `_common`); feature
checksums participate in the reproducibility chain via the experiment module.
