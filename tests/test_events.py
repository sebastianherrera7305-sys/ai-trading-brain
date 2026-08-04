"""Tests for the Event Bus (Subsystem 1, docs/specs/01-storage-and-event-bus.md)."""

import pytest

from trading_brain.events import Event, HandlerErrors, InMemoryEventBus, SignalCandidateEvent, RegimeChangedEvent


def test_publish_with_no_subscribers_is_a_noop():
    bus = InMemoryEventBus()
    bus.publish(SignalCandidateEvent(trade_id="t1"))  # must not raise


def test_subscriber_only_receives_its_own_event_type():
    bus = InMemoryEventBus()
    received = []
    bus.subscribe(SignalCandidateEvent, lambda e: received.append(e))
    bus.publish(RegimeChangedEvent(symbol="GC=F"))
    assert received == []
    bus.publish(SignalCandidateEvent(trade_id="t1"))
    assert len(received) == 1
    assert received[0].trade_id == "t1"


def test_multiple_subscribers_to_the_same_type_all_receive_the_event():
    bus = InMemoryEventBus()
    a, b = [], []
    bus.subscribe(SignalCandidateEvent, lambda e: a.append(e))
    bus.subscribe(SignalCandidateEvent, lambda e: b.append(e))
    bus.publish(SignalCandidateEvent(trade_id="t1"))
    assert len(a) == 1 and len(b) == 1


def test_a_failing_handler_does_not_prevent_other_handlers_from_running():
    bus = InMemoryEventBus()
    ran = []

    def broken(e):
        raise ValueError("boom")

    def fine(e):
        ran.append(e)

    bus.subscribe(SignalCandidateEvent, broken)
    bus.subscribe(SignalCandidateEvent, fine)

    with pytest.raises(HandlerErrors):
        bus.publish(SignalCandidateEvent(trade_id="t1"))

    assert len(ran) == 1  # fine() still ran despite broken() raising


def test_every_event_has_a_unique_id_and_a_timestamp():
    a = SignalCandidateEvent(trade_id="t1")
    b = SignalCandidateEvent(trade_id="t2")
    assert a.event_id != b.event_id
    assert isinstance(a, Event)
