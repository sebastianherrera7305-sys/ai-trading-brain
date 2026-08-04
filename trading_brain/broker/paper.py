"""
Paper Broker Module — AI Trading Brain, Phase 3

An in-memory fill simulator implementing the same Broker ABC as ibkr.py.
Two reasons this exists as its own adapter rather than just "IBKR in paper
mode": (1) it lets the whole service (settings, dashboard, engine_runner)
be exercised end-to-end in this sandbox with no IB Gateway reachable at
all, and (2) it's a second independent implementation of the same
interface, which is itself a check that the Broker ABC in base.py is
actually broker-agnostic and not secretly shaped around IBKR's quirks.

Fill model: market orders fill instantly at the last known price for the
symbol (via feed_bar). Limit orders rest until a later feed_bar touches the
limit -- BUY fills when price <= limit, SELL fills when price >= limit,
the standard limit-order rule regardless of whether the order is opening,
closing, or flipping a position.

PnL accounting: avg_entry_price is a running weighted average while a
position stays on one side. A fill on the opposite side first realizes P&L
against the existing position for the closing portion (credited to cash
immediately -- this is exactly the bug class to avoid: crediting realized
P&L only as margin-back-to-starting-balance means the account can never
show a real gain or loss), then opens a fresh position at the fill price
for any leftover size if the fill flips the position through flat.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .base import (
    AccountSummary,
    Bar,
    BarCallback,
    Broker,
    ConnectionCallback,
    ConnectionState,
    FillCallback,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
    Position,
)


@dataclass
class _RestingOrder:
    broker_order_id: str
    request: OrderRequest
    on_fill: Optional[FillCallback]


@dataclass
class _Bracket:
    stop_loss: Optional[float]
    take_profit: Optional[float]


class PaperBroker(Broker):
    def __init__(self, starting_cash: float = 100_000.0, max_contracts: int = 10):
        self.starting_cash = starting_cash
        self.max_contracts = max_contracts
        self._cash = starting_cash
        self._realized_pnl_today = 0.0
        self._positions: Dict[str, Position] = {}
        self._last_price: Dict[str, float] = {}
        self._resting: Dict[str, List[_RestingOrder]] = {}
        self._brackets: Dict[str, _Bracket] = {}
        self._bar_callbacks: Dict[str, List[BarCallback]] = {}
        self._connection_callbacks: List[ConnectionCallback] = []
        self._order_log: List[OrderResult] = []
        self._order_log_entries: List[Dict[str, Any]] = []
        self._next_order_id = 1
        self._state = ConnectionState.DISCONNECTED

    # ---- connection ----

    def connect(self) -> None:
        self._set_state(ConnectionState.CONNECTED)

    def disconnect(self) -> None:
        self._set_state(ConnectionState.DISCONNECTED)

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    def on_connection_state_change(self, callback: ConnectionCallback) -> None:
        self._connection_callbacks.append(callback)

    def _set_state(self, state: ConnectionState) -> None:
        if state == self._state:
            return
        self._state = state
        for cb in self._connection_callbacks:
            cb(state)

    # ---- market data ----

    def subscribe_bars(self, symbol: str, on_bar: BarCallback) -> None:
        self._bar_callbacks.setdefault(symbol, []).append(on_bar)

    def mark_price(self, symbol: str, price: float) -> None:
        """Updates the last-known price and unrealized P&L only -- no
        resting-order resolution, no bracket checks, no bar callbacks (so
        it never reaches LiveEngine). For intraday price ticks a live feed
        polls between real bars: this keeps the displayed price/P&L
        current without the strategy engine seeing anything but genuine
        bars at the cadence it was validated against (see
        engine_runner.py's module docstring on why that matters)."""
        self._last_price[symbol] = price
        self._mark_to_market(symbol)

    def feed_bar(self, bar: Bar) -> None:
        """Test/driver entry point: simulates a new bar arriving for a
        symbol. Updates the mark price, resolves any resting limit orders
        that the bar's range touches, marks open positions to market, and
        notifies subscribers -- in that order, so a fill triggered by this
        bar is reflected before on_bar callbacks see it."""
        self._last_price[bar.symbol] = bar.close
        self._resolve_resting_orders(bar)
        self._check_bracket_exit(bar)
        self._mark_to_market(bar.symbol)
        for cb in self._bar_callbacks.get(bar.symbol, []):
            cb(bar)

    def _check_bracket_exit(self, bar: Bar) -> None:
        """Auto-closes a position when its stop-loss or take-profit (attached
        at entry via OrderRequest.stop_loss/take_profit) is touched by this
        bar -- without this, a filled entry would just sit open forever with
        no broker-side exit, since PaperBroker doesn't poll continuously the
        way a real order book does. Stop is checked before target, matching
        the backtester's own conservative rule for a bar that touches both."""
        symbol = bar.symbol
        bracket = self._brackets.get(symbol)
        pos = self._positions.get(symbol)
        if bracket is None or pos is None or pos.quantity == 0:
            return
        long = pos.quantity > 0
        exit_price = None
        if bracket.stop_loss is not None:
            stopped = (bar.low <= bracket.stop_loss) if long else (bar.high >= bracket.stop_loss)
            if stopped:
                exit_price = bracket.stop_loss
        if exit_price is None and bracket.take_profit is not None:
            targeted = (bar.high >= bracket.take_profit) if long else (bar.low <= bracket.take_profit)
            if targeted:
                exit_price = bracket.take_profit
        if exit_price is None:
            return
        side = OrderSide.SELL if long else OrderSide.BUY
        req = OrderRequest(symbol=symbol, side=side, quantity=abs(pos.quantity))
        self._execute_fill(req, exit_price)

    def _resolve_resting_orders(self, bar: Bar) -> None:
        remaining = []
        for resting in self._resting.get(bar.symbol, []):
            req = resting.request
            touched = (
                bar.low <= req.limit_price if req.side == OrderSide.BUY
                else bar.high >= req.limit_price
            )
            if touched:
                result = self._execute_fill(req, req.limit_price, resting.broker_order_id)
                if resting.on_fill:
                    resting.on_fill(result)
            else:
                remaining.append(resting)
        if remaining:
            self._resting[bar.symbol] = remaining
        else:
            self._resting.pop(bar.symbol, None)

    # ---- orders ----

    def _record(self, request: OrderRequest, result: OrderResult) -> None:
        """Keeps an enriched log entry alongside the raw OrderResult -- the
        dashboard needs symbol/side/quantity/timestamp to render an order
        log line, none of which OrderResult itself carries (it only reports
        what the broker did, not what was asked for). Timestamp is wall-
        clock at record time; this is a paper-simulation convenience for
        driving the dashboard, not a claim about simulated-market time."""
        self._order_log.append(result)
        self._order_log_entries.append({
            "client_order_id": result.client_order_id,
            "broker_order_id": result.broker_order_id,
            "symbol": request.symbol,
            "side": request.side.value,
            "status": result.status.value,
            "quantity": request.quantity,
            "avg_fill_price": result.avg_fill_price,
            "reason": result.reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    @property
    def order_log_entries(self) -> List[Dict[str, Any]]:
        return list(self._order_log_entries)

    def _new_order_id(self) -> str:
        oid = f"paper-{self._next_order_id}"
        self._next_order_id += 1
        return oid

    def place_order(self, request: OrderRequest, on_fill: Optional[FillCallback] = None) -> OrderResult:
        existing = self._positions.get(request.symbol)
        existing_qty = existing.quantity if existing else 0.0
        signed_delta = request.quantity if request.side == OrderSide.BUY else -request.quantity
        prospective = existing_qty + signed_delta
        if abs(prospective) > self.max_contracts:
            result = OrderResult(
                client_order_id=request.client_order_id,
                broker_order_id=None,
                status=OrderStatus.REJECTED,
                reason=(
                    f"would bring {request.symbol} position to {prospective:g}, "
                    f"exceeds max_contracts={self.max_contracts}"
                ),
            )
            self._record(request, result)
            return result

        if request.limit_price is None:
            price = self._last_price.get(request.symbol, 0.0)
            result = self._execute_fill(request, price)
            if on_fill:
                on_fill(result)
            return result

        # Resting limit order: acknowledge as submitted, fill later on a bar
        # whose range touches the limit price (see _resolve_resting_orders).
        broker_order_id = self._new_order_id()
        self._resting.setdefault(request.symbol, []).append(
            _RestingOrder(broker_order_id, request, on_fill)
        )
        result = OrderResult(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id,
            status=OrderStatus.SUBMITTED,
        )
        self._record(request, result)
        return result

    def _execute_fill(
        self, request: OrderRequest, price: float, broker_order_id: Optional[str] = None
    ) -> OrderResult:
        symbol = request.symbol
        existing = self._positions.get(symbol)
        existing_qty = existing.quantity if existing else 0.0
        avg_entry = existing.avg_entry_price if existing else 0.0
        realized_before = existing.realized_pnl if existing else 0.0

        signed_delta = request.quantity if request.side == OrderSide.BUY else -request.quantity
        same_direction = existing_qty == 0 or (existing_qty > 0) == (signed_delta > 0)

        if same_direction:
            new_qty = existing_qty + signed_delta
            if new_qty == 0:
                new_avg = 0.0
            else:
                new_avg = (
                    (abs(existing_qty) * avg_entry + abs(signed_delta) * price) / abs(new_qty)
                )
            realized_delta = 0.0
        else:
            closing_qty = min(abs(existing_qty), abs(signed_delta))
            if existing_qty > 0:  # long being sold down/closed
                realized_delta = (price - avg_entry) * closing_qty
            else:  # short being bought back
                realized_delta = (avg_entry - price) * closing_qty
            leftover = abs(signed_delta) - closing_qty
            new_qty = existing_qty + signed_delta
            if leftover > 0:
                # Flipped through flat -- the leftover opens a fresh position.
                new_avg = price
            else:
                new_avg = avg_entry if new_qty != 0 else 0.0

        self._cash += realized_delta
        self._realized_pnl_today += realized_delta
        self._positions[symbol] = Position(
            symbol=symbol,
            quantity=new_qty,
            avg_entry_price=new_avg,
            unrealized_pnl=0.0,
            realized_pnl=realized_before + realized_delta,
        )
        if new_qty == 0:
            self._brackets.pop(symbol, None)
        elif request.stop_loss is not None or request.take_profit is not None:
            self._brackets[symbol] = _Bracket(request.stop_loss, request.take_profit)
        self._mark_to_market(symbol)

        result = OrderResult(
            client_order_id=request.client_order_id,
            broker_order_id=broker_order_id or self._new_order_id(),
            status=OrderStatus.FILLED,
            filled_quantity=request.quantity,
            avg_fill_price=price,
        )
        self._record(request, result)
        return result

    def _mark_to_market(self, symbol: str) -> None:
        pos = self._positions.get(symbol)
        if pos is None or pos.quantity == 0:
            return
        price = self._last_price.get(symbol, pos.avg_entry_price)
        if pos.quantity > 0:
            pos.unrealized_pnl = (price - pos.avg_entry_price) * pos.quantity
        else:
            pos.unrealized_pnl = (pos.avg_entry_price - price) * abs(pos.quantity)

    def cancel_order(self, broker_order_id: str) -> None:
        for symbol, resting_list in list(self._resting.items()):
            kept = [r for r in resting_list if r.broker_order_id != broker_order_id]
            if kept:
                self._resting[symbol] = kept
            else:
                self._resting.pop(symbol, None)

    def flatten_all(self) -> List[OrderResult]:
        results = []
        for symbol, pos in list(self._positions.items()):
            if pos.quantity == 0:
                continue
            side = OrderSide.SELL if pos.quantity > 0 else OrderSide.BUY
            price = self._last_price.get(symbol, pos.avg_entry_price)
            req = OrderRequest(symbol=symbol, side=side, quantity=abs(pos.quantity))
            results.append(self._execute_fill(req, price))
        self._resting.clear()
        return results

    def get_positions(self) -> Dict[str, Position]:
        return {s: p for s, p in self._positions.items() if p.quantity != 0}

    def get_account_summary(self) -> AccountSummary:
        unrealized = sum(p.unrealized_pnl for p in self._positions.values())
        net_liq = self._cash + unrealized
        return AccountSummary(
            net_liquidation=net_liq,
            cash=self._cash,
            buying_power=self._cash,
            realized_pnl_today=self._realized_pnl_today,
            unrealized_pnl=unrealized,
        )

    def reset_day(self) -> None:
        self._realized_pnl_today = 0.0

    @property
    def order_log(self) -> List[OrderResult]:
        return list(self._order_log)
