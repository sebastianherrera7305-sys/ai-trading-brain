"""Comparison engine: answer research questions over the registry.

Supported questions (one function each):

* ``best`` — which experiment performed best (aggregated over seeds)?
* ``significance`` — is the difference between two groups of runs
  statistically significant? (two-sample permutation test, numpy-only)
* ``robustness`` — which parameter combinations are robust (stable
  across seeds and above threshold)?
* ``failures`` — which experiments failed, and why?
* ``alpha_by_assumption`` — which documented assumptions consistently
  produce alpha?

All statistics are implemented in-house on numpy (no scipy), consistent
with the framework's independence requirement. The permutation test is
exact under the exchangeability null and is seeded from the framework's
deterministic policy, so significance verdicts are reproducible too.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ._util import canonical_json, sha256_text
from .schema import ExperimentRecord
from .store import ResearchStore


class CompareError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def latest_completed_run(store: ResearchStore, experiment: ExperimentRecord):
    """The most recent completed run of an experiment (or None)."""
    for run in reversed(store.get_runs(experiment.uuid)):
        if run.status == "completed":
            return run
    return None


def metric_value(store: ResearchStore, experiment: ExperimentRecord, metric: str) -> float:
    """The numeric value of ``metric`` from an experiment's latest run."""
    run = latest_completed_run(store, experiment)
    if run is None:
        raise CompareError("experiment %s has no completed run" % experiment.uuid)
    if metric not in run.metrics:
        raise CompareError(
            "experiment %s has no metric '%s' (has: %s)"
            % (experiment.uuid, metric, ", ".join(sorted(run.metrics)) or "(none)")
        )
    value = run.metrics[metric]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CompareError(
            "metric '%s' of experiment %s is not numeric (%s)"
            % (metric, experiment.uuid, type(value).__name__)
        )
    return float(value)


def group_key(experiment: ExperimentRecord) -> str:
    """Grouping key: experiments with identical params are the same
    parameter combination regardless of seed/repeat."""
    return sha256_text(canonical_json(experiment.params))


def resolve_group(store: ResearchStore, ref: str) -> List[ExperimentRecord]:
    """Resolve a reference to a group of experiments.

    ``ref`` may be an experiment uuid (single member) or a sweep id /
    config hash (all experiments from that sweep).
    """
    if len(ref) == 36:
        try:
            return [store.get_experiment(ref)]
        except Exception:
            pass
    try:
        found = store.find_experiments(sweep_id=ref)
        if found:
            return found
    except Exception:
        pass
    try:
        return [store.get_experiment(ref)]
    except Exception as exc:
        raise CompareError("unknown experiment or sweep: %s (%s)" % (ref, exc))


def group_metric_values(
    store: ResearchStore, experiments: List[ExperimentRecord], metric: str
) -> List[float]:
    values = [metric_value(store, e, metric) for e in experiments]
    if len(values) < 2:
        raise CompareError(
            "significance needs >= 2 metric values per group, got %d" % len(values)
        )
    return values


# ---------------------------------------------------------------------------
# Permutation test (two-sample)
# ---------------------------------------------------------------------------

def permutation_two_sample(
    a: np.ndarray, b: np.ndarray, n_permutations: int = 10000, seed: int = 0
) -> Dict[str, float]:
    """Two-sided two-sample permutation test on mean difference.

    Exact under the exchangeability null: shuffle the pooled sample,
    recompute the mean difference, and count how often the permuted
    statistic reaches the observed one in absolute value. The p-value
    is (count + 1) / (P + 1), so it can never be reported as exactly 0.
    """
    if len(a) < 2 or len(b) < 2:
        raise CompareError("permutation test needs >= 2 values per group")
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    pooled = np.concatenate([a, b])
    na = len(a)
    observed = float(a.mean() - b.mean())
    rng = np.random.default_rng(seed)
    extreme = 0
    total = 0
    for _ in range(int(n_permutations)):
        perm = rng.permutation(pooled)
        diff = float(perm[:na].mean() - perm[na:].mean())
        if abs(diff) >= abs(observed):
            extreme += 1
        total += 1
    pooled_std = float(np.std(pooled, ddof=1))
    cohens_d = abs(observed) / pooled_std if pooled_std > 0.0 else math.inf
    return {
        "mean_a": float(a.mean()),
        "mean_b": float(b.mean()),
        "mean_diff": observed,
        "effect_size_cohens_d": cohens_d,
        "p_value": (extreme + 1.0) / (total + 1.0),
        "n_permutations": total,
        "n_a": na,
        "n_b": len(b),
        "seed": seed,
    }


# ---------------------------------------------------------------------------
# The five research questions
# ---------------------------------------------------------------------------

def best(
    store: ResearchStore,
    metric: str,
    direction: str = "max",
    tag: Optional[str] = None,
    assumption: Optional[str] = None,
    sweep_id: Optional[str] = None,
    author: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Rank parameter combinations by their median metric value.

    Experiments are grouped by identical parameter sets (seeds are
    replicates of the same combination), so the ranking is robust to
    single-lucky-seed results.
    """
    if direction not in ("max", "min"):
        raise CompareError("direction must be 'max' or 'min'")
    experiments = store.find_experiments(
        status="completed", tag=tag, assumption=assumption,
        sweep_id=sweep_id, author=author,
    )
    groups: Dict[str, Dict[str, Any]] = {}
    for exp in experiments:
        key = group_key(exp)
        g = groups.setdefault(key, {"uuids": [], "params": exp.params, "values": []})
        try:
            g["values"].append(metric_value(store, exp, metric))
            g["uuids"].append(exp.uuid)
        except CompareError:
            continue
    rows = []
    for g in groups.values():
        if not g["values"]:
            continue
        values = g["values"]
        arr = np.asarray(values, dtype=float)
        rows.append({
            "params": g["params"],
            "uuids": g["uuids"],
            "n": len(values),
            "median": float(np.median(arr)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)) if len(values) > 1 else 0.0,
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        })
    rows.sort(key=lambda r: r["median"], reverse=(direction == "max"))
    return rows[:limit]


def significance(
    store: ResearchStore,
    group_a_ref: str,
    group_b_ref: str,
    metric: str,
    n_permutations: int = 10000,
    seed: int = 0,
) -> Dict[str, Any]:
    """Is the difference in ``metric`` between two groups significant?

    Groups are resolved by uuid or sweep id; the per-experiment metric
    values (one per experiment, from its latest completed run) form the
    two samples.
    """
    a = resolve_group(store, group_a_ref)
    b = resolve_group(store, group_b_ref)
    if any(e.uuid in {x.uuid for x in b} for e in a):
        raise CompareError("groups must not overlap")
    values_a = group_metric_values(store, a, metric)
    values_b = group_metric_values(store, b, metric)
    test = permutation_two_sample(
        np.asarray(values_a), np.asarray(values_b),
        n_permutations=n_permutations, seed=seed,
    )
    return {
        "metric": metric,
        "group_a": {"ref": group_a_ref, "n": len(values_a),
                    "uuids": [e.uuid for e in a],
                    "values": values_a},
        "group_b": {"ref": group_b_ref, "n": len(values_b),
                    "uuids": [e.uuid for e in b],
                    "values": values_b},
        "test": test,
        "conclusion": (
            "significant at 5%"
            if test["p_value"] < 0.05 else "not significant at 5%"
        ),
    }


def robustness(
    store: ResearchStore,
    metric: str,
    parameter: str,
    threshold: Optional[float] = None,
    direction: str = "max",
    sweep_id: Optional[str] = None,
    tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Aggregate results by one parameter's values.

    For every distinct value of ``parameter`` reports n, mean, std,
    median, min/max, and — when ``threshold`` is given — the pass rate
    (fraction of runs better than the threshold), i.e. robustness.
    """
    if direction not in ("max", "min"):
        raise CompareError("direction must be 'max' or 'min'")
    experiments = store.find_experiments(
        status="completed", sweep_id=sweep_id, tag=tag
    )
    groups: Dict[str, Dict[str, Any]] = {}
    for exp in experiments:
        if parameter not in exp.params:
            continue
        key = canonical_json(exp.params[parameter])
        g = groups.setdefault(key, {"parameter_value": exp.params[parameter], "values": []})
        try:
            g["values"].append(metric_value(store, exp, metric))
        except CompareError:
            continue
    rows = []
    for g in groups.values():
        if not g["values"]:
            continue
        values = g["values"]
        arr = np.asarray(values, dtype=float)
        row = {
            "parameter": parameter,
            "parameter_value": g["parameter_value"],
            "n": len(values),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)) if len(values) > 1 else 0.0,
            "median": float(np.median(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
        }
        if threshold is not None:
            if direction == "max":
                row["pass_rate"] = float(np.mean(arr >= threshold))
            else:
                row["pass_rate"] = float(np.mean(arr <= threshold))
        rows.append(row)
    rows.sort(key=lambda r: r["median"], reverse=(direction == "max"))
    return rows


def failures(
    store: ResearchStore,
    tag: Optional[str] = None,
    author: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Every failed experiment with its recorded failure reason."""
    experiments = store.find_experiments(status="failed", tag=tag, author=author)
    rows = []
    for exp in experiments:
        rows.append({
            "uuid": exp.uuid,
            "author": exp.author,
            "module": exp.module,
            "created_at": exp.created_at,
            "seed": exp.seed,
            "sweep_value": exp.sweep_value,
            "params": exp.params,
            "failure_reason": exp.failure_reason,
            "runtime_seconds": exp.runtime_seconds,
        })
    return rows[:limit]


def alpha_by_assumption(
    store: ResearchStore,
    metric: str,
    direction: str = "max",
    tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Group completed experiments by their declared assumptions.

    Answers "which assumptions consistently produce alpha": for each
    assumption (an experiment may declare several), the median/mean/
    spread of the metric across all experiments that declared it.
    """
    if direction not in ("max", "min"):
        raise CompareError("direction must be 'max' or 'min'")
    experiments = store.find_experiments(status="completed", tag=tag)
    buckets: Dict[str, List[float]] = {}
    bucket_uuids: Dict[str, List[str]] = {}
    for exp in experiments:
        try:
            value = metric_value(store, exp, metric)
        except CompareError:
            continue
        labels = exp.assumptions or ["(none declared)"]
        for label in labels:
            buckets.setdefault(label, []).append(value)
            bucket_uuids.setdefault(label, []).append(exp.uuid)
    rows = []
    for label, values in buckets.items():
        arr = np.asarray(values, dtype=float)
        rows.append({
            "assumption": label,
            "n": len(values),
            "median": float(np.median(arr)),
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)) if len(values) > 1 else 0.0,
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "uuids": bucket_uuids[label],
        })
    rows.sort(key=lambda r: r["median"], reverse=(direction == "max"))
    return rows
