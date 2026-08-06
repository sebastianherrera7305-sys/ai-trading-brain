"""Tests for the C002 trial-matrix evidence selection (R1 fix).

The assembly must gate every candidate run on the B3 eligibility
criteria (completed, clean git tree, full metadata) and must REPORT
excluded candidates — an ineligible (e.g. dirty-tree smoke) run can
never become a DSR/Reality Check input.
"""

import importlib.util
import pathlib
import sys

import pytest

from research_platform.schema import ExperimentRecord, RunRecord
from research_platform.store import open_store

_STUDIES = pathlib.Path(__file__).resolve().parents[1] / "research_studies"
sys.path.insert(0, str(_STUDIES))

_spec = importlib.util.spec_from_file_location(
    "c002_assembly",
    _STUDIES / "gap_fading" / "assemble_trial_matrix.py",
)
asm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(asm)


@pytest.fixture
def store(tmp_path):
    s = open_store(str(tmp_path / "research"))
    yield s
    s.close()


class _Exp:
    def __init__(self, uuid="exp", git_dirty=None, git_commit=None):
        self.uuid = uuid
        self.git_dirty = git_dirty
        self.git_commit = git_commit


class _Run:
    def __init__(self, status="completed", env=None):
        self.status = status
        self.env = env


class _FakeStore:
    def __init__(self, run):
        self.run = run

    def get_latest_run(self, uuid):
        return self.run


def _mk(store, uuid, created_at, params, env, git_dirty=None,
        exp_status="completed", run_status="completed"):
    rec = ExperimentRecord(
        uuid=uuid, hypothesis="H-MS-01", objective="t", author="t",
        created_at=created_at, dataset_id=None, params=params, seed=0,
        status=exp_status, config_hash="c", module="gap_fading",
        function="run", module_checksum="m", git_dirty=git_dirty,
    )
    store.create_experiment(rec)
    run = RunRecord(
        experiment_uuid=uuid, run_number=1, status=run_status,
        metrics={"ann_sharpe": 0.5}, env=env,
    )
    store.save_run(run)
    return rec


CELL = {"threshold_pct": 0.5, "hold_days": 1, "direction": "both", "cost_bps": 0.0}


# ---------------------------------------------------------------------------
# _is_eligible_run
# ---------------------------------------------------------------------------

def test_eligible_run_accepts_clean_completed():
    exp = _Exp()
    run = _Run(env={"git": {"commit": "abc", "dirty": False},
                    "quant_research_version": "0.3.0"})
    ok, reason = asm._is_eligible_run(_FakeStore(run), exp)
    assert ok is True
    assert "eligible" in reason


def test_eligible_run_rejects_unverifiable_marker():
    exp = _Exp()
    run = _Run(env={"unverifiable_reproduction": True,
                    "git": {"commit": "abc", "dirty": True}})
    ok, reason = asm._is_eligible_run(_FakeStore(run), exp)
    assert ok is False
    assert "UNVERIFIABLE_REPRODUCTION" in reason


def test_eligible_run_rejects_dirty_env_without_marker():
    exp = _Exp()
    run = _Run(env={"git": {"commit": "abc", "dirty": True}})
    ok, reason = asm._is_eligible_run(_FakeStore(run), exp)
    assert ok is False
    assert "dirty" in reason


def test_eligible_run_rejects_failed_run():
    exp = _Exp()
    run = _Run(status="failed", env={"git": {"commit": "a", "dirty": False}})
    ok, reason = asm._is_eligible_run(_FakeStore(run), exp)
    assert ok is False
    assert "not completed" in reason


def test_eligible_run_rejects_missing_run():
    ok, reason = asm._is_eligible_run(_FakeStore(None), _Exp())
    assert ok is False
    assert "no run" in reason


def test_eligible_run_rejects_missing_env_snapshot():
    exp = _Exp()
    ok, reason = asm._is_eligible_run(_FakeStore(_Run(env={})), exp)
    assert ok is False
    assert "environment snapshot" in reason


def test_eligible_run_rejects_dirty_record_flag():
    exp = _Exp(git_dirty=True, git_commit="abc")
    run = _Run(env={"git": {"commit": "abc", "dirty": False}})
    ok, reason = asm._is_eligible_run(_FakeStore(run), exp)
    assert ok is False
    assert "git_dirty=True" in reason


# ---------------------------------------------------------------------------
# ordered_cells — evidence selection on a real store
# ---------------------------------------------------------------------------

def _single_cell_grid(monkeypatch):
    monkeypatch.setattr(asm, "THRESHOLDS", [0.5])
    monkeypatch.setattr(asm, "HOLDS", [1])
    monkeypatch.setattr(asm, "DIRECTIONS", ["both"])


def test_ordered_cells_prefers_clean_over_smoke(store, monkeypatch, capsys):
    _single_cell_grid(monkeypatch)
    smoke = _mk(store, "11111111-1111-1111-1111-111111111111",
                "2026-08-06T01:00:00.000000Z", CELL,
                {"unverifiable_reproduction": True,
                 "git": {"commit": "abc", "dirty": True}}, git_dirty=True)
    clean = _mk(store, "22222222-2222-2222-2222-222222222222",
                "2026-08-06T02:00:00.000000Z", CELL,
                {"git": {"commit": "def", "dirty": False},
                 "quant_research_version": "0.3.0"})

    cells = asm.ordered_cells(store, "gap_fading")

    assert len(cells) == 1
    assert cells[(0.5, 1, "both")].uuid == clean.uuid
    out = capsys.readouterr().out
    assert "excluded" in out
    assert smoke.uuid[:8] in out
    assert "UNVERIFIABLE_REPRODUCTION" in out


def test_ordered_cells_refuses_ineligible_only_candidate(store, monkeypatch):
    _single_cell_grid(monkeypatch)
    _mk(store, "33333333-3333-3333-3333-333333333333",
        "2026-08-06T01:00:00.000000Z", CELL,
        {"unverifiable_reproduction": True,
         "git": {"commit": "abc", "dirty": True}}, git_dirty=True)

    with pytest.raises(RuntimeError, match="missing eligible"):
        asm.ordered_cells(store, "gap_fading")
