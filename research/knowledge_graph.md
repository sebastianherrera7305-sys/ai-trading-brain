# Laboratory Knowledge Graph — Specification and Relationship Registry

Connects every research asset into one coherent knowledge system. The graph
does not replace the registries — it is the **semantic layer** on top of them:
entities are the registry documents and store records; relationships are
declared in this file or derived automatically.

## 1. Entities (node types)

Counts verified by `research/graph.py` (2026-08-06, snapshot `graph_snapshot.json`).

| Type | ID prefix | Source of truth | Count |
|---|---|---|---|
| dataset | DS-### | dataset_quality_registry.md + store | 6 (9 incl. ranges; 2 registered) |
| feature | F-* | feature_registry.md / features.md | 48 (12 verified, 3 library-tested) |
| hypothesis | H-* | catalog.md (+ H-C001, pre-catalog) | 31 |
| campaign | C### | campaigns.md / roadmap.md | 11 (1 completed) |
| experiment | uuid | research store (research.db) | 354 |
| run | uuid:run# | research store | 357 |
| test | AS-ST-### | asset_registry.md | 12 |
| benchmark | AS-BM-### | asset_registry.md | 4 |
| asset (other classes) | AS-(IND/FLT/RP/TP/VP)-### | asset_registry.md | 33 |
| report | path | campaign directories | 1 |
| edge | E-#### | edge_database.md | 3 |
| negative | NK-#### | negative_knowledge.md | 2 |

## 2. Relationships (edge types)

Provenance: `declared` = written in this registry or the source documents;
`auto` = derived from the research store; `computed` = derived by the graph
tool (comparisons over stored metrics).

| Type | From → To | Cardinality | Provenance | Meaning |
|---|---|---|---|---|
| USED_BY | dataset → campaign | n:m | auto (store) + declared | campaign executed on dataset |
| SUPPORTS | dataset → feature | n:m | declared | dataset provides the feature's inputs |
| USED_BY | feature → hypothesis | n:m | auto (catalog) | hypothesis consumes feature |
| VALIDATED_IN | feature → campaign | n:1 | auto (registry) | campaign verified the feature |
| BELONGS_TO | hypothesis → campaign | n:1 | declared | campaign card / roadmap |
| TESTED_BY | hypothesis → experiment | 1:n | auto (module map) | experiments executing the hypothesis |
| USES | experiment → dataset | 1:1 | auto (store) | experiment's registered dataset |
| EVALUATED_BY | experiment → test | 1:n | auto (run.tests) | statistical tests applied to the run |
| RECORDS | experiment → run | 1:n | auto (store) | run instances |
| BEATS | benchmark → experiment | 1:n | computed | benchmark Sharpe > cell Sharpe |
| PRODUCES | campaign → report | 1:1 | declared + file check | final report |
| UPDATES | campaign → edge | 1:n | auto (edge DB) | knowledge base entry |
| UPDATES | campaign → negative | 1:n | declared | negative knowledge entry |
| REJECTS | test → hypothesis | 1:1 | declared | decisive rejection evidence |
| RESULTS_IN | hypothesis → edge | 1:n | declared | outcome entry for the hypothesis |
| SUCCEEDS | hypothesis → hypothesis | 1:1 | declared | catalog successor of a pre-catalog hypothesis (H-C001 → H-MS-01) |

## 3. Relationship registry (declared instances)

Document-level relations not derivable from the store. Store-derived edges
(dataset/experiment/run/test/BEATS) are materialized automatically by
`research/graph.py` into `research/graph_snapshot.json`.

### 3.1 Dataset → Campaign (declared additions)

| Dataset | Campaigns | Note |
|---|---|---|
| DS-001 (es-f-10y-ohlc-v1) | C001 (auto), C002, C005, C006, C008, C009, C011 | all daily ES campaigns |
| DS-002 (es-gap-trial-matrix-v1) | C001 (auto) | derived asset |
| DS-003 (CL) | C003, C004, C007 | needs registration (Grade B) |
| DS-004 (GC) | C003, C004, C007 | needs registration (Grade B) |
| DS-005 (EURUSD) | C003, C004, C007 | needs preprocessing (Grade C, weekend bars) |

### 3.2 Dataset → Feature (SUPPORTS)

| Dataset | Features |
|---|---|
| DS-001 | F-RET, F-MA, F-EMA, F-RVOL, F-ZSCORE, F-GAP, F-GAP-COMP, F-CAL, F-DON, F-MOM, F-RANGE, F-ATR, F-POSITION, F-STREAK, F-SWEEP, F-FVG, F-POOL, F-REGIME, F-TRIAL |
| DS-002 | F-TRIAL |
| DS-003, DS-004 | F-ALIGN, F-IMK-LAG, F-MOM (with DS-001) |
| DS-005 | F-ALIGN, F-IMK-LAG (after weekend filtering) |
| (future intraday) | F-OR, F-IB, F-VWAP, F-VPROF, F-SWEEP-I, F-SESSION, F-DELTA, F-IMBALANCE |
| (future VIX) | F-EXTVOL |

### 3.3 Hypothesis → Campaign (BELONGS_TO) — declared

| Hypothesis | Campaign |
|---|---|
| H-C001 (pre-catalog gap continuation) | C001 |
| H-MS-01 | C002 |
| H-TF-01, H-TF-02 | C003 |
| H-MR-01, H-MR-02 | C004 |
| H-SESS-01, H-SESS-02 | C005 |
| H-VOL-01, H-VOL-02 | C006 |
| H-IMK-01, H-IMK-02 | C007 |
| H-FVG-01 | C008 |
| H-LIQ-01 | C009 |
| H-ML-01 | C010 |
| H-MS-02, H-AMT-01, H-TOD-01 | C011 |

(Others: proposed/unassigned — H-LIQ-02, H-AMT-02, H-TOD-02, H-VP-01,
H-FUT-01/02, H-OPT-01, H-ALT-01/02, H-ML-02.)

### 3.4 Campaign → Negative knowledge (UPDATES)

| Campaign | Entries |
|---|---|
| C001 | NK-0001, NK-0002 |

### 3.5 Test → Hypothesis (REJECTS)

| Test | Hypothesis | Evidence |
|---|---|---|
| AS-ST-004 (deflated_sharpe_ratio) | H-C001 | p = 0.285 |
| AS-ST-005 (reality_check_p_value) | H-C001 | p ≈ 0.37–0.40 |

### 3.6 Hypothesis → Edge (RESULTS_IN) / succession

| Edge | Hypothesis | Note |
|---|---|---|
| E-0001 | H-C001 | verdict: rejected |
| E-0002 | — | benchmark facts (no hypothesis) |
| E-0003 | — | process fact (no hypothesis) |
| H-C001 → H-MS-01 | — | SUCCEEDS (catalog successor, opposite sign) |

## 4. Automatic consistency checks (run by `research/graph.py`)

| ID | Check | Fatal |
|---|---|---|
| C1 | Catalog hypothesis IDs are unique | yes |
| C2 | Every hypothesis referenced by a campaign exists | yes |
| C3 | Every edge entry references a real campaign | yes |
| C4 | Every completed campaign has its report file on disk | yes |
| C5 | Every experiment's dataset_id resolves to a registered dataset | yes |
| C6 | Every feature used by a hypothesis exists (registry or roadmap) | yes |
| C7 | Feature nodes have ≥ 1 relationship (no orphans; planned exempt) | no |
| C8 | Declared grid vs store: 36 strategy cells, benchmark modules, 3 meta runs present | yes |
| C9 | Negative-knowledge entries link to an edge entry or campaign | yes |
| C10 | No dangling benchmark references in the catalog | no |
| C11 | Every hypothesis belongs to exactly one campaign (unassigned reported) | no |
| C12 | Every campaign references datasets that exist in the Dataset Registry | yes |
| C13 | Every dataset used by experiments exists in the Dataset Registry | yes |
| C14 | Every report file belongs to a campaign (and vice versa) | yes |
| C15 | No orphaned research assets (datasets/features/assets with no relationships) | no |
| C16 | No undocumented data files in `data/` (every file mapped to a DS-### entry) | yes |

The graph tool materializes all checks into `research/graph_report.md`;
a failing fatal check must be fixed before any campaign result is trusted.
Validation failures never stop the laboratory: they are reported clearly
(fail/warn) and listed in `graph_report.md` §6 and the freeze audit.

## 5. Queries (implemented in `research/graph.py`)

| ID | Question | Answer source |
|---|---|---|
| Q1 | Which features consistently survive validation? | VALIDATED_IN ∩ no REJECTS |
| Q2 | Which datasets generate the highest research value? | experiment USES edges per dataset + grade |
| Q3 | Which benchmarks eliminate the most hypotheses? | BEATS counts per benchmark |
| Q4 | Which research domains are underexplored? | hypothesis status per catalog domain |
| Q5 | Which rejected hypotheses share characteristics? | cluster NK entries by market/family/features |
| Q6 | Which campaigns produced reusable assets? | asset rows grouped by campaign |
| Q7 | Which tests reject the most? | per-test rejection counts (cells / grids) |
| Q8 | Graph health (nodes, edges, orphans, checks) | graph totals |

## 6. Integration with the dashboard

`research/generate_dashboard.py` imports the graph module and adds:
- graph node/edge totals and orphan count (dashboard §5),
- consistency-check pass rate (dashboard §8 — "Knowledge graph"),
- headline edges (best dataset, best benchmark eliminator) — dashboard §6.

The dashboard therefore reports *knowledge-system health*, not just counts.

## 7. Maintenance rules

1. `python3 research/graph.py` regenerates `graph_snapshot.json` +
   `graph_report.md`; run it after every store change or document change,
   and always before committing a campaign closure.
2. New declared relations (3.x) are appended here at the time they become
   true — never retroactively redefined.
3. `graph_report.md` and `graph_snapshot.json` are generated artifacts
   (like the dashboard) and are committed as snapshots.
4. A new entity type or edge type requires this spec update first.
