"""Tests for the comparison engine: permutation test internals and
all five research questions."""

import json

import numpy as np
import pytest

from research_platform.compare import (
    CompareError,
    alpha_by_assumption,
    best,
    failures,
    group_metric_values,
    metric_value,
    permutation_two_sample,
    resolve_group,
    robustness,
    significance,
)
from research_platform.runner import run_config
from research_platform.store import open_store

PAYOFF = '''\
import numpy as np

def run(ctx):
    w = ctx.params["w"]
    rng = ctx.rng
    noise = rng.normal(scale=0.1, size=20)
    return {"metrics": {"payoff": w + float(noise.mean())}}
'''

RAISING = '''\
def run(ctx):
    raise RuntimeError("kaput")
'''

NO_METRIC = '''\
def run(ctx):
    return {"metrics": {}}
'''


@pytest.fixture
def store(tmp_path):
    s = open_store(str(tmp_path / "research"))
    yield s
    s.close()


def write_module(tmp_path, source, name):
    path = tmp_path / ("%s.py" % name)
    path.write_text(source, encoding="utf-8")
    return name


def run_sweep(tmp_path, store, source, name, sweep_values, seeds=(0, 1, 2),
              tags=None, assumptions=None):
    module = write_module(tmp_path, source, name)
    raw = {
        "hypothesis": "H-TST-01", "objective": "o", "author": "author-a",
        "assumptions": assumptions if assumptions is not None else ["base-assumption"],
        "tags": tags or ["sweep-tag"],
        "experiment": {"module": module, "parameters": {"w": 0}},
        "sweep": {"parameter": "w", "values": sweep_values},
        "seeds": list(seeds),
    }
    path = tmp_path / ("%s.json" % name)
    path.write_text(json.dumps(raw), encoding="utf-8")
    return run_config(store, str(path))


def test_permutation_test_rejects_small_samples():
    with pytest.raises(CompareError, match=">= 2"):
        permutation_two_sample(np.array([1.0]), np.array([2.0, 3.0]))


def test_permutation_test_separated_groups_significant():
    a = np.zeros(20)
    b = np.ones(20)
    res = permutation_two_sample(a, b, n_permutations=2000, seed=0)
    assert res["mean_diff"] == pytest.approx(-1.0)
    assert res["p_value"] < 0.05
    assert res["n_a"] == 20 and res["n_b"] == 20
    assert res["seed"] == 0
    assert res["n_permutations"] == 2000
    assert res["effect_size_cohens_d"] > 0


def test_permutation_test_identical_groups_not_significant():
    a = np.random.default_rng(1).normal(size=10)
    res = permutation_two_sample(a, a, n_permutations=200, seed=1)
    assert res["p_value"] > 0.05


def test_permutation_test_deterministic():
    r1 = permutation_two_sample(np.zeros(8), np.ones(8), n_permutations=1000, seed=7)
    r2 = permutation_two_sample(np.zeros(8), np.ones(8), n_permutations=1000, seed=7)
    assert r1["p_value"] == r2["p_value"]


def test_best_ranks_by_median(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff", sweep_values=[1, 2])
    rows = best(store, "payoff", direction="max", tag="sweep-tag")
    assert [r["params"]["w"] for r in rows] == [2, 1]
    assert rows[0]["n"] == 3  # three seeds
    assert rows[0]["median"] > rows[1]["median"]
    assert "uuids" in rows[0]


def test_best_min_direction(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_min", sweep_values=[1, 2])
    rows = best(store, "payoff", direction="min", tag="sweep-tag")
    assert [r["params"]["w"] for r in rows] == [1, 2]


def test_best_filters_by_tag_and_author(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_tag", sweep_values=[1],
              tags=["other-tag"])
    assert best(store, "payoff", tag="sweep-tag") == []
    assert len(best(store, "payoff", tag="other-tag")) == 1
    assert len(best(store, "payoff", author="author-a", tag="other-tag")) == 1
    assert best(store, "payoff", author="nobody") == []


def test_best_skips_missing_metric(tmp_path, store):
    run_sweep(tmp_path, store, NO_METRIC, "no_metric", sweep_values=[1])
    assert best(store, "payoff") == []


def test_best_rejects_bad_direction(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_dir", sweep_values=[1])
    with pytest.raises(CompareError, match="direction"):
        best(store, "payoff", direction="up")


def test_metric_value_errors(tmp_path, store):
    run_sweep(tmp_path, store, NO_METRIC, "no_metric2", sweep_values=[1])
    exps = store.find_experiments()
    with pytest.raises(CompareError, match="no metric"):
        metric_value(store, exps[0], "payoff")
    run_sweep(tmp_path, store, RAISING, "raising3", sweep_values=[1])
    failed = [e for e in store.find_experiments() if e.status == "failed"][0]
    with pytest.raises(CompareError, match="no completed run"):
        metric_value(store, failed, "payoff")


def test_resolve_group_by_uuid_and_sweep(tmp_path, store):
    summary = run_sweep(tmp_path, store, PAYOFF, "payoff_resolve",
                        sweep_values=[1, 2], seeds=(0, 1))
    uuids = [o["uuid"] for o in summary["outcomes"]]
    single = resolve_group(store, uuids[0])
    assert len(single) == 1
    group = resolve_group(store, summary["config_hash"])
    assert len(group) == 4
    with pytest.raises(CompareError, match="unknown"):
        resolve_group(store, "bogus")


def test_group_metric_values_requires_two(tmp_path, store):
    summary = run_sweep(tmp_path, store, PAYOFF, "payoff_groups",
                        sweep_values=[1], seeds=(0,))
    exps = [store.get_experiment(o["uuid"]) for o in summary["outcomes"]]
    assert len(exps) == 1
    with pytest.raises(CompareError, match=">= 2"):
        group_metric_values(store, exps, "payoff")


def test_significance_rejects_overlap(tmp_path, store):
    summary = run_sweep(tmp_path, store, PAYOFF, "payoff_overlap",
                        sweep_values=[1, 2], seeds=(0, 1))
    with pytest.raises(CompareError, match="overlap"):
        significance(store, summary["outcomes"][0]["uuid"],
                     summary["config_hash"], "payoff")


def test_significance_verdict(tmp_path, store):
    # Two separate sweeps => two distinct config hashes to resolve groups.
    sweep_a = run_sweep(tmp_path, store, PAYOFF, "sig_a",
                        sweep_values=[1], seeds=tuple(range(10)))
    sweep_b = run_sweep(tmp_path, store, PAYOFF, "sig_b",
                        sweep_values=[10], seeds=tuple(range(10)))
    result = significance(
        store, sweep_a["config_hash"], sweep_b["config_hash"], "payoff",
        n_permutations=500,
    )
    assert result["metric"] == "payoff"
    assert result["group_a"]["n"] == 10
    assert result["group_b"]["n"] == 10
    assert result["conclusion"] == "significant at 5%"


def test_robustness_groups_by_parameter(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_robust", sweep_values=[1, 2, 3])
    rows = robustness(store, "payoff", "w", threshold=1.5)
    assert {r["parameter_value"] for r in rows} == {1, 2, 3}
    by_value = {r["parameter_value"]: r for r in rows}
    assert by_value[2]["pass_rate"] == pytest.approx(1.0)
    assert by_value[1]["pass_rate"] == pytest.approx(0.0)
    assert by_value[1]["n"] == 3


def test_robustness_min_direction(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_robust_min", sweep_values=[1, 2])
    rows = robustness(store, "payoff", "w", threshold=1.5, direction="min")
    by_value = {r["parameter_value"]: r for r in rows}
    assert by_value[2]["pass_rate"] == 0.0
    assert by_value[1]["pass_rate"] == 1.0


def test_robustness_ignores_experiments_without_parameter(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_robust2", sweep_values=[1])
    rows = robustness(store, "payoff", "missing-param")
    assert rows == []


def test_failures_lists_failed(tmp_path, store):
    run_sweep(tmp_path, store, RAISING, "raising_failures", sweep_values=[1],
              tags=["broken-tag"])
    rows = failures(store, tag="broken-tag")
    assert len(rows) == 3
    assert all("kaput" in r["failure_reason"] for r in rows)
    assert all(r["module"].startswith("raising_failures") for r in rows)
    assert failures(store, tag="nope") == []


def test_failures_limit(tmp_path, store):
    run_sweep(tmp_path, store, RAISING, "raising_limit", sweep_values=[1])
    assert len(failures(store, limit=2)) == 2


def test_alpha_by_assumption_buckets(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_alpha",
              sweep_values=[1, 2],
              assumptions=["market-neutral", "no-costs"])
    rows = alpha_by_assumption(store, "payoff")
    labels = {r["assumption"] for r in rows}
    assert labels == {"market-neutral", "no-costs"}
    for r in rows:
        assert r["n"] == 6
        assert len(r["uuids"]) == 6


def test_alpha_by_assumption_none_declared(tmp_path, store):
    run_sweep(tmp_path, store, PAYOFF, "payoff_alpha2", sweep_values=[1],
              assumptions=[])
    rows = alpha_by_assumption(store, "payoff")
    assert len(rows) == 1
    assert rows[0]["assumption"] == "(none declared)"
