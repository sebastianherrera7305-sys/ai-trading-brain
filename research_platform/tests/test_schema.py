"""Tests for record schemas and validation."""

import pytest

from research_platform.schema import (
    DatasetRecord,
    ExperimentRecord,
    ReproductionRecord,
    RunRecord,
    ValidationError,
    _validate_params,
)


def test_dataset_manifest_round_trip():
    rec = DatasetRecord(
        id="id-1", name="es-daily", source="vendor-a", provider="p",
        version="1.0", symbol="ES", timeframe="1d", timezone="America/New_York",
        pipeline="ohlcv", feature_version="v2", checksum="abc",
        file_name="es.csv", total_bytes=42, created_at="2024-01-01T00:00:00Z",
        meta={"note": "x"},
    )
    restored = DatasetRecord.from_manifest(rec.manifest())
    assert restored == rec


def test_dataset_require_fields():
    DatasetRecord.require_fields(dict(
        source="a", provider="b", version="c", symbol="d",
        timeframe="e", timezone="f", checksum="g",
    ))
    with pytest.raises(ValidationError, match="symbol"):
        DatasetRecord.require_fields(dict(
            source="a", provider="b", version="c", symbol="",
            timeframe="e", timezone="f", checksum="g",
        ))
    with pytest.raises(ValidationError, match="checksum"):
        DatasetRecord.require_fields(dict(
            source="a", provider="b", version="c", symbol="d",
            timeframe="e", timezone="f", checksum="",
        ))


def test_params_forbid_seed():
    with pytest.raises(ValidationError, match="must not declare 'seed'"):
        _validate_params({"seed": 3})
    with pytest.raises(ValidationError, match="JSON object"):
        _validate_params([1, 2])  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="non-JSON-safe"):
        _validate_params({"x": object()})


def test_experiment_validate_meta():
    good = dict(hypothesis="H-TST-01", objective="o", author="a", seed=0, status="queued")
    ExperimentRecord.validate_meta(**good)
    for field in ("hypothesis", "objective", "author"):
        bad = dict(good)
        bad[field] = "  "
        with pytest.raises(ValidationError, match=field):
            ExperimentRecord.validate_meta(**bad)
    with pytest.raises(ValidationError, match="seed"):
        ExperimentRecord.validate_meta(**{**good, "seed": 1.5})
    with pytest.raises(ValidationError, match="status"):
        ExperimentRecord.validate_meta(**{**good, "status": "nonsense"})


def test_experiment_validate_meta_requires_canonical_hypothesis_id():
    with pytest.raises(ValidationError, match="canonical catalog ID"):
        ExperimentRecord.validate_meta(
            hypothesis="Overnight gaps tend to continue", objective="o",
            author="a", seed=0, status="queued",
        )


def test_experiment_summary():
    rec = ExperimentRecord(
        uuid="u", hypothesis="H-TST-01", objective="o", author="a",
        created_at="t", dataset_id=None, params={}, seed=1,
        status="completed", config_hash="c", module="m", function="run",
        module_checksum="mc",
    )
    assert "u" in rec.summary() and "seed=1" in rec.summary()


def test_run_validate_result():
    run = RunRecord(experiment_uuid="u", run_number=1, status="completed")
    run.validate_result()
    run.metrics = {"x": object()}
    with pytest.raises(ValidationError, match="non-JSON-safe"):
        run.validate_result()
    run.metrics = {"x": 1}
    run.tests = [{"statistic": 1}]  # missing name
    with pytest.raises(ValidationError, match="name"):
        run.validate_result()
    run.tests = [{"name": "t", "statistic": 1.0, "p_value": 0.5, "conclusion": "pass"}]
    run.validate_result()


def test_run_to_db():
    run = RunRecord(
        experiment_uuid="u", run_number=2, status="completed",
        metrics={"m": 1}, tests=[{"name": "t"}],
    )
    db = run.to_db()
    assert db["run_number"] == 2
    import json

    assert json.loads(db["metrics"]) == {"m": 1}


def test_reproduction_record_defaults():
    rec = ReproductionRecord(
        original_uuid="u", run_number=1, status="matched", new_run_number=2,
        max_metric_abs_diff=0.0, metric_names=["m"], explanation="ok",
    )
    assert rec.checked_at.endswith("Z")
