"""
Event Bus — AI Trading Brain, Subsystem 1 (see docs/specs/01-storage-and-event-bus.md)

Implements ARCHITECTURE.md §4's EventBus as a Protocol with one in-memory
implementation today, so a durable/distributed implementation can replace
it later (§4's stated swap-later seam) without any publisher or subscriber
changing.

Deliberately synchronous, not asyncio-based, despite §4's own sketch --
see the spec doc's "Design decision" for the reasoning: every pure-domain
module this bus will eventually carry events about (strategy.py,
backtest.py, risk.py, scoring.py) is synchronous, and forcing async here
would either infect that layer for no domain reason or require every
domain publisher to bridge into an event loop. A synchronous bus can be
called from async code (service/'s FastAPI handlers) trivially; the
reverse is not true. Recorded as a deviation from §4's sketch, not an
oversight -- the ADD's own eight-question checklist (unnecessary
complexity, coupling) is what motivated it.

Event types here are the vocabulary named in §4, not a claim that every
producer/consumer exists yet -- most don't (Risk Engine, Portfolio
Engine, AI Decision Engine are still architecture, not code). Declaring
the shape now is cheap and keeps the data contract in one place; wiring
real producers onto the bus is later subsystems' work, scoped out
explicitly in docs/specs/01-storage-and-event-bus.md.
"""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Type, TypeVar


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Event:
    """Base for every event on the bus. Concrete events below add their
    own fields via dataclass inheritance; event_id/occurred_at are always
    present so any event can be logged/traced uniformly (ARCHITECTURE.md
    §22's trade_id-threading idea generalizes to event_id here)."""
    event_id: str = field(default_factory=_new_id)
    occurred_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class SignalCandidateEvent(Event):
    trade_id: str = ""
    symbol: str = ""
    strategy_name: str = ""
    generated_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class RegimeChangedEvent(Event):
    symbol: str = ""
    regime: str = ""
    confidence: float = 0.0
    as_of: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class OrderFilledEvent(Event):
    trade_id: str = ""
    order_id: str = ""
    fill_price: float = 0.0
    quantity: int = 0
    filled_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class PositionClosedEvent(Event):
    trade_id: str = ""
    exit_price: float = 0.0
    outcome: str = ""
    realized_r: Optional[float] = None
    exit_at: datetime = field(default_factory=_now)


@dataclass(frozen=True)
class SettingsChangedEvent(Event):
    field_name: str = ""
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    changed_by: str = ""


@dataclass(frozen=True)
class KillSwitchEvent(Event):
    active: bool = False
    triggered_by: str = ""
    reason: str = ""


class HandlerErrors(Exception):
    """Raised by publish() when one or more subscriber handlers raised.
    Not the builtin ExceptionGroup (Python 3.11+) -- pyproject.toml
    targets >=3.9, matching the Python 3.9 the project actually runs on
    (see the Mac's own traceback in this session: Python3.framework/
    Versions/3.9), so a 3.11-only builtin would crash there at runtime."""

    def __init__(self, message: str, errors: List[Exception]):
        super().__init__(message)
        self.errors = errors


E = TypeVar("E", bound=Event)
Handler = Callable[[E], None]


class EventBus(ABC):
    @abstractmethod
    def publish(self, event: Event) -> None:
        raise NotImplementedError

    @abstractmethod
    def subscribe(self, event_type: Type[E], handler: Handler) -> None:
        raise NotImplementedError


class InMemoryEventBus(EventBus):
    """The only implementation that exists today. publish() calls every
    matching handler synchronously, in subscription order. One handler
    raising does not stop the others -- a broken subscriber (e.g. a
    logging handler with a bug) must never be able to silently prevent a
    Storage-writing handler from running, since durability depends on
    that handler actually executing (§16: "every event that matters is
    persisted synchronously")."""

    def __init__(self) -> None:
        self._handlers: Dict[Type[Event], List[Handler]] = {}

    def publish(self, event: Event) -> None:
        errors: List[Exception] = []
        for handler in self._handlers.get(type(event), []):
            try:
                handler(event)
            except Exception as exc:  # noqa: BLE001 -- isolate handlers from each other, see docstring
                errors.append(exc)
        if errors:
            raise HandlerErrors(f"{len(errors)} handler(s) failed for {type(event).__name__}", errors)

    def subscribe(self, event_type: Type[E], handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
