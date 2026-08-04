"""
Broker Module — AI Trading Brain, Phase 3

Defines the contract every broker adapter must satisfy. The engine and the
dashboard service only ever talk to this interface -- never to a specific
broker's SDK directly. That's what lets ibkr.py (real Interactive Brokers,
paper or live) and paper.py (an in-memory fill simulator, no broker needed)
sit behind the exact same code path.

Money-handling rule: an OrderResult always reports what actually happened,
never what was requested. If a broker rejects, partially fills, or reprices
an order, that shows up in the result -- callers must not assume their
request was honored just because no exception was raised.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, List, Optional


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class Position:
    symbol: str
    quantity: float  # signed: positive = long, negative = short
    avg_entry_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    limit_price: Optional[float] = None  # None = market order
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    client_order_id: Optional[str] = None  # caller-assigned, for correlating fills/rejects


@dataclass
class OrderResult:
    client_order_id: Optional[str]
    broker_order_id: Optional[str]
    status: OrderStatus
    filled_quantity: float = 0.0
    avg_fill_price: Optional[float] = None
    reason: Optional[str] = None  # populated on REJECTED/CANCELLED


@dataclass
class AccountSummary:
    net_liquidation: float
    cash: float
    buying_power: float
    realized_pnl_today: float
    unrealized_pnl: float


@dataclass
class Bar:
    """A single OHLC bar for one symbol, timestamped -- what the engine
    consumes on each tick to decide whether to act."""
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


# Callback signatures the engine/service register to react to broker events,
# rather than polling. `fill` fires once per OrderResult transition (e.g. a
# partial fill followed later by a full fill fires twice); `bar` fires once
# per new bar per subscribed symbol.
FillCallback = Callable[[OrderResult], None]
BarCallback = Callable[[Bar], None]
ConnectionCallback = Callable[[ConnectionState], None]


class Broker(ABC):
    """Every method is synchronous from the caller's point of view; adapters
    that are natively async (ib_async) are responsible for bridging that
    internally. This keeps engine_runner.py broker-agnostic."""

    @abstractmethod
    def connect(self) -> None:
        """Establish the connection. Must be safe to call again after
        disconnect() (e.g. after a dropped session) -- adapters should not
        assume connect() is only ever called once per process lifetime."""
        raise NotImplementedError

    @abstractmethod
    def disconnect(self) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def connection_state(self) -> ConnectionState:
        raise NotImplementedError

    @abstractmethod
    def subscribe_bars(self, symbol: str, on_bar: BarCallback) -> None:
        """Registers on_bar to be called for every new bar on symbol. Safe to
        call multiple times for the same symbol with different callbacks --
        adapters must not silently drop earlier subscribers."""
        raise NotImplementedError

    @abstractmethod
    def on_connection_state_change(self, callback: ConnectionCallback) -> None:
        raise NotImplementedError

    @abstractmethod
    def place_order(self, request: OrderRequest, on_fill: Optional[FillCallback] = None) -> OrderResult:
        """Submits an order. Returns the immediate result (typically
        SUBMITTED for a live order, or FILLED/REJECTED for adapters that
        resolve synchronously, like the paper broker). Later fill/status
        transitions are delivered via on_fill, keyed by client_order_id."""
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def flatten_all(self) -> List[OrderResult]:
        """Market-closes every open position immediately. This is the 'flatten
        all' panic button -- it must not depend on the strategy engine or on
        any pending/resting orders being in a particular state."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> Dict[str, Position]:
        raise NotImplementedError

    @abstractmethod
    def get_account_summary(self) -> AccountSummary:
        raise NotImplementedError
