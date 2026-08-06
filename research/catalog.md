# Research Catalog

Every hypothesis this laboratory may investigate, in every research domain.
**No undocumented research**: a hypothesis only enters an experiment once it
is specified here.

Feasibility classes (data):

| Class | Meaning |
|---|---|
| **A** | Executable now — daily OHLC only (ES/CL/GC/EURUSD, 10y aligned daily bars in `data/`) |
| **B** | Blocked on data acquisition; the required dataset is specified in the entry |

Status values: `proposed`, `ready`, `in-progress`, `rejected`, `accepted`, `blocked-data`.

Effort (with platform as-is): S ≤ 1 day, M ≤ 3 days, L > 3 days.
Info value: expected information gained per unit effort, not expected profitability.

Statistical methodology references: nullity gate and test battery as defined in
`docs/research/05-edge-detection-methods.md` and executed in Campaign 001
(gap_continuation): permutation nullity gate, Welch t vs construction-matched
pool, block bootstrap CI, Bayesian win-rate, Wald SPRT, DSR + White's Reality
Check for searched grids. All statistics via `quant_research` (frozen v0.3.0).

---

## 1. Market Structure (MS)

### H-MS-01 — Gap Fading (mirror of C001)
- **Description:** After an overnight gap exceeding `threshold_pct`, the
  holding-period open→close move *reverses* the gap (gap up → short).
- **Motivation:** C001 rejected gap *continuation* on ES daily. The literature
  on equity-index gap fading suggests the opposite sign may carry the effect.
  This distinguishes "no gap edge" from "gap edge of opposite sign".
- **Datasets:** `es-f-10y-ohlc-v1` (A). 
- **Features:** F-GAP, F-GAP-COMP.
- **Methodology:** Identical battery to C001 (permutation gate vs signed pool,
  Welch, bootstrap, Bayesian, SPRT), 36-cell grid, DSR/RC meta-validation.
- **Benchmarks:** buy & hold, EMA(10,100), random entries, C001 best cell.
- **Effort:** S. **Info value:** High. **Status:** `ready` (Campaign 002).

### H-MS-02 — Daily range position predicts next-day direction
- **Description:** The position of the close within the day's [low, high]
  (range position, and its N-day normalized form) predicts the next day's
  open→close sign.
- **Motivation:** Range structure is the most basic market-structure feature;
  a documented link would inform every other hypothesis; rejection is cheap.
- **Datasets:** `es-f-10y-ohlc-v1`, plus CL/GC/EURUSD (A).
- **Features:** F-RANGE, F-POSITION.
- **Methodology:** Nullity gate + Welch vs construction-matched pool over a
  (window × position-quantile) grid; per-market replication.
- **Benchmarks:** buy & hold, random entries.
- **Effort:** M. **Info value:** Medium-High. **Status:** `proposed`.

---

## 2. Trend Following (TF)

### H-TF-01 — Donchian channel breakout, multi-market
- **Description:** Enter long on close > N-day high (short on close < N-day
  low), exit on the opposite M-day extreme; grid over (N, M) and all four
  markets.
- **Motivation:** The canonical persistent futures anomaly; validates the
  platform's multi-dataset workflow and measures which markets respond.
- **Datasets:** all four 10y daily sets, each registered as its own dataset (A).
- **Features:** F-DON, F-TREND.
- **Methodology:** Same battery as C001 per cell; DSR/RC per market over the
  (N,M) grid; cross-market consistency table; cost ladder.
- **Benchmarks:** buy & hold, EMA/SMA crossovers, random entries.
- **Effort:** M. **Info value:** High. **Status:** `ready` (Campaign 003).

### H-TF-02 — Multi-day momentum sign
- **Description:** Sign of close_t / close_{t-k} − 1 for k ∈ {5, 21, 63}
  predicts the next 1–5 day direction.
- **Motivation:** Isolates pure time-series momentum from breakout mechanics.
- **Datasets:** all four markets (A).
- **Features:** F-MOM, F-TREND.
- **Methodology:** Permutation gate vs construction-matched pool; grid (k,
  holding); DSR/RC.
- **Benchmarks:** buy & hold, crossover family.
- **Effort:** S. **Info value:** Medium-High. **Status:** `ready`.

---

## 3. Mean Reversion (MR)

### H-MR-01 — Rolling z-score reversion (Bollinger-style)
- **Description:** Enter against close more than z standard deviations from
  the N-day mean (z grid), exit at the mean or after H days.
- **Motivation:** The complement of momentum; establishes which of the two
  canonical families has evidence on these instruments.
- **Datasets:** all four markets (A).
- **Features:** F-ZSCORE (rolling_mean, rolling_std, rolling_z_score exist in
  quant_research.core).
- **Methodology:** Battery as C001; grid over (N, z, hold); DSR/RC; per-market.
- **Benchmarks:** buy & hold, random entries, crossover family.
- **Effort:** M. **Info value:** High. **Status:** `ready` (Campaign 004).

### H-MR-02 — Short-term reversal after streaks
- **Description:** After K consecutive same-direction daily closes, the next
  day's open→close return reverses.
- **Motivation:** Cheapest test of overreaction; high sample count on daily data.
- **Datasets:** all four markets (A).
- **Features:** F-STREAK.
- **Methodology:** Welch + permutation vs signed pool; per-market; per-year
  breakdown.
- **Benchmarks:** random entries, buy & hold.
- **Effort:** S. **Info value:** Medium. **Status:** `proposed`.

---

## 4. Volatility (VOL)

### H-VOL-01 — Volatility state persistence and return conditioning
- **Description:** EWMA-volatility tercile/quantile state at time t predicts
  next-day return magnitude and sign asymmetry; and whether vol state clusters
  (persistence) beyond what a GARCH(1,1) null implies.
- **Motivation:** C001's regime breakdown hinted that gap trades cluster in
  high-vol states; vol knowledge feeds every other campaign (filters, sizing).
- **Datasets:** all four markets (A).
- **Features:** F-RVOL (ewma_volatility, rolling_std), F-REGIME.
- **Methodology:** Chi-square/jarque-bera style state-transition tests, Welch
  on regime-conditioned returns, bootstrap CIs.
- **Benchmarks:** buy & hold.
- **Effort:** S. **Info value:** Medium-High. **Status:** `ready` (Campaign 006).

### H-VOL-02 — Volatility targeting
- **Description:** Scaling position by 1/σ_t (EWMA vol) improves the
  risk-adjusted return of a base rule relative to constant sizing.
- **Motivation:** A robustness/engineering layer for whatever the TF/MR
  campaigns accept; tests risk-management claims.
- **Datasets:** depends on base rule (A).
- **Features:** F-RVOL.
- **Methodology:** Compare Sharpe/distribution of base vs vol-scaled on the
  same trade series; bootstrap CI on the Sharpe difference; cost ladder.
- **Benchmarks:** the unscaled base rule.
- **Effort:** M. **Info value:** Medium. **Status:** `proposed` (extension of C003/C004).

---

## 5. Opening Range (OR)

### H-OR-01 — Opening Range Breakout, intraday
- **Description:** Trade the first break of the opening range (OR(5)/OR(15)),
  with variants OR+trend, OR+VWAP, OR+volume filter, OR+volatility filter.
- **Motivation:** The canonical intraday institutional pattern; high market
  relevance, but requires intraday data. Acquiring 1–5 min ES bars unlocks
  this and the TOD/VP/FVG-intraday family at once.
- **Datasets:** intraday ES (1m or 5m, ≥2y), registered (B).
- **Features:** F-OR, F-IB, F-ATR, F-VWAP.
- **Methodology:** Standard battery; grid over range length and filters;
  DSR/RC.
- **Benchmarks:** buy & hold, intraday random entries.
- **Effort:** L. **Info value:** High. **Status:** `blocked-data`.

---

## 6. VWAP

### H-VWAP-01 — VWAP deviation reversion, intraday
- **Description:** Price deviation from cumulative VWAP (z-scored) reverts;
  trade the deviation.
- **Motivation:** Most widely used institutional anchor; complements OR.
- **Datasets:** intraday ES with volume (B).
- **Features:** F-VWAP.
- **Methodology:** Battery; grid over deviation z and hold.
- **Benchmarks:** random entries, ORB.
- **Effort:** L. **Info value:** Medium-High. **Status:** `blocked-data`.

### H-VWAP-02 — Daily VWAP anchor reversion (daily bars)
- **Description:** Daily-bar VWAP proxy (typical price × volume) as anchor;
  reversion of close-to-anchor distance.
- **Motivation:** Only volume-dependent daily-bar hypothesis possible with our
  data; tests whether volume information changes daily conclusions at all.
- **Datasets:** daily OHLC + volume series (B — volume column required).
- **Features:** F-VWAP, F-VPROF-lite.
- **Methodology:** Battery; distance quantile grid.
- **Benchmarks:** buy & hold, random entries.
- **Effort:** M. **Info value:** Medium. **Status:** `blocked-data`.

---

## 7. Liquidity (LIQ)

### H-LIQ-01 — Daily liquidity-sweep proxy: failed breaks
- **Description:** A day whose high exceeds the prior N-day high but closes
  below it (failed breakout / stop run) predicts a reversal of the break.
- **Motivation:** Tests the "liquidity sweep" idea with data we already have,
  acknowledging it is a proxy for true intraday sweeps.
- **Datasets:** all four markets (A).
- **Features:** F-SWEEP, F-DON.
- **Methodology:** Battery; grid over N and confirmation rule; per-market.
- **Benchmarks:** buy & hold, random entries.
- **Effort:** S-M. **Info value:** Medium. **Status:** `ready`.

### H-LIQ-02 — True intraday liquidity sweeps
- **Description:** Wicks beyond resting liquidity at prior session extremes
  followed by fast reversal.
- **Motivation:** Core order-flow concept; requires intraday data.
- **Datasets:** intraday ES (B).
- **Features:** F-SWEEP, F-PIVOT.
- **Methodology:** Battery; event-study framing.
- **Effort:** L. **Info value:** High. **Status:** `blocked-data`.

---

## 8. Fair Value Gaps (FVG)

### H-FVG-01 — Daily-bar Fair Value Gap fill behavior
- **Description:** A bullish FVG is the price void between candle1.high and
  candle3.low; test fill probability within K days and the direction after
  fill/failed fill.
- **Motivation:** The FVG concept is popular in retail order-flow; daily bars
  give a cheap first read before any intraday commitment.
- **Datasets:** all four markets (A).
- **Features:** F-FVG.
- **Methodology:** Battery on fill events; grid over gap-size filter.
- **Benchmarks:** random entries, buy & hold.
- **Effort:** M. **Info value:** Medium-High. **Status:** `ready`.

---

## 9. Auction Market Theory (AMT)

### H-AMT-01 — Range expansion days predict continuation
- **Description:** A day with range > R × the N-day average range (expansion
  day) is followed by continuation (vs balance days followed by reversal).
- **Motivation:** AMT's core prediction, testable on daily bars.
- **Datasets:** all four markets (A).
- **Features:** F-RANGE, F-ATR.
- **Methodology:** Welch + permutation vs construction-matched pool; grid over
  (R, N); per-market.
- **Benchmarks:** buy & hold, random entries.
- **Effort:** S. **Info value:** Medium. **Status:** `ready`.

### H-AMT-02 — Balance vs trend day classification via initial balance
- **Description:** Trend-day classification (close beyond IB) and its
  predictive power.
- **Motivation:** AMT's second core concept; needs the opening auction window.
- **Datasets:** intraday ES (B).
- **Features:** F-IB, F-OR.
- **Methodology:** Battery; classification accuracy vs random.
- **Effort:** L. **Info value:** Medium. **Status:** `blocked-data`.

---

## 10. Session Behavior (SESS)

### H-SESS-01 — Day-of-week effects
- **Description:** Returns, vol, and gap behavior differ by weekday (Monday
  open gap, Friday close, etc.).
- **Motivation:** Classic calendar hypothesis; on liquid modern futures the
  expected outcome is rejection — which is itself valuable calibration for the
  laboratory's false-positive rate.
- **Datasets:** all four markets (A).
- **Features:** F-CAL, F-GAP.
- **Methodology:** Welch per-day-of-week vs other days; bootstrap CI; multiple-
  comparison-corrected.
- **Benchmarks:** buy & hold.
- **Effort:** S. **Info value:** Medium (process value high). **Status:** `ready` (Campaign 005).

### H-SESS-02 — Turn-of-month and month effects
- **Description:** Returns cluster around month-end and specific months.
- **Motivation:** Same family as SESS-01; cheap and high sample.
- **Datasets:** all four markets (A).
- **Features:** F-CAL.
- **Methodology:** As SESS-01.
- **Effort:** S. **Info value:** Low-Medium. **Status:** `ready` (with SESS-01).

---

## 11. Time-of-Day (TOD)

### H-TOD-01 — Gap vs intraday return component decomposition
- **Description:** Decompose each day into overnight (close_{t-1}→open_t) and
  intraday (open_t→close_t) returns; measure which component carries the
  weekly/monthly drift and whether components are negatively correlated.
- **Motivation:** Directly extends C001 knowledge: C001 showed intraday returns
  after gaps differ from overall intraday drift; the decomposition locates the
  effect precisely.
- **Datasets:** `es-f-10y-ohlc-v1` + others (A).
- **Features:** F-GAP-COMP.
- **Methodology:** Correlation tests (pearson/spearman), Welch comparisons,
  bootstrap CIs on component means.
- **Benchmarks:** buy & hold.
- **Effort:** S-M. **Info value:** Medium-High. **Status:** `ready`.

### H-TOD-02 — Intraday session phase returns
- **Description:** First-hour vs midday vs last-hour return profiles; overnight
  session vs day session.
- **Motivation:** Institutional execution relevance; needs intraday data.
- **Datasets:** intraday ES (B).
- **Features:** F-SESSION.
- **Methodology:** Battery per phase.
- **Effort:** L. **Info value:** Medium-High. **Status:** `blocked-data`.

---

## 12. Volume Profile (VP)

### H-VP-01 — Point-of-control reversion
- **Description:** Price reverts toward the volume-profile POC after deviation
  beyond the value area.
- **Motivation:** The core Volume Profile claim; intraday + volume.
- **Datasets:** intraday ES with volume (B).
- **Features:** F-VPROF.
- **Methodology:** Battery; deviation grid.
- **Effort:** L. **Info value:** Medium-High. **Status:** `blocked-data`.

---

## 13. Intermarket Relationships (IMK)

### H-IMK-01 — Cross-market lead into ES
- **Description:** Prior-day (and overnight) moves in CL, GC, EURUSD predict
  the next ES day direction or magnitude, individually and combined.
- **Motivation:** Unique to this laboratory: four aligned 10y daily series are
  already in the repo. Intermarket effects are under-exploited in retail
  research and require no new data.
- **Datasets:** all four 10y daily sets, aligned (A).
- **Features:** F-ALIGN, F-MOM, F-IMK-LAG.
- **Methodology:** Nullity gate with lag-aligned pools; grid over lags and
  conditioning; DSR/RC; regime splits (crisis vs calm).
- **Benchmarks:** buy & hold, random entries, EMA(10,100).
- **Effort:** M. **Info value:** High. **Status:** `ready` (Campaign 007).

### H-IMK-02 — Correlation regime predicts ES vol
- **Description:** Rolling correlation regimes (ES–GC, ES–CL, ES–EURUSD)
  forecast ES realized vol state.
- **Motivation:** Risk-management value; uses rolling_correlation directly.
- **Datasets:** all four markets (A).
- **Features:** F-IMK-CORR, F-RVOL.
- **Methodology:** Regime-contingency tests (chi2_p_value), Welch comparisons.
- **Effort:** S-M. **Info value:** Medium. **Status:** `proposed`.

---

## 14. Futures Structure (FUT)

### H-FUT-01 — Term-structure / roll-yield signals
- **Description:** Backwardation/contango states (calendar spread sign) predict
  directional returns of the front month.
- **Motivation:** The classic futures-specific premium; requires multiple
  contracts per date.
- **Datasets:** multi-contract daily settle/OHLC history, ≥2 contracts, all
  markets (B).
- **Features:** F-TERM.
- **Methodology:** Battery; regime grid.
- **Effort:** L. **Info value:** Medium-High. **Status:** `blocked-data`.

### H-FUT-02 — Roll-day behavior of continuous series
- **Description:** Behavior of the provider's continuous series around roll
  dates (if recoverable) — artifacts vs signal.
- **Motivation:** Defensive research: quantify how much of measured effects is
  roll artifact. Requires roll-date metadata (B).
- **Datasets:** roll dates per contract (B).
- **Features:** F-ROLL.
- **Methodology:** Event study, Welch comparisons.
- **Effort:** M. **Info value:** Medium (process). **Status:** `blocked-data`.

---

## 15. Options-Derived (OPT)

### H-OPT-01 — Option-market signals (P/C ratio, IV term structure)
- **Description:** Options-derived crowding/skew states predict equity-index
  returns.
- **Motivation:** The option market reveals positioning invisible in futures
  prices.
- **Datasets:** ES option chain daily (B).
- **Features:** F-OPT.
- **Methodology:** Battery; quantile grid.
- **Effort:** L. **Info value:** Medium-High. **Status:** `blocked-data`.

---

## 16. Alternative Data (ALT)

### H-ALT-01 — Volatility-index data as external input
- **Description:** VIX level, change, and term structure forecast ES return/vol
  beyond own-price volatility.
- **Motivation:** The cheapest external dataset (daily VIX is freely
  available); establishes the alternative-data pipeline.
- **Datasets:** VIX daily OHLC, 10y, registered (B — trivial acquisition).
- **Features:** F-EXTVOL.
- **Methodology:** Battery with lag discipline; grid over conditioning.
- **Effort:** M. **Info value:** Medium-High. **Status:** `blocked-data`.

### H-ALT-02 — External alt-data (news, positioning, flows)
- **Description:** Text/news sentiment, CFTC positioning, or flow aggregates
  as signals.
- **Motivation:** Long-term differentiator; heavy acquisition and pipeline cost
  for unknown value at this scale.
- **Datasets:** to be specified at acquisition time (B).
- **Features:** F-SENT, F-POS.
- **Methodology:** Standard battery; strict OOS protocol.
- **Effort:** L. **Info value:** Medium. **Status:** `proposed` (deferred).

---

## 17. Machine Learning (ML)

### H-ML-01 — Honest ML benchmark on catalog features
- **Description:** Cross-validated linear (and one nonlinear) model on the
  feature library predicts next-day ES direction; assessed with the same
  statistical discipline (feature-search multiplicity → DSR-style correction,
  time-series CV, no leakage).
- **Motivation:** Either validates the "ML edge" claim rigorously or kills it —
  the highest-information single test available to the laboratory once the
  feature library exists.
- **Datasets:** `es-f-10y-ohlc-v1` + features (A once features ship).
- **Features:** the full library, subset selection documented.
- **Methodology:** Purged/embargoed time-series CV; DSR/RC over model-feature
  search set; benchmark comparison on out-of-sample walk-forward.
- **Benchmarks:** buy & hold, EMA(10,100), best accepted rule.
- **Effort:** L. **Info value:** High. **Status:** `proposed` (after C002–C007).

### H-ML-02 — Feature-importance meta-analysis
- **Description:** Across all completed experiments, measure which features
  appear in accepted results and which are consistently dead.
- **Motivation:** Pure research-process asset; feeds `meta_research.md`
  mechanically.
- **Datasets:** Edge Database + registry (A).
- **Features:** n/a.
- **Methodology:** Descriptive statistics on the Edge Database.
- **Effort:** M. **Info value:** Medium-High (process). **Status:** `proposed`.

---

## Cross-references

- Campaign assignments: `campaigns.md`.
- Feature dependencies: `features.md`.
- Outcomes: `edge_database.md` (append-only).
