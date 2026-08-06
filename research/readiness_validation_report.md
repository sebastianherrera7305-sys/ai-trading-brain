# READINESS VALIDATION REPORT — Alpha Research Laboratory

Status: **C002_READY = PASS (one precondition)**. Date: 2026-08-06.

Validation pass only: no experiments executed, no architecture changes, no
new registries, no historical records modified. Every claim below was
verified live this session (evidence inline).

---

## B1 — Campaign Decision Criteria: **PASS**

Requirement — a campaign definition must contain: hypothesis ID, research
question, success criteria, rejection criteria, statistical methodology,
benchmark policy, final decision categories.

| Required field | Template (`campaigns.md`) | C002 card |
|---|---|---|
| Hypothesis ID | ✓ (`Hypothesis:` H-IDs, canonical only) | ✓ H-MS-01 |
| Research question | ✓ (`Research question:`) | ✓ "Does the opposite sign of the C001 rule carry the edge…" |
| Success criteria | ✓ (`Success criteria:`) | ✓ DSR p<0.05 AND best cell > C001 best cell (0.52) AND ≥1 benchmark (0.79/0.89) at 0 bps |
| Rejection criteria | ✓ (`Rejection criteria:`) | ✓ DSR p≥0.05 OR ≤ C001 best cell OR all benchmarks n.s. |
| Statistical methodology | ✓ (`Statistical validation:`) | ✓ battery (permutation vs signed pool, Welch, bootstrap, Bayesian, SPRT) + DSR/RC on grid + paired meta |
| Benchmark policy | ✓ (`Benchmark comparison:`) | ✓ buy & hold, EMA(10,100), random entries (seed 0), C001 best cell, same P&L basis |
| Final decision categories | ✓ (`Decision:` ACCEPTED \| REJECTED \| INCONCLUSIVE \| REQUIRES_MORE_DATA) | ✓ all four defined incl. INCONCLUSIVE/REQUIRES_MORE_DATA rules |

C002 card field scan (live): all 11 card lines present — Research question,
Hypothesis, Experiment matrix, Success criteria, Rejection criteria,
Statistical validation, Benchmark comparison, Decision, Robustness, Expected
value/cost, Edge DB outcome. **C001 historical card byte-identical before and
after B1** (`git diff a86e0d1..HEAD` on the C001 card block: 0 lines changed).

## B2 — Hypothesis Traceability: **PASS**

Chain traced end-to-end with live evidence (no execution):

```
Hypothesis  H-MS-01 (catalog.md §1, status ready, Campaign 002)
    ↓       graph edge H-MS-01 --BELONGS_TO--> C002 (snapshot, declared 3.3)
Campaign    C002 card (campaigns.md) — hypothesis referenced by ID
    ↓       config validation requires canonical H-ID
Config      "hypothesis": "H-MS-01" required; free text/empty → ValidationError
    ↓       run records: env {git commit, git dirty, quant_research_version}, 
Run         params, seed; experiment: config_hash, module_checksum
    ↓       run.tests (name, statistic, p_value, conclusion) + metrics
Result      metrics + tests stored with result_checksum; decision → Edge DB
```

| Check | Result | Evidence |
|---|---|---|
| New configs require canonical H-IDs | PASS | `ExperimentConfig.validate()` + `ExperimentRecord.validate_meta()`; live demo: `H-MS-01` ACCEPTED, `H-C001` ACCEPTED |
| Missing hypothesis IDs fail validation | PASS | live demo: `""` → "config missing required keys", `"h"` → "must be a canonical catalog ID", prose → "must be a canonical catalog ID" |
| Historical experiments remain readable | PASS | 354 experiments readable; 98.9% (350/354) carry all 5 persisted fields (git_commit, git_dirty, module_checksum, config_hash, seed); historical hypothesis text preserved (2 pre-catalog variants, untouched); 201+ runs with env intact; 8 dirty-origin records retained (marked, never deleted) |

## B3 — Reproducibility Enforcement: **PASS**

| Required per-run field | Recorded for new runs | Live evidence |
|---|---|---|
| Git commit hash | ✓ `env.git.commit` + experiment `git_commit` | demo repo: commit `32384a79` captured |
| Clean/dirty state | ✓ `env.git.dirty` + experiment `git_dirty` | demo: dirty=False (clean), dirty=True (after uncommitted write), dirty=False after commit |
| quant_research version | ✓ `env.quant_research_version` | `0.3.0` reported |
| Module checksum | ✓ experiment `module_checksum` | store: 98.9% populated; runner refuses changed-code execution |
| Config hash | ✓ experiment `config_hash` | store: populated; configs content-hashed |
| Random seed | ✓ experiment `seed` (first-class field) | store: seeds {0,1,2} present |

| Rule | Status | Evidence |
|---|---|---|
| dirty tree → UNVERIFIABLE_REPRODUCTION | PASS | runner `_unverifiable_marker`: dirty → marker True + reason w/ commit (experiment meta + run env); unit tests pass |
| clean tree → reproducible candidate | PASS | marker False; env confirms clean + commit + version; 3 matched reproductions on record |
| Historical campaigns not rerun | PASS | no runs executed this session; store untouched (read-only probes) |
| Regression suite | PASS | 101/101 tests pass (incl. 5 governance tests) |

## C002 Launch Dry Run

No experiments executed. Static validation only:

| Gate | Item | Status | Evidence |
|---|---|---|---|
| A | Hypothesis registered | PASS | H-MS-01 in catalog, status `ready (Campaign 002)` |
| B | Dataset available | PASS | DS-001 Grade A; checksum re-verified `b3159e9d…` = `data/es_f_10y_ohlc_v1.npz`; 2,513 bars |
| C | Features available | **CONDITION** | F-GAP `verified` ✓; F-GAP-COMP `planned (P0, C002)` — see precondition P1 |
| D | Benchmarks defined | PASS | buy & hold, EMA(10,100), random entries (seed 0), C001 best cell — same P&L basis |
| E | Statistics defined | PASS | C001 battery + DSR/RC + paired meta; quant_research v0.3.0 |
| F | Decision criteria defined | PASS | success/rejection/inconclusive/requires-more-data rules on card |
| G | Reproducibility requirements defined | PASS | checklist Gate F + B3 enforcement (6 fields, UNVERIFIABLE_REPRODUCTION) |
| — | Campaign complete | PASS | 11/11 card fields present; graph H-MS-01→C002 BELONGS_TO edge present |

## Result

**C002_READY = PASS** (one precondition):

**P1 (non-blocking, in-campaign):** F-GAP-COMP is `planned (P0, C002)` in
`feature_registry.md`, not yet verified. It is not consumed by the 36-cell
strategy matrix (F-GAP only) and is already pledged as a C002 deliverable
("Gap family closed …; F-GAP-COMP verified" — `roadmap.md`). It must be
implemented and verified as the campaign's first step, before the
gap/intraday decomposition analysis, and the graph check C6 must be clean
for H-MS-01 at closure.

## Remaining blockers

- **None blocking C002 launch.** Gates A, B, D, E, F, G green; Gate C green
  with precondition P1 executed in-campaign.
- Open non-blocking items carried from the readiness review (unchanged):
  C6 dangling F-TREND/F-IMK-CORR (before C003/C007), unregistered CL/GC/
  EURUSD (before C003), test-parameter persistence N3, graph check C17,
  C003–C010 card rewrites at their launches.

## Verification method

Read-only store probes, config-parsing demos in-memory (no execution),
environment snapshots against a throwaway git repo in the OS temp dir (no
research store touched), git diffs of canonical documents, checksum
recomputation, and the platform test suite (101 passed).
