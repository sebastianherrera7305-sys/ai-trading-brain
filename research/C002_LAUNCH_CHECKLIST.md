# C002 LAUNCH CHECKLIST — Gap Fading (H-MS-01)

Gate document: every box below must pass (with evidence) before the first
C002 experiment is executed. Last reviewed: 2026-08-06. Governed by
campaigns.md card template (decision categories) and the readiness report
(research/RESEARCH_READINESS_REPORT.md, blocking items B1–B3, all resolved).

---

## Gate A — Hypothesis registered

- [ ] H-MS-01 exists in `research/catalog.md` with a canonical ID (pattern
      `H-XXX-NN`), domain (MS), description, datasets, features, methodology,
      benchmarks, effort, and status `ready (Campaign 002)`
- [ ] C002 card in `research/campaigns.md` references H-MS-01 by ID
- [ ] Every C002 experiment config carries `"hypothesis": "H-MS-01"`
      (config validation rejects missing/non-canonical IDs — B2 enforced)
- [ ] The graph maps H-MS-01 → C002 (BELONGS_TO) after regeneration

## Gate B — Dataset verified

- [ ] `es-f-10y-ohlc-v1` registered (id `8d2a7d6b…9a84`), Grade A in
      `dataset_quality_registry.md`
- [ ] Dataset checksum re-verified against `data/es_f_10y_ohlc_v1.npz`
      (`b3159e9d…24276`) — must match (verified 2026-08-06)
- [ ] 2,513 bars, 2016-08-04 → 2026-08-04, 0 missing, no duplicates
- [ ] Dataset integrity check passes at run time (`verify_dataset` — the
      runner refuses runs on tampered blobs)

## Gate C — Features verified

- [ ] F-GAP exists in `feature_registry.md` and is marked verified/available
- [ ] F-GAP-COMP exists in `feature_registry.md` and is marked
      verified/available
- [ ] No dangling feature references for H-MS-01 (graph check C6 clean for
      this hypothesis — F-TREND/F-IMK-CORR are unrelated to C002)
- [ ] Feature implementations present in the study module (sign flip reuses
      C001's F-GAP computation verbatim; F-GAP-COMP verified in C001)

## Gate D — Benchmarks defined

- [ ] Benchmark set defined on the C002 card and in this checklist:
      buy & hold, EMA(10,100), random entries (seed 0), C001 best cell
- [ ] All benchmarks on the **same P&L basis** as the strategy (same daily
      bars, window, cost handling) — C001 module reuse guarantees this
- [ ] Benchmark modules pinned in git (`buy_hold.py`, `random_entries.py`,
      `ema_crossover.py`, `sma_crossover.py` + configs)
- [ ] Benchmark configs carry `"hypothesis": "H-C001"` (pre-catalog baseline
      ID) — they are C001 artifacts reused for comparison
- [ ] Random-entries seed-0 convention applied (avoids the seed-2
      lucky-draw distortion documented in the graph audit)

## Gate E — Statistical methodology defined

- [ ] Battery identical to C001, stated on the card:
      permutation nullity gate **vs signed pool** (C001 pool-alignment
      lesson), Welch t vs construction-matched pool, block bootstrap CI,
      Bayesian win-rate, Wald SPRT
- [ ] **DSR + White's Reality Check over the 36-cell grid** (mandatory for
      any searched grid — NK-0002)
- [ ] Paired C001-vs-C002 best-cell meta-comparison specified
- [ ] Test parameters (n_permutations, iterations, CI method) recorded — in
      the report appendix if the platform cannot persist them (N3)
- [ ] All statistics via `quant_research` v0.3.0 (frozen); version recorded
      per run in the run environment (B3)

## Gate F — Reproducibility requirements passed

- [ ] **Git tree clean** before every run batch (`git status --porcelain`
      empty); any run on a dirty tree is marked **UNVERIFIABLE_REPRODUCTION**
      and cannot support acceptance (B3, enforced by the runner)
- [ ] Commit hash recorded per experiment (`git_commit` populated)
- [ ] `quant_research` version recorded per run (env
      `quant_research_version`)
- [ ] Module checksum recorded (`module_checksum` populated; the runner
      refuses to execute under changed code)
- [ ] Configuration hash recorded (`config_hash` populated from the config
      document)
- [ ] Random seed recorded per experiment (`seed` field; {0,1,2} across the
      grid)
- [ ] Experiment `hypothesis` field = `H-MS-01` (B2 — validated at creation)
- [ ] Every headline run reproduced at its recorded commit (dirty-tree
      refusal or mismatch = fail this gate)
- [ ] Platform test suite passes (`python3 -m pytest research_platform/tests`)

## Gate G — Decision criteria defined

- [ ] Success criteria (ACCEPTED): DSR p < 0.05 AND best cell beats C001 best
      cell (Sharpe 0.52) on identical cost basis AND ≥ 1 benchmark (buy &
      hold 0.79 or EMA(10,100) 0.89) at 0 bps
- [ ] Rejection criteria (REJECTED): DSR p ≥ 0.05 OR best cell ≤ C001 best
      cell OR all benchmark comparisons not significant
- [ ] INCONCLUSIVE rule: fade side too few events / SPRT undecided
- [ ] REQUIRES_MORE_DATA rule: fade event count inadequate on ES daily →
      multi-market follow-up; edge verdict `inconclusive` + limitation
- [ ] Final decision recorded as E-00xx in `edge_database.md` (append-only,
      verdict + verdict_evidence + limitations)
- [ ] Catalog status for H-MS-01 updated at closure
- [ ] Negative knowledge entry appended if REJECTED (gap family closure on
      ES daily); reinvestigation triggers documented
- [ ] Campaign report (publication-quality, README §6) with statistics
      verbatim; graph + dashboard regenerated; single closure commit

---

**Pass condition:** all boxes ticked with evidence. Gates A–F must pass
before execution starts; Gate G is the closure gate. C002 must NOT start
until A–F are green.
