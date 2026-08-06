"""Reproducibility engine: `research run EXPERIMENT_UUID`.

Reproducing an experiment means:

1. **Precondition audit** — prove that the inputs still exist and are
   unchanged: the git commit, the dataset blob (re-hashed), and the
   experiment module source (re-hashed). Every failing precondition is
   reported explicitly, so when reproducibility is impossible the
   framework says exactly why.
2. **Re-execution** — run the same atomic experiment (same params,
   same seed, same dataset snapshot) under the same uuid, appended as
   the next run number. The registry stays append-only.
3. **Verification** — compare the new metrics against the recorded
   ones (structural equality; floats within tolerance). The outcome is
   one of:

   * ``matched`` — same results, same inputs;
   * ``differed`` — inputs verified, outputs changed (a bug or
     nondeterminism in the experiment);
   * ``unverifiable`` — at least one input cannot be proven unchanged
     (explanation included); nothing is re-executed.
"""

import os
from typing import Any, Dict, List, Optional, Tuple

from ._util import git_state, metrics_match, sha256_file
from .runner import _execute
from .schema import ReproductionRecord
from .store import ResearchStore


class ReproduceError(RuntimeError):
    pass


class Precondition:
    def __init__(self, name: str, ok: bool, detail: str, blocking: bool):
        self.name = name
        self.ok = ok
        self.detail = detail
        self.blocking = blocking

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "detail": self.detail,
                "blocking": self.blocking}


def audit_preconditions(store: ResearchStore, uuid: str, cwd: Optional[str] = None) -> List[Precondition]:
    """Verify that every input of an experiment is still present and
    unchanged. Pure audit — does not re-execute anything."""
    cwd = cwd or os.getcwd()
    rec = store.get_experiment(uuid)
    checks: List[Precondition] = []

    # 1. Git commit
    if rec.git_commit:
        now = git_state(cwd)
        if now is None:
            checks.append(Precondition(
                "git", False,
                "original run recorded commit %s but the current workspace "
                "is not a git repository" % rec.git_commit[:12],
                blocking=True,
            ))
        elif now["commit"] == rec.git_commit:
            checks.append(Precondition(
                "git", True,
                "workspace is at the recorded commit %s" % rec.git_commit[:12],
                blocking=False,
            ))
        else:
            checks.append(Precondition(
                "git", False,
                "workspace is at commit %s but the experiment was recorded at "
                "%s — results would come from different code"
                % (now["commit"][:12], rec.git_commit[:12]),
                blocking=True,
            ))
        if rec.git_dirty:
            checks.append(Precondition(
                "git_cleanliness", False,
                "the original run was executed from a dirty working tree "
                "(uncommitted changes existed); recorded code may not be "
                "exactly what was run",
                blocking=True,
            ))
    else:
        checks.append(Precondition(
            "git", True,
            "no git commit was recorded (workspace was not a git repo); "
            "the module checksum below is the only code pin",
            blocking=False,
        ))

    # 2. Dataset
    if rec.dataset_id:
        try:
            check = store.verify_dataset(rec.dataset_id)
            if check["ok"]:
                checks.append(Precondition(
                    "dataset", True,
                    "dataset %s verified (sha256 %s, %d bytes)"
                    % (rec.dataset_id[:8], check["checksum"][:12], check["bytes"]),
                    blocking=False,
                ))
            else:
                checks.append(Precondition(
                    "dataset", False, check["reason"], blocking=True
                ))
        except Exception as exc:  # noqa: BLE001
            checks.append(Precondition(
                "dataset", False, "dataset missing: %s" % exc, blocking=True
            ))
    else:
        checks.append(Precondition(
            "dataset", True, "experiment uses no dataset", blocking=False
        ))

    # 3. Experiment module
    try:
        from .runner import load_experiment_function

        _, current = load_experiment_function(rec.module, rec.function, cwd)
        if current == rec.module_checksum:
            checks.append(Precondition(
                "module", True,
                "module '%s' verified (sha256 %s)"
                % (rec.module, rec.module_checksum[:12]),
                blocking=False,
            ))
        else:
            checks.append(Precondition(
                "module", False,
                "module '%s' has changed since the experiment was recorded "
                "(%s != %s) — the recorded code no longer exists at that path"
                % (rec.module, current[:12], rec.module_checksum[:12]),
                blocking=True,
            ))
    except Exception as exc:  # noqa: BLE001
        checks.append(Precondition(
            "module", False, "module unavailable: %s" % exc, blocking=True
        ))

    return checks


def audit(store: ResearchStore, uuid: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Static reproducibility audit of an experiment (no re-execution)."""
    rec = store.get_experiment(uuid)
    checks = [c.to_dict() for c in audit_preconditions(store, uuid, cwd)]
    run = store.get_latest_run(uuid)
    artifacts = []
    if run is not None:
        for name, info in run.artifacts.items():
            path = os.path.join(
                store.experiments_dir, uuid, "run_%d" % run.run_number, info["path"]
            )
            if os.path.isfile(path):
                artifacts.append({
                    "name": name, "ok": sha256_file(path) == info["sha256"],
                    "detail": info["path"],
                })
            else:
                artifacts.append({"name": name, "ok": False, "detail": "file missing"})
    return {
        "uuid": uuid,
        "status": rec.status,
        "preconditions": checks,
        "artifacts": artifacts,
        "reproducible_in_place": all(c["ok"] for c in checks),
    }


def reproduce(
    store: ResearchStore, uuid: str, cwd: Optional[str] = None, force: bool = False
) -> Dict[str, Any]:
    """Reproduce an experiment: audit inputs, re-execute, verify.

    Returns a report with status ``matched`` / ``differed`` /
    ``unverifiable`` and an explicit explanation.
    """
    cwd = cwd or os.getcwd()
    rec = store.get_experiment(uuid)
    checks = audit_preconditions(store, uuid, cwd)
    blocking = [c for c in checks if not c.ok and c.blocking]
    run = store.get_latest_run(uuid)

    if run is None:
        raise ReproduceError(
            "experiment %s has no recorded run to reproduce" % uuid
        )
    if run.status != "completed":
        raise ReproduceError(
            "experiment %s's latest run is %s; only completed runs can be "
            "reproduced" % (uuid, run.status)
        )

    if blocking and not force:
        explanation = (
            "reproducibility is not verifiable: "
            + "; ".join(c.detail for c in blocking)
        )
        store.record_reproduction(ReproductionRecord(
            original_uuid=uuid,
            run_number=run.run_number,
            status="unverifiable",
            new_run_number=0,
            max_metric_abs_diff=None,
            metric_names=list(run.metrics.keys()),
            explanation=explanation,
        ))
        return {
            "status": "unverifiable",
            "uuid": uuid,
            "explanation": explanation,
            "preconditions": [c.to_dict() for c in checks],
            "re_executed": False,
        }

    # Re-execute under the same identity (append-only: new run number).
    new_rec = _execute(store, rec, cwd=cwd)
    new_run = store.get_latest_run(uuid)
    assert new_run is not None and new_run.run_number > run.run_number

    if new_run.status != "completed":
        explanation = (
            "re-execution failed (%s) after successful precondition audit; "
            "the experiment is not deterministic across executions"
            % new_run.failure_reason
        )
        status = "differed"
        max_diff = None
    else:
        diff = metrics_match(run.metrics, new_run.metrics)
        if diff is None:
            explanation = (
                "metrics differ structurally between the recorded run "
                "(run %d) and the reproduction (run %d)"
                % (run.run_number, new_run.run_number)
            )
            status = "differed"
            max_diff = None
        elif diff > 0.0:
            explanation = (
                "metrics differ within tolerance-checked comparison "
                "(max abs diff %.3e between run %d and run %d)"
                % (diff, run.run_number, new_run.run_number)
            )
            status = "differed"
            max_diff = float(diff)
        else:
            explanation = (
                "metrics match exactly between run %d and reproduction "
                "run %d (%d metrics compared)"
                % (run.run_number, new_run.run_number, len(run.metrics))
            )
            status = "matched"
            max_diff = 0.0

    store.record_reproduction(ReproductionRecord(
        original_uuid=uuid,
        run_number=run.run_number,
        status=status,
        new_run_number=new_run.run_number,
        max_metric_abs_diff=max_diff,
        metric_names=list(run.metrics.keys()),
        explanation=explanation,
    ))
    return {
        "status": status,
        "uuid": uuid,
        "explanation": explanation,
        "max_metric_abs_diff": max_diff,
        "original_run_number": run.run_number,
        "new_run_number": new_run.run_number,
        "preconditions": [c.to_dict() for c in checks],
        "re_executed": True,
    }
