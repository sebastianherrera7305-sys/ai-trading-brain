"""Typed records and validation for the research registry.

Every entity that the framework persists (datasets, experiments, runs,
reproductions) has a record class here with explicit validation, so that
no experiment can ever be created without the mandatory provenance
fields, and nothing is silently stored in a partial state.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ._util import canonical_json, utcnow

# ---------------------------------------------------------------------------
# Statuses
# ---------------------------------------------------------------------------

EXPERIMENT_STATUSES = ("created", "queued", "running", "completed", "failed", "aborted")
RUN_STATUSES = ("running", "completed", "failed")
REPRODUCTION_STATUSES = ("matched", "differed", "unverifiable")


class ValidationError(ValueError):
    """Raised when a record or config fails schema validation."""


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

@dataclass
class DatasetRecord:
    """An immutable registered dataset.

    Identity: ``id`` (UUID) recorded in the manifest; immutability is
    enforced by content-addressed blob storage keyed on ``checksum``
    (SHA-256 of the file bytes) — once registered, the bytes at a given
    id can never change, and ``verify_dataset`` re-checks them.
    """

    id: str
    name: Optional[str]
    source: str
    provider: str
    version: str
    symbol: str
    timeframe: str
    timezone: str
    pipeline: str
    feature_version: str
    checksum: str
    file_name: str
    total_bytes: int
    created_at: str
    meta: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def require_fields(fields: Dict[str, Any]) -> None:
        missing = [k for k in (
            "source", "provider", "version", "symbol", "timeframe", "timezone"
        ) if not str(fields.get(k) or "").strip()]
        if missing:
            raise ValidationError(
                "dataset registration is missing required fields: %s"
                % ", ".join(missing)
            )
        if not str(fields.get("checksum") or "").strip():
            raise ValidationError("dataset registration is missing the content checksum")

    def manifest(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "provider": self.provider,
            "version": self.version,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timezone": self.timezone,
            "pipeline": self.pipeline,
            "feature_version": self.feature_version,
            "checksum": self.checksum,
            "file_name": self.file_name,
            "total_bytes": self.total_bytes,
            "created_at": self.created_at,
            "meta": self.meta,
        }

    @staticmethod
    def from_manifest(m: Dict[str, Any]) -> "DatasetRecord":
        return DatasetRecord(
            id=m["id"],
            name=m.get("name"),
            source=m["source"],
            provider=m["provider"],
            version=m["version"],
            symbol=m["symbol"],
            timeframe=m["timeframe"],
            timezone=m["timezone"],
            pipeline=m.get("pipeline", ""),
            feature_version=m.get("feature_version", ""),
            checksum=m["checksum"],
            file_name=m["file_name"],
            total_bytes=m["total_bytes"],
            created_at=m["created_at"],
            meta=m.get("meta", {}),
        )


# ---------------------------------------------------------------------------
# Experiment
# ---------------------------------------------------------------------------

def _validate_params(params: Dict[str, Any]) -> None:
    if not isinstance(params, dict):
        raise ValidationError("parameters must be a JSON object")
    if "seed" in params:
        raise ValidationError(
            "parameters must not declare 'seed': seeds are declared at the "
            "config top level so the framework controls determinism"
        )
    # Force a full JSON round-trip so non-JSON-safe values fail here,
    # at creation time, not in the middle of a sweep.
    try:
        canonical_json(params)
    except Exception as exc:  # noqa: BLE001
        raise ValidationError("parameters contain non-JSON-safe values: %s" % exc)


@dataclass
class ExperimentRecord:
    """A single atomic execution unit.

    One experiment = one parameter set x one seed x one dataset snapshot.
    Sweeps and repeats are materialized as sibling experiments sharing
    ``sweep_id`` and ``config_hash``, which keeps every atomic result
    individually traceable and individually reproducible.
    """

    uuid: str
    hypothesis: str
    objective: str
    author: str
    created_at: str
    dataset_id: Optional[str]
    params: Dict[str, Any]
    seed: int
    status: str
    config_hash: str
    module: str
    function: str
    module_checksum: str
    assumptions: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    sweep_id: Optional[str] = None
    sweep_parameter: Optional[str] = None
    sweep_value: Optional[Any] = None
    repeat_index: int = 0
    git_commit: Optional[str] = None
    git_repo: Optional[str] = None
    git_dirty: Optional[bool] = None
    status_changed_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    runtime_seconds: Optional[float] = None
    failure_reason: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def validate_meta(
        hypothesis: str, objective: str, author: str, seed: int, status: str
    ) -> None:
        for name, value in (
            ("hypothesis", hypothesis),
            ("objective", objective),
            ("author", author),
        ):
            if not str(value or "").strip():
                raise ValidationError("%s must be a non-empty string" % name)
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValidationError("seed must be an integer")
        if status not in EXPERIMENT_STATUSES:
            raise ValidationError("invalid experiment status: %s" % status)

    def summary(self) -> str:
        return (
            "experiment %s (%s) seed=%d status=%s"
            % (self.uuid[:8], self.module, self.seed, self.status)
        )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    """The durable record of one execution of an experiment.

    Contains everything the reproducibility engine needs: metrics,
    statistical tests, artifacts (with checksums), logs, environment,
    git state, and the canonical result checksum.
    """

    experiment_uuid: str
    run_number: int
    status: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    tests: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    log_path: Optional[str] = None
    env: Dict[str, Any] = field(default_factory=dict)
    result_checksum: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    runtime_seconds: Optional[float] = None
    failure_reason: Optional[str] = None

    def validate_result(self) -> None:
        """Validate the experiment's returned payload (called by runner)."""
        if not isinstance(self.metrics, dict):
            raise ValidationError("metrics must be a JSON object")
        try:
            canonical_json(self.metrics)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("metrics contain non-JSON-safe values: %s" % exc)
        if not isinstance(self.tests, list):
            raise ValidationError("tests must be a list")
        for t in self.tests:
            if not isinstance(t, dict) or "name" not in t:
                raise ValidationError("every test entry needs a 'name' key")
        if not isinstance(self.artifacts, dict):
            raise ValidationError("artifacts must be an object")

    def to_db(self) -> Dict[str, Any]:
        return {
            "experiment_uuid": self.experiment_uuid,
            "run_number": self.run_number,
            "status": self.status,
            "metrics": json.dumps(self.metrics, sort_keys=True),
            "tests": json.dumps(self.tests, sort_keys=True),
            "artifacts": json.dumps(self.artifacts, sort_keys=True),
            "log_path": self.log_path,
            "env": json.dumps(self.env, sort_keys=True),
            "result_checksum": self.result_checksum,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "runtime_seconds": self.runtime_seconds,
            "failure_reason": self.failure_reason,
        }


# ---------------------------------------------------------------------------
# Reproduction
# ---------------------------------------------------------------------------

@dataclass
class ReproductionRecord:
    """Outcome of a `research run UUID` reproducibility check."""

    original_uuid: str
    run_number: int
    status: str  # matched | differed | unverifiable
    new_run_number: int
    max_metric_abs_diff: Optional[float]
    metric_names: List[str]
    explanation: str
    checked_at: str = field(default_factory=utcnow)
