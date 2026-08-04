"""Tests for the Registry (Subsystem 2, docs/specs/02-registry.md)."""

from datetime import datetime, timedelta, timezone

import pytest

from trading_brain.registry import (
    ArtifactStatus,
    ArtifactType,
    IllegalTransitionError,
    Registry,
    UnknownArtifactError,
)
from trading_brain.storage import ExperimentRecord, RegistryArtifactRepository, RegistryStatusTransitionRepository, Storage


@pytest.fixture
def registry():
    s = Storage(":memory:")
    s.migrate()
    r = Registry(s)
    r.register_experiment(ExperimentRecord(
        experiment_id="exp-1", experiment_type="walk_forward", code_git_hash="abc123",
        config_json="{}", metrics_json="{}",
    ))
    return r


def test_register_artifact_creates_one_artifact_row_and_one_research_transition(registry):
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    assert registry.current_status("strat-1") == ArtifactStatus.RESEARCH
    history = registry.history("strat-1")
    assert len(history) == 1
    assert history[0].status == ArtifactStatus.RESEARCH.value


def test_legal_promotion_path_succeeds_at_each_step(registry):
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    registry.promote("strat-1", ArtifactStatus.SHADOW, promoted_by="human:test")
    assert registry.current_status("strat-1") == ArtifactStatus.SHADOW
    registry.promote("strat-1", ArtifactStatus.PAPER, promoted_by="human:test")
    assert registry.current_status("strat-1") == ArtifactStatus.PAPER
    registry.promote("strat-1", ArtifactStatus.LIVE, promoted_by="human:test")
    assert registry.current_status("strat-1") == ArtifactStatus.LIVE
    registry.promote("strat-1", ArtifactStatus.RETIRED, promoted_by="human:test")
    assert registry.current_status("strat-1") == ArtifactStatus.RETIRED


def test_illegal_transition_is_rejected_and_writes_no_row(registry):
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")

    with pytest.raises(IllegalTransitionError):
        registry.promote("strat-1", ArtifactStatus.LIVE, promoted_by="human:test")

    # rejected attempt must leave zero trace, not a second row
    assert registry.current_status("strat-1") == ArtifactStatus.RESEARCH
    assert len(registry.history("strat-1")) == 1


def test_no_transitions_are_legal_out_of_retired(registry):
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    registry.promote("strat-1", ArtifactStatus.RETIRED, promoted_by="human:test")

    with pytest.raises(IllegalTransitionError):
        registry.promote("strat-1", ArtifactStatus.SHADOW, promoted_by="human:test")


def test_promote_unknown_artifact_raises():
    s = Storage(":memory:")
    s.migrate()
    registry = Registry(s)
    with pytest.raises(UnknownArtifactError):
        registry.promote("nope", ArtifactStatus.SHADOW, promoted_by="human:test")


def test_status_as_of_reflects_the_state_at_a_point_in_time_not_just_now(registry):
    """The entire reason for ADR-0002: history must be queryable at a
    timestamp, not just as 'current status'."""
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    t_research = datetime.now(timezone.utc)

    registry.promote("strat-1", ArtifactStatus.SHADOW, promoted_by="human:test")
    t_shadow = datetime.now(timezone.utc)

    registry.promote("strat-1", ArtifactStatus.PAPER, promoted_by="human:test")
    registry.promote("strat-1", ArtifactStatus.LIVE, promoted_by="human:test")

    assert registry.status_as_of("strat-1", t_research) == ArtifactStatus.RESEARCH
    assert registry.status_as_of("strat-1", t_shadow) == ArtifactStatus.SHADOW
    assert registry.current_status("strat-1") == ArtifactStatus.LIVE
    # before the artifact even existed
    assert registry.status_as_of("strat-1", t_research - timedelta(days=1)) is None


def test_live_artifacts_returns_only_currently_live_ones_filtered_by_type(registry):
    registry.register_experiment(ExperimentRecord(
        experiment_id="exp-2", experiment_type="model_training", code_git_hash="def456",
        config_json="{}", metrics_json="{}",
    ))
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    registry.register_artifact("strat-2", ArtifactType.STRATEGY, "v1", "exp-1")
    registry.register_artifact("model-1", ArtifactType.AI_MODEL, "v1", "exp-2")

    for artifact_id in ("strat-1", "model-1"):
        registry.promote(artifact_id, ArtifactStatus.SHADOW, promoted_by="human:test")
        registry.promote(artifact_id, ArtifactStatus.PAPER, promoted_by="human:test")
        registry.promote(artifact_id, ArtifactStatus.LIVE, promoted_by="human:test")
    # strat-2 stays in RESEARCH -- must not appear in live_artifacts()

    all_live = registry.live_artifacts()
    assert {a.artifact_id for a in all_live} == {"strat-1", "model-1"}

    strategies_only = registry.live_artifacts(ArtifactType.STRATEGY)
    assert {a.artifact_id for a in strategies_only} == {"strat-1"}


def test_promotion_checklist_snapshot_is_stored_and_retrievable(registry):
    registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "exp-1")
    registry.promote(
        "strat-1", ArtifactStatus.SHADOW, promoted_by="human:sebastian",
        promotion_checklist_snapshot={"min_oos_trades": 30, "actual_oos_trades": 45},
    )
    latest = registry.history("strat-1")[-1]
    assert latest.promoted_by == "human:sebastian"
    assert "min_oos_trades" in latest.promotion_checklist_snapshot


def test_registry_artifact_repository_has_no_update_or_delete():
    assert not hasattr(RegistryArtifactRepository, "update")
    assert not hasattr(RegistryArtifactRepository, "delete")


def test_registry_status_transition_repository_has_no_update_or_delete():
    assert not hasattr(RegistryStatusTransitionRepository, "update")
    assert not hasattr(RegistryStatusTransitionRepository, "delete")


def test_register_artifact_with_unknown_experiment_fails(registry):
    with pytest.raises(Exception):  # DuckDB FK violation -- storage stays a dumb leaf, doesn't wrap it
        registry.register_artifact("strat-1", ArtifactType.STRATEGY, "v1", "does-not-exist")
