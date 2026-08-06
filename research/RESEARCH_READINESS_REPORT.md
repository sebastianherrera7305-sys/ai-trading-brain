# RESEARCH READINESS REPORT — Alpha Research Laboratory

Status: **READY WITH CONDITIONS**. Date: 2026-08-06.

Scope: final scientific readiness review before Campaign C002 (Gap Fading).
Verification-only — no experiments were executed, no architecture was
modified, no registries were added. Every claim below is backed by a check of
the canonical documents, the store, or the generated knowledge graph
(`graph_snapshot.json`, verified this audit).

---

## 0. Executive summary

| Area | Score | Verdict |
|---|---|---|
| 1. Hypothesis Catalog Integrity | 95/100 | PASS |
| 2. Campaign Readiness | 68/100 | PASS WITH CONDITIONS |
| 3. Evidence Model | 95/100 | PASS |
| 4. Reproducibility Readiness | 72/100 | PASS WITH CONDITIONS |
| 5. Knowledge Accumulation | 65/100 | PASS WITH CONDITIONS |
| **Overall** | **79/100** | **READY WITH CONDITIONS** |

The laboratory can accumulate research knowledge reliably over many future
campaigns. **Three blocking items** (B1–B3, §3) must pass before C002
executes; they are convention/documentation items costing ≤ 1 day total, not
architecture changes. All other gaps (§4) are non-blocking and scheduled.

---

## 1. Hypothesis Catalog Integrity — PASS (95/100)

Verified against `catalog.md` (30 hypotheses, 17 domains) + graph C1/C2/C11.

| Requirement | Result | Evidence |
|---|---|---|
| Canonical IDs | PASS — all 30 have `H-XXX-NN` pattern | 30/30 rows parsed by graph (C1 unique) |
| Domain assignment | PASS — every hypothesis under exactly one domain section | 17 domains, no cross-section entries |
| Duplicate concepts | PASS — no exact duplicates. 5 *adjacent* concept pairs flagged (below) | structural scan; no scientific judgment |
| Proposed without campaign explicitly marked | PASS — every unassigned hypothesis carries status `proposed` (H-ALT-02, H-ML-02) or `blocked-data` (10 others) | statuses in catalog; graph C11 lists 13 unassigned, all marked |
| Historical provenance preserved | PASS — the pre-catalog C001 hypothesis (gap continuation) survives in: E-0001, NK-0001 (full parameter space, reinvestigation triggers), C001 campaign card, knowledge_graph.md §2 (H-C001), and H-MS-01's motivation | cross-referenced; nothing deleted |

Adjacent concepts (not duplicates; both kept — note for future meta-analysis):
- H-TF-01 (Donchian break) ↔ H-LIQ-01 (failed break) — shared F-DON, inverse event.
- H-MS-02 (daily range position) ↔ H-OR-01 (intraday OR breakout) — same family, different timeframe.
- H-VWAP-01 ↔ H-VWAP-02 — same anchor, intraday vs daily.
- H-IMK-02 (correlation regime → ES vol) ↔ H-VOL-01 (own-vol state) — regime conditioning, different inputs.
- H-TOD-01 (gap/intraday decomposition) ↔ H-MS-01 — deliberate extension of the closed gap family.

Catalog statuses: 12 `ready`, 7 `proposed`, 11 `blocked-data`. The catalog
status vocabulary (`proposed/ready/in-progress/rejected/accepted/blocked-data`)
supports lifecycle tracking; no `rejected` entries exist yet (only pre-catalog
C001, preserved elsewhere).

## 2. Campaign Readiness — PASS WITH CONDITIONS (68/100)

Verified against `campaigns.md` card template + all cards + `roadmap.md`.

The card template specifies: Status, Objective, Hypotheses, Matrix,
Benchmarks, Validation, Robustness, Info value/cost, Report. **Missing from
the template: Datasets, Features, Markets, Expected decision criteria.**

| Campaign | Question | Hypothesis | Datasets | Features | Benchmarks | Validation | Decision criteria |
|---|---|---|---|---|---|---|---|
| C001 (closed) | ✓ | ✓ (pre-catalog) | ✓ | ✓ | ✓ | ✓ | ✓ (verdict + verdict_evidence) |
| **C002** | ✓ | ✓ H-MS-01 | via H-MS-01 (A) | via H-MS-01 | ✓ incl. C001 best cell | ✓ battery + DSR/RC + paired meta | **MISSING** (only "expected entry E-00xx") |
| C003 | ✓ | ✓ | ✓ (register CL/GC/EURUSD) | via H-TF-01/02 | ✓ | ✓ | MISSING |
| C004 | ✓ | ✓ | implicit | via H-MR-01/02 | ✓ | ✓ | MISSING |
| C005 | ✓ | ✓ | implicit | via H-SESS-01/02 | via H-SESS-01 | ✓ | MISSING |
| C006 | ✓ | ✓ | implicit | via H-VOL-01/02 | via H-VOL-01 | via hypothesis | MISSING |
| C007 | ✓ | ✓ | implicit | via H-IMK-01/02 | ✓ | ✓ | MISSING |
| C008 | ✓ | ✓ | implicit | via H-FVG-01 | **via hypothesis** | **via hypothesis** | MISSING |
| C009 | ✓ | ✓ | implicit | via H-LIQ-01 | **via hypothesis** | **via hypothesis** | MISSING |
| C010 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | MISSING |
| C011 | in roadmap only (rank 5) — **no registry card yet** | | | | | | |

Findings:
- No campaign card states explicit accept/reject decision criteria. C001's
  verdict discipline (DSR p<0.05 after multiplicity correction, beating
  benchmarks on identical basis) exists in edge_database + negative knowledge,
  but is not codified per card. **B1.**
- C002 is the most complete card (reuses C001 battery and matrix; benchmarks
  include the C001 best cell for direct comparison). Only decision criteria
  missing.
- C008/C009 cards are sparse (matrix/validation/benchmarks only via hypothesis
  reference). C011 has no registry card. Non-blocking (N1, N2).

## 3. Evidence Model — PASS (95/100)

Verified end-to-end on the only closed campaign (C001); chain is structurally
complete for future campaigns.

```
Hypothesis (catalog H-ID)
  → Campaign (C0XX card; BELONGS_TO edge in graph)
    → Experiment (store record: hypothesis, params, seed, git_commit, module_checksum)
      → Run (store record: env, metrics, tests)
        → Statistical Tests (run.tests: name, statistic, p_value, conclusion)
          → Decision (campaign report verdict + catalog status change at closure)
            → Edge Database Entry (E-0xxx, append-only, verdict + verdict_evidence)
```

| Requirement | Result | Evidence |
|---|---|---|
| Every result representable in the chain | PASS | C001 fully represented: 354 experiments → 357 runs → 8+ tests/run → E-0001/E-0002/E-0003 + NK-0001/NK-0002 |
| Rejected hypotheses preserved as knowledge | PASS | NK-0001 (gap continuation, full parameter space + reinvestigation triggers), NK-0002 (methodological); append-only rules; catalog policy "hypothesis only enters an experiment once specified" |
| Failed experiments preserved | PASS | 6 failed experiments retained with `failure_reason` (3 gap_strategy bring-up: import/broadcast/datetime; 3 gap_meta import) |
| Campaign closure requires report + Edge DB entry | PASS | campaign policy; C001 report reachable (graph PRODUCES edge, C4/C14) |
| Graph guarantees the chain | PASS WITH GAP | C9/C14 exist; **no check yet: "closed campaign → ≥1 Edge DB entry + catalog status update"** (recommend C17 at next graph iteration, N13) |
| Hypothesis field convention | GAP | `experiment.hypothesis` currently holds pre-catalog descriptive text ("Overnight gaps in ES daily futures tend to continue…", 2 variants); C002 experiments must carry **H-MS-01** (**B2**) |

## 4. Reproducibility Readiness — PASS WITH CONDITIONS (72/100)

Verified via store records + data files + module sources.

| Aspect | Result | Evidence |
|---|---|---|
| Dataset availability | PASS | All 10 files in `data/` present. **Checksums re-verified this audit**: `es_f_10y_ohlc_v1.npz` = `b3159e9d…24276` ✓ matches DS-001; `es_gap_trial_matrix_v1.npz` = `519cb85d…1a00520` ✓ matches DS-002 |
| Experiment config persistence | PASS | params dict + `config_hash` + `module_checksum` per experiment; per-cell JSON configs in git (38 config files in study dir) |
| Commit discipline | PASS WITH GAP | `git_commit`/`git_dirty` per experiment; 346/354 clean. **8 origin runs recorded dirty=True** (pre-discipline); reproductions already refuse dirty trees (**B3**) |
| Random seed handling | PASS | First-class `seed` field: {0:126, 1:114, 2:114}; random_entries seeds 0–2 × 3 holds; benchmark seed-0 convention (documented in graph, avoids the seed-2 lucky-draw distortion) |
| Benchmark reproducibility | PASS | 4 benchmark modules on disk (`buy_hold.py`, `random_entries.py`, `sma_crossover.py`, `ema_crossover.py`) + configs; same-P&L-basis rule in card template |
| Statistical test reproducibility | PASS WITH GAP | Tests from frozen `quant_research` v0.3.0; but **test parameters (n_permutations, iterations, CI method) not persisted in run.tests** (only name/statistic/p_value/conclusion) and **quant_research version not in run env** (N3, N4) |
| Reproduction attempts | GAP | 7 attempts / 354 experiments (1.1%); 3 matched, 4 unverifiable (3 wrong `--cwd`, 1 dirty tree) — root causes documented and fixed in meta log (N7) |

## 5. Knowledge Accumulation — PASS WITH CONDITIONS (65/100)

After 100 campaigns, the laboratory can answer the required questions today
with one caveat (market dimension):

| Question after 100 campaigns | Answerable? | How |
|---|---|---|
| Which ideas were tested? | YES | catalog statuses + campaign registry + graph TESTED_BY (354 edges) |
| Which failed repeatedly? | YES | negative_knowledge (NK-0001/0002) + edge verdicts + graph REJECTS/SUPPORTS |
| Which features are valuable? | YES (qualitative) | features.md statuses + VALIDATED_IN (12) + campaign deliverables table (roadmap "what each campaign must deliver") |
| Which markets respond? | PARTIAL | edge DB schema has `markets`; datasets have market; but **hypotheses/campaigns have no markets field** (N8) |
| Which directions should stop? | YES | edge verdicts + NK reinvestigation triggers + roadmap skip policy ("a campaign may be skipped only if a newer result eliminates its question") |
| Which areas deserve more investigation? | YES | roadmap ranking (re-ranked at closure/quarterly) + meta_learning standing questions (P1–P8) |

Missing metadata for long-term learning (all non-blocking, N8–N12):
- **Markets field on hypotheses/campaign cards** (market dimension currently
  implied by datasets only; the only gap that limits a full per-market
  knowledge scan).
- **Feature effect metadata** — feature_role (signal/filter/context) and
  observed effect per campaign are not recorded; feature-value questions are
  qualitative only. H-ML-02 will add mechanical feature-importance later.
- **H-ID in experiment records** (B2 — blocks clean "which hypotheses were
  tested" joins at 100-campaign scale).
- **Decision criteria per campaign** (B1) — without explicit accept/reject
  rules, verdict consistency degrades with campaign count.
- **Window/regime metadata per experiment** — implicit via dataset; fine at
  current scale.

---

## 3. Blocking issues (must pass before C002 execution)

| ID | Issue | Evidence | Fix (effort) |
|---|---|---|---|
| **B1** | C002 card lacks explicit expected decision criteria (accept/reject rule) | campaigns.md C002 card: "expected entry E-00xx (rejected or accepted)" only | Codify on the card: accept iff DSR p<0.05 AND best cell beats C001 best cell on identical cost basis AND ≥1 benchmark (buy & hold or EMA(10,100)); otherwise reject. Any other rule stated in the report. (S) |
| **B2** | `experiment.hypothesis` holds descriptive text, not canonical H-IDs | store probe: 2 pre-catalog variants; 0 H-IDs | C002 experiments record hypothesis = `H-MS-01` (ID convention; description optional in objective). (S) |
| **B3** | Commit-before-run not enforced at origin (8/354 origin experiments dirty) | store probe: git_dirty True × 8 | Enforce clean-tree refusal in the runner at execution (platform maintenance release, outside this review's scope). C002 runs only on clean trees. (M, scheduled) |

## 4. Non-blocking issues

| ID | Issue | Scheduled with |
|---|---|---|
| N1 | C008/C009 cards sparse (matrix/validation/benchmarks via hypothesis only) | before C008/C009 launch |
| N2 | C011 in roadmap (rank 5) but no registry card | when it enters the ranked backlog |
| N3 | Test parameters (n_permutations, iterations, CI) not persisted in run.tests | next platform release |
| N4 | quant_research version not recorded in run env (frozen v0.3.0 declared in docs) | next platform release |
| N5 | Raw CSVs (ES/CL/GC/EURUSD 10y) lack registered checksums (git-tracked; registered checksums cover the npz blobs — verified) | dataset registration wave (F5) |
| N6 | CL/GC/EURUSD 10y registration pending (Grade B); DS-005 EURUSD weekend-bar preprocessing required before C007 | C003 (registration), C007 (preprocessing) |
| N7 | Reproduction coverage 1.1% (3 matched / 7 attempts) — raise for headline/accepted results | every campaign closure, starting C002 |
| N8 | No markets field on hypotheses/campaign cards | next campaign card review |
| N9 | No feature-effect metadata (role/effect size) | H-ML-02 / quarterly review |
| N10 | 6 bring-up failed experiments (documented, reasons recorded — acceptable) | none |
| N11 | `gap_description` run-test has no asset id (descriptive, not statistical) | map or document at next asset review |
| N12 | F-TREND (H-TF-01/02) and F-IMK-CORR (H-IMK-02) dangling (graph C6 fail) | before C003/C007: define F-TREND; F-IMK-CORR likely = F-CORR |
| N13 | No graph check "closed campaign → ≥1 Edge DB entry + catalog status update" (future C17) | next graph iteration |

## 5. Recommended fixes (priority order)

1. **(B1)** Add "Expected decision criteria" to the campaign card template; fill C002. — S, before C002.
2. **(B2)** Store convention: experiment hypothesis field = canonical H-ID for all new experiments. — S, before C002.
3. **(B3)** Runner refuses dirty trees at execution (platform release). — M, scheduled.
4. **(N12)** Resolve F-TREND definition + F-IMK-CORR naming (graph C6 → clean). — S, before C003/C007.
5. **(N6/F5)** Register CL/GC/EURUSD 10y (mirror DS-001 pipeline, incl. raw-CSV checksums); document EURUSD weekend preprocessing. — M, before C003.
6. **(N7)** Reproduce every C002 run at launch (full-sweep reproducibility pass). — S–M, with C002.
7. **(N3/N4)** Persist test parameters + quant_research version in run records. — M, next platform release.
8. **(N8/N9)** Add markets field to hypothesis/campaign cards; log feature effects in meta_learning. — M, next card review.
9. **(N1/N2)** Complete C008/C009 cards; add C011 card. — S, before those launches.
10. **(N13)** Add graph check C17. — S, next graph iteration.

## 6. Verification method (this audit)

- Documents read in full: catalog.md, campaigns.md, roadmap.md,
  dataset_quality_registry.md, edge_database.md, negative_knowledge.md,
  knowledge_graph.md, graph_report.md, meta_research.md.
- Store probes (read-only): experiment/module/status/seed/git distributions,
  params completeness, run env + tests structure, dataset metadata,
  reproduction records, failure reasons.
- Checksum verification: DS-001 and DS-002 registered checksums re-computed
  against `data/` (both match).
- No experiments executed; no files modified except the two deliverables and
  the meta-research log; no registries or architecture changed.
