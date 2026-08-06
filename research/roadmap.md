# Research Roadmap — Next Ten Campaigns

Prioritized by **expected information gain**, per the Decision Policy
(catalog/campaigns docs): each campaign must answer unresolved questions,
validate reusable components, or eliminate a hypothesis space. All ten are
executable with data already in the repository (daily OHLC, four markets) —
no acquisition-gated item is in this list.

Numbering continues from `campaigns.md` (C001 closed, C002–C010 already
registered there; C011+ are new).

Rank = priority order. Info gain: H/M/L (expected information per unit effort).
Effort: S ≤ 1 day, M ≤ 3 days, L > 3 days.

| Rank | Campaign | Hypotheses | Effort | Info gain | Why it ranks here |
|---|---|---|---|---|---|
| 1 | C002 Gap Fading | H-MS-01 | S | H | Closes the entire gap family: "no continuation" + "no fade" = gap dimension exhausted on daily ES; opposite-sign finding = first edge candidate. Near-zero marginal cost (C001 modules, sign flip). |
| 2 | C003 Trend Multi-Market | H-TF-01, H-TF-02 | M | H | Largest single information gain: momentum validity + market responsiveness (P5 in meta_learning). Also ships F-DON/F-MOM and the multi-market workflow. |
| 3 | C004 Mean Reversion | H-MR-01, H-MR-02 | M | H | Second canonical family; with C003, calibrates the momentum-vs-reversion question on identical benchmarks. |
| 4 | C007 Intermarket | H-IMK-01, H-IMK-02 | M | H | Unique asset (4 aligned 10y series in-repo). Cross-market lead/correlation knowledge no other hypothesis touches; answers "which markets are easiest to model". |
| 5 | C011 Range & Auction Structure | H-MS-02, H-AMT-01, H-TOD-01 | M | H | Foundational structure knowledge: close position, range expansion, gap/intraday decomposition. Informs every later directional hypothesis and quantifies P3 (drift components). |
| 6 | C006 Volatility State & Targeting | H-VOL-01, H-VOL-02 | S-M | M-H | Validates F-REGIME/F-RVOL as reusable components and adds the vol-targeting layer to whichever of C003/C004 survived. |
| 7 | C008 Daily Fair Value Gaps | H-FVG-01 | M | M-H | Tests a popular pattern family with data in hand; if dead, prunes FVG from the intraday wishlist; if alive, prioritizes intraday acquisition. |
| 8 | C009 Daily Liquidity Sweep Proxy | H-LIQ-01 | S-M | M | Same logic as C008 for the sweep/failed-break family; F-SWEEP ships. |
| 9 | C005 Calendar Effects | H-SESS-01, H-SESS-02 | S | M (process) | Expected rejection class; second false-discovery calibration point (after E-0003) and completes the "dead anomaly" baseline. |
| 10 | C010 Honest ML Benchmark | H-ML-01 | L | H | Kept last deliberately: maximal info only if the feature library has been battle-tested by C002–C009 and the benchmark suite is stable (R2, R8). Runs the full feature matrix through purged CV with DSR-style multiplicity control. |

## Dependency graph

- C006 (vol-targeting) applies to winners of C003/C004 → run after them.
- C010 depends on the P0 feature batch (R6) + standard benchmark suite (R2).
- C008/C009 depend on F-FVG / F-SWEEP implementations (P0 batch).
- C005 is independent — can be slotted earlier as a filler without disturbing
  the order.
- C007 needs F-ALIGN/F-IMK-LAG + the EURUSD preprocessing (dataset registry
  DS-005).

## What each campaign must deliver (beyond its report)

| Campaign | Deliverable to the laboratory |
|---|---|
| C002 | Gap family closed (edge DB + negative knowledge); F-GAP-COMP verified |
| C003 | Multi-market workflow (4 registered datasets); market-responsiveness table; F-DON/F-MOM verified |
| C004 | Momentum-vs-reversion comparison on identical basis; F-ZSCORE campaign-verified |
| C007 | Cross-market lead/correlation facts; F-ALIGN/F-IMK-LAG verified; EURUSD calendar fixed |
| C011 | Drift-component decomposition (overnight vs intraday); F-RANGE/F-ATR/F-POSITION/F-STREAK verified |
| C006 | Vol persistence + targeting facts; F-REGIME trailing-quantile upgrade |
| C008 | FVG daily family verdict; F-FVG verified |
| C009 | Sweep-proxy family verdict; F-SWEEP verified |
| C005 | Second FDR calibration point; F-CAL verified |
| C010 | ML-validity verdict under multiplicity control; feature-importance data |

## Beyond the ten (acquisition-gated)

Once data lands: ORB/VWAP/volume-profile/order-flow campaigns (intraday ES),
VIX-based signals (H-ALT-01), term structure (H-FUT-01/02), options-derived
signals (H-OPT-01). These enter the ranked queue only after their datasets
are registered and graded (dataset_quality_registry.md rules).

## Roadmap policy

- Re-rank at each campaign closure and at quarterly review, using
  `meta_learning.md` standing questions; write the justification in the
  meta-research log.
- A campaign may be skipped only if a newer result eliminates its question
  (e.g., C008/C009 are pre-empted if C004/C011 show daily structure effects
  are uniformly absent).
