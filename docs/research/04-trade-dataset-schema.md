# 04 — Trade Research Dataset: Schema Specification

Every field stored for every executed (or simulated) trade, so a trade can be
reproduced, audited, and researched years later. Schema only — no implementation.

Conventions: `id` = UUIDv7; timestamps = ISO-8601 UTC (or explicit exchange
TZ with tz-offset); prices = float64; sizes = int; booleans = 0/1. All
raw-data references point to immutable content-hashed snapshots (ADD §40).

---

## 1. trade_core — the identity row

| Field | Type | Notes |
|---|---|---|
| trade_id | UUID | primary key |
| dataset_snapshot_id | ref | hash of raw data version used (immutable) |
| strategy_id | ref | Registry artifact id (ADD §32) |
| model_version | ref | AI Decision Engine model version |
| instrument | str | NQ / MNQ / ES ... |
| contract | str | e.g. NQU26 |
| session_id | ref | continuous session instance (overnight/RTH split) |
| entry_datetime | timestamp | execution timestamp |
| exit_datetime | timestamp | |
| direction | int | +1 long / -1 short |
| entry_price | float | fill price (or mark for paper) |
| exit_price | float | |
| quantity | int | contracts |
| multiplier | float | $/point (20 for NQ, 2 for MNQ) |
| gross_pnl | float | (exit−entry)×multiplier×qty×direction |
| net_pnl | float | gross − all costs (fees, slippage, spread) |
| commission | float | |
| slippage_cost | float | | 
| spread_cost | float | half-spread estimate on fills |
| status | enum | filled / partial / rejected / simulated |
| paper_or_live | enum | research / backtest / paper / live |
| execution_venue | str | IBKR / Databento / simulated |

## 2. signal_features — what triggered the trade

| Field | Type | Notes |
|---|---|---|
| signal_id | ref | unique signal record id |
| signal_type | str | trend_cross / fvg / vol_target / ai_model... |
| signal_value | float | raw signal output |
| signal_parameters | json | frozen param set (hash for lookup) |
| ai_model_inputs_hash | str | hash of the exact feature vector |
| ai_win_probability | float | calibrated P(win) at decision time |
| ai_confidence | float | model confidence |
| ai_decision | enum | approve / reject / resize |
| setup_id | ref | setup template id (rejected-setup tracking) |
| setup_rejection_reason | str | if rejected |

## 3. market_features — context at decision/execution time

| Field | Type | Notes |
|---|---|---|
| session_type | enum | overnight / rth / settlement |
| open_price, high, low, close | float | current bar |
| bar_open_datetime | timestamp | bar anchor |
| vwap | float | session-cumulative |
| vwap_deviation | float | (P−VWAP) in points |
| opening_range_high/low | float | OR of chosen N |
| initial_balance_high/low | float | 60-min IB |
| volume | int | bar volume |
| profile_poc | float | day volume profile POC |
| profile_vah, profile_val | float | value area bounds |
| realized_vol_10m | float | realized vol (10-min) |
| ewma_vol | float | EWMA volatility estimate |
| atr | float | average true range |
| spread_bps | float | bid-ask spread in bps |
| depth_top_of_book | json | best bid/ask sizes |
| market_maker_liquidity | float | est. liquidity at level |

## 4. macro_features — exogenous context

| Field | Type | Notes |
|---|---|---|
| fomc_date | bool | decision day |
| fomc_time_to_event | float | hours to announcement |
| cpi_date / ppi_date | bool | CPI/PPI release days |
| earnings_window | bool | index heavy-earnings week |
| quarter_end / month_end | bool | rebalancing windows |
| vix_close_prev | float | prior-day VIX |
| vix_futures_contango | float | VIX future basis |
| treasury_10y_yield | float | |
| dxy | float | dollar index |
| ois/fed_funds_implied | float | implied rate change |
| sentiment_index | float | optional composite |
| news_events | json | tagged events with ids |

## 5. session_features — execution session context

| Field | Type | Notes |
|---|---|---|
| day_of_week | int | |
| minute_of_day | int | since 5pm CT session open |
| minutes_to_settle | int | |
| overnight_range | float | 5pm-9:30am range |
| gap_at_open | float | open vs prior settlement |
| prior_day_range | float | |
| prior_day_volume | float | |
| consecutive_up_days / down | int | streak |
| session_high / low | float | cumulative session extremes |
| session_pnl | float | intraday P&L before trade |
| daily_loss_used | float | % of daily limit consumed |

## 6. risk_features — risk state at decision time

| Field | Type | Notes |
|---|---|---|
| account_equity | float | |
| account_cash | float | |
| margin_used | float | |
| margin_available | float | |
| open_positions | json | all open positions (symbol, qty, entry) |
| portfolio_delta | float | net market exposure |
| portfolio_corr | float | est. correlation of new pos vs book |
| risk_budget_remaining | float | % of risk budget left |
| daily_loss_used_pct | float | |
| stop_loss_price | float | planned stop |
| take_profit_price | float | planned target |
| risk_per_trade_pct | float | actual % risked |
| position_size_formula | str | sizing rule id + params |
| kelly_fraction | float | if Kelly sizing used |

## 7. execution_features — what really happened

| Field | Type | Notes |
|---|---|---|
| order_type | enum | market / limit / stop / vwap algo |
| order_route | str | smart / direct |
| requested_price | float | limit/stop level |
| fill_price | float | |
| slippage_bps | float | fill vs mid/market at send |
| fill_latency_ms | float | order send → fill |
| partial_fills | json | fill-by-fill (time, px, qty) |
| venue_liquidity_at_fill | float | size available at level |
| order_id_broker | str | broker reference |
| cancel_reason | str | if cancelled |
| mmp_status | enum | none / pausing / blocked |

## 8. portfolio_features — book-level effects

| Field | Type | Notes |
|---|---|---|
| portfolio_value_before / after | float | |
| total_exposure_before / after | float | |
| net_exposure_before / after | float | |
| gross_exposure_before / after | float | |
| max_drawdown_live | float | live peak-to-trough before trade |
| correlation_to_book | float | |
| var_1d_95 | float | portfolio VaR |
| portfolio_regime | str | regime label (edge monitor) |

## 9. ai_features — model provenance

| Field | Type | Notes |
|---|---|---|
| model_name | str | |
| model_version | str | registry ref |
| training_data_snapshot | ref | hashed dataset |
| feature_importance | json | attribution at decision time |
| model_explanation | json | explanation tokens (explainability layer) |
| model_uncertainty | float | predictive variance / entropy |
| calibration_bin | float | calibration bucket (e.g., 0.55-0.60) |
| calibration_error | float | Brier score component |
| adversarial_flag | bool | data shift detected at inference |

## 10. research_metadata — reproducibility

| Field | Type | Notes |
|---|---|---|
| experiment_id | ref | experiment tracking id |
| hypothesis_id | ref | findings-table entry (ADD §39) |
| walkforward_fold | str | fold id if part of WF validation |
| oos_flag | bool | was this trade out-of-sample |
| parameters_frozen_hash | str | hash of strategy params |
| backtest_engine_version | str | software version |
| random_seed | int | if stochastic |
| researcher_notes | str | free text (owner) |
| tags | json | arbitrary research tags |

## 11. validation_metadata — post-trade truth

| Field | Type | Notes |
|---|---|---|
| validation_status | enum | open / confirmed / refuted / superseded |
| validated_by | str | process (edge monitor / manual / SPRT) |
| validation_datetime | timestamp | |
| sprt_decision | enum | continue / accept / reject edge |
| sprt_log_likelihood | float | cumulative LL ratio |
| post_trade_market_context | json | what happened after (frozen) |
| outcome_fair | bool | fill/execution considered fair |
| corrected_pnl | float | P&L after corrections |
| lesson_id | ref | linked lesson in knowledge base |

## 12. Lineage & immutability rules

- Trade rows are **insert-only**; corrections append a new validation row
  with `corrected_pnl` (never UPDATE a filled trade — ADD §41).
- Every FK points to an immutable, content-hashed record; no "latest"
  pointers inside the research store (point-in-time semantics).
- All feature values are frozen at decision time: no look-ahead by
  construction; the snapshot hash at `decision_time` is part of the trade id
  signature.
- Deletions are not possible for filled trades; simulated rows may be
  purged only via a recorded governance action (ADRs, Part III §41).

## 13. Storage mapping

| Group | Engine | Notes |
|---|---|---|
| trade_core + execution | DuckDB (append-only) | transactional, indexed by trade_id |
| features (2-9) | DuckDB tables or parquet-partitioned | wide tables, partition by instrument/date |
| ai artifacts | Registry (Subsystem 2) | model/param versioning |
| raw market data | immutable object store (local S3-compatible / files) | content-hashed files |
| research knowledge | findings table (Part III §39) | lifecycle-tracked claims |
