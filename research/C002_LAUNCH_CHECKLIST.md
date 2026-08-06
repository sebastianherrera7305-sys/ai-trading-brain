# C002 LAUNCH CHECKLIST — Gap Fading (H-MS-01)

Gate document: every box below must be ticked (with evidence) before the
first C002 experiment is executed. Last reviewed: 2026-08-06
(RESEARCH_READINESS_REPORT.md, blocking items B1–B3).

---

## Gate A — Hypothesis & card (catalog/campaigns)

- [ ] C002 card states an explicit **objective** (research question)
- [ ] C002 card references the canonical hypothesis **H-MS-01** (catalog)
- [ ] **B1:** C002 card states explicit **expected decision criteria**, e.g.:
      accept iff DSR p<0.05 AND best cell beats the C001 best cell on
      identical cost basis AND ≥1 benchmark (buy & hold or EMA(10,100));
      otherwise reject → E-00xx with verdict_evidence
- [ ] Hypothesis's features (F-GAP, F-GAP-COMP) exist or are marked verified
      (C6 dangling-feature check clean for H-MS-01)
- [ ] Dataset requirement stated (es-f-10y-ohlc-v1, Grade A)

## Gate B — Data & configuration

- [ ] `es-f-10y-ohlc-v1` registered (id `8d2a7d6b…9a84`), Grade A
- [ ] Dataset checksum verified against `data/es_f_10y_ohlc_v1.npz`
      (`b3159e9d…24276`) — no integrity failures
- [ ] Experiment matrix generated: 36 cells (4 thr × 3 hold × 3 dir, sign
      flipped) × seeds {0,1,2} @ 0 bps + cost ladder @ 2.5/5 bps (mirror C001)
- [ ] Matrix configs committed to git before any run (no config drift)
- [ ] `gap_meta` configuration targets the C002 trial matrix (fresh assembly,
      not the C001 matrix)

## Gate C — Code & reproducibility discipline

- [ ] Gap-fading module implemented as C001 sign flip (no new logic), committed
- [ ] Module imports cleanly outside the framework cwd
      (`python3 -c "import <module>"` from the study dir)
- [ ] **B2:** every experiment's `hypothesis` field = `H-MS-01` (canonical ID,
      not descriptive text)
- [ ] `seed` field set per experiment: exactly {0,1,2} across the grid
- [ ] **B3:** `git_dirty = False` for every experiment at creation (runner
      enforces clean tree; zero dirty-origin runs)
- [ ] `git_commit`, `config_hash`, `module_checksum` populated on all runs
- [ ] Benchmarks configured on the same P&L basis as the strategy
      (identical cost handling, daily bars, same window)

## Gate D — Statistical pipeline (identical to C001)

- [ ] Permutation nullity gate **vs signed pool** (directional rule) — the
      C001 pool-alignment lesson applied
- [ ] Welch t vs construction-matched pool (all possible trades)
- [ ] Block bootstrap CI on mean/trade
- [ ] Bayesian win-rate + Wald SPRT
- [ ] **DSR + White's Reality Check over the 36-cell grid** (mandatory for
      any searched grid — NK-0002)
- [ ] Test parameters recorded (n_permutations, iterations, CI method) —
      N3; if the platform cannot persist them, they are stated verbatim in
      the report appendix
- [ ] All statistics via `quant_research` frozen v0.3.0 (version stated in
      the report)

## Gate E — Benchmarks & comparisons

- [ ] buy & hold (Sharpe 0.79 baseline on C001 window)
- [ ] EMA(10,100) (0.89 baseline)
- [ ] random entries, seed 0 (seed-0 convention — avoids the seed-2
      lucky-draw distortion documented in the graph audit)
- [ ] **C001 best cell** (0.52) — direct paired comparison
- [ ] Benchmark modules pinned in git; benchmark runs completed, status
      `completed`

## Gate F — Meta-validation & robustness

- [ ] C001 vs C002 best-cell paired comparison (meta stage)
- [ ] Cost ladder report (0 / 2.5 / 5 bps) — Sharpe + mean/trade at each cost
- [ ] Per-year breakdown; vol-regime breakdown (C001's implicit vol-timing
      lesson)
- [ ] Seed stability across the 3 seeds (ranking, not just point estimates)
- [ ] 111-trade sample-size lesson from C001 acknowledged (non-overlapping
      trades; if the fade side has fewer events, say so)

## Gate G — Decision & knowledge recording

- [ ] **B1** criteria applied; verdict recorded as E-00xx in edge_database.md
      (append-only; verdict + verdict_evidence + limitations)
- [ ] Catalog status for H-MS-01 updated at closure
      (`rejected` / `accepted` / `in-progress` → per outcome)
- [ ] Negative knowledge: if rejected, NK entry for gap fading with
      reinvestigation triggers (closes or documents the gap family on ES
      daily); if accepted, H-MS-01's acceptance record notes the same
- [ ] Campaign report `research_platform/research_studies/gap_fading/report.md`
      (publication-quality, per README §6) with all statistics verbatim
- [ ] Graph regenerated (`python3 research/graph.py`) — no new fatal checks;
      C17-style verification: C002 closed → E-00xx present + catalog updated
- [ ] Dashboard regenerated (`python3 research/generate_dashboard.py`)
- [ ] Reproductions: every headline run reproduced at its recorded commit
      (dirty-tree refusal = fail this gate)
- [ ] meta_research.md log entry appended (what C002 changed about the
      laboratory's knowledge and process)
- [ ] All of the above committed to git in a single closure commit

---

**Pass condition:** all boxes ticked with evidence. C002 must NOT start
until Gates A–C pass; D–F are campaign-internal gates; G is the closure gate
before the next campaign opens.
