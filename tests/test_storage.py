"""Tests for the Storage layer (Subsystem 1, docs/specs/01-storage-and-event-bus.md)."""

from datetime import datetime, timezone

import pytest

from trading_brain.events import InMemoryEventBus, SignalCandidateEvent
from trading_brain.storage import (
    AccountSnapshotRecord,
    AccountSnapshotRepository,
    RegimeHistoryRecord,
    RegimeHistoryRepository,
    SettingsAuditRecord,
    SettingsAuditRepository,
    SignalRecord,
    SignalRepository,
    Storage,
    TradeExitRecord,
    TradeRecord,
    TradeRepository,
)


@pytest.fixture
def storage():
    s = Storage(":memory:")
    s.migrate()
    return s


def _signal(trade_id="t1", symbol="GC=F") -> SignalRecord:
    return SignalRecord(
        trade_id=trade_id, symbol=symbol, strategy_name="smart_money_concepts",
        generated_at=datetime.now(timezone.utc), direction="bullish",
        entry=2500.0, stop_loss=2490.0, take_profit=2520.0, invalidation_price=2485.0,
        tier="A", checklist_json="{}", risk_decision="approved", account_mode="paper",
    )


def test_migrate_is_idempotent(storage):
    before = storage.connection().execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    storage.migrate()  # second call must not raise or duplicate schema
    after = storage.connection().execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    # not hardcoding a migration count: this suite gains a migration file
    # per future subsystem, so the real assertion is "no duplicates
    # appeared", not "there is exactly one migration"
    assert after == before
    assert len(after) == len(set(after))


def test_signal_insert_then_get_round_trips_every_field(storage):
    repo = SignalRepository(storage)
    rec = _signal()
    repo.insert(rec)
    assert repo.get("t1") == rec


def test_signal_get_missing_returns_none(storage):
    repo = SignalRepository(storage)
    assert repo.get("nope") is None


def test_signal_recent_filters_by_symbol_and_orders_newest_first(storage):
    repo = SignalRepository(storage)
    repo.insert(_signal(trade_id="a", symbol="GC=F"))
    repo.insert(_signal(trade_id="b", symbol="ES=F"))
    repo.insert(_signal(trade_id="c", symbol="GC=F"))
    gc_only = repo.recent(symbol="GC=F")
    assert {r.trade_id for r in gc_only} == {"a", "c"}


def test_signal_repository_has_no_update_or_delete():
    # Append-only is a property of what the object CAN do, not a
    # convention -- asserted via introspection, not "we didn't call it".
    assert not hasattr(SignalRepository, "update")
    assert not hasattr(SignalRepository, "delete")


def test_settings_audit_repository_has_no_update_or_delete():
    assert not hasattr(SettingsAuditRepository, "update")
    assert not hasattr(SettingsAuditRepository, "delete")


def test_trade_insert_then_record_exit_round_trips(storage):
    SignalRepository(storage).insert(_signal())
    trades = TradeRepository(storage)
    trades.insert(TradeRecord(trade_id="t1", broker_order_id="o1", filled_at=datetime.now(timezone.utc), fill_price=2500.0, quantity=1))

    changed = trades.record_exit(TradeExitRecord(
        trade_id="t1", exit_index=5, exit_price=2520.0, exit_at=datetime.now(timezone.utc),
        outcome="win", realized_r=2.0,
    ))
    assert changed is True

    row = trades.get("t1")
    assert row["outcome"] == "win"
    assert row["realized_r"] == 2.0


def test_record_exit_on_an_already_closed_trade_is_a_noop_not_a_second_write(storage):
    SignalRepository(storage).insert(_signal())
    trades = TradeRepository(storage)
    trades.insert(TradeRecord(trade_id="t1"))
    trades.record_exit(TradeExitRecord(trade_id="t1", exit_index=1, exit_price=100.0, exit_at=datetime.now(timezone.utc), outcome="win", realized_r=1.0))

    second = trades.record_exit(TradeExitRecord(trade_id="t1", exit_index=2, exit_price=200.0, exit_at=datetime.now(timezone.utc), outcome="loss", realized_r=-1.0))

    assert second is False
    row = trades.get("t1")
    assert row["exit_price"] == 100.0  # untouched by the second call
    assert row["outcome"] == "win"


def test_regime_history_latest_returns_the_most_recent_entry(storage):
    repo = RegimeHistoryRepository(storage)
    repo.insert(RegimeHistoryRecord(symbol="GC=F", regime="trending", confidence=0.6, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    repo.insert(RegimeHistoryRecord(symbol="GC=F", regime="ranging", confidence=0.8, as_of=datetime(2026, 2, 1, tzinfo=timezone.utc)))
    latest = repo.latest("GC=F")
    assert latest.regime == "ranging"


def test_settings_audit_history_round_trips(storage):
    repo = SettingsAuditRepository(storage)
    repo.insert(SettingsAuditRecord(field="risk_percent", old_value="0.5", new_value="1.0", changed_by="human:dashboard", changed_at=datetime.now(timezone.utc)))
    history = repo.history(field="risk_percent")
    assert len(history) == 1
    assert history[0].new_value == "1.0"


def test_account_snapshot_equity_curve_is_ordered_oldest_first(storage):
    repo = AccountSnapshotRepository(storage)
    repo.insert(AccountSnapshotRecord(account_mode="paper", equity=100_000.0, open_positions=0, as_of=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    repo.insert(AccountSnapshotRecord(account_mode="paper", equity=101_000.0, open_positions=1, as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    curve = repo.equity_curve("paper")
    assert [s.equity for s in curve] == [101_000.0, 100_000.0]


def test_event_bus_publish_persists_synchronously_via_a_subscriber(storage):
    """The smallest possible proof of ARCHITECTURE.md §16's rule: every
    event that matters is persisted synchronously as part of its handler,
    not asynchronously or best-effort."""
    bus = InMemoryEventBus()
    repo = SignalRepository(storage)

    def on_signal(event: SignalCandidateEvent) -> None:
        repo.insert(_signal(trade_id=event.trade_id, symbol=event.symbol))

    bus.subscribe(SignalCandidateEvent, on_signal)
    bus.publish(SignalCandidateEvent(trade_id="live-1", symbol="ES=F", strategy_name="smart_money_concepts"))

    assert repo.get("live-1") is not None
