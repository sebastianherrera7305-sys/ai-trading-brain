"""
Registry — AI Trading Brain, Subsystem 2 (see docs/specs/02-registry.md)

ARCHITECTURE.md §30: "the security boundary between research and
capital." Nothing crosses from the offline research loop to the online
execution loop except through here. This module owns the one piece of
business logic storage.py deliberately doesn't have: which status
transitions are legal. Storage stays a dumb leaf (ARCHITECTURE.md §6);
this is where "research -> live" without passing through "shadow" and
"paper" first gets rejected outright, not silently recorded.

Status history is an append-only transition log, not a mutable column --
see ADR-0002 (docs/adr/0002-registry-status-history-is-append-only.md)
for why that's a deliberate correction to the frozen ADD's own §32
sketch, made before writing this module rather than after.
"""

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set

from .storage import (
    ArtifactRecord,
    ExperimentRecord,
    ExperimentRepository,
    RegistryArtifactRepository,
    RegistryStatusTransitionRepository,
    StatusTransitionRecord,
    Storage,
)


class ArtifactType(str, Enum):
    STRATEGY = "strategy"
    AI_MODEL = "ai_model"


class ArtifactStatus(str, Enum):
    RESEARCH = "research"
    SHADOW = "shadow"
    PAPER = "paper"
    LIVE = "live"
    RETIRED = "retired"


_ALLOWED_TRANSITIONS: Dict[ArtifactStatus, Set[ArtifactStatus]] = {
    ArtifactStatus.RESEARCH: {ArtifactStatus.SHADOW, ArtifactStatus.RETIRED},
    ArtifactStatus.SHADOW: {ArtifactStatus.PAPER, ArtifactStatus.RETIRED},
    ArtifactStatus.PAPER: {ArtifactStatus.LIVE, ArtifactStatus.RETIRED},
    ArtifactStatus.LIVE: {ArtifactStatus.RETIRED},
    ArtifactStatus.RETIRED: set(),
}


class IllegalTransitionError(Exception):
    def __init__(self, artifact_id: str, from_status: ArtifactStatus, to_status: ArtifactStatus):
        super().__init__(
            f"artifact {artifact_id!r} cannot move from {from_status.value!r} to {to_status.value!r} "
            f"-- allowed from {from_status.value!r}: "
            f"{sorted(s.value for s in _ALLOWED_TRANSITIONS[from_status])}"
        )
        self.artifact_id = artifact_id
        self.from_status = from_status
        self.to_status = to_status


class UnknownArtifactError(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Registry:
    def __init__(self, storage: Storage):
        self._experiments = ExperimentRepository(storage)
        self._artifacts = RegistryArtifactRepository(storage)
        self._transitions = RegistryStatusTransitionRepository(storage)

    def register_experiment(self, experiment: ExperimentRecord) -> None:
        self._experiments.insert(experiment)

    def register_artifact(
        self, artifact_id: str, artifact_type: ArtifactType, version: str, source_experiment_id: str,
    ) -> None:
        """The only way an artifact enters the registry. Always starts at
        RESEARCH -- there is no path to register something already
        further along; it must be promoted there like everything else."""
        self._artifacts.insert(ArtifactRecord(
            artifact_id=artifact_id, artifact_type=artifact_type.value, version=version,
            source_experiment_id=source_experiment_id, created_at=_now(),
        ))
        self._transitions.insert(StatusTransitionRecord(
            artifact_id=artifact_id, status=ArtifactStatus.RESEARCH.value,
            transitioned_at=_now(), promoted_by="system:register_artifact",
            promotion_checklist_snapshot=None,
        ))

    def promote(
        self, artifact_id: str, to_status: ArtifactStatus, promoted_by: str,
        promotion_checklist_snapshot: Optional[dict] = None,
    ) -> None:
        current = self.current_status(artifact_id)
        if current is None:
            raise UnknownArtifactError(f"artifact {artifact_id!r} is not registered")
        if to_status not in _ALLOWED_TRANSITIONS[current]:
            raise IllegalTransitionError(artifact_id, current, to_status)

        snapshot_json = json.dumps(promotion_checklist_snapshot) if promotion_checklist_snapshot else None
        self._transitions.insert(StatusTransitionRecord(
            artifact_id=artifact_id, status=to_status.value, transitioned_at=_now(),
            promoted_by=promoted_by, promotion_checklist_snapshot=snapshot_json,
        ))

    def current_status(self, artifact_id: str) -> Optional[ArtifactStatus]:
        latest = self._transitions.latest(artifact_id)
        return ArtifactStatus(latest.status) if latest else None

    def status_as_of(self, artifact_id: str, at: datetime) -> Optional[ArtifactStatus]:
        row = self._transitions.latest_as_of(artifact_id, at)
        return ArtifactStatus(row.status) if row else None

    def history(self, artifact_id: str) -> List[StatusTransitionRecord]:
        return self._transitions.history(artifact_id)

    def live_artifacts(self, artifact_type: Optional[ArtifactType] = None) -> List[ArtifactRecord]:
        live_ids = {
            t.artifact_id for t in self._transitions.all_latest() if t.status == ArtifactStatus.LIVE.value
        }
        results = [a for a in self._artifacts.all() if a.artifact_id in live_ids]
        if artifact_type is not None:
            results = [a for a in results if a.artifact_type == artifact_type.value]
        return results
