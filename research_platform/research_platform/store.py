"""ResearchStore — the durable registry behind the framework.

Layout (``root`` = research home, e.g. ``~/.research`` or
``$RESEARCH_HOME``)::

    <root>/
    ├── research.db              # SQLite registry (metadata)
    ├── configs/<sha256>.json    # recorded experiment configs
    ├── datasets/
    │   ├── objects/<sha256><ext>   # immutable content-addressed blobs
    │   └── <uuid>/manifest.json    # dataset manifests
    └── experiments/<uuid>/
        ├── manifest.json
        └── run_<n>/{env,params,metrics,tests}.json, log.txt, artifacts/

The SQLite database is the queryable registry; the filesystem holds the
content. Datasets are immutable: the blob lives at a checksum-derived
path, so the same bytes can never be overwritten, and registration
metadata is written once in the manifest. Nothing in this module deletes
or mutates registered content.
"""

import json
import os
import shutil
import sqlite3
import uuid as uuidlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._util import (
    canonical_json,
    sha256_file,
    sha256_text,
    utcnow,
    write_json,
)
from .schema import (
    DatasetRecord,
    ExperimentRecord,
    ReproductionRecord,
    RunRecord,
    ValidationError,
    _validate_params,
)

DEFAULT_ROOT = os.environ.get("RESEARCH_HOME", os.path.expanduser("~/.research"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    source TEXT NOT NULL,
    provider TEXT NOT NULL,
    version TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timezone TEXT NOT NULL,
    pipeline TEXT NOT NULL DEFAULT '',
    feature_version TEXT NOT NULL DEFAULT '',
    checksum TEXT NOT NULL,
    file_name TEXT NOT NULL,
    total_bytes INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    meta TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS experiments (
    uuid TEXT PRIMARY KEY,
    hypothesis TEXT NOT NULL,
    objective TEXT NOT NULL,
    author TEXT NOT NULL,
    created_at TEXT NOT NULL,
    dataset_id TEXT,
    params TEXT NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL,
    status_changed_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    runtime_seconds REAL,
    failure_reason TEXT,
    config_hash TEXT NOT NULL,
    sweep_id TEXT,
    sweep_parameter TEXT,
    sweep_value TEXT,
    repeat_index INTEGER NOT NULL DEFAULT 0,
    assumptions TEXT NOT NULL DEFAULT '[]',
    tags TEXT NOT NULL DEFAULT '[]',
    module TEXT NOT NULL,
    function TEXT NOT NULL,
    module_checksum TEXT NOT NULL,
    git_commit TEXT,
    git_repo TEXT,
    git_dirty INTEGER,
    meta TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_experiments_config ON experiments(config_hash);
CREATE INDEX IF NOT EXISTS idx_experiments_sweep ON experiments(sweep_id);
CREATE INDEX IF NOT EXISTS idx_experiments_dataset ON experiments(dataset_id);

CREATE TABLE IF NOT EXISTS runs (
    experiment_uuid TEXT NOT NULL REFERENCES experiments(uuid),
    run_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    metrics TEXT NOT NULL DEFAULT '{}',
    tests TEXT NOT NULL DEFAULT '[]',
    artifacts TEXT NOT NULL DEFAULT '{}',
    log_path TEXT,
    env TEXT NOT NULL DEFAULT '{}',
    result_checksum TEXT NOT NULL DEFAULT '',
    started_at TEXT,
    finished_at TEXT,
    runtime_seconds REAL,
    failure_reason TEXT,
    PRIMARY KEY (experiment_uuid, run_number)
);

CREATE TABLE IF NOT EXISTS reproductions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_uuid TEXT NOT NULL,
    run_number INTEGER NOT NULL,
    status TEXT NOT NULL,
    new_run_number INTEGER NOT NULL,
    max_metric_abs_diff REAL,
    metric_names TEXT NOT NULL DEFAULT '[]',
    explanation TEXT NOT NULL,
    checked_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reproductions_experiment
    ON reproductions (original_uuid, run_number);
"""


class StoreError(RuntimeError):
    pass


class ResearchStore:
    def __init__(self, root: Optional[str] = None):
        self.root = Path(root or DEFAULT_ROOT).expanduser().resolve()
        self.db_path = self.root / "research.db"
        self.datasets_dir = self.root / "datasets"
        self.objects_dir = self.datasets_dir / "objects"
        self.experiments_dir = self.root / "experiments"
        self.configs_dir = self.root / "configs"
        self.init()

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def init(self) -> None:
        for d in (
            self.root,
            self.datasets_dir,
            self.objects_dir,
            self.experiments_dir,
            self.configs_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Dataset registry (immutable)
    # ------------------------------------------------------------------

    def register_dataset(
        self,
        file_path: str,
        source: str,
        provider: str,
        version: str,
        symbol: str,
        timeframe: str,
        timezone: str,
        name: Optional[str] = None,
        pipeline: str = "",
        feature_version: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> DatasetRecord:
        """Register a data file as an immutable dataset.

        The file is copied into content-addressed storage (keyed on its
        SHA-256), so registration is idempotent per content and no
        registered bytes can ever be overwritten.
        """
        src = Path(file_path)
        if not src.is_file():
            raise StoreError("dataset file not found: %s" % src)
        DatasetRecord.require_fields(dict(
            source=source, provider=provider, version=version, symbol=symbol,
            timeframe=timeframe, timezone=timezone, checksum="pending",
        ))
        ext = src.suffix or ".bin"
        checksum = sha256_file(str(src))
        object_path = self.objects_dir / ("%s%s" % (checksum, ext))
        if not object_path.exists():
            shutil.copyfile(str(src), str(object_path))
        # Sanity: the copy must hash identically, or storage is corrupt.
        if sha256_file(str(object_path)) != checksum:
            raise StoreError("content-addressed copy failed checksum verification")

        rec = DatasetRecord(
            id=str(uuidlib.uuid4()),
            name=name,
            source=source,
            provider=provider,
            version=version,
            symbol=symbol,
            timeframe=timeframe,
            timezone=timezone,
            pipeline=pipeline,
            feature_version=feature_version,
            checksum=checksum,
            file_name=src.name,
            total_bytes=object_path.stat().st_size,
            created_at=utcnow(),
            meta=dict(meta or {}),
        )
        manifest_dir = self.datasets_dir / rec.id
        manifest_dir.mkdir(parents=True, exist_ok=True)
        write_json(str(manifest_dir / "manifest.json"), rec.manifest())
        try:
            self._conn.execute(
                "INSERT INTO datasets (id, name, source, provider, version, symbol,"
                " timeframe, timezone, pipeline, feature_version, checksum, file_name,"
                " total_bytes, created_at, meta) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rec.id, rec.name, rec.source, rec.provider, rec.version,
                    rec.symbol, rec.timeframe, rec.timezone, rec.pipeline,
                    rec.feature_version, rec.checksum, rec.file_name,
                    rec.total_bytes, rec.created_at,
                    canonical_json(rec.meta),
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise StoreError("dataset registration rejected: %s" % exc)
        return rec

    def get_dataset(self, ref: str) -> DatasetRecord:
        """Look up a dataset by id or by registered name."""
        row = self._conn.execute(
            "SELECT * FROM datasets WHERE id = ? OR name = ?", (ref, ref)
        ).fetchone()
        if row is None:
            raise StoreError("unknown dataset: %s" % ref)
        return self._row_to_dataset(row)

    def list_datasets(self) -> List[DatasetRecord]:
        rows = self._conn.execute(
            "SELECT * FROM datasets ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_dataset(r) for r in rows]

    def verify_dataset(self, ref: str) -> Dict[str, Any]:
        """Re-hash the stored blob and report integrity.

        Immutability is an invariant of the store; this is the
        executable proof of it.
        """
        rec = self.get_dataset(ref)
        object_path = self.objects_dir / (
            "%s%s" % (rec.checksum, Path(rec.file_name).suffix or ".bin")
        )
        if not object_path.exists():
            return {"ok": False, "reason": "blob missing: %s" % object_path}
        actual = sha256_file(str(object_path))
        return {
            "ok": actual == rec.checksum,
            "checksum": rec.checksum,
            "actual": actual,
            "bytes": object_path.stat().st_size,
        }

    def dataset_object_path(self, rec: DatasetRecord) -> Path:
        return self.objects_dir / (
            "%s%s" % (rec.checksum, Path(rec.file_name).suffix or ".bin")
        )

    @staticmethod
    def _row_to_dataset(row: sqlite3.Row) -> DatasetRecord:
        return DatasetRecord(
            id=row["id"],
            name=row["name"],
            source=row["source"],
            provider=row["provider"],
            version=row["version"],
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            timezone=row["timezone"],
            pipeline=row["pipeline"],
            feature_version=row["feature_version"],
            checksum=row["checksum"],
            file_name=row["file_name"],
            total_bytes=row["total_bytes"],
            created_at=row["created_at"],
            meta=json.loads(row["meta"] or "{}"),
        )

    # ------------------------------------------------------------------
    # Configs
    # ------------------------------------------------------------------

    def record_config(self, config: Dict[str, Any]) -> str:
        """Persist a config under its canonical hash; returns the hash."""
        h = self.config_hash(config)
        path = self.configs_dir / ("%s.json" % h)
        if not path.exists():
            write_json(str(path), config)
        return h

    @staticmethod
    def config_hash(config: Dict[str, Any]) -> str:
        return sha256_text(canonical_json(config))

    # ------------------------------------------------------------------
    # Experiment registry
    # ------------------------------------------------------------------

    def create_experiment(self, rec: ExperimentRecord) -> ExperimentRecord:
        ExperimentRecord.validate_meta(
            rec.hypothesis, rec.objective, rec.author, rec.seed, rec.status
        )
        _validate_params(rec.params)
        try:
            params_json = canonical_json(rec.params)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError("parameters are not JSON-safe: %s" % exc)
        try:
            self._conn.execute(
                "INSERT INTO experiments (uuid, hypothesis, objective, author,"
                " created_at, dataset_id, params, seed, status, status_changed_at,"
                " config_hash, sweep_id, sweep_parameter, sweep_value, repeat_index,"
                " assumptions, tags, module, function, module_checksum, git_commit,"
                " git_repo, git_dirty, meta)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rec.uuid, rec.hypothesis, rec.objective, rec.author,
                    rec.created_at, rec.dataset_id, params_json,
                    rec.seed, rec.status, rec.status_changed_at,
                    rec.config_hash, rec.sweep_id, rec.sweep_parameter,
                    None if rec.sweep_value is None else canonical_json(rec.sweep_value),
                    rec.repeat_index,
                    canonical_json(rec.assumptions), canonical_json(rec.tags),
                    rec.module, rec.function, rec.module_checksum,
                    rec.git_commit, rec.git_repo,
                    (1 if rec.git_dirty else 0) if rec.git_dirty is not None else None,
                    canonical_json(rec.meta),
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise StoreError("experiment creation rejected: %s" % exc)
        return rec

    def set_module_checksum(self, uuid: str, checksum: str) -> None:
        self._conn.execute(
            "UPDATE experiments SET module_checksum = ? WHERE uuid = ?",
            (checksum, uuid),
        )
        self._conn.commit()

    def set_status(
        self, uuid: str, status: str, failure_reason: Optional[str] = None,
        started_at: Optional[str] = None, finished_at: Optional[str] = None,
        runtime_seconds: Optional[float] = None,
    ) -> None:
        now = utcnow()
        self._conn.execute(
            "UPDATE experiments SET status = ?, status_changed_at = ?,"
            " started_at = COALESCE(?, started_at),"
            " finished_at = COALESCE(?, finished_at),"
            " runtime_seconds = COALESCE(?, runtime_seconds),"
            " failure_reason = ? WHERE uuid = ?",
            (status, now, started_at, finished_at, runtime_seconds, failure_reason, uuid),
        )
        self._conn.commit()

    def get_experiment(self, uuid: str) -> ExperimentRecord:
        row = self._conn.execute(
            "SELECT * FROM experiments WHERE uuid = ?", (uuid,)
        ).fetchone()
        if row is None:
            raise StoreError("unknown experiment: %s" % uuid)
        return self._row_to_experiment(row)

    def find_experiments(
        self,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        assumption: Optional[str] = None,
        sweep_id: Optional[str] = None,
        author: Optional[str] = None,
        dataset_id: Optional[str] = None,
        module: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[ExperimentRecord]:
        clauses: List[str] = []
        args: List[Any] = []
        if status is not None:
            clauses.append("status = ?")
            args.append(status)
        if tag is not None:
            clauses.append("tags LIKE ?")
            args.append('%%"%s"%%' % tag)
        if assumption is not None:
            clauses.append("assumptions LIKE ?")
            args.append('%%"%s"%%' % assumption)
        if sweep_id is not None:
            clauses.append("sweep_id = ?")
            args.append(sweep_id)
        if author is not None:
            clauses.append("author = ?")
            args.append(author)
        if dataset_id is not None:
            clauses.append("dataset_id = ?")
            args.append(dataset_id)
        if module is not None:
            clauses.append("module = ?")
            args.append(module)
        sql = "SELECT * FROM experiments"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at ASC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(limit)
        return [self._row_to_experiment(r) for r in self._conn.execute(sql, args)]

    @staticmethod
    def _row_to_experiment(row: sqlite3.Row) -> ExperimentRecord:
        return ExperimentRecord(
            uuid=row["uuid"],
            hypothesis=row["hypothesis"],
            objective=row["objective"],
            author=row["author"],
            created_at=row["created_at"],
            dataset_id=row["dataset_id"],
            params=json.loads(row["params"] or "{}"),
            seed=row["seed"],
            status=row["status"],
            config_hash=row["config_hash"],
            module=row["module"],
            function=row["function"],
            module_checksum=row["module_checksum"],
            assumptions=json.loads(row["assumptions"] or "[]"),
            tags=json.loads(row["tags"] or "[]"),
            sweep_id=row["sweep_id"],
            sweep_parameter=row["sweep_parameter"],
            sweep_value=json.loads(row["sweep_value"]) if row["sweep_value"] else None,
            repeat_index=row["repeat_index"],
            git_commit=row["git_commit"],
            git_repo=row["git_repo"],
            git_dirty=bool(row["git_dirty"]) if row["git_dirty"] is not None else None,
            status_changed_at=row["status_changed_at"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            runtime_seconds=row["runtime_seconds"],
            failure_reason=row["failure_reason"],
            meta=json.loads(row["meta"] or "{}"),
        )

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    def next_run_number(self, uuid: str) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(run_number), 0) AS n FROM runs WHERE experiment_uuid = ?",
            (uuid,),
        ).fetchone()
        return int(row["n"]) + 1

    def save_run(self, rec: RunRecord) -> None:
        rec.validate_result()
        try:
            self._conn.execute(
                "INSERT INTO runs (experiment_uuid, run_number, status, metrics,"
                " tests, artifacts, log_path, env, result_checksum, started_at,"
                " finished_at, runtime_seconds, failure_reason)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rec.experiment_uuid, rec.run_number, rec.status,
                    json.dumps(rec.metrics, sort_keys=True),
                    json.dumps(rec.tests, sort_keys=True),
                    json.dumps(rec.artifacts, sort_keys=True),
                    rec.log_path, json.dumps(rec.env, sort_keys=True),
                    rec.result_checksum, rec.started_at, rec.finished_at,
                    rec.runtime_seconds, rec.failure_reason,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise StoreError("run save rejected: %s" % exc)

    def get_runs(self, uuid: str) -> List[RunRecord]:
        rows = self._conn.execute(
            "SELECT * FROM runs WHERE experiment_uuid = ? ORDER BY run_number ASC",
            (uuid,),
        ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def get_latest_run(self, uuid: str) -> Optional[RunRecord]:
        row = self._conn.execute(
            "SELECT * FROM runs WHERE experiment_uuid = ?"
            " ORDER BY run_number DESC LIMIT 1",
            (uuid,),
        ).fetchone()
        return self._row_to_run(row) if row is not None else None

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            experiment_uuid=row["experiment_uuid"],
            run_number=row["run_number"],
            status=row["status"],
            metrics=json.loads(row["metrics"] or "{}"),
            tests=json.loads(row["tests"] or "[]"),
            artifacts=json.loads(row["artifacts"] or "{}"),
            log_path=row["log_path"],
            env=json.loads(row["env"] or "{}"),
            result_checksum=row["result_checksum"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            runtime_seconds=row["runtime_seconds"],
            failure_reason=row["failure_reason"],
        )

    # ------------------------------------------------------------------
    # Reproductions
    # ------------------------------------------------------------------

    def record_reproduction(self, rec: ReproductionRecord) -> None:
        self._conn.execute(
            "INSERT INTO reproductions (original_uuid, run_number, status,"
            " new_run_number, max_metric_abs_diff, metric_names, explanation,"
            " checked_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                rec.original_uuid, rec.run_number, rec.status, rec.new_run_number,
                rec.max_metric_abs_diff,
                json.dumps(rec.metric_names, sort_keys=True),
                rec.explanation, rec.checked_at,
            ),
        )
        self._conn.commit()

    def get_reproductions(self, uuid: str) -> List[ReproductionRecord]:
        rows = self._conn.execute(
            "SELECT * FROM reproductions WHERE original_uuid = ? ORDER BY run_number ASC",
            (uuid,),
        ).fetchall()
        return [
            ReproductionRecord(
                original_uuid=r["original_uuid"],
                run_number=r["run_number"],
                status=r["status"],
                new_run_number=r["new_run_number"],
                max_metric_abs_diff=r["max_metric_abs_diff"],
                metric_names=json.loads(r["metric_names"] or "[]"),
                explanation=r["explanation"],
                checked_at=r["checked_at"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Experiment run directories
    # ------------------------------------------------------------------

    def experiment_dir(self, uuid: str) -> Path:
        d = self.experiments_dir / uuid
        d.mkdir(parents=True, exist_ok=True)
        return d

    def run_dir(self, uuid: str, run_number: int) -> Path:
        d = self.experiment_dir(uuid) / ("run_%d" % run_number)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_experiment_manifest(self, rec: ExperimentRecord) -> None:
        manifest = {
            "uuid": rec.uuid,
            "hypothesis": rec.hypothesis,
            "objective": rec.objective,
            "author": rec.author,
            "created_at": rec.created_at,
            "dataset_id": rec.dataset_id,
            "params": rec.params,
            "seed": rec.seed,
            "status": rec.status,
            "config_hash": rec.config_hash,
            "module": rec.module,
            "function": rec.function,
            "module_checksum": rec.module_checksum,
            "assumptions": rec.assumptions,
            "tags": rec.tags,
            "sweep_id": rec.sweep_id,
            "sweep_parameter": rec.sweep_parameter,
            "sweep_value": rec.sweep_value,
            "repeat_index": rec.repeat_index,
            "git": (
                {"commit": rec.git_commit, "repo": rec.git_repo, "dirty": rec.git_dirty}
                if rec.git_commit
                else None
            ),
        }
        write_json(str(self.experiment_dir(rec.uuid) / "manifest.json"), manifest)


def open_store(root: Optional[str] = None) -> ResearchStore:
    return ResearchStore(root)
