# Research Asset Registry

Registry of every reusable scientific component. Complete traceability and
reuse: any new campaign should first check here. Append-only; new assets get
the next free ID.

Schema per asset: **ID | name | version | dependencies | validation status |
campaigns used | known limitations | documentation**.

Version conventions: `qr-0.3.0` = frozen quant_research v0.3.0; `v1` = study
modules as committed with C001 (commits eafdf3d→c407039).

---

## 1. Datasets (AS-DS)

Full quality assessment: `dataset_quality_registry.md`.

| ID | Name | Version | Deps | Validation | Campaigns | Limitations | Docs |
|---|---|---|---|---|---|---|---|
| AS-DS-001 | es-f-10y-ohlc-v1 | v1 | — | registered, checksummed `b3159e9d…`, no missing values | C001 | roll methodology undocumented (provider); roll gaps can pollute gap series | dataset_quality_registry.md DS-001 |
| AS-DS-002 | es-gap-trial-matrix-v1 | v1 | AS-DS-001, registry runs | registered, checksummed `519cb85d…` | C001 | derived artifact; row order tied to assembly script | dataset_quality_registry.md DS-002 |
| AS-DS-003 | CL_F_10y.csv | raw | — | verified clean, **unregistered** | — | roll methodology undocumented | dataset_quality_registry.md DS-003 |
| AS-DS-004 | GC_F_10y.csv | raw | — | verified clean, **unregistered** | — | roll methodology undocumented | dataset_quality_registry.md DS-004 |
| AS-DS-005 | EURUSD_X_10y.csv | raw | — | verified clean, **unregistered**; 305 weekend bars | — | spot (X), weekend rows, different date axis vs futures | dataset_quality_registry.md DS-005 |
| AS-DS-006..009 | `*_F.csv` / `EURUSD_X.csv` (2y) | raw | — | verified clean, **unregistered** | — | short overlap windows; sanity checks only | dataset_quality_registry.md |

## 2. Indicators (AS-IND)

Mathematical definitions, lag, look-ahead safety: `feature_registry.md`.

| ID | Name | Version | Deps | Validation | Campaigns | Limitations | Docs |
|---|---|---|---|---|---|---|---|
| AS-IND-001 | F-RET (returns, cumulative, drawdown) | qr-0.3.0 | numpy | frozen-library tests + C001 reproduction | C001 | index-0 NaN convention must be propagated | feature_registry F-RET |
| AS-IND-002 | F-MA (rolling mean) | qr-0.3.0 | numpy | idem | C001 | O(n·w); NaN warm-up | feature_registry F-MA |
| AS-IND-003 | F-EMA (ewma) | qr-0.3.0 | numpy | idem | C001 | span must be > 0 | feature_registry F-EMA |
| AS-IND-004 | F-RVOL (ewma_volatility) | qr-0.3.0 | numpy | idem | C001 | warm-up NaN; regime labels are percentile-based | feature_registry F-RVOL |
| AS-IND-005 | F-ZSCORE (rolling_z_score) | qr-0.3.0 | numpy | idem | — | ddof choice matters for small windows | feature_registry F-ZSCORE |
| AS-IND-006 | F-CORR (rolling_correlation) | qr-0.3.0 | numpy | idem | — | minimum overlap enforced? verify per call | feature_registry F-CORR |
| AS-IND-007 | F-SMOOTH (centered_smooth) | qr-0.3.0 | numpy | idem | — | **NON-CAUSAL (centered)** — signals only with lag shift | feature_registry F-SMOOTH |

## 3. Filters (AS-FLT)

| ID | Name | Version | Deps | Validation | Campaigns | Limitations | Docs |
|---|---|---|---|---|---|---|---|
| AS-FLT-001 | direction filter (up/down/both) | v1 | F-GAP | C001 reproduction | C001 | sign tie (gap=0) treated as short | gap_strategy.py `_select_entries` |
| AS-FLT-002 | n_trades ≥ 3 gate | v1 | — | C001 reproduction | C001 | cells below gate are excluded from stats, zero-filled | gap_strategy.py |
| AS-FLT-003 | EWMA-vol tercile regime | v1 | F-RVOL | C001 reproduction | C001 | terciles computed in-sample (leakage risk for filters — use trailing quantiles in future campaigns) | gap_strategy.py |

## 4. Benchmark strategies (AS-BM)

| ID | Name | Version | Deps | Validation | Campaigns | Limitations | Docs |
|---|---|---|---|---|---|---|---|
| AS-BM-001 | buy_hold | v1 | F-RET | reproduced (6 metrics matched) | C001 | deterministic; one sample | buy_hold.py |
| AS-BM-002 | random_entries | v1 | F-RET, ctx.rng | C001 (3 seeds) | C001 | stochastic; report across seeds | random_entries.py |
| AS-BM-003 | sma_crossover | v1 | F-MA | C001 | C001 | long-only; 1-day lag | sma_crossover.py |
| AS-BM-004 | ema_crossover | v1 | F-EMA | C001 | C001 | long-only; 1-day lag | ema_crossover.py |

**Standard benchmark suite for all future daily campaigns:** buy_hold +
random_entries (3 seeds) + sma_crossover(10,100) + ema_crossover(10,100).
Rationale: meta_learning.md R2.

## 5. Statistical tests (AS-ST)

All `qr-0.3.0`, numpy-only, seeded, frozen-library tested. Full contract:
quant_research docs.

| ID | Name | Purpose | Used in C001 |
|---|---|---|---|
| AS-ST-001 | permutation_test_signal | nullity gate: entry-day selection has no edge | yes |
| AS-ST-002 | two_sample_t_test | Welch comparison vs construction-matched pool | yes |
| AS-ST-003 | bootstrap_confidence_interval | block bootstrap CI on mean trade return | yes |
| AS-ST-004 | deflated_sharpe_ratio | Bailey–López de Prado post-selection Sharpe | yes (meta) |
| AS-ST-005 | reality_check_p_value | White's Reality Check over trial matrix | yes (meta) |
| AS-ST-006 | probability_edge_above | Bayesian P(win rate > 50%), uniform prior | yes |
| AS-ST-007 | beta_posterior | posterior Beta(a,b) | yes |
| AS-ST-008 | sprt_bernoulli | Wald SPRT, win-rate 50% vs 55% | yes |
| AS-ST-009 | jarque_bera / skewness / excess_kurtosis | normality + DSR moment inputs | yes (meta) |
| AS-ST-010 | pearson/spearman_correlation | association tests | planned (C007) |
| AS-ST-011 | chi2_p_value | contingency tests | planned (C005/006) |
| AS-ST-012 | kelly_fraction / fractional_kelly | position-sizing layer | planned (H-VOL-02) |

## 6. Robustness procedures (AS-RP)

| ID | Name | Version | Validation | Campaigns | Notes |
|---|---|---|---|---|---|
| AS-RP-001 | cost ladder (0 / 2.5 / 5 bps) | v1 | C001 | C001 | report Sharpe AND mean/trade; Sharpe hid cost decay |
| AS-RP-002 | per-year breakdown (n, mean, win) | v1 | C001 | C001 | instability visible (2023, 2026 negative) |
| AS-RP-003 | vol-regime breakdown | v1 | C001 | C001 | entries cluster in high-vol states |
| AS-RP-004 | seed repeats (3 seeds) | v1 | C001 | C001 | deterministic strategies: tests statistical draws only |
| AS-RP-005 | commit-before-run discipline | framework | C001 | all | dirty-tree runs are refused by reproduce |
| AS-RP-006 | independent recomputation of headline stats | v1 | C001 | C001 | caught pool-alignment bug |

## 7. Experiment templates (AS-TP)

| ID | Name | Version | Validation | Campaigns | Notes |
|---|---|---|---|---|---|
| AS-TP-001 | deterministic config generator | v1 | C001 | C001 | `generate_configs.py`; 38 configs committed |
| AS-TP-002 | scan / cost / benchmark / meta config family | v1 | C001 | C001 | single-param sweep per config; one config per fixed cell |
| AS-TP-003 | smoke config | v1 | C001 | C001 | 1-cell config for bring-up |
| AS-TP-004 | trial-matrix assembly script | v1 | C001 | C001 | registry → npz, data-engineering only |
| AS-TP-005 | study `_common.py` bootstrap module | v1 | C001 | C001 | repo-root sys.path + shared metrics vocabulary |

## 8. Validation pipelines (AS-VP)

| ID | Name | Version | Deps | Validation | Campaigns | Notes |
|---|---|---|---|---|---|---|
| AS-VP-001 | per-cell battery | v1 | AS-ST-001..008 | C001 | C001 | nullity gate + Welch + bootstrap + Bayesian + SPRT |
| AS-VP-002 | grid meta-validation | v1 | AS-ST-004/005, AS-TP-004 | C001 (26 metrics matched) | C001 | DSR + White's RC over trial matrix + benchmark Welch |
| AS-VP-003 | cross-market replication pattern | — | AS-TP-001 | — | planned C003/C004/C007 | per-market battery + consistency table |

## 9. Counts

| Class | Registered assets |
|---|---|
| Datasets | 9 (2 registered) |
| Indicators | 7 |
| Filters | 3 |
| Benchmarks | 4 |
| Statistical tests | 12 |
| Robustness procedures | 6 |
| Experiment templates | 5 |
| Validation pipelines | 3 |
| **Total reusable assets** | **49** |
