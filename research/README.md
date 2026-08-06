# Alpha Research Laboratory — Charter and Operations

This directory is the operating center of the quantitative research organization.
The repository's primary asset is accumulated, verified market knowledge —
not software. Every file here is a living operational document.

## 1. Mission

Continuously discover, test, reject, refine, and archive trading hypotheses
using the existing platform (`quant_research` + `research_platform`).
Every experiment must increase the organization's understanding of financial
markets regardless of outcome. **A rejected hypothesis is a successful
research outcome.**

## 2. Research principles

- Optimize for: information gained, statistical rigor, reproducibility,
  knowledge accumulation, efficient elimination of false ideas.
- Never optimize for the number of experiments or hypotheses.
- No undocumented research. Every hypothesis enters the catalog
  (`catalog.md`) before execution.
- The platform is stable. Do not modify infrastructure unless a deficiency
  directly prevents scientific research.
- Every completed campaign must leave the project with more verified
  knowledge than it started with, and must conclude with a
  publication-quality research report (Section 6).

## 3. Scientific workflow (no exceptions)

```
Idea -> Specification -> Dataset Selection -> Feature Engineering ->
Experiment Execution -> Statistical Validation -> Robustness Testing ->
Benchmark Comparison -> Decision -> Knowledge Base -> Archive
```

Gate rules:

| Gate | Requirement |
|---|---|
| Idea → Specification | Hypothesis has an ID in `catalog.md` and a campaign assignment |
| Specification → Dataset | Datasets registered in the store, immutable, checksum-verified |
| Dataset → Features | Features used are documented in `features.md`; no ad-hoc feature code |
| Execution | Configs generated deterministically and committed **before** runs (clean-tree discipline) |
| Validation | quant_research tests only; nullity gate + confirmatory battery per cell |
| Robustness | Cost ladder, per-year and per-regime breakdowns, seed stability |
| Comparison | Same daily-P&L basis vs registered benchmarks; never vs a hand-picked baseline |
| Decision | Data-snooping-adjusted (DSR / Reality Check) when a grid was searched |
| Knowledge Base | Edge Database entry appended (accepted, rejected, or inconclusive) |
| Archive | Campaign closes with a report in the campaign directory; campaign status updated |

## 4. Standards inherited from the reference campaign

The Gap Continuation campaign (`research_platform/research_studies/gap_continuation/`,
verdict REJECTED) is the reference standard. Its conventions:

- Study lives in `research_platform/research_studies/<campaign>/`.
- Deterministic config generator committed to the repo; configs in the same
  directory as experiment modules.
- Statistical machinery imported from `_common.py` (repo-root bootstrap, shared
  metrics vocabulary, `quant_research` re-export).
- Trial matrices assembled from registry artifacts (data engineering only),
  registered as immutable datasets.
- Meta-validation (DSR, White's Reality Check, Welch vs benchmarks) as the
  decisive layer for any multi-cell search.
- Reproduce at each commit: best cell, one benchmark, meta-validation.

## 5. Laboratory documents

| File | Purpose | Owner discipline |
|---|---|---|
| `catalog.md` | Research Catalog: every hypothesis, all domains | Add before execution; update status after decision |
| `features.md` | Feature Library Roadmap: reusable feature inventory | Update when a feature ships or data unblocks one |
| `campaigns.md` | Campaign registry + prioritized backlog | Open a campaign card before first run; close with report |
| `edge_database.md` | Edge Database: outcome of every campaign (append-only) | Append after every campaign; never edit past entries |
| `meta_research.md` | Meta-research: analysis of research itself | Iterate after each campaign; full review each quarter |

## 6. Publication-quality report (mandatory for every campaign)

A completed campaign is not finished until `report.md` exists in the campaign
directory and covers all of:

1. **Hypothesis** — exact statement, falsifiable form.
2. **Methodology** — design, entry/exit rules, trade construction, costs.
3. **Datasets** — source, checksums, registered IDs, provenance.
4. **Features** — IDs from `features.md`, definitions, dependencies.
5. **Experiment matrix** — full parameter grid, seeds, run counts.
6. **Benchmarks** — buy & hold, random entries, trend crossovers; same P&L basis.
7. **Statistical tests** — nullity gate, Welch, bootstrap, Bayesian, SPRT, DSR/RC.
8. **Robustness analysis** — cost ladder, per-year/per-regime breakdowns.
9. **Reproducibility verification** — commits, checksums, reproduce verdicts.
10. **Limitations** — data, assumptions, generalization boundaries.
11. **Final verdict** — accepted / rejected / inconclusive, with the deciding evidence.
12. **Lessons learned** — process and market lessons.
13. **Recommendations for future research** — what this campaign implies next.

The Gap Continuation report
(`research_platform/research_studies/gap_continuation/report.md`) is the template.

## 7. Running a campaign — checklist

1. Pick the next campaign from `campaigns.md` (top of prioritized backlog).
2. Register/prepare datasets; verify checksums.
3. Implement features per `features.md` (shared, reusable).
4. Write experiment modules + deterministic config generator; commit (C1).
5. Execute grid on a clean tree; commit interim artifacts as needed.
6. Assemble trial matrix; register it (C2); run meta-validation; commit fixes (C3).
7. Reproduce best cell, a benchmark, and meta-validation at their commits.
8. Append Edge Database entry; write `report.md`; close campaign; push.

## 8. Success metrics

The project is evaluated by: validated research campaigns, reproducible
experiments, statistically sound conclusions, accumulated market knowledge,
reusable research assets, and improvement of the Edge Database.
