"""The experiment runner: deterministic execution of config-defined
experiments, parameter sweeps, repeated runs, and durable result storage.

Execution contract for experiment modules
    A module named in ``experiment.module`` must expose a function
    (default ``run``) with the signature::

        def run(ctx) -> dict

    ``ctx`` is an :class:`ExperimentContext` providing:

    * ``ctx.params`` — the frozen parameter dict for this atomic run
    * ``ctx.seed`` — the deterministic seed for this run
    * ``ctx.rng`` — ``numpy.random.Generator`` seeded with ``ctx.seed``
    * ``ctx.dataset`` — ``None`` or ``{"meta": {...}, "data": <content>}``
    * ``ctx.log`` — callable/method appending to the run's log

    The returned dict may contain:

    * ``metrics`` — JSON-safe dict (recorded verbatim)
    * ``tests`` — list of ``{"name", "statistic", "p_value",
      "conclusion", ...}`` records
    * ``artifacts`` — dict of name -> value; numpy arrays are stored as
      .npy, strings as .txt, bytes as .bin, JSON-safe values as .json
    * ``logs`` — optional extra log lines (string or list of strings)

Determinism
    The runner seeds ``numpy.random`` (via ``default_rng(seed)``) and
    ``random`` (via ``random.seed(seed)``) before every atomic run.
    Anything else the experiment does (network, unseeded libraries,
    filesystem reads) is the experiment author's responsibility and is
    recorded in the environment snapshot so the reproducibility engine
    can flag it.
"""

import importlib
import io
import os
import random
import sys
import time
import traceback
import uuid as uuidlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from ._util import (
    canonical_json,
    env_snapshot,
    git_state,
    sha256_bytes,
    sha256_file,
    sha256_text,
    utcnow,
    write_json,
)
from .config import ExperimentConfig, PlanItem, load_config
from .schema import ExperimentRecord, RunRecord, ValidationError
from .store import ResearchStore


class RunnerError(RuntimeError):
    pass


@dataclass
class ExperimentContext:
    """Everything an atomic run is allowed to see."""

    params: Dict[str, Any]
    seed: int
    rng: np.random.Generator
    dataset: Optional[Dict[str, Any]]
    log_lines: List[str] = field(default_factory=list)
    name: str = "experiment"

    def log(self, message: str) -> None:
        self.log_lines.append("[%s] %s" % (self.name, message))


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------

def load_experiment_function(
    module_path: str, function_name: str, cwd: Optional[str] = None
):
    """Import the experiment module and return (function, module_checksum).

    The current working directory and the framework root are added to
    ``sys.path`` so that research configs can reference modules by their
    workspace-relative import path (and the examples package when the
    framework is used uninstalled). The module's source file is
    checksummed so the reproducibility engine can later prove the code
    did not change.
    """
    cwd = cwd or os.getcwd()
    candidates = [cwd]
    framework_root = str(Path(__file__).resolve().parent.parent)
    if framework_root not in candidates:
        candidates.append(framework_root)
    for candidate in candidates:
        if candidate not in sys.path:
            sys.path.insert(0, candidate)
    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        raise RunnerError(
            "cannot import experiment module '%s': %s" % (module_path, exc)
        )
    if not hasattr(module, function_name):
        raise RunnerError(
            "module '%s' has no function '%s'" % (module_path, function_name)
        )
    fn = getattr(module, function_name)
    src = getattr(module, "__file__", None)
    checksum = sha256_file(src) if src and Path(src).is_file() else "n/a"
    return fn, checksum


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------

def load_dataset_content(object_path: Path) -> Any:
    """Load a registered dataset blob into the payload passed to runs.

    .npy → ndarray; .npz → dict of ndarrays; .csv → ndarray
    (np.genfromtxt); anything else → raw bytes.
    """
    ext = object_path.suffix.lower()
    if ext == ".npy":
        return np.load(str(object_path))
    if ext == ".npz":
        return dict(np.load(str(object_path)))
    if ext == ".csv":
        return np.genfromtxt(str(object_path), delimiter=",", dtype=float)
    return object_path.read_bytes()


def resolve_dataset_payload(store: ResearchStore, dataset_id: Optional[str]):
    """Resolve a dataset id to the (record, payload) for a run."""
    if dataset_id is None:
        return None, None
    rec = store.get_dataset(dataset_id)
    check = store.verify_dataset(dataset_id)
    if not check["ok"]:
        raise RunnerError(
            "dataset integrity check failed for %s: %s"
            % (dataset_id, check.get("reason", "blob content mismatch"))
        )
    return rec, {
        "meta": rec.manifest(),
        "data": load_dataset_content(store.dataset_object_path(rec)),
    }


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def _artifact_kind(value: Any) -> str:
    if isinstance(value, np.ndarray):
        return "npy"
    if isinstance(value, bytes):
        return "bin"
    if isinstance(value, str):
        return "txt"
    return "json"


def save_artifact(run_dir: Path, name: str, value: Any) -> Dict[str, Any]:
    """Persist one artifact; returns the {kind, path, sha256} record."""
    safe_name = name.replace("/", "_").replace("..", "_")
    kind = _artifact_kind(value)
    if kind == "npy":
        buf = io.BytesIO()
        np.save(buf, value)
        data = buf.getvalue()
        rel = "artifacts/%s.npy" % safe_name
    elif kind == "bin":
        data = bytes(value)
        rel = "artifacts/%s.bin" % safe_name
    elif kind == "txt":
        data = str(value).encode("utf-8")
        rel = "artifacts/%s.txt" % safe_name
    else:
        data = canonical_json(value).encode("utf-8")
        rel = "artifacts/%s.json" % safe_name
    target = run_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {"kind": kind, "path": rel, "sha256": sha256_bytes(data)}


# ---------------------------------------------------------------------------
# Atomic execution
# ---------------------------------------------------------------------------

def run_atomic(
    store: ResearchStore,
    config: ExperimentConfig,
    item: PlanItem,
    config_hash: str,
    cwd: Optional[str] = None,
    quiet: bool = False,
) -> ExperimentRecord:
    """Execute one atomic (params, seed) experiment and store everything.

    Never raises for experiment code failures: the failure is recorded
    on the experiment record and the run, and control returns so that
    sweeps continue. Raises only for infrastructure errors.
    """
    cwd = cwd or os.getcwd()
    uuid = str(uuidlib.uuid4())
    git = git_state(cwd)
    dataset_id = config.resolve_dataset(store)
    rec = ExperimentRecord(
        uuid=uuid,
        hypothesis=config.hypothesis,
        objective=config.objective,
        author=config.author,
        created_at=utcnow(),
        dataset_id=dataset_id,
        params=item.params,
        seed=item.seed,
        status="queued",
        config_hash=config_hash,
        module=config.module,
        function=config.function,
        module_checksum="",
        assumptions=list(config.assumptions),
        tags=list(config.tags),
        sweep_id=config_hash if config.has_sweep else None,
        sweep_parameter=item.sweep_parameter,
        sweep_value=item.sweep_value,
        repeat_index=item.repeat_index,
        git_commit=git["commit"] if git else None,
        git_repo=git["repo"] if git else None,
        git_dirty=git["dirty"] if git else None,
    )
    store.create_experiment(rec)
    store.save_experiment_manifest(rec)
    return _execute(store, rec, cwd=cwd, quiet=quiet)


def _execute(
    store: ResearchStore,
    rec: ExperimentRecord,
    cwd: Optional[str] = None,
    quiet: bool = False,
) -> ExperimentRecord:
    """Run one more execution of an existing experiment record.

    Used by the runner (fresh experiments) and by the reproducibility
    engine (re-execution of an existing experiment under the same
    uuid, appended as run_number+1). Never raises for experiment
    failures.
    """
    cwd = cwd or os.getcwd()
    store.set_status(rec.uuid, "running", started_at=utcnow())
    started = time.monotonic()
    run_number = store.next_run_number(rec.uuid)
    run_dir = store.run_dir(rec.uuid, run_number)
    run = RunRecord(
        experiment_uuid=rec.uuid,
        run_number=run_number,
        status="running",
        started_at=utcnow(),
        env=env_snapshot(cwd),
        log_path=None,
    )
    ctx = ExperimentContext(
        params=rec.params,
        seed=rec.seed,
        rng=np.random.default_rng(rec.seed),
        dataset=None,
        name="experiment-%s" % rec.uuid[:8],
    )
    random.seed(rec.seed)

    try:
        fn, module_checksum = load_experiment_function(rec.module, rec.function, cwd)
        if rec.module_checksum and module_checksum != rec.module_checksum:
            raise RunnerError(
                "module '%s' checksum changed since creation (%s != %s); "
                "refusing to execute under changed code"
                % (rec.module, module_checksum, rec.module_checksum)
            )
        if not rec.module_checksum:
            rec.module_checksum = module_checksum
            store.set_module_checksum(rec.uuid, module_checksum)

        _, payload = resolve_dataset_payload(store, rec.dataset_id)
        ctx.dataset = payload
        if not quiet:
            ctx.log("dataset: %s" % (rec.dataset_id or "(none)"))
            ctx.log("params: %s" % canonical_json(rec.params))
            ctx.log("seed: %d" % rec.seed)

        result = fn(ctx)
        if result is None:
            result = {}
        if not isinstance(result, dict):
            raise ValidationError(
                "experiment function must return a dict, got %s"
                % type(result).__name__
            )

        run.metrics = dict(result.get("metrics", {}))
        run.tests = [dict(t) for t in result.get("tests", [])]
        artifacts_in = result.get("artifacts", {})
        if not isinstance(artifacts_in, dict):
            raise ValidationError("'artifacts' must be an object")
        for name, value in artifacts_in.items():
            run.artifacts[name] = save_artifact(run_dir, str(name), value)
        extra_logs = result.get("logs", [])
        if isinstance(extra_logs, str):
            ctx.log_lines.append(extra_logs)
        elif isinstance(extra_logs, list):
            ctx.log_lines.extend(str(x) for x in extra_logs)

        run.validate_result()
        run.status = "completed"
        run.finished_at = utcnow()
        run.runtime_seconds = time.monotonic() - started
        run.result_checksum = sha256_text(canonical_json(run.metrics))
        log_text = "\n".join(ctx.log_lines) + ("\n" if ctx.log_lines else "")
        log_path = run_dir / "log.txt"
        log_path.write_text(log_text, encoding="utf-8")
        run.log_path = str(log_path)
        run.env = env_snapshot(cwd)
        write_json(str(run_dir / "env.json"), run.env)
        write_json(str(run_dir / "params.json"), rec.params)
        write_json(str(run_dir / "metrics.json"), run.metrics)
        write_json(str(run_dir / "tests.json"), run.tests)
        store.save_run(run)
        store.set_status(
            rec.uuid, "completed",
            finished_at=run.finished_at, runtime_seconds=run.runtime_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — experiment failures are data
        tb = traceback.format_exc()
        run.status = "failed"
        run.failure_reason = "%s: %s" % (type(exc).__name__, exc)
        run.finished_at = utcnow()
        run.runtime_seconds = time.monotonic() - started
        log_text = "\n".join(ctx.log_lines)
        log_text += "\n" + tb if tb else ""
        log_path = run_dir / "log.txt"
        log_path.write_text(log_text, encoding="utf-8")
        run.log_path = str(log_path)
        store.save_run(run)
        store.set_status(
            rec.uuid, "failed", failure_reason=run.failure_reason,
            finished_at=run.finished_at, runtime_seconds=run.runtime_seconds,
        )
    return store.get_experiment(rec.uuid)


def _fail(store: ResearchStore, rec: ExperimentRecord, exc: Exception) -> None:
    reason = "%s: %s" % (type(exc).__name__, exc)
    store.set_status(rec.uuid, "failed", failure_reason=reason, finished_at=utcnow())


# ---------------------------------------------------------------------------
# Config-level orchestration
# ---------------------------------------------------------------------------

def run_config(
    store: ResearchStore,
    config_path: str,
    cwd: Optional[str] = None,
    quiet: bool = False,
) -> Dict[str, Any]:
    """Run every atomic experiment implied by a config file.

    ``cwd`` defaults to the config file's directory, so experiment
    modules can be referenced relative to the config (a config's
    home directory is added to sys.path for the run). Returns a
    summary dict listing each experiment's uuid and status.
    """
    config = load_config(config_path)
    config_hash = store.record_config(config.to_document())
    plan = config.plan()
    if cwd is None:
        cwd = str(Path(config_path).resolve().parent)
    outcomes = []
    for item in plan:
        rec = run_atomic(store, config, item, config_hash, cwd=cwd, quiet=quiet)
        outcomes.append(
            {"uuid": rec.uuid, "status": rec.status, "seed": rec.seed,
             "sweep_value": rec.sweep_value, "repeat_index": rec.repeat_index,
             "failure_reason": rec.failure_reason}
        )
    completed = sum(1 for o in outcomes if o["status"] == "completed")
    return {
        "config": config_path,
        "config_hash": config_hash,
        "experiments": len(outcomes),
        "completed": completed,
        "failed": len(outcomes) - completed,
        "outcomes": outcomes,
    }
