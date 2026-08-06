"""Shared low-level utilities: canonical JSON, hashing, timestamps,
environment snapshots, and git state capture (PRIVATE module).

Not part of the public API. Everything here is deterministic so that
registry artifacts can be checksummed and compared across machines.
"""

import datetime
import hashlib
import json
import os
import platform
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

UTC = datetime.timezone.utc


# ---------------------------------------------------------------------------
# Timestamps
# ---------------------------------------------------------------------------

def utcnow() -> str:
    """Current UTC time as an ISO-8601 string with Z suffix (sortable)."""
    return (
        datetime.datetime.now(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def to_json_safe(value: Any) -> Any:
    """Recursively convert a value to JSON-safe types.

    numpy scalars become Python floats/ints; ndarrays become nested
    lists; bytes become base64 strings (prefix ``base64:``); tuples
    become lists. Raises TypeError for unsupported types so that
    silently non-deterministic payloads fail loudly.
    """
    if isinstance(value, np.ndarray):
        return [to_json_safe(v) for v in value.tolist()]
    if isinstance(value, np.generic):
        if np.iscomplexobj(value):
            raise TypeError("complex numbers are not JSON-safe")
        return value.item()
    if isinstance(value, (dict,)):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_safe(v) for v in value]
    if isinstance(value, bytes):
        import base64

        return "base64:" + base64.b64encode(value).decode("ascii")
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError("unsupported value type: %s" % type(value).__name__)


def canonical_json(value: Any) -> str:
    """Deterministic JSON serialization: sorted keys, compact separators.

    Two equal payloads always produce identical bytes, which is what
    config hashing, result checksums and reproducibility comparisons
    rely on.
    """
    return json.dumps(
        to_json_safe(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: str, value: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(value))
        fh.write("\n")


def read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Environment and git state
# ---------------------------------------------------------------------------

def git_state(path: str) -> Optional[Dict[str, Any]]:
    """Capture the git state of the repository containing ``path``.

    Returns None when ``path`` is not inside a git working tree.
    ``commit`` is the full HEAD hash; ``dirty`` reports uncommitted
    changes in the working tree (checked via ``git status --porcelain``).
    """
    try:
        root = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if root.returncode != 0:
            return None
        repo = root.stdout.strip()
        commit = subprocess.run(
            ["git", "-C", repo, "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        status = subprocess.run(
            ["git", "-C", repo, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if commit.returncode != 0:
            return None
        return {
            "repo": repo,
            "commit": commit.stdout.strip(),
            "dirty": bool(status.stdout.strip()),
        }
    except Exception:
        return None


def env_snapshot(cwd: Optional[str] = None) -> Dict[str, Any]:
    """A reproducible description of the execution environment.

    Recorded with every run so that "same result years later" can be
    checked against the environment that produced it.
    """
    cwd = cwd or os.getcwd()
    snap: Dict[str, Any] = {
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "hostname": platform.node(),
        "cwd": cwd,
        "timezone": (datetime.datetime.now().astimezone().tzname() or "UTC"),
        "env": {
            "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", ""),
        },
    }
    try:
        snap["numpy_version"] = np.__version__
    except Exception:
        snap["numpy_version"] = "n/a"
    git = git_state(cwd)
    if git is not None:
        snap["git"] = git
    else:
        snap["git"] = None
    return snap


def float_eq(a: float, b: float, rtol: float = 1e-9, atol: float = 1e-12) -> bool:
    """Floating-point equality used by reproducibility comparisons."""
    return abs(a - b) <= atol + rtol * max(abs(a), abs(b))


def metrics_match(a: Any, b: Any) -> Optional[float]:
    """Recursively compare two metric payloads.

    Returns the maximum absolute difference between any two comparable
    floats, or 0.0 when all values match exactly, or None when the
    payloads differ structurally (different keys, types, lengths).
    """
    if isinstance(a, bool) and isinstance(b, bool):
        return 0.0 if a == b else None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if float_eq(float(a), float(b)):
            return abs(float(a) - float(b))
        return None
    if isinstance(a, str) and isinstance(b, str):
        return 0.0 if a == b else None
    if a is None and b is None:
        return 0.0
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return None
        total = 0.0
        for k in a:
            sub = metrics_match(a[k], b[k])
            if sub is None:
                return None
            total = max(total, sub)
        return total
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return None
        total = 0.0
        for x, y in zip(a, b):
            sub = metrics_match(x, y)
            if sub is None:
                return None
            total = max(total, sub)
        return total
    return None
