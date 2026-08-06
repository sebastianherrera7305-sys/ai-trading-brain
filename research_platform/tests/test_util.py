"""Tests for the private utilities: canonical JSON, hashing, env and
git snapshots, and reproducibility comparisons."""

import json
import os

import numpy as np
import pytest

from research_platform._util import (
    canonical_json,
    env_snapshot,
    float_eq,
    git_state,
    metrics_match,
    sha256_bytes,
    sha256_file,
    sha256_text,
    to_json_safe,
    utcnow,
)


def test_utcnow_format():
    stamp = utcnow()
    assert stamp.endswith("Z")
    assert "T" in stamp


def test_canonical_json_deterministic():
    a = {"b": 1, "a": [3, 2], "c": {"z": None, "y": True}}
    b = {"c": {"y": True, "z": None}, "a": [3, 2], "b": 1}
    assert canonical_json(a) == canonical_json(b)
    assert " " not in canonical_json(a)


def test_to_json_safe_numpy():
    assert to_json_safe(np.float64(1.5)) == 1.5
    assert to_json_safe(np.int64(7)) == 7
    assert to_json_safe(np.array([[1, 2], [3, 4]])) == [[1, 2], [3, 4]]
    assert to_json_safe((1, "x")) == [1, "x"]
    assert to_json_safe(b"hi").startswith("base64:")


def test_to_json_safe_rejects_complex():
    with pytest.raises(TypeError):
        to_json_safe(complex(1, 2))
    with pytest.raises(TypeError):
        to_json_safe(np.array([1 + 2j]))


def test_to_json_safe_rejects_objects():
    with pytest.raises(TypeError):
        to_json_safe(object())


def test_sha256_known_vectors():
    assert sha256_text("hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
    assert sha256_bytes(b"hello") == sha256_text("hello")
    import tempfile

    with tempfile.NamedTemporaryFile("wb", suffix=".txt") as fh:
        fh.write(b"hello")
        fh.flush()
        assert sha256_file(fh.name) == sha256_text("hello")


def test_git_state_in_git_repo(tmp_path):
    state = git_state(os.getcwd())
    assert state is not None
    assert len(state["commit"]) == 40
    assert state["repo"]
    assert isinstance(state["dirty"], bool)


def test_git_state_outside_repo(tmp_path):
    assert git_state(str(tmp_path)) is None


def test_env_snapshot_keys():
    snap = env_snapshot(os.getcwd())
    for key in ("python_version", "platform", "numpy_version", "git", "cwd"):
        assert key in snap
    assert "PYTHONHASHSEED" in snap["env"]


def test_float_eq():
    assert float_eq(1.0, 1.0 + 1e-13)
    assert not float_eq(1.0, 1.001)


def test_metrics_match_equal():
    assert metrics_match({"a": 1.0, "b": {"c": 2}}, {"a": 1.0, "b": {"c": 2}}) == 0.0


def test_metrics_match_float_tolerance():
    assert metrics_match(1.0, 1.0 + 1e-13) == pytest.approx(1e-13)
    assert metrics_match(1.0, 1.5) is None


def test_metrics_match_structural_mismatch():
    assert metrics_match({"a": 1}, {"a": 1, "b": 2}) is None
    assert metrics_match([1, 2], [1]) is None
    assert metrics_match(1, "x") is None
    assert metrics_match([1, "a"], [1, "b"]) is None
    assert metrics_match(None, 1) is None
    assert metrics_match(True, False) is None
