"""Tests for the reproducibility engine: audit, re-execution, and the
matched / differed / unverifiable verdicts."""

import json

import pytest

from research_platform.config import load_config
from research_platform.reproduce import (
    ReproduceError,
    audit,
    audit_preconditions,
    reproduce,
)
from research_platform.runner import run_atomic
from research_platform.store import open_store

DETERMINISTIC = '''\
import numpy as np

def run(ctx):
    x = ctx.rng.normal(size=50)
    return {"metrics": {"mean": float(x.mean())}}
'''

NONDETERMINISTIC = '''\
import numpy as np

def run(ctx):
    # Deliberately unseeded: breaks the runner's determinism contract.
    x = np.random.random(50)
    return {"metrics": {"mean": float(x.mean())}}
'''

FAILING = '''\
def run(ctx):
    raise ValueError("boom")
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


def run_one(tmp_path, store, source, name="det_mod", cwd=None):
    module = write_module(tmp_path, source, name)
    raw = {
        "hypothesis": "H-TST-01", "objective": "o", "author": "a",
        "experiment": {"module": module, "parameters": {}},
        "seeds": [0],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    cfg = load_config(str(path))
    item = cfg.plan()[0]
    rec = run_atomic(store, cfg, item, "cfg-hash", cwd=cwd or str(tmp_path))
    return rec


def test_matched_reproduction(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_det")
    assert store.get_latest_run(rec.uuid).run_number == 1
    report = reproduce(store, rec.uuid, cwd=str(tmp_path))
    assert report["status"] == "matched"
    assert report["max_metric_abs_diff"] == 0.0
    assert report["original_run_number"] == 1
    assert report["new_run_number"] == 2
    assert report["re_executed"] is True
    # A second execution was appended, nothing was overwritten.
    assert store.get_latest_run(rec.uuid).run_number == 2
    assert len(store.get_runs(rec.uuid)) == 2
    # The reproduction itself was recorded.
    rows = store.get_reproductions(rec.uuid)
    assert len(rows) == 1
    assert rows[0].status == "matched"
    assert rows[0].max_metric_abs_diff == 0.0
    assert rows[0].new_run_number == 2


def test_differed_reproduction(tmp_path, store):
    rec = run_one(tmp_path, store, NONDETERMINISTIC, name="m_nondet")
    report = reproduce(store, rec.uuid, cwd=str(tmp_path))
    assert report["status"] == "differed"
    assert report["re_executed"] is True
    rows = store.get_reproductions(rec.uuid)
    assert rows[0].status == "differed"


def test_unverifiable_when_module_changed(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_uv")
    module_path = tmp_path / "m_uv.py"
    module_path.write_text(
        DETERMINISTIC.replace("50", "51"), encoding="utf-8"
    )
    report = reproduce(store, rec.uuid, cwd=str(tmp_path))
    assert report["status"] == "unverifiable"
    assert report["re_executed"] is False
    assert "changed" in report["explanation"]
    # Nothing was re-executed.
    assert store.get_latest_run(rec.uuid).run_number == 1
    rows = store.get_reproductions(rec.uuid)
    assert rows[0].status == "unverifiable"


def test_force_overrides_blocking_preconditions(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_force")
    module_path = tmp_path / "m_force.py"
    module_path.write_text(
        DETERMINISTIC.replace("50", "51"), encoding="utf-8"
    )
    report = reproduce(store, rec.uuid, cwd=str(tmp_path), force=True)
    assert report["status"] == "differed"  # re-ran under changed code
    assert report["re_executed"] is True
    assert report["new_run_number"] == 2


def test_missing_dataset_is_unverifiable(tmp_path, store):
    data_path = tmp_path / "data.csv"
    data_path.write_text("1,2\n3,4\n", encoding="utf-8")
    dataset = store.register_dataset(
        str(data_path), source="s", provider="p", version="1",
        symbol="ES", timeframe="1d", timezone="UTC", name="ds",
    )
    module = write_module(tmp_path, DETERMINISTIC, "det_ds")
    raw = {
        "hypothesis": "H-TST-01", "objective": "o", "author": "a",
        "experiment": {"module": module, "parameters": {}, "dataset": "ds"},
        "seeds": [0],
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    cfg = load_config(str(path))
    rec = run_atomic(store, cfg, cfg.plan()[0], "cfg", cwd=str(tmp_path))
    assert rec.status == "completed"
    blob = store.dataset_object_path(dataset)
    blob.write_bytes(b"tampered!")
    report = reproduce(store, rec.uuid, cwd=str(tmp_path))
    assert report["status"] == "unverifiable"
    assert report["re_executed"] is False
    assert any(c["name"] == "dataset" and not c["ok"] for c in report["preconditions"])


def test_reproduce_failed_experiment_raises(tmp_path, store):
    rec = run_one(tmp_path, store, FAILING, name="failing_mod")
    assert rec.status == "failed"
    with pytest.raises(ReproduceError, match="only completed runs"):
        reproduce(store, rec.uuid, cwd=str(tmp_path))


def test_reproduce_no_runs_raises(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_noruns")
    import sqlite3

    conn = sqlite3.connect(str(store.db_path))
    conn.execute("DELETE FROM runs WHERE experiment_uuid = ?", (rec.uuid,))
    conn.commit()
    conn.close()
    with pytest.raises(ReproduceError, match="no recorded run"):
        reproduce(store, rec.uuid, cwd=str(tmp_path))


def test_audit_static_report(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_audit")
    report = audit(store, rec.uuid, cwd=str(tmp_path))
    assert report["uuid"] == rec.uuid
    assert report["reproducible_in_place"] is True
    assert {c["name"] for c in report["preconditions"]} >= {"git", "dataset", "module"}
    assert all(c["ok"] for c in report["preconditions"])
    # Artifacts section: no artifacts here, so it's just present.
    assert report["artifacts"] == []
    # After mutation the audit flips.
    (tmp_path / "m_audit.py").write_text("x = 1\n", encoding="utf-8")
    report = audit(store, rec.uuid, cwd=str(tmp_path))
    assert report["reproducible_in_place"] is False
    module_check = next(c for c in report["preconditions"] if c["name"] == "module")
    assert module_check["ok"] is False


def test_audit_preconditions_list(tmp_path, store):
    rec = run_one(tmp_path, store, DETERMINISTIC, name="m_checks")
    checks = audit_preconditions(store, rec.uuid, cwd=str(tmp_path))
    names = [c.name for c in checks]
    assert "git" in names and "dataset" in names and "module" in names
    git_check = next(c for c in checks if c.name == "git")
    assert git_check.ok is True  # outside git => recorded commit None, non-blocking
