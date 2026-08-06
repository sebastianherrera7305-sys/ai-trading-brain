"""Tests for config loading, validation, and run planning."""

import json

import pytest

from research_platform.config import ExperimentConfig, load_config
from research_platform.schema import ValidationError


def write_config(tmp_path, raw):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return str(path)


BASE = {
    "hypothesis": "h",
    "objective": "o",
    "author": "a",
    "experiment": {"module": "examples.experiments.momentum_scan", "parameters": {"x": 1}},
    "seeds": [0, 1],
}


def test_load_and_defaults(tmp_path):
    cfg = load_config(write_config(tmp_path, BASE))
    assert cfg.hypothesis == "h"
    assert cfg.function == "run"
    assert cfg.seeds == [0, 1]
    assert cfg.experiment_count == 2
    assert cfg.has_sweep is False


def test_missing_file():
    with pytest.raises(ValidationError, match="not found"):
        load_config("/nonexistent/config.json")


def test_invalid_json():
    path = "/tmp/invalid-config.json"
    with open(path, "w") as fh:
        fh.write("{nope")
    try:
        with pytest.raises(ValidationError, match="valid JSON"):
            load_config(path)
    finally:
        import os

        os.remove(path)


def test_missing_required_keys(tmp_path):
    raw = dict(BASE)
    del raw["objective"]
    with pytest.raises(ValidationError, match="objective"):
        ExperimentConfig(raw)


def test_seeds_and_repeats_exclusive(tmp_path):
    with pytest.raises(ValidationError, match="not both"):
        ExperimentConfig({**BASE, "repeats": 3})


def test_repeats_expand_to_seeds():
    cfg = ExperimentConfig({
        "hypothesis": "h", "objective": "o", "author": "a",
        "experiment": {"module": "m", "parameters": {}},
        "repeats": 3,
    })
    assert cfg.seeds == [0, 1, 2]


def test_seed_in_parameters_rejected():
    with pytest.raises(ValidationError, match="must not declare 'seed'"):
        ExperimentConfig({**BASE, "experiment": {"module": "m", "parameters": {"seed": 5}}})


def test_negative_seed_rejected():
    with pytest.raises(ValidationError, match="non-negative"):
        ExperimentConfig({**BASE, "seeds": [0, -1]})


def test_empty_sweep_rejected():
    with pytest.raises(ValidationError, match="non-empty"):
        ExperimentConfig({**BASE, "sweep": {"parameter": "x", "values": []}})


def test_non_json_sweep_value_rejected():
    with pytest.raises(ValidationError):
        ExperimentConfig({**BASE, "sweep": {"parameter": "x", "values": [object()]}})


def test_plan_order_sweep_outer_seeds_inner():
    cfg = ExperimentConfig({
        **BASE,
        "sweep": {"parameter": "w", "values": [1, 2]},
    })
    plan = cfg.plan()
    assert cfg.experiment_count == 4
    assert [(p.sweep_value, p.seed) for p in plan] == [
        (1, 0), (1, 1), (2, 0), (2, 1),
    ]
    assert plan[0].params == {"x": 1, "w": 1}
    assert plan[2].repeat_index == 0


def test_plan_no_sweep():
    cfg = ExperimentConfig(BASE)
    plan = cfg.plan()
    assert [(p.sweep_value, p.seed) for p in plan] == [(None, 0), (None, 1)]
    for p in plan:
        assert p.sweep_parameter is None
        assert p.repeat_index == p.seed


def test_to_document_round_trip():
    cfg = ExperimentConfig({**BASE, "sweep": {"parameter": "w", "values": [1, 2]}})
    doc = cfg.to_document()
    assert doc["sweep"] == {"parameter": "w", "values": [1, 2]}
    assert doc["seeds"] == [0, 1]
    # The document is a legal config itself.
    ExperimentConfig(doc)
    cfg2 = ExperimentConfig({**BASE, "sweep": None})
    assert cfg2.to_document()["sweep"] is None
