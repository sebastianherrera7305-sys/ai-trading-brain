# Edge Database

Persistent, **append-only** knowledge base of every completed campaign and its
outcome. Its purpose is to prevent rediscovering rejected ideas and to make
the laboratory's accumulated knowledge explicit and queryable.

## Rules

- One entry per campaign (and per notable standalone finding), appended at
  campaign closure.
- Entries are never edited after append; corrections add a new entry
  referencing the old one.
- Every entry links to its report and registry location.
- Verdicts: `accepted`, `rejected`, `inconclusive`, `fact` (documented market
  observation, not a tradeable claim).

## Entry schema

```yaml
E-<NNNN>:
  campaign: C0XX (or standalone)
  date: YYYY-MM-DD
  verdict: accepted | rejected | inconclusive | fact
  hypotheses: [H-IDs]
  experiments: (grid summary, run counts, commits)
  statistical_confidence: (DSR/RC p-values, key test statistics)
  robustness: (cost ladder result, per-year/regime stability, seed stability)
  markets: [ES, CL, GC, EURUSD, ...]
  timeframes: [1d, intraday...]
  benchmarks: (which benchmarks, and who won)
  limitations: [...]
  related: [E-IDs, H-IDs, reports]
  verdict_evidence: (the deciding statistic(s))
```

---

## Entries

### E-0001 — Campaign C001: Overnight Gap Continuation
- **campaign:** C001
- **date:** 2026-08-06
- **verdict:** `rejected`
- **hypotheses:** gap continuation on daily ES (catalog successor: H-MS-01)
- **experiments:** 36 cells (4 thr × 3 hold × 3 dir) × 3 seeds @ 0 bps = 108
  runs; 216 cost-ladder runs @ 2.5/5 bps; 16 benchmark runs; 3 meta-validation
  runs. Commits eafdf3d (C1), fe4828c (C2), c407039 (C3).
- **statistical_confidence:** best cell nominally significant pre-adjustment
  (permutation p=0.014–0.027; Welch p>0.09; bootstrap CI includes 0; SPRT
  undecided). **Decisive:** DSR p=0.285; White's Reality Check p≈0.37–0.40
  (3 seeds). Not significant at 5%.
- **robustness:** best cell survives the cost ladder (mean/trade +0.22% →
  +0.17% at 5 bps) but is unstable per-year (2023, 2026 negative); 14% of
  cells nominally significant ≈ chance.
- **markets:** ES. **timeframes:** 1d.
- **benchmarks:** buy & hold (Sharpe 0.79) and EMA(10,100) (0.89) dominated
  the best cell (0.52); best trial indistinguishable from random entries
  (p=0.375).
- **limitations:** single market; continuous front-month; no volume; no
  intraday fill modeling; non-overlapping trades limit sample to 111.
- **related:** report `research_platform/research_studies/gap_continuation/report.md`;
  E-0002, E-0003.
- **verdict_evidence:** DSR p=0.285 and RC p≈0.39 with all benchmark
  comparisons not significant (p ≥ 0.080).

### E-0002 — Fact: ES daily benchmark ladder (C001 window)
- **campaign:** C001 (standalone fact)
- **date:** 2026-08-06
- **verdict:** `fact`
- **experiments:** 16 benchmark runs on `es-f-10y-ohlc-v1`.
- **statistical_confidence:** deterministic runs (single sample each); Sharpe
  figures are descriptive, not edge claims.
- **markets:** ES. **timeframes:** 1d, 2016-08 → 2026-08.
- **findings:** buy & hold Sharpe 0.79, +254%; SMA(5/50,10/100,20/200)
  0.77/0.86/0.77; EMA(5/50,10/100,20/200) 0.80/0.89/0.72, exposures ≈0.7–0.8;
  random entries ≈−0.03…+0.22 by hold length. On this window, simple
  long-biased trend rules dominate; the index rose ~2.5×.
- **limitations:** single 10y window; descriptive.
- **related:** E-0001.
- **verdict_evidence:** registry run metrics.

### E-0003 — Fact: multiple-testing calibration on C001
- **campaign:** C001 (standalone fact / process)
- **date:** 2026-08-06
- **verdict:** `fact`
- **experiments:** 36-cell search grid.
- **statistical_confidence:** 5 of 36 cells (14%) nominally significant at 5%
  by the permutation gate; 13 of 36 (36%) with positive Sharpe.
- **findings:** the unadjusted permutation gate over-rejects in a 36-cell
  search; DSR/RC corrected the verdict. Calibration point for the laboratory:
  single-cell significance is never sufficient for a grid result.
- **related:** E-0001; meta_research.md §2.
- **verdict_evidence:** registry queries.

### E-0004 — Campaign C002: Overnight Gap Fading
- **campaign:** C002
- **date:** 2026-08-06
- **verdict:** `rejected`
- **hypotheses:** gap fading on daily ES (H-MS-01, sign-flip of C001)
- **experiments:** 36 cells (4 thr × 3 hold × 3 dir) × 3 seeds @ 0 bps = 108
  runs; 216 cost-ladder runs @ 2.5/5 bps; 108 delayed-fill runs; 3
  meta-validation runs. Commits 6aeae2c (C1), c4a4199 (C2), eb0667c (matrix).
- **statistical_confidence:** best cell (0.5%, h=3, both) raw statistics strong
  (permutation p=0.0007; Welch p=0.020; bootstrap CI [+0.066%, +0.949%];
  P(win>50%)=0.954; SPRT undecided). **Decisive:** DSR p=0.370; White's Reality
  Check p=0.083–0.101 (3 seeds). Not significant at 5%.
- **robustness:** survives the cost ladder (mean/trade +0.525% → +0.475% at
  5 bps) but the delayed-fill layer loses significance (p=0.061, Sharpe 0.569 →
  0.299) and per-year means are negative in 5 of 11 years; 39% of cells
  nominally significant (within the C001 false-discovery calibration).
- **markets:** ES. **timeframes:** 1d, 2016-08 → 2026-08.
- **benchmarks:** best fade trial not distinguishable from buy & hold (p=0.214),
  random entries (p=0.188), best SMA (p=0.445) or best EMA (p=0.383); mean daily
  return below buy & hold and both crossovers.
- **limitations:** single market; continuous front-month; no volume; same-day
  open fills modeled (next-close only as robustness check); non-overlapping
  trades (114); storage incident in the first execution pass (re-executed
  deterministically, 36/36 + 36/36 series verified identical).
- **related:** E-0001, E-0002, E-0003, NK-0003;
  report `research_platform/research_studies/gap_fading/report.md`.
- **verdict_evidence:** DSR p=0.370 and RC p≈0.083–0.101 with all benchmark and
  paired C001 comparisons not significant (p ≥ 0.188).

---

## Queries the Edge DB supports

- What have we rejected on ES daily? → E-0001 (gap continuation), E-0004 (gap fading).
- Which benchmarks dominate on ES daily? → E-0002.
- What is our measured false-discovery calibration? → E-0003.
- Is the gap family on ES daily exhausted? → yes in both signs: E-0001 + E-0004 (NK-0003).
- (Future) Which domains are exhausted vs open → per-domain scan of verdicts.
