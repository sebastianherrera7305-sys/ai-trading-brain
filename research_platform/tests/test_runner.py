"""Tests for the experiment runner: atomic execution, sweeps,
repeats, artifacts, dataset payloads, and failure handling."""

import json
import os
import uuid as uuidlib

import numpy as np
import pytest

from research_platform.config import load_config
from research_platform.runner import (
    ExperimentContext,
    UNVERIFIABLE_MARKER,
    _unverifiable_marker,
    load_dataset_content,
    load_experiment_function,
    run_atomic,
    run_config,
    save_artifact,
)
from research_platform.schema import ExperimentRecord
from research_platform.store import open_store

SIMPLE = '''\
import numpy as np

def run(ctx):
    ctx.log("hello")
    rng = ctx.rng
    x = rng.normal(size=10)
    return {
        "metrics": {"mean": float(x.mean()), "seed": ctx.seed,
                    "param": ctx.params.get("w", None)},
        "tests": [{"name": "sanity", "statistic": 1.0, "p_value": 0.5,
                   "conclusion": "pass"}],
        "artifacts": {"vec": x, "note": "a note", "blob": b"\\x00\\x01"},
        "logs": ["done"],
    }
'''

RAISING = '''\
def run(ctx):
    raise ValueError("boom")
'''

DATASET_MODULE = '''\
def run(ctx):
    data = ctx.dataset["data"]
    return {"metrics": {"rows": float(len(data))}}
'''


def write_module(tmp_path, source, name=None):
    name = name or ("mod_%s" % uuidlib.uuid4().hex[:8])
    path = tmp_path / ("%s.py" % name)
    path.write_text(source, encoding="utf-8")
    return name


def make_config(tmp_path, module, sweep=None, seeds=(0,), parameters=None,
                dataset=None, function=None):
    exp = {"module": module, "parameters": parameters or {}}
    if function:
        exp["function"] = function
    if dataset:
        exp["dataset"] = dataset
    raw = {
        "hypothesis": "H-TST-01", "objective": "o", "author": "a",
        "assumptions": ["assumption-1"], "tags": ["tag-1"],
        "experiment": exp, "seeds": list(seeds),
    }
    if sweep is not None:
        raw["sweep"] = sweep
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


@pytest.fixture
def store(tmp_path):
    s = open_store(str(tmp_path / "research"))
    yield s
    s.close()


def test_successful_atomic_run(tmp_path, store):
    module = write_module(tmp_path, SIMPLE)
    config_path = make_config(tmp_path, module, seeds=(7,), parameters={"w": 3})
    summary = run_config(store, config_path)
    assert summary["experiments"] == 1
    assert summary["completed"] == 1
    assert summary["failed"] == 0
    rec = store.get_experiment(summary["outcomes"][0]["uuid"])
    assert rec.status == "completed"
    assert rec.seed == 7
    assert rec.module_checksum
    assert rec.config_hash == summary["config_hash"]
    run = store.get_latest_run(rec.uuid)
    assert run.status == "completed"
    assert run.result_checksum
    assert run.metrics["mean"] is not None
    # Durable files
    run_dir = store.run_dir(rec.uuid, 1)
    assert (run_dir / "log.txt").is_file()
    assert (run_dir / "env.json").is_file()
    assert (run_dir / "params.json").is_file()
    assert (run_dir / "metrics.json").is_file()
    assert (run_dir / "tests.json").is_file()
    assert (run_dir / "artifacts" / "vec.npy").is_file()
    assert (run_dir / "artifacts" / "note.txt").is_file()
    assert (run_dir / "artifacts" / "blob.bin").is_file()
    env = json.loads((run_dir / "env.json").read_text())
    assert "python_version" in env
    assert run.env == env


def test_experiment_failure_is_recorded_not_raised(tmp_path, store):
    module = write_module(tmp_path, RAISING)
    config_path = make_config(tmp_path, module, seeds=(0, 1))
    summary = run_config(store, config_path)
    assert summary["completed"] == 0
    assert summary["failed"] == 2
    for outcome in summary["outcomes"]:
        rec = store.get_experiment(outcome["uuid"])
        assert rec.status == "failed"
        assert "ValueError" in rec.failure_reason
        run = store.get_latest_run(rec.uuid)
        assert run.status == "failed"
        assert "boom" in run.failure_reason
        log = (store.run_dir(rec.uuid, 1) / "log.txt").read_text()
        assert "Traceback" in log


def test_missing_function_is_recorded_failure(tmp_path, store):
    module = write_module(tmp_path, RAISING)
    config_path = make_config(tmp_path, module, function="nope")
    summary = run_config(store, config_path)
    assert summary["failed"] == 1
    rec = store.get_experiment(summary["outcomes"][0]["uuid"])
    assert "no function 'nope'" in rec.failure_reason


def test_sweep_and_repeats_materialize_siblings(tmp_path, store):
    module = write_module(tmp_path, SIMPLE)
    config_path = make_config(
        tmp_path, module,
        sweep={"parameter": "w", "values": [1, 2]}, seeds=(0, 1),
    )
    summary = run_config(store, config_path)
    assert summary["experiments"] == 4
    uuids = [o["uuid"] for o in summary["outcomes"]]
    recs = [store.get_experiment(u) for u in uuids]
    assert [r.sweep_value for r in recs] == [1, 1, 2, 2]
    assert [r.seed for r in recs] == [0, 1, 0, 1]
    assert len({r.sweep_id for r in recs}) == 1
    assert all(r.sweep_id == summary["config_hash"] for r in recs)
    assert all(r.repeat_index == r.seed for r in recs)
    for r in recs:
        assert r.params["w"] == r.sweep_value
    # Params stored with the sweep value; identical sweep value => identical params.
    assert recs[0].params == recs[1].params


def test_repeats_only_config(tmp_path, store):
    module = write_module(tmp_path, SIMPLE)
    raw = {
        "hypothesis": "H-TST-01", "objective": "o", "author": "a",
        "experiment": {"module": module, "parameters": {}},
        "repeats": 3,
    }
    path = tmp_path / "config2.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    summary = run_config(store, str(path))
    assert summary["experiments"] == 3
    recs = [store.get_experiment(o["uuid"]) for o in summary["outcomes"]]
    assert [r.seed for r in recs] == [0, 1, 2]
    assert all(r.sweep_id is None for r in recs)
    # Same params => same grouping key, but distinct experiments.
    assert len({r.uuid for r in recs}) == 3
    assert [r.repeat_index for r in recs] == [0, 1, 2]


def test_run_atomic_with_dataset(tmp_path, store):
    data_path = tmp_path / "data.csv"
    data_path.write_text("1.0,2.0\n3.0,4.0\n", encoding="utf-8")
    dataset = store.register_dataset(
        str(data_path), source="s", provider="p", version="1",
        symbol="ES", timeframe="1d", timezone="UTC", name="ds",
    )
    module = write_module(tmp_path, DATASET_MODULE)
    config_path = make_config(tmp_path, module, dataset="ds")
    summary = run_config(store, config_path)
    rec = store.get_experiment(summary["outcomes"][0]["uuid"])
    assert rec.dataset_id == dataset.id
    run = store.get_latest_run(rec.uuid)
    assert run.metrics["rows"] == 2.0


def test_dataset_integrity_failure_recorded(tmp_path, store):
    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n", encoding="utf-8")
    dataset = store.register_dataset(
        str(data_path), source="s", provider="p", version="1",
        symbol="ES", timeframe="1d", timezone="UTC", name="ds",
    )
    blob = store.dataset_object_path(dataset)
    blob.write_bytes(b"tampered!")
    module = write_module(tmp_path, SIMPLE)
    config_path = make_config(tmp_path, module, dataset="ds")
    summary = run_config(store, config_path)
    rec = store.get_experiment(summary["outcomes"][0]["uuid"])
    assert rec.status == "failed"
    assert "integrity" in rec.failure_reason


def test_load_experiment_function_errors(tmp_path):
    with pytest.raises(Exception, match="no function"):
        load_experiment_function(write_module(tmp_path, SIMPLE), "missing", str(tmp_path))
    with pytest.raises(Exception, match="cannot import"):
        load_experiment_function("no_such_module_xyz", "run", str(tmp_path))
    fn, checksum = load_experiment_function(
        write_module(tmp_path, SIMPLE), "run", str(tmp_path)
    )
    assert callable(fn)
    assert len(checksum) == 64


def test_load_dataset_content(tmp_path):
    arr = np.arange(12).reshape(3, 4)
    npy = tmp_path / "d.npy"
    np.save(str(npy), arr)
    loaded = load_dataset_content(npy)
    assert np.array_equal(loaded, arr)
    npz = tmp_path / "d.npz"
    np.savez(str(npz), a=arr)
    loaded = load_dataset_content(npz)
    assert np.array_equal(loaded["a"], arr)
    csv = tmp_path / "d.csv"
    csv.write_text("1,2\n3,4", encoding="utf-8")
    loaded = load_dataset_content(csv)
    assert np.array_equal(loaded, [[1, 2], [3, 4]])
    blob = tmp_path / "d.bin"
    blob.write_bytes(b"\x00\x01\x02")
    assert load_dataset_content(blob) == b"\x00\x01\x02"


def test_save_artifact_kinds(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rec = save_artifact(run_dir, "v", np.array([1.0, 2.0]))
    assert rec["kind"] == "npy"
    assert (run_dir / rec["path"]).is_file()
    assert save_artifact(run_dir, "s", "hi")["kind"] == "txt"
    assert save_artifact(run_dir, "b", b"\x00")["kind"] == "bin"
    assert save_artifact(run_dir, "j", {"a": 1})["kind"] == "json"
    assert save_artifact(run_dir, "a/b", 1)["path"] == "artifacts/a_b.json"
    for info in (rec,):
        import hashlib

        data = (run_dir / info["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"]


def test_experiment_context_log():
    ctx = ExperimentContext(
        params={}, seed=1, rng=np.random.default_rng(1), dataset=None,
    )
    ctx.log("one")
    assert ctx.log_lines == ["[experiment] one"]


def test_unverifiable_marker_marks_dirty_git():
    dirty = _unverifiable_marker({"commit": "abc123", "dirty": True})
    assert dirty[UNVERIFIABLE_MARKER] is True
    assert "abc123" in dirty["unverifiable_reproduction_reason"]
    clean = _unverifiable_marker({"commit": "abc123", "dirty": False})
    assert clean[UNVERIFIABLE_MARKER] is False
    no_git = _unverifiable_marker(None)
    assert no_git[UNVERIFIABLE_MARKER] is False


def test_run_atomic_returns_record(tmp_path, store):
    module = write_module(tmp_path, SIMPLE)
    cfg = load_config(make_config(tmp_path, module, seeds=(3,)))
    item = cfg.plan()[0]
    rec = run_atomic(store, cfg, item, "cfg-hash", cwd=str(tmp_path))
    assert isinstance(rec, ExperimentRecord)
    assert rec.status == "completed"
