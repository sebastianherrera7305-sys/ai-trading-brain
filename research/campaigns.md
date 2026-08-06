# Research Campaigns — Registry and Prioritized Backlog

Research is executed in campaigns. A campaign is a coherent family of
experiments around one research question, with a fixed objective, experiment
matrix, benchmarks, validation methodology, robustness tests, and a closing
report (publication-quality, per `README.md` §6).

## Campaign card template

```markdown
### C0XX — <Title>
- **Status:** proposed | in-progress | completed | archived
- **Objective:** (the question the campaign must answer)
- **Hypotheses:** H-IDs from catalog.md
- **Experiment matrix:** (grid: parameters × markets × seeds)
- **Benchmarks:** (same-P&L basis)
- **Validation:** (tests from the battery; DSR/RC if any grid is searched)
- **Robustness:** (cost ladder, per-year/regime, seed stability)
- **Expected info value / cost:** H/M/L × S/M/L
- **Report:** <path to report.md> (when completed)
```

## Registry

### C001 — Overnight Gap Continuation (COMPLETED — REJECTED)
- **Objective:** Does gap continuation on daily ES futures have an edge?
- **Hypotheses:** (gap continuation; the catalog successor is H-MS-01)
- **Matrix:** 36 cells (4 thresholds × 3 holds × 3 directions) × 3 seeds @ 0 bps; 36 cells × 3 seeds @ 2.5/5 bps; 16 benchmark runs.
- **Benchmarks:** buy & hold, random entries, SMA/EMA crossovers.
- **Validation:** permutation nullity gate, Welch, bootstrap CI, Bayesian win rate, SPRT, DSR, White's Reality Check.
- **Verdict:** REJECTED — DSR p=0.285, RC p≈0.39; best cell (Sharpe 0.52) below buy & hold (0.79) and EMA(10,100) (0.89).
- **Report:** `research_platform/research_studies/gap_continuation/report.md` (reference template).
- **Edge DB:** E-0001, E-0002, E-0003.

---

## Prioritized backlog (ranked by expected information value per unit effort)

### C002 — Gap Fading (H-MS-01) — STATUS: ready, next
- **Objective:** Does the *opposite* sign of the C001 rule carry the edge
  (gaps fade instead of continue)?
- **Hypotheses:** H-MS-01.
- **Matrix:** 36 cells × 3 seeds @ 0 bps + 2.5/5 bps ladder; reuses C001 modules
  (sign flip + same battery).
- **Benchmarks:** buy & hold, EMA(10,100), random entries, **C001 best cell**
  (directly comparable).
- **Validation:** identical to C001; DSR/RC on the 36-cell grid; meta-compares
  C001 vs C002 best cells (paired).
- **Robustness:** cost ladder, per-year, vol regime; seed stability.
- **Expected value/cost:** High / S — the cheapest experiment with the highest
  incremental information: it converts C001's "no edge" into either "no gap
  edge at all" or "opposite-sign edge".
- **Edge DB outcome:** expected entry E-00xx (rejected or accepted).

### C003 — Trend Following Multi-Market (H-TF-01, H-TF-02) — STATUS: ready
- **Objective:** Which markets respond to time-series momentum/breakout rules,
  with what magnitude and stability?
- **Hypotheses:** H-TF-01 (Donchian grid), H-TF-02 (momentum sign grid).
- **Matrix:** (N,M) grid × 4 markets × 3 seeds; momentum k-grid × 4 markets ×
  3 seeds; cost ladder on winners.
- **Datasets:** register CL/GC/EURUSD 10y daily (ES already registered) —
  exercises the platform's multi-dataset workflow.
- **Benchmarks:** buy & hold, crossover family, random entries (per market).
- **Validation:** full battery per market; DSR/RC per market over the grid;
  cross-market consistency table; inter-market correlation of results.
- **Robustness:** per-year, per-regime, vol-targeted variant (pulls in H-VOL-02).
- **Expected value/cost:** High / M — validates or rejects the canonical
  persistent anomaly on our data and produces the market-responsiveness
  knowledge every later campaign needs.
- **Edge DB outcome:** expected entry (per market).

### C004 — Mean Reversion (H-MR-01, H-MR-02) — STATUS: ready
- **Objective:** Is there time-series mean reversion on daily bars, and does
  it complement or contradict C003's momentum findings?
- **Hypotheses:** H-MR-01 (z-score grid), H-MR-02 (streak reversal).
- **Matrix:** (N, z, hold) grid × 4 markets × 3 seeds; streak K-grid.
- **Benchmarks:** same family as C003 (allows direct momentum-vs-reversion
  comparison on identical P&L basis).
- **Validation:** full battery; DSR/RC; paired C003-vs-C004 comparison.
- **Expected value/cost:** High / M.

### C005 — Calendar and Session Effects (H-SESS-01, H-SESS-02) — STATUS: ready
- **Objective:** Quantify day-of-week / turn-of-month effects on all four
  markets; expected outcome: rejection in modern liquid futures.
- **Matrix:** weekday × market; month × market; turn-of-month × market.
- **Validation:** Welch + bootstrap CIs + multiple-comparison correction.
- **Expected value/cost:** Medium (high process value) / S — calibrates the
  laboratory's false-discovery rate and exercises a non-strategy campaign end
  to end.

### C006 — Volatility State (H-VOL-01, H-VOL-02) — STATUS: ready
- **Objective:** Does EWMA-vol state persist and condition returns; does
  vol-targeting improve the winners of C003/C004?
- **Matrix:** regime definitions × markets; base rules × {flat, vol-scaled}.
- **Expected value/cost:** Medium-High / S-M.

### C007 — Intermarket Lead (H-IMK-01, H-IMK-02) — STATUS: ready
- **Objective:** Do CL/GC/EURUSD lead ES direction or vol? (Unique asset:
  four aligned 10y daily series already in-repo.)
- **Matrix:** lag grid × conditioning grid × 4→ES; correlation regimes × ES vol.
- **Validation:** lag-discipline nullity pools; DSR/RC; crisis vs calm splits.
- **Expected value/cost:** High / M.

### C008 — Daily Fair Value Gaps (H-FVG-01) — STATUS: ready
- **Objective:** Do daily-bar FVGs get filled, and is fill behavior informative?
- **Expected value/cost:** Medium-High / M.

### C009 — Daily Liquidity Sweep Proxy (H-LIQ-01) — STATUS: ready
- **Objective:** Do failed breaks (sweep proxy) reverse?
- **Expected value/cost:** Medium / S-M.

### C010 — Honest ML Benchmark (H-ML-01) — STATUS: proposed (after C002–C007)
- **Objective:** Rigorously establish whether any ML model on the feature
  library beats benchmarks out-of-sample.
- **Expected value/cost:** High / L.

## Acquisition-gated backlog (data required first)

| Priority | Item | Unlocks | Acquisition |
|---|---|---|---|
| 1 | VIX daily OHLC, 10y | H-ALT-01, H-VOL cross-checks | trivial (free data) |
| 2 | Intraday ES (1m/5m, ≥2y, with volume) | H-OR-01, H-VWAP-01, H-TOD-02, H-AMT-02, H-VP-01, H-LIQ-02 | brokerage/API export |
| 3 | Multi-contract daily settles | H-FUT-01/02 | API |
| 4 | ES option chains | H-OPT-01 | API |
| 5 | News/sentiment corpus | H-ALT-02 | commercial |

## Campaign policy

- Execute in backlog order unless a campaign card changes rank (justify in
  `meta_research.md`).
- One campaign at a time; a campaign is closed only by its report + Edge DB
  entry.
- A campaign that changes the catalog's status values must be reflected in
  `catalog.md` at closure.
