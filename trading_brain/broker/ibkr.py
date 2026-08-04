"""
IBKR Broker Adapter -- AI Trading Brain, Phase 3

Implements the `Broker` ABC (see base.py) against Interactive Brokers using
the `ib_async` library. Defaults point at the *paper* trading endpoints
(TWS paper = port 7497, IB Gateway paper = port 4002) -- pass a different
host/port/client_id to target a live account, but nothing here changes
behavior based on that; treat this whole module as "talks to whatever
account the given port belongs to" and keep pointing it at paper unless you
mean it.

Money-handling rule (from base.py): an OrderResult always reports what the
broker actually did, never what was requested. Every method below builds its
OrderResult from the ib_async Trade/OrderStatus objects IBKR handed back --
never by echoing the request back to the caller -- and place_order/flatten_all
never claim FILLED just because placeOrder() didn't raise.

Known approximation -- READ THIS BEFORE LIVE USE:

    Futures front-month selection (`_resolve_front_month_future`) is a real
    unsolved problem here. Our Yahoo-style tickers (GC=F, ES=F, CL=F) don't
    encode an expiry, so on first use of a futures symbol we ask IBKR for
    every listed contract on that symbol/exchange (`reqContractDetails` on a
    bare Future(symbol=..., exchange=..., currency=...)) and pick the
    nearest one whose lastTradeDateOrContractMonth hasn't passed yet. That's
    a reasonable default for paper trading and for "just get a tradeable
    front-month contract", but it is NOT a rollover strategy: it doesn't
    know about volume/open-interest rollover conventions, doesn't avoid
    trading through a contract's last few illiquid days before expiry, and
    resolves once then caches for the adapter's lifetime (so it won't roll
    you into the next contract automatically as expiry approaches). Real
    production use needs an explicit, tested rollover policy -- picking the
    wrong expiry silently trades the wrong instrument.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

import ib_async

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

logger = logging.getLogger(__name__)


# Paper-trading defaults per IBKR docs: TWS paper account = 7497,
# IB Gateway paper account = 4002. Live ports are 7496 / 4001 respectively --
# pass those explicitly if you really want a live account.
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7497
DEFAULT_CLIENT_ID = 1

# Realtime bar size in seconds -- 5s is the only granularity IBKR's
# reqRealTimeBars API supports; consumers that want coarser bars aggregate
# these themselves.
REALTIME_BAR_SIZE = 5

# accountSummary() tags we care about, mapped to AccountSummary fields below.
_ACCOUNT_TAGS = ("NetLiquidation", "TotalCashValue", "BuyingPower", "RealizedPnL", "UnrealizedPnL")

# IBKR order-status strings that mean "done, one way or another".
_DONE_CANCELLED_STATUSES = ("Cancelled", "ApiCancelled")


class IBKRBroker(Broker):
    """Broker adapter for Interactive Brokers via ib_async.

    Every ib_async call used here (`connect`, `positions`, `accountSummary`,
    `placeOrder`, ...) is ib_async's *synchronous* wrapper -- it runs its own
    event loop internally and blocks the calling thread until the request
    resolves, so this class stays a plain synchronous Broker implementation
    per the ABC's contract; callers never see an asyncio object.
    """

    # Symbol map: our Yahoo-style CSV/backtest tickers -> how to build the
    # IBKR contract. "future" entries are resolved to a specific expiry by
    # _resolve_front_month_future (see module docstring caveat above);
    # "forex" entries need no expiry and are qualified directly.
    SYMBOL_MAP: Dict[str, Dict[str, str]] = {
        "GC=F": {"kind": "future", "symbol": "GC", "exchange": "COMEX", "currency": "USD"},
        "ES=F": {"kind": "future", "symbol": "ES", "exchange": "CME", "currency": "USD"},
        "CL=F": {"kind": "future", "symbol": "CL", "exchange": "NYMEX", "currency": "USD"},
        "EURUSD=X": {"kind": "forex", "pair": "EURUSD"},
    }

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        client_id: int = DEFAULT_CLIENT_ID,
        account: str = "",
        ib_factory=None,
    ):
        """
        Args:
            host, port, client_id: TWS/IB Gateway connection params. Defaults
                target TWS paper trading (127.0.0.1:7497).
            account: IBKR account id to scope positions/summary/orders to.
                Leave blank to use whichever single account the session has
                (fine for a personal paper account; required for tests/CI to
                specify an explicit account if the session ever has more than
                one linked).
            ib_factory: callable returning a fresh `ib_async.IB()`-like
                object. Defaults to `ib_async.IB`. Overridable so tests can
                inject a mock without touching the network.
        """
        self._host = host
        self._port = port
        self._client_id = client_id
        self._account = account
        self._ib_factory = ib_factory or ib_async.IB

        self.ib = None  # type: Optional[object]  # ib_async.IB once connected
        self._state = ConnectionState.DISCONNECTED
        self._connection_callbacks: List[ConnectionCallback] = []

        # symbol -> [callback, ...]; never replaced wholesale so registering
        # a second callback for the same symbol doesn't drop the first.
        self._bar_callbacks: Dict[str, List[BarCallback]] = {}
        # symbol -> the live ib_async RealTimeBarList, so a second
        # subscribe_bars() call for the same symbol reuses the one IBKR
        # subscription instead of opening a duplicate market data line.
        self._bar_subscriptions: Dict[str, object] = {}

        self._contract_cache: Dict[str, object] = {}

        # client_order_id -> caller's on_fill callback.
        self._fill_callbacks: Dict[str, FillCallback] = {}
        # ib orderId -> client_order_id, so orderStatusEvent/errorEvent (which
        # only carry IBKR's numeric orderId) can find the right callback.
        self._order_meta: Dict[int, str] = {}

        # Reverse lookup for get_positions(): (secType, ib-side symbol) ->
        # our ticker, built once from SYMBOL_MAP.
        self._reverse_symbol_map: Dict[tuple, str] = {}
        for our_symbol, spec in self.SYMBOL_MAP.items():
            if spec["kind"] == "future":
                self._reverse_symbol_map[("FUT", spec["symbol"])] = our_symbol
            elif spec["kind"] == "forex":
                self._reverse_symbol_map[("CASH", spec["pair"])] = our_symbol

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def connection_state(self) -> ConnectionState:
        return self._state

    def on_connection_state_change(self, callback: ConnectionCallback) -> None:
        self._connection_callbacks.append(callback)

    def _set_state(self, new_state: ConnectionState) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        for callback in list(self._connection_callbacks):
            try:
                callback(new_state)
            except Exception:
                logger.exception("on_connection_state_change callback raised")

    def connect(self) -> None:
        """Idempotent: a no-op if already connected. Safe to call again
        after disconnect() -- builds a fresh ib_async.IB() each time rather
        than reusing a possibly-torn-down one from a prior session."""
        if self._state == ConnectionState.CONNECTED and self.ib is not None and self.ib.isConnected():
            return

        self._set_state(ConnectionState.CONNECTING)
        self.ib = self._ib_factory()
        self._wire_events(self.ib)
        try:
            self.ib.connect(self._host, self._port, clientId=self._client_id)
        except Exception:
            self._set_state(ConnectionState.ERROR)
            raise
        self._set_state(ConnectionState.CONNECTED)

    def disconnect(self) -> None:
        if self.ib is not None:
            try:
                self.ib.disconnect()
            except Exception:
                logger.exception("ib_async disconnect() raised")
        self._set_state(ConnectionState.DISCONNECTED)

    def _wire_events(self, ib) -> None:
        ib.disconnectedEvent += self._on_ib_disconnected
        ib.orderStatusEvent += self._on_order_status
        ib.errorEvent += self._on_error

    def _on_ib_disconnected(self) -> None:
        # Fires on both a clean disconnect() and an unexpected drop -- either
        # way the connection is gone, so reflect that regardless of who
        # initiated it.
        self._set_state(ConnectionState.DISCONNECTED)

    def _is_connected(self) -> bool:
        return self.ib is not None and self._state == ConnectionState.CONNECTED

    # ------------------------------------------------------------------
    # Symbol / contract resolution
    # ------------------------------------------------------------------

    def _get_contract(self, symbol: str):
        if symbol in self._contract_cache:
            return self._contract_cache[symbol]

        spec = self.SYMBOL_MAP.get(symbol)
        if spec is None:
            raise ValueError(
                f"No IBKR contract mapping for symbol {symbol!r}. "
                f"Known symbols: {sorted(self.SYMBOL_MAP)}"
            )

        if spec["kind"] == "forex":
            contract = ib_async.Forex(spec["pair"])
            qualified = self.ib.qualifyContracts(contract)
            if qualified:
                contract = qualified[0]
        elif spec["kind"] == "future":
            contract = self._resolve_front_month_future(spec)
        else:
            raise ValueError(f"Unknown contract kind {spec['kind']!r} for symbol {symbol!r}")

        self._contract_cache[symbol] = contract
        return contract

    def _resolve_front_month_future(self, spec: Dict[str, str]):
        """See the module docstring's front-month caveat -- this is a
        best-effort "nearest unexpired listing" pick, not a rollover
        strategy."""
        template = ib_async.Future(symbol=spec["symbol"], exchange=spec["exchange"], currency=spec["currency"])
        details = self.ib.reqContractDetails(template)
        if not details:
            raise RuntimeError(
                f"IBKR returned no contract details for future {spec['symbol']} "
                f"on {spec['exchange']}; cannot resolve a front-month contract."
            )

        today = datetime.now(timezone.utc).strftime("%Y%m%d")

        def expiry_key(cd) -> str:
            expiry = cd.contract.lastTradeDateOrContractMonth or "99999999"
            if len(expiry) == 6:  # YYYYMM -> normalize for string comparison
                expiry += "01"
            return expiry

        ordered = sorted(details, key=expiry_key)
        unexpired = [cd for cd in ordered if expiry_key(cd) >= today]
        chosen = unexpired[0] if unexpired else ordered[-1]
        return chosen.contract

    def _symbol_for_contract(self, contract) -> str:
        if contract.secType == "CASH":
            key = ("CASH", contract.symbol + contract.currency)
        else:
            key = (contract.secType, contract.symbol)
        return self._reverse_symbol_map.get(key, contract.localSymbol or contract.symbol)

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def subscribe_bars(self, symbol: str, on_bar: BarCallback) -> None:
        self._bar_callbacks.setdefault(symbol, []).append(on_bar)

        if symbol in self._bar_subscriptions:
            return  # already have a live IBKR subscription; just added a callback to it

        contract = self._get_contract(symbol)
        bars = self.ib.reqRealTimeBars(contract, REALTIME_BAR_SIZE, "TRADES", False)
        bars.updateEvent += self._make_bar_update_handler(symbol)
        self._bar_subscriptions[symbol] = bars

    def _make_bar_update_handler(self, symbol: str):
        def _on_update(bars, has_new_bar):
            if not has_new_bar or not bars:
                return
            rt_bar = bars[-1]
            bar = Bar(
                symbol=symbol,
                timestamp=rt_bar.time,
                open=rt_bar.open_,
                high=rt_bar.high,
                low=rt_bar.low,
                close=rt_bar.close,
            )
            for callback in list(self._bar_callbacks.get(symbol, [])):
                try:
                    callback(bar)
                except Exception:
                    logger.exception("on_bar callback raised for %s", symbol)

        return _on_update

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def place_order(self, request: OrderRequest, on_fill: Optional[FillCallback] = None) -> OrderResult:
        client_order_id = request.client_order_id or str(uuid.uuid4())

        if not self._is_connected():
            return OrderResult(
                client_order_id=client_order_id,
                broker_order_id=None,
                status=OrderStatus.REJECTED,
                reason="Not connected to IBKR",
            )

        try:
            contract = self._get_contract(request.symbol)
        except Exception as exc:
            return OrderResult(
                client_order_id=client_order_id,
                broker_order_id=None,
                status=OrderStatus.REJECTED,
                reason=f"Contract resolution failed: {exc}",
            )

        if on_fill is not None:
            self._fill_callbacks[client_order_id] = on_fill

        action = "BUY" if request.side == OrderSide.BUY else "SELL"
        orders = self._build_order_group(action, request, client_order_id)

        trades = []
        for order in orders:
            trade = self.ib.placeOrder(contract, order)
            trades.append(trade)
            self._order_meta[trade.order.orderId] = client_order_id

        # trades[0] is always the parent (entry) order -- its immediate
        # status is what place_order reports back synchronously; the stop
        # and/or target legs (if any) only become live once IBKR fills the
        # parent, and their own status transitions arrive later via on_fill.
        return self._trade_to_order_result(client_order_id, trades[0])

    def _build_order_group(self, action: str, request: OrderRequest, client_order_id: str) -> List[object]:
        """Builds [parent, *exit_legs]. If both stop_loss and take_profit
        are set this is a full bracket (parent + target + stop), submitted
        with IBKR-native parent/child linkage so IBKR manages the exits --
        we never poll price ourselves to trigger them. If only one of the
        two is set, we still attach it as a resting child order rather than
        silently dropping it. transmit=False on every leg but the last means
        TWS holds the whole group and sends it as one unit when the last
        leg's transmit=True order goes out."""
        reverse_action = "SELL" if action == "BUY" else "BUY"
        parent_id = self.ib.client.getReqId()

        if request.limit_price is not None:
            parent = ib_async.LimitOrder(
                action, request.quantity, request.limit_price, orderId=parent_id, orderRef=client_order_id
            )
        else:
            parent = ib_async.MarketOrder(
                action, request.quantity, orderId=parent_id, orderRef=client_order_id
            )

        exit_legs = []
        if request.take_profit is not None:
            exit_legs.append(
                ib_async.LimitOrder(
                    reverse_action,
                    request.quantity,
                    request.take_profit,
                    orderId=self.ib.client.getReqId(),
                    parentId=parent_id,
                    orderRef=client_order_id,
                )
            )
        if request.stop_loss is not None:
            exit_legs.append(
                ib_async.StopOrder(
                    reverse_action,
                    request.quantity,
                    request.stop_loss,
                    orderId=self.ib.client.getReqId(),
                    parentId=parent_id,
                    orderRef=client_order_id,
                )
            )

        if exit_legs:
            parent.transmit = False
            for leg in exit_legs[:-1]:
                leg.transmit = False
            exit_legs[-1].transmit = True
        else:
            parent.transmit = True

        return [parent] + exit_legs

    def cancel_order(self, broker_order_id: str) -> None:
        if not self._is_connected():
            return
        try:
            order_id = int(broker_order_id)
        except (TypeError, ValueError):
            logger.warning("cancel_order: broker_order_id %r is not a valid IBKR orderId", broker_order_id)
            return

        for trade in self.ib.trades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                return
        logger.warning("cancel_order: no open trade found for broker_order_id=%s", broker_order_id)

    def flatten_all(self) -> List[OrderResult]:
        """Panic button: market-closes every open position reported by IBKR
        right now. Reads live broker positions, not our own subscriptions or
        any strategy/engine state, so it works even if the rest of the
        adapter's bookkeeping is stale or was never populated."""
        results: List[OrderResult] = []
        if not self._is_connected():
            return results

        for position in self.ib.positions(self._account):
            quantity = position.position
            if not quantity:
                continue

            action = "SELL" if quantity > 0 else "BUY"
            client_order_id = f"flatten-{position.contract.conId or position.contract.localSymbol or uuid.uuid4()}"
            order = ib_async.MarketOrder(action, abs(quantity), orderRef=client_order_id)

            trade = self.ib.placeOrder(position.contract, order)
            self._order_meta[trade.order.orderId] = client_order_id
            results.append(self._trade_to_order_result(client_order_id, trade))

        return results

    # ------------------------------------------------------------------
    # Fill / status event bridging
    # ------------------------------------------------------------------

    def _on_order_status(self, trade) -> None:
        client_order_id = self._order_meta.get(trade.order.orderId)
        if client_order_id is None:
            return
        callback = self._fill_callbacks.get(client_order_id)
        if callback is None:
            return
        try:
            callback(self._trade_to_order_result(client_order_id, trade))
        except Exception:
            logger.exception("on_fill callback raised for client_order_id=%s", client_order_id)

    def _on_error(self, reqId, errorCode, errorString, contract) -> None:
        # IBKR reports outright order rejections (bad contract, margin,
        # trading halted, etc.) as an error keyed by the order's reqId/
        # orderId rather than as an orderStatusEvent -- forward those too so
        # on_fill sees a REJECTED result instead of silence.
        client_order_id = self._order_meta.get(reqId)
        if client_order_id is None:
            return
        callback = self._fill_callbacks.get(client_order_id)
        if callback is None:
            return
        if errorCode < 400 or errorCode >= 1100:
            # < 400: informational/warning codes, not rejections.
            # >= 1100: connectivity/system notices, not order-specific.
            return
        try:
            callback(
                OrderResult(
                    client_order_id=client_order_id,
                    broker_order_id=str(reqId),
                    status=OrderStatus.REJECTED,
                    reason=f"IBKR error {errorCode}: {errorString}",
                )
            )
        except Exception:
            logger.exception("on_fill callback raised for client_order_id=%s", client_order_id)

    def _trade_to_order_result(self, client_order_id: str, trade) -> OrderResult:
        order_status = trade.orderStatus
        status = self._map_status(order_status.status, order_status.filled, order_status.remaining)
        reason = None
        if status in (OrderStatus.REJECTED, OrderStatus.CANCELLED):
            if trade.log:
                reason = trade.log[-1].message
            elif order_status.whyHeld:
                reason = order_status.whyHeld
        return OrderResult(
            client_order_id=client_order_id,
            broker_order_id=str(trade.order.orderId) if trade.order.orderId else None,
            status=status,
            filled_quantity=order_status.filled or 0.0,
            avg_fill_price=order_status.avgFillPrice or None,
            reason=reason,
        )

    @staticmethod
    def _map_status(ib_status: str, filled: float, remaining: float) -> OrderStatus:
        if ib_status == "Filled":
            return OrderStatus.FILLED
        if ib_status in _DONE_CANCELLED_STATUSES:
            return OrderStatus.CANCELLED
        if ib_status == "Inactive":
            # IBKR's catch-all for "the order will never execute" (rejected,
            # margin check failed, etc.) that isn't a user-initiated cancel.
            return OrderStatus.REJECTED
        # PendingSubmit / PreSubmitted / Submitted / ApiPending / ApiUpdate /
        # ValidationError -- TWS doesn't have a distinct "PartiallyFilled"
        # status string; a partial fill still shows as "Submitted" with
        # filled > 0 and remaining > 0, so we derive it from the quantities.
        if filled and remaining:
            return OrderStatus.PARTIALLY_FILLED
        return OrderStatus.SUBMITTED

    # ------------------------------------------------------------------
    # Positions / account
    # ------------------------------------------------------------------

    def get_positions(self) -> Dict[str, Position]:
        if not self._is_connected():
            return {}

        positions: Dict[str, Position] = {}
        for p in self.ib.positions(self._account):
            if not p.position:
                continue
            symbol = self._symbol_for_contract(p.contract)
            positions[symbol] = Position(
                symbol=symbol,
                quantity=p.position,
                avg_entry_price=p.avgCost,
            )

        # portfolio() carries live PnL figures that positions() doesn't --
        # enrich rather than replace so a symbol without a portfolio() entry
        # (e.g. mocked/partial data) still shows up with pnl defaulted to 0.
        for item in self.ib.portfolio(self._account):
            symbol = self._symbol_for_contract(item.contract)
            if symbol in positions:
                positions[symbol].unrealized_pnl = item.unrealizedPNL
                positions[symbol].realized_pnl = item.realizedPNL

        return positions

    def get_account_summary(self) -> AccountSummary:
        if not self._is_connected():
            return AccountSummary(
                net_liquidation=0.0, cash=0.0, buying_power=0.0, realized_pnl_today=0.0, unrealized_pnl=0.0
            )

        values: Dict[str, float] = {}
        for av in self.ib.accountSummary(self._account):
            if av.tag in _ACCOUNT_TAGS:
                try:
                    values[av.tag] = float(av.value)
                except (TypeError, ValueError):
                    continue

        return AccountSummary(
            net_liquidation=values.get("NetLiquidation", 0.0),
            cash=values.get("TotalCashValue", 0.0),
            buying_power=values.get("BuyingPower", 0.0),
            realized_pnl_today=values.get("RealizedPnL", 0.0),
            unrealized_pnl=values.get("UnrealizedPnL", 0.0),
        )
