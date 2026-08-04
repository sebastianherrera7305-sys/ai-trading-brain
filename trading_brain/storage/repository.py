"""
Repositories — AI Trading Brain, Subsystem 1

One repository per table, each exposing only the operations
ARCHITECTURE.md §41 (append-only) allows for that table. Record dataclasses
here intentionally do not import from strategy.py/scoring.py -- callers
serialize (e.g. a ChecklistInputs to checklist_json) before handing a
record to a repository, keeping storage a leaf in the dependency graph
(ARCHITECTURE.md §6) that nothing above it needs to know the internals of.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from .db import Storage


@dataclass(frozen=True)
class SignalRecord:
    trade_id: str
    symbol: str
    strategy_name: str
    generated_at: datetime
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    invalidation_price: float
    tier: str
    checklist_json: str
    risk_decision: str
    account_mode: str
    ai_win_probability: Optional[float] = None
    ai_rationale: Optional[str] = None
    ai_model_version: Optional[str] = None
    regime_at_signal: Optional[str] = None
    risk_reason: Optional[str] = None
    portfolio_decision: Optional[str] = None


class SignalRepository:
    """Append-only: insert() and reads only. There is deliberately no
    update()/delete() defined on this class -- not merely unused, absent,
    so the append-only contract is a property of what this object *can*
    do, not a convention about what it happens not to do."""

    def __init__(self, storage: Storage):
        self._conn = storage.connection()

    def insert(self, s: SignalRecord) -> None:
        self._conn.execute(
            """INSERT INTO signals (
                trade_id, symbol, strategy_name, generated_at, direction,
                entry, stop_loss, take_profit, invalidation_price, tier,
                checklist_json, ai_win_probability, ai_rationale, ai_model_version,
                regime_at_signal, risk_decision, risk_reason, portfolio_decision, account_mode
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                s.trade_id, s.symbol, s.strategy_name, s.generated_at, s.direction,
                s.entry, s.stop_loss, s.take_profit, s.invalidation_price, s.tier,
                s.checklist_json, s.ai_win_probability, s.ai_rationale, s.ai_model_version,
                s.regime_at_signal, s.risk_decision, s.risk_reason, s.portfolio_decision, s.account_mode,
            ],
        )

    def get(self, trade_id: str) -> Optional[SignalRecord]:
        row = self._conn.execute(
            "SELECT trade_id, symbol, strategy_name, generated_at, direction, entry, stop_loss, "
            "take_profit, invalidation_price, tier, checklist_json, ai_win_probability, ai_rationale, "
            "ai_model_version, regime_at_signal, risk_decision, risk_reason, portfolio_decision, account_mode "
            "FROM signals WHERE trade_id = ?",
            [trade_id],
        ).fetchone()
        return _row_to_signal(row) if row else None

    def recent(self, symbol: Optional[str] = None, limit: int = 100) -> List[SignalRecord]:
        if symbol is None:
            rows = self._conn.execute(
                "SELECT trade_id, symbol, strategy_name, generated_at, direction, entry, stop_loss, "
                "take_profit, invalidation_price, tier, checklist_json, ai_win_probability, ai_rationale, "
                "ai_model_version, regime_at_signal, risk_decision, risk_reason, portfolio_decision, account_mode "
                "FROM signals ORDER BY generated_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT trade_id, symbol, strategy_name, generated_at, direction, entry, stop_loss, "
                "take_profit, invalidation_price, tier, checklist_json, ai_win_probability, ai_rationale, "
                "ai_model_version, regime_at_signal, risk_decision, risk_reason, portfolio_decision, account_mode "
                "FROM signals WHERE symbol = ? ORDER BY generated_at DESC LIMIT ?",
                [symbol, limit],
            ).fetchall()
        return [_row_to_signal(r) for r in rows]


def _row_to_signal(row) -> SignalRecord:
    return SignalRecord(
        trade_id=row[0], symbol=row[1], strategy_name=row[2], generated_at=row[3], direction=row[4],
        entry=row[5], stop_loss=row[6], take_profit=row[7], invalidation_price=row[8], tier=row[9],
        checklist_json=row[10], ai_win_probability=row[11], ai_rationale=row[12], ai_model_version=row[13],
        regime_at_signal=row[14], risk_decision=row[15], risk_reason=row[16], portfolio_decision=row[17],
        account_mode=row[18],
    )


@dataclass(frozen=True)
class TradeRecord:
    trade_id: str
    broker_order_id: Optional[str] = None
    filled_at: Optional[datetime] = None
    fill_price: Optional[float] = None
    quantity: Optional[int] = None


@dataclass(frozen=True)
class TradeExitRecord:
    trade_id: str
    exit_index: int
    exit_price: float
    exit_at: datetime
    outcome: str
    realized_r: Optional[float] = None


class TradeRepository:
    """Append-only for the fill, with exactly one narrow, named mutation
    (record_exit) for the one real lifecycle transition a trade has:
    open -> closed, happening at most once per trade_id. See the spec
    doc's Data Contracts section for why this is documented as the one
    deliberate exception rather than left to look like an inconsistency."""

    def __init__(self, storage: Storage):
        self._conn = storage.connection()

    def insert(self, t: TradeRecord) -> None:
        self._conn.execute(
            "INSERT INTO trades (trade_id, broker_order_id, filled_at, fill_price, quantity) "
            "VALUES (?, ?, ?, ?, ?)",
            [t.trade_id, t.broker_order_id, t.filled_at, t.fill_price, t.quantity],
        )

    def record_exit(self, e: TradeExitRecord) -> bool:
        """Returns False (no-op) if this trade_id was already closed or
        never inserted -- never a silent second write to an already-closed
        trade's exit fields. DuckDB's UPDATE returns the affected-row
        count as a single-row result (verified against duckdb 1.5.5, not
        assumed from another driver's convention)."""
        (changed,) = self._conn.execute(
            "UPDATE trades SET exit_index = ?, exit_price = ?, exit_at = ?, outcome = ?, realized_r = ? "
            "WHERE trade_id = ? AND exit_at IS NULL",
            [e.exit_index, e.exit_price, e.exit_at, e.outcome, e.realized_r, e.trade_id],
        ).fetchone()
        return changed > 0

    def get(self, trade_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT trade_id, broker_order_id, filled_at, fill_price, quantity, exit_index, "
            "exit_price, exit_at, outcome, realized_r FROM trades WHERE trade_id = ?",
            [trade_id],
        ).fetchone()
        if row is None:
            return None
        return {
            "trade_id": row[0], "broker_order_id": row[1], "filled_at": row[2], "fill_price": row[3],
            "quantity": row[4], "exit_index": row[5], "exit_price": row[6], "exit_at": row[7],
            "outcome": row[8], "realized_r": row[9],
        }


@dataclass(frozen=True)
class RegimeHistoryRecord:
    symbol: str
    regime: str
    confidence: float
    as_of: datetime


class RegimeHistoryRepository:
    def __init__(self, storage: Storage):
        self._conn = storage.connection()

    def insert(self, r: RegimeHistoryRecord) -> None:
        self._conn.execute(
            "INSERT INTO regime_history (symbol, regime, confidence, as_of) VALUES (?, ?, ?, ?)",
            [r.symbol, r.regime, r.confidence, r.as_of],
        )

    def latest(self, symbol: str) -> Optional[RegimeHistoryRecord]:
        row = self._conn.execute(
            "SELECT symbol, regime, confidence, as_of FROM regime_history "
            "WHERE symbol = ? ORDER BY as_of DESC LIMIT 1",
            [symbol],
        ).fetchone()
        return RegimeHistoryRecord(*row) if row else None


@dataclass(frozen=True)
class SettingsAuditRecord:
    field: str
    changed_by: str
    changed_at: datetime
    old_value: Optional[str] = None
    new_value: Optional[str] = None


class SettingsAuditRepository:
    """Append-only: the audit log itself must never be editable -- see
    ARCHITECTURE.md §41's point that a log table with an update path
    isn't actually an audit trail."""

    def __init__(self, storage: Storage):
        self._conn = storage.connection()

    def insert(self, a: SettingsAuditRecord) -> None:
        self._conn.execute(
            "INSERT INTO settings_audit_log (field, old_value, new_value, changed_by, changed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            [a.field, a.old_value, a.new_value, a.changed_by, a.changed_at],
        )

    def history(self, field: Optional[str] = None, limit: int = 100) -> List[SettingsAuditRecord]:
        if field is None:
            rows = self._conn.execute(
                "SELECT field, old_value, new_value, changed_by, changed_at "
                "FROM settings_audit_log ORDER BY changed_at DESC LIMIT ?",
                [limit],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT field, old_value, new_value, changed_by, changed_at "
                "FROM settings_audit_log WHERE field = ? ORDER BY changed_at DESC LIMIT ?",
                [field, limit],
            ).fetchall()
        return [SettingsAuditRecord(field=r[0], old_value=r[1], new_value=r[2], changed_by=r[3], changed_at=r[4]) for r in rows]


@dataclass(frozen=True)
class AccountSnapshotRecord:
    account_mode: str
    equity: float
    open_positions: int
    as_of: datetime


class AccountSnapshotRepository:
    def __init__(self, storage: Storage):
        self._conn = storage.connection()

    def insert(self, snap: AccountSnapshotRecord) -> None:
        self._conn.execute(
            "INSERT INTO account_snapshots (account_mode, equity, open_positions, as_of) "
            "VALUES (?, ?, ?, ?)",
            [snap.account_mode, snap.equity, snap.open_positions, snap.as_of],
        )

    def latest(self, account_mode: str) -> Optional[AccountSnapshotRecord]:
        row = self._conn.execute(
            "SELECT account_mode, equity, open_positions, as_of FROM account_snapshots "
            "WHERE account_mode = ? ORDER BY as_of DESC LIMIT 1",
            [account_mode],
        ).fetchone()
        return AccountSnapshotRecord(*row) if row else None

    def equity_curve(self, account_mode: str, since: Optional[datetime] = None) -> List[AccountSnapshotRecord]:
        if since is None:
            rows = self._conn.execute(
                "SELECT account_mode, equity, open_positions, as_of FROM account_snapshots "
                "WHERE account_mode = ? ORDER BY as_of ASC",
                [account_mode],
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT account_mode, equity, open_positions, as_of FROM account_snapshots "
                "WHERE account_mode = ? AND as_of >= ? ORDER BY as_of ASC",
                [account_mode, since],
            ).fetchall()
        return [AccountSnapshotRecord(*r) for r in rows]
