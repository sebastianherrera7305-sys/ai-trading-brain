"""Tests for the research store: datasets, experiments, runs,
reproductions, and the immutable-storage invariants."""

import os

import pytest

from research_platform.schema import (
    ExperimentRecord,
    ReproductionRecord,
    RunRecord,
    ValidationError,
)
from research_platform.store import ResearchStore, StoreError, open_store


@pytest.fixture
def store(tmp_path):
    s = open_store(str(tmp_path / "research"))
    yield s
    s.close()


def write_data(tmp_path, name="data.csv", content=b"1,2,3\n4,5,6\n"):
    path = tmp_path / name
    path.write_bytes(content)
    return str(path)


def register(store, tmp_path, **overrides):
    kwargs = dict(
        file_path=write_data(
            tmp_path,
            name=overrides.pop("fname", "data.csv"),
            content=overrides.pop("content", b"1,2,3\n4,5,6\n"),
        ),
        source="vendor",
        provider="p",
        version="1.0",
        symbol="ES",
        timeframe="1d",
        timezone="America/New_York",
        name="es-daily",
    )
    kwargs.update(overrides)
    return store.register_dataset(**kwargs)


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------

def test_register_dataset_records_manifest(tmp_path):
    store = open_store(str(tmp_path / "r"))
    rec = register(store, tmp_path)
    manifest_path = store.datasets_dir / rec.id / "manifest.json"
    assert manifest_path.is_file()
    store.close()


def test_register_requires_fields(tmp_path):
    store = open_store(str(tmp_path / "r"))
    with pytest.raises(ValidationError, match="timezone"):
        register(store, tmp_path, timezone="")
    store.close()


def test_register_missing_file(tmp_path):
    store = open_store(str(tmp_path / "r"))
    with pytest.raises(StoreError, match="not found"):
        store.register_dataset(
            str(tmp_path / "missing.csv"), source="s", provider="p",
            version="v", symbol="S", timeframe="1d", timezone="UTC",
        )
    store.close()


def test_register_idempotent_per_content(tmp_path):
    store = open_store(str(tmp_path / "r"))
    a = register(store, tmp_path, name="one")
    b = register(store, tmp_path, name="two")  # same bytes, same checksum
    assert a.checksum == b.checksum
    assert a.id != b.id
    blob_a = store.dataset_object_path(a)
    blob_b = store.dataset_object_path(b)
    assert blob_a == blob_b  # content-addressed: one physical copy
    store.close()


def test_get_dataset_by_id_and_name(tmp_path):
    store = open_store(str(tmp_path / "r"))
    rec = register(store, tmp_path)
    assert store.get_dataset(rec.id).id == rec.id
    assert store.get_dataset("es-daily").id == rec.id
    with pytest.raises(StoreError, match="unknown"):
        store.get_dataset("nope")
    store.close()


def test_list_datasets_order(tmp_path):
    store = open_store(str(tmp_path / "r"))
    register(store, tmp_path, name="first")
    register(store, tmp_path, name="second", content=b"other bytes")
    names = [d.name for d in store.list_datasets()]
    assert names == ["second", "first"]  # created_at DESC
    store.close()


def test_verify_dataset_and_immutability(tmp_path):
    store = open_store(str(tmp_path / "r"))
    rec = register(store, tmp_path)
    check = store.verify_dataset(rec.id)
    assert check["ok"] is True
    assert check["checksum"] == rec.checksum
    # Tamper with the blob: verification must catch it.
    blob = store.dataset_object_path(rec)
    blob.write_bytes(b"tampered!")
    check = store.verify_dataset(rec.id)
    assert check["ok"] is False
    assert check["actual"] != check["checksum"]
    store.close()


def test_verify_missing_blob(tmp_path):
    store = open_store(str(tmp_path / "r"))
    rec = register(store, tmp_path)
    os.remove(store.dataset_object_path(rec))
    check = store.verify_dataset(rec.id)
    assert check["ok"] is False
    assert "missing" in check["reason"]
    store.close()


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

def make_experiment(store, uuid="exp-1", params=None, seed=0, status="created"):
    return ExperimentRecord(
        uuid=uuid, hypothesis="h", objective="o", author="a",
        created_at="2024-01-01T00:00:00Z", dataset_id=None,
        params=params or {}, seed=seed, status=status,
        config_hash="cfg-1", module="m", function="run", module_checksum="",
        assumptions=["momentum persists"], tags=["momentum"],
    )


def test_create_and_get_experiment(store):
    rec = make_experiment(store, uuid="exp-1")
    store.create_experiment(rec)
    got = store.get_experiment("exp-1")
    assert got.uuid == "exp-1"
    assert got.assumptions == ["momentum persists"]
    assert got.tags == ["momentum"]


def test_create_rejects_bad_params(store):
    rec = make_experiment(store, uuid="exp-1", params={"x": object()})
    with pytest.raises(ValidationError, match="JSON-safe"):
        store.create_experiment(rec)


def test_create_rejects_seed_in_params(store):
    rec = make_experiment(store, uuid="exp-1", params={"seed": 1})
    with pytest.raises(ValidationError, match="must not declare"):
        store.create_experiment(rec)


def test_create_rejects_duplicate_uuid(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    with pytest.raises(StoreError, match="rejected"):
        store.create_experiment(make_experiment(store, uuid="exp-1"))


def test_set_status_and_module_checksum(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    store.set_module_checksum("exp-1", "abc123")
    store.set_status("exp-1", "completed", finished_at="t", runtime_seconds=1.0)
    rec = store.get_experiment("exp-1")
    assert rec.module_checksum == "abc123"
    assert rec.status == "completed"
    assert rec.runtime_seconds == 1.0


def test_find_experiments_filters(store):
    store.create_experiment(make_experiment(
        store, uuid="a", params={"w": 1}, status="completed",
    ))
    b = make_experiment(store, uuid="b", params={"w": 2}, status="failed")
    b.tags = ["other"]
    b.assumptions = ["different"]
    b.author = "other-author"
    b.sweep_id = "sweep-1"
    store.create_experiment(b)
    assert [e.uuid for e in store.find_experiments(status="completed")] == ["a"]
    assert [e.uuid for e in store.find_experiments(tag="other")] == ["b"]
    assert [e.uuid for e in store.find_experiments(assumption="different")] == ["b"]
    assert [e.uuid for e in store.find_experiments(sweep_id="sweep-1")] == ["b"]
    assert [e.uuid for e in store.find_experiments(author="other-author")] == ["b"]
    assert [e.uuid for e in store.find_experiments(limit=1)] == ["a"]


def test_get_experiment_unknown(store):
    with pytest.raises(StoreError, match="unknown"):
        store.get_experiment("nope")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

def test_run_numbering_and_save(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    assert store.next_run_number("exp-1") == 1
    store.save_run(RunRecord(
        experiment_uuid="exp-1", run_number=1, status="completed",
        metrics={"m": 1.0}, tests=[{"name": "t", "statistic": 1.0}],
    ))
    assert store.next_run_number("exp-1") == 2
    runs = store.get_runs("exp-1")
    assert len(runs) == 1
    assert runs[0].metrics == {"m": 1.0}


def test_save_run_rejects_invalid_result(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    with pytest.raises(ValidationError, match="metrics"):
        store.save_run(RunRecord(
            experiment_uuid="exp-1", run_number=1, status="completed",
            metrics={"m": object()},
        ))


def test_get_latest_run(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    store.save_run(RunRecord(
        experiment_uuid="exp-1", run_number=1, status="completed", metrics={"m": 1},
    ))
    store.save_run(RunRecord(
        experiment_uuid="exp-1", run_number=2, status="failed", metrics={},
    ))
    latest = store.get_latest_run("exp-1")
    assert latest.run_number == 2
    assert latest.status == "failed"
    assert store.get_latest_run("exp-2") is None


# ---------------------------------------------------------------------------
# Reproductions
# ---------------------------------------------------------------------------

def test_reproduction_round_trip(store):
    rec = ReproductionRecord(
        original_uuid="exp-1", run_number=1, status="matched", new_run_number=2,
        max_metric_abs_diff=0.0, metric_names=["m"], explanation="ok",
        checked_at="2024-01-02T00:00:00Z",
    )
    store.record_reproduction(rec)
    rows = store.get_reproductions("exp-1")
    assert len(rows) == 1
    assert rows[0].status == "matched"
    assert rows[0].max_metric_abs_diff == 0.0
    assert rows[0].metric_names == ["m"]


# ---------------------------------------------------------------------------
# Filesystem layout
# ---------------------------------------------------------------------------

def test_fs_layout(store):
    store.create_experiment(make_experiment(store, uuid="exp-1"))
    assert store.experiment_dir("exp-1").is_dir()
    run_dir = store.run_dir("exp-1", 1)
    assert run_dir.is_dir()
    store.save_experiment_manifest(store.get_experiment("exp-1"))
    manifest = store.experiment_dir("exp-1") / "manifest.json"
    assert manifest.is_file()
    import json

    doc = json.loads(manifest.read_text())
    assert doc["uuid"] == "exp-1"


def test_config_storage(store):
    cfg = {"hypothesis": "h", "seeds": [0]}
    h = store.record_config(cfg)
    assert h == store.config_hash(cfg)
    assert (store.configs_dir / ("%s.json" % h)).is_file()
    store.record_config(cfg)  # idempotent
    assert len(list(store.configs_dir.glob("*.json"))) == 1
