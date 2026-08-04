"""
Storage — AI Trading Brain, Subsystem 1

DuckDB per ADR-0001 (docs/adr/0001-unified-storage-engine.md): one
embedded file, no server process, right-sized for this platform's actual
data volume (ARCHITECTURE.md §31). Migrations are plain numbered .sql
files applied once, in order, tracked in schema_migrations -- not a full
migration framework (Alembic etc.), which would be institutional-scale
tooling for what is, at this platform's size, a handful of files that
change rarely.
"""

from pathlib import Path
from typing import List

import duckdb

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _migration_files() -> List[Path]:
    return sorted(_MIGRATIONS_DIR.glob("*.sql"))


def _version_of(path: Path) -> int:
    # "0001_core_schema.sql" -> 1
    return int(path.stem.split("_", 1)[0])


class Storage:
    """Owns the one DuckDB connection for this process. Nothing outside
    trading_brain/storage/ should hold a raw connection -- repositories
    are the only sanctioned way in, which is what makes the append-only
    contract (ARCHITECTURE.md §41) enforceable by Python's own module
    boundaries rather than by database triggers (see the spec doc's Data
    Contracts section for why)."""

    def __init__(self, path: str = "trading_brain.duckdb"):
        self.path = path
        self._conn = duckdb.connect(path)

    def connection(self) -> "duckdb.DuckDBPyConnection":
        return self._conn

    def migrate(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
        )
        applied = {
            row[0] for row in self._conn.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for path in _migration_files():
            version = _version_of(path)
            if version in applied:
                continue
            sql = path.read_text()
            self._conn.execute(sql)
            self._conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, now())", [version]
            )

    def close(self) -> None:
        self._conn.close()
