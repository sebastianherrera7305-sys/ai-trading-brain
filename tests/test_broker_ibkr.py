"""Tests for the IBKR broker adapter (AI Trading Brain, Phase 3).

ib_async's IB class talks to a real TWS/IB Gateway socket -- there is no
broker to connect to in this sandbox, so every test here drives IBKRBroker
against a hand-built stand-in for `ib_async.IB` (constructed with
unittest.mock and real, inert ib_async data objects for fixtures) rather
than a real IB() instance. No test opens a network connection.
"""

import itertools
import unittest
from datetime import datetime
from unittest import mock

import ib_async

from trading_brain.broker.base import (
    ConnectionState,
    OrderRequest,
    OrderSide,
    OrderStatus,
)
from trading_brain.broker.ibkr import IBKRBroker


def make_mock_ib():
    """A MagicMock standing in for ib_async.IB, wired just enough to behave
    like the real thing for the calls IBKRBroker makes: connect/disconnect
    toggle isConnected() and emit disconnectedEvent, placeOrder returns a
    real ib_async.Trade tracking orderStatus, client.getReqId() hands out
    increasing ids, and reqContractDetails/positions/portfolio/
    accountSummary are simple return-value hooks tests configure per case.
    """
    ib = mock.MagicMock(name="FakeIB")
    ib._connected = False

    def _connect(host, port, clientId):
        ib._connected = True

    def _disconnect():
        ib._connected = False
        ib.disconnectedEvent.emit()

    ib.connect.side_effect = _connect
    ib.disconnect.side_effect = _disconnect
    ib.isConnected.side_effect = lambda: ib._connected

    # Real Event objects so `ib.xEvent += handler` / `.emit(...)` behave
    # exactly as they do on a genuine IB instance.
    ib.disconnectedEvent = ib_async.Event("disconnectedEvent")
    ib.orderStatusEvent = ib_async.Event("orderStatusEvent")
    ib.errorEvent = ib_async.Event("errorEvent")

    req_ids = itertools.count(1)
    ib.client = mock.MagicMock()
    ib.client.getReqId.side_effect = lambda: next(req_ids)

    ib.qualifyContracts.side_effect = lambda c: [c]
    ib.reqContractDetails.return_value = []
    ib.positions.return_value = []
    ib.portfolio.return_value = []
    ib.accountSummary.return_value = []

    placed_trades = []

    def _place_order(contract, order):
        status = ib_async.order.OrderStatus(
            orderId=order.orderId,
            status="Submitted",
            filled=0.0,
            remaining=order.totalQuantity,
            avgFillPrice=0.0,
        )
        trade = ib_async.order.Trade(contract=contract, order=order, orderStatus=status)
        placed_trades.append(trade)
        return trade

    ib.placeOrder.side_effect = _place_order
    ib.trades.side_effect = lambda: list(placed_trades)
    ib._placed_trades = placed_trades  # test-only escape hatch

    return ib


def make_broker(ib=None):
    """An IBKRBroker whose ib_factory hands back a pre-built mock (or a
    fresh one), already connected -- avoids repeating connect() boilerplate
    in every test that isn't specifically about connection lifecycle."""
    ib = ib or make_mock_ib()
    broker = IBKRBroker(ib_factory=lambda: ib)
    broker.connect()
    return broker, ib


# ----------------------------------------------------------------------
# Connection lifecycle
# ----------------------------------------------------------------------

class TestConnectionLifecycle(unittest.TestCase):
    def test_starts_disconnected(self):
        broker = IBKRBroker(ib_factory=make_mock_ib)
        self.assertEqual(broker.connection_state, ConnectionState.DISCONNECTED)

    def test_connect_transitions_to_connected(self):
        ib = make_mock_ib()
        broker = IBKRBroker(ib_factory=lambda: ib)
        broker.connect()
        self.assertEqual(broker.connection_state, ConnectionState.CONNECTED)
        self.assertTrue(ib.connect.called)

    def test_default_ports_are_paper_trading(self):
        broker = IBKRBroker()
        self.assertEqual(broker._host, "127.0.0.1")
        self.assertEqual(broker._port, 7497)  # TWS paper port

    def test_disconnect_transitions_to_disconnected(self):
        broker, ib = make_broker()
        broker.disconnect()
        self.assertEqual(broker.connection_state, ConnectionState.DISCONNECTED)
        self.assertTrue(ib.disconnect.called)

    def test_reconnect_after_disconnect_is_safe(self):
        """The ABC requires connect() to work again after disconnect() --
        not to assume it's only ever called once per process lifetime."""
        calls = []

        def factory():
            ib = make_mock_ib()
            calls.append(ib)
            return ib

        broker = IBKRBroker(ib_factory=factory)
        broker.connect()
        broker.disconnect()
        broker.connect()  # must not raise, must reach CONNECTED again

        self.assertEqual(broker.connection_state, ConnectionState.CONNECTED)
        self.assertEqual(len(calls), 2)  # fresh IB() built each connect()

    def test_connect_is_idempotent_when_already_connected(self):
        broker, ib = make_broker()
        ib.connect.reset_mock()
        broker.connect()  # no-op
        ib.connect.assert_not_called()

    def test_connection_callback_fires_only_on_transitions(self):
        ib = make_mock_ib()
        broker = IBKRBroker(ib_factory=lambda: ib)
        seen = []
        broker.on_connection_state_change(seen.append)

        broker.connect()
        broker.connect()  # already connected -- must not fire again
        broker.disconnect()

        # connect() legitimately passes through CONNECTING on its way to
        # CONNECTED; the "must not fire again" guarantee is about the
        # second connect() call being a no-op, not about skipping CONNECTING.
        self.assertEqual(
            seen,
            [ConnectionState.CONNECTING, ConnectionState.CONNECTED, ConnectionState.DISCONNECTED],
        )

    def test_unexpected_drop_updates_state_via_disconnected_event(self):
        """A real IB() fires disconnectedEvent on an unexpected drop too,
        not just on our own disconnect() call -- state must follow it."""
        broker, ib = make_broker()
        ib.disconnectedEvent.emit()
        self.assertEqual(broker.connection_state, ConnectionState.DISCONNECTED)


# ----------------------------------------------------------------------
# Symbol -> contract mapping
# ----------------------------------------------------------------------

class TestContractMapping(unittest.TestCase):
    def test_unknown_symbol_raises(self):
        broker, ib = make_broker()
        with self.assertRaises(ValueError):
            broker._get_contract("TSLA")

    def test_forex_maps_to_ib_async_forex_contract(self):
        broker, ib = make_broker()
        contract = broker._get_contract("EURUSD=X")
        self.assertIsInstance(contract, ib_async.Forex)
        self.assertEqual(contract.symbol, "EUR")
        self.assertEqual(contract.currency, "USD")

    def test_forex_contract_is_qualified_and_cached(self):
        broker, ib = make_broker()
        first = broker._get_contract("EURUSD=X")
        second = broker._get_contract("EURUSD=X")
        self.assertIs(first, second)
        self.assertEqual(ib.qualifyContracts.call_count, 1)  # cached after first resolve

    def test_future_picks_nearest_unexpired_expiry(self):
        """Front-month selection: given several listed expiries, pick the
        soonest one that hasn't already passed -- not just the first one
        IBKR happens to return."""
        broker, ib = make_broker()

        expired = ib_async.ContractDetails(
            contract=ib_async.Future(symbol="ES", lastTradeDateOrContractMonth="20260619",
                                      exchange="CME", currency="USD")
        )
        near = ib_async.ContractDetails(
            contract=ib_async.Future(symbol="ES", lastTradeDateOrContractMonth="20260918",
                                      exchange="CME", currency="USD")
        )
        far = ib_async.ContractDetails(
            contract=ib_async.Future(symbol="ES", lastTradeDateOrContractMonth="20261218",
                                      exchange="CME", currency="USD")
        )
        # Deliberately out of order and with the expired one present, to
        # prove sorting/filtering actually happens rather than "first wins".
        ib.reqContractDetails.return_value = [far, expired, near]

        contract = broker._get_contract("ES=F")
        self.assertEqual(contract.lastTradeDateOrContractMonth, "20260918")
        self.assertEqual(contract.exchange, "CME")

    def test_future_falls_back_to_last_listing_if_all_expired(self):
        broker, ib = make_broker()
        only = ib_async.ContractDetails(
            contract=ib_async.Future(symbol="CL", lastTradeDateOrContractMonth="20200101",
                                      exchange="NYMEX", currency="USD")
        )
        ib.reqContractDetails.return_value = [only]
        contract = broker._get_contract("CL=F")
        self.assertEqual(contract.lastTradeDateOrContractMonth, "20200101")

    def test_future_with_no_listings_raises(self):
        broker, ib = make_broker()
        ib.reqContractDetails.return_value = []
        with self.assertRaises(RuntimeError):
            broker._get_contract("GC=F")


# ----------------------------------------------------------------------
# place_order / bracket construction
# ----------------------------------------------------------------------

class TestPlaceOrder(unittest.TestCase):
    def _seed_contract(self, broker, symbol="ES=F"):
        contract = ib_async.Future(symbol="ES", lastTradeDateOrContractMonth="20260918",
                                    exchange="CME", currency="USD")
        broker._contract_cache[symbol] = contract
        return contract

    def test_rejects_when_not_connected(self):
        broker = IBKRBroker(ib_factory=make_mock_ib)  # never connected
        result = broker.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("connect", result.reason.lower())

    def test_rejects_unmapped_symbol(self):
        broker, ib = make_broker()
        result = broker.place_order(OrderRequest(symbol="TSLA", side=OrderSide.BUY, quantity=1))
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIsNotNone(result.reason)
        ib.placeOrder.assert_not_called()

    def test_plain_market_order_places_single_order(self):
        broker, ib = make_broker()
        self._seed_contract(broker)
        result = broker.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=2))

        self.assertEqual(ib.placeOrder.call_count, 1)
        (contract, order), _ = ib.placeOrder.call_args
        self.assertEqual(order.orderType, "MKT")
        self.assertEqual(order.action, "BUY")
        self.assertEqual(order.totalQuantity, 2)
        self.assertTrue(order.transmit)  # no legs -- transmits immediately

        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertEqual(result.filled_quantity, 0.0)
        self.assertIsNotNone(result.broker_order_id)

    def test_bracket_order_builds_parent_stop_and_target(self):
        broker, ib = make_broker()
        self._seed_contract(broker)

        request = OrderRequest(
            symbol="ES=F", side=OrderSide.BUY, quantity=1,
            stop_loss=4950.0, take_profit=5100.0,
        )
        result = broker.place_order(request)

        self.assertEqual(ib.placeOrder.call_count, 3)
        orders = [call.args[1] for call in ib.placeOrder.call_args_list]
        parent, target, stop = orders

        # Parent: market buy, not yet transmitted (bracket held together).
        self.assertEqual(parent.action, "BUY")
        self.assertEqual(parent.orderType, "MKT")
        self.assertFalse(parent.transmit)
        self.assertEqual(parent.parentId, 0)

        # Target: opposite side, limit at take_profit, child of parent.
        self.assertEqual(target.action, "SELL")
        self.assertEqual(target.orderType, "LMT")
        self.assertEqual(target.lmtPrice, 5100.0)
        self.assertEqual(target.parentId, parent.orderId)
        self.assertFalse(target.transmit)

        # Stop: opposite side, stop at stop_loss, child of parent, and the
        # last leg transmitted -- this is what sends the whole bracket.
        self.assertEqual(stop.action, "SELL")
        self.assertEqual(stop.orderType, "STP")
        self.assertEqual(stop.auxPrice, 4950.0)
        self.assertEqual(stop.parentId, parent.orderId)
        self.assertTrue(stop.transmit)

        # All three IBKR orders correlate back to one client_order_id.
        self.assertEqual(parent.orderRef, request.client_order_id or result.client_order_id)
        self.assertEqual(target.orderRef, stop.orderRef)

        # place_order reports the parent's immediate status, not a made-up FILLED.
        self.assertEqual(result.status, OrderStatus.SUBMITTED)
        self.assertEqual(result.broker_order_id, str(parent.orderId))

    def test_bracket_order_uses_limit_entry_when_limit_price_set(self):
        broker, ib = make_broker()
        self._seed_contract(broker)
        broker.place_order(OrderRequest(
            symbol="ES=F", side=OrderSide.SELL, quantity=1, limit_price=5000.0,
            stop_loss=5050.0, take_profit=4900.0,
        ))
        parent = ib.placeOrder.call_args_list[0].args[1]
        self.assertEqual(parent.orderType, "LMT")
        self.assertEqual(parent.lmtPrice, 5000.0)

    def test_stop_only_still_attaches_child_order(self):
        """Only stop_loss set (no take_profit): must not silently drop the
        risk leg just because it isn't a full bracket."""
        broker, ib = make_broker()
        self._seed_contract(broker)
        broker.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1, stop_loss=4900.0))
        self.assertEqual(ib.placeOrder.call_count, 2)
        parent, stop = [c.args[1] for c in ib.placeOrder.call_args_list]
        self.assertFalse(parent.transmit)
        self.assertTrue(stop.transmit)
        self.assertEqual(stop.orderType, "STP")

    def test_client_order_id_is_generated_when_absent(self):
        broker, ib = make_broker()
        self._seed_contract(broker)
        result = broker.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))
        self.assertTrue(result.client_order_id)

    def test_client_order_id_is_preserved_when_given(self):
        broker, ib = make_broker()
        self._seed_contract(broker)
        result = broker.place_order(
            OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1, client_order_id="my-id-1")
        )
        self.assertEqual(result.client_order_id, "my-id-1")


# ----------------------------------------------------------------------
# on_fill wiring via orderStatusEvent
# ----------------------------------------------------------------------

class TestFillCallback(unittest.TestCase):
    def test_on_fill_fires_on_later_status_transition(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")

        fills = []
        result = broker.place_order(
            OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1),
            on_fill=fills.append,
        )
        self.assertEqual(fills, [])  # nothing yet -- only the immediate SUBMITTED result returned directly

        trade = ib._placed_trades[0]
        trade.orderStatus.status = "Filled"
        trade.orderStatus.filled = 1.0
        trade.orderStatus.remaining = 0.0
        trade.orderStatus.avgFillPrice = 5012.5
        ib.orderStatusEvent.emit(trade)

        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].client_order_id, result.client_order_id)
        self.assertEqual(fills[0].status, OrderStatus.FILLED)
        self.assertEqual(fills[0].avg_fill_price, 5012.5)

    def test_partial_fill_is_reported_as_partially_filled(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")
        fills = []
        broker.place_order(
            OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=10),
            on_fill=fills.append,
        )
        trade = ib._placed_trades[0]
        trade.orderStatus.status = "Submitted"
        trade.orderStatus.filled = 4.0
        trade.orderStatus.remaining = 6.0
        ib.orderStatusEvent.emit(trade)

        self.assertEqual(fills[-1].status, OrderStatus.PARTIALLY_FILLED)
        self.assertEqual(fills[-1].filled_quantity, 4.0)

    def test_order_status_for_unrelated_order_is_ignored(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")
        fills = []
        broker.place_order(
            OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1, client_order_id="mine"),
            on_fill=fills.append,
        )
        other_order = ib_async.Order(orderId=999999, action="BUY", totalQuantity=1, orderType="MKT")
        other_status = ib_async.order.OrderStatus(orderId=999999, status="Filled", filled=1.0, remaining=0.0)
        other_trade = ib_async.order.Trade(contract=ib_async.Future(), order=other_order, orderStatus=other_status)
        ib.orderStatusEvent.emit(other_trade)
        self.assertEqual(fills, [])


# ----------------------------------------------------------------------
# cancel_order
# ----------------------------------------------------------------------

class TestCancelOrder(unittest.TestCase):
    def test_cancel_order_cancels_matching_trade(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")
        result = broker.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))

        broker.cancel_order(result.broker_order_id)

        ib.cancelOrder.assert_called_once()
        cancelled_order = ib.cancelOrder.call_args.args[0]
        self.assertEqual(str(cancelled_order.orderId), result.broker_order_id)

    def test_cancel_order_with_unknown_id_does_not_raise(self):
        broker, ib = make_broker()
        broker.cancel_order("999999")  # nothing placed -- should just log and return
        ib.cancelOrder.assert_not_called()


# ----------------------------------------------------------------------
# flatten_all
# ----------------------------------------------------------------------

class TestFlattenAll(unittest.TestCase):
    def test_flatten_all_closes_every_open_position(self):
        broker, ib = make_broker()
        long_gc = ib_async.objects.Position(
            account="DU123", contract=ib_async.Future(symbol="GC", exchange="COMEX", currency="USD"),
            position=2.0, avgCost=2500.0,
        )
        short_cl = ib_async.objects.Position(
            account="DU123", contract=ib_async.Future(symbol="CL", exchange="NYMEX", currency="USD"),
            position=-3.0, avgCost=70.0,
        )
        flat_es = ib_async.objects.Position(
            account="DU123", contract=ib_async.Future(symbol="ES", exchange="CME", currency="USD"),
            position=0.0, avgCost=0.0,
        )
        ib.positions.return_value = [long_gc, short_cl, flat_es]

        results = broker.flatten_all()

        self.assertEqual(ib.placeOrder.call_count, 2)  # flat position skipped
        orders = [c.args[1] for c in ib.placeOrder.call_args_list]
        gc_order = next(o for o in orders if o.action == "SELL")
        cl_order = next(o for o in orders if o.action == "BUY")
        self.assertEqual(gc_order.totalQuantity, 2.0)
        self.assertEqual(gc_order.orderType, "MKT")
        self.assertEqual(cl_order.totalQuantity, 3.0)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.status == OrderStatus.SUBMITTED for r in results))

    def test_flatten_all_when_not_connected_returns_empty(self):
        broker = IBKRBroker(ib_factory=make_mock_ib)  # never connected
        self.assertEqual(broker.flatten_all(), [])

    def test_flatten_all_does_not_depend_on_internal_subscriptions(self):
        """The panic button reads live broker positions, not our own
        bar-subscription bookkeeping or any cached symbol state."""
        broker, ib = make_broker()
        self.assertEqual(broker._bar_subscriptions, {})  # nothing subscribed
        ib.positions.return_value = [
            ib_async.objects.Position(
                account="", contract=ib_async.Future(symbol="ES", exchange="CME", currency="USD"),
                position=1.0, avgCost=5000.0,
            )
        ]
        results = broker.flatten_all()
        self.assertEqual(len(results), 1)


# ----------------------------------------------------------------------
# get_positions / get_account_summary
# ----------------------------------------------------------------------

class TestPositionsAndAccountSummary(unittest.TestCase):
    def test_get_positions_maps_fields_and_symbol(self):
        broker, ib = make_broker()
        ib.positions.return_value = [
            ib_async.objects.Position(
                account="DU1", contract=ib_async.Future(symbol="GC", exchange="COMEX", currency="USD"),
                position=1.5, avgCost=2500.0,
            )
        ]
        ib.portfolio.return_value = [
            ib_async.objects.PortfolioItem(
                contract=ib_async.Future(symbol="GC", exchange="COMEX", currency="USD"),
                position=1.5, marketPrice=2510.0, marketValue=3765.0, averageCost=2500.0,
                unrealizedPNL=15.0, realizedPNL=0.0, account="DU1",
            )
        ]
        positions = broker.get_positions()
        self.assertIn("GC=F", positions)
        pos = positions["GC=F"]
        self.assertEqual(pos.quantity, 1.5)
        self.assertEqual(pos.avg_entry_price, 2500.0)
        self.assertEqual(pos.unrealized_pnl, 15.0)
        self.assertEqual(pos.realized_pnl, 0.0)

    def test_get_positions_maps_forex_symbol(self):
        broker, ib = make_broker()
        ib.positions.return_value = [
            ib_async.objects.Position(
                account="DU1", contract=ib_async.Forex("EURUSD"), position=-10000.0, avgCost=1.08,
            )
        ]
        positions = broker.get_positions()
        self.assertIn("EURUSD=X", positions)

    def test_get_positions_skips_flat_and_when_disconnected(self):
        broker = IBKRBroker(ib_factory=make_mock_ib)  # never connected
        self.assertEqual(broker.get_positions(), {})

    def test_get_account_summary_maps_tags(self):
        broker, ib = make_broker()
        ib.accountSummary.return_value = [
            ib_async.AccountValue(account="DU1", tag="NetLiquidation", value="105000.50", currency="USD", modelCode=""),
            ib_async.AccountValue(account="DU1", tag="TotalCashValue", value="100000.00", currency="USD", modelCode=""),
            ib_async.AccountValue(account="DU1", tag="BuyingPower", value="400000.00", currency="USD", modelCode=""),
            ib_async.AccountValue(account="DU1", tag="RealizedPnL", value="250.00", currency="USD", modelCode=""),
            ib_async.AccountValue(account="DU1", tag="UnrealizedPnL", value="4750.50", currency="USD", modelCode=""),
            ib_async.AccountValue(account="DU1", tag="SomeOtherTag", value="ignored", currency="USD", modelCode=""),
        ]
        summary = broker.get_account_summary()
        self.assertEqual(summary.net_liquidation, 105000.50)
        self.assertEqual(summary.cash, 100000.00)
        self.assertEqual(summary.buying_power, 400000.00)
        self.assertEqual(summary.realized_pnl_today, 250.00)
        self.assertEqual(summary.unrealized_pnl, 4750.50)

    def test_get_account_summary_when_disconnected_returns_zeroed_summary(self):
        broker = IBKRBroker(ib_factory=make_mock_ib)  # never connected
        summary = broker.get_account_summary()
        self.assertEqual(summary.net_liquidation, 0.0)
        self.assertEqual(summary.cash, 0.0)


# ----------------------------------------------------------------------
# subscribe_bars
# ----------------------------------------------------------------------

class TestSubscribeBars(unittest.TestCase):
    def test_multiple_callbacks_for_same_symbol_both_fire(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")

        bar_list = ib_async.RealTimeBarList()
        ib.reqRealTimeBars.return_value = bar_list

        first_calls = []
        second_calls = []
        broker.subscribe_bars("ES=F", first_calls.append)
        broker.subscribe_bars("ES=F", second_calls.append)  # must NOT clobber the first

        self.assertEqual(ib.reqRealTimeBars.call_count, 1)  # one underlying IBKR subscription

        rt_bar = ib_async.RealTimeBar(
            time=datetime(2026, 8, 4, 14, 30, 0), endTime=0,
            open_=5000.0, high=5005.0, low=4998.0, close=5002.0,
        )
        bar_list.append(rt_bar)
        bar_list.updateEvent.emit(bar_list, True)

        self.assertEqual(len(first_calls), 1)
        self.assertEqual(len(second_calls), 1)
        bar = first_calls[0]
        self.assertEqual(bar.symbol, "ES=F")
        self.assertEqual(bar.open, 5000.0)
        self.assertEqual(bar.close, 5002.0)
        self.assertEqual(second_calls[0].close, 5002.0)

    def test_no_new_bar_does_not_fire_callback(self):
        broker, ib = make_broker()
        broker._contract_cache["ES=F"] = ib_async.Future(symbol="ES", exchange="CME", currency="USD")
        bar_list = ib_async.RealTimeBarList()
        ib.reqRealTimeBars.return_value = bar_list

        calls = []
        broker.subscribe_bars("ES=F", calls.append)
        bar_list.updateEvent.emit(bar_list, False)  # hasNewBar=False
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
