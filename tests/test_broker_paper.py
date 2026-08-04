from datetime import datetime

from trading_brain.broker.base import (
    Bar,
    ConnectionState,
    OrderRequest,
    OrderSide,
    OrderStatus,
)
from trading_brain.broker.paper import PaperBroker


def _bar(symbol, price, low=None, high=None):
    return Bar(
        symbol=symbol,
        timestamp=datetime(2026, 1, 1),
        open=price,
        high=high if high is not None else price,
        low=low if low is not None else price,
        close=price,
    )


def test_connect_disconnect_state():
    b = PaperBroker()
    assert b.connection_state == ConnectionState.DISCONNECTED
    b.connect()
    assert b.connection_state == ConnectionState.CONNECTED
    b.disconnect()
    assert b.connection_state == ConnectionState.DISCONNECTED


def test_connection_callback_fires_on_transition_only():
    b = PaperBroker()
    seen = []
    b.on_connection_state_change(seen.append)
    b.connect()
    b.connect()  # no-op, already connected -- must not fire again
    assert seen == [ConnectionState.CONNECTED]


def test_market_order_fills_immediately_at_current_price():
    b = PaperBroker()
    b.feed_bar(_bar("GC=F", 2500.0))
    result = b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))
    assert result.status == OrderStatus.FILLED
    assert result.avg_fill_price == 2500.0
    pos = b.get_positions()["GC=F"]
    assert pos.quantity == 1
    assert pos.avg_entry_price == 2500.0


def test_realized_pnl_credited_to_cash_on_close_not_just_margin_refund():
    """The bug class this guards against: an account that only ever moves
    margin in and out will always show cash == starting_cash once flat,
    even after a real winning or losing trade. Realized P&L must actually
    change cash."""
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=2))
    b.feed_bar(_bar("GC=F", 2510.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.SELL, quantity=2))

    summary = b.get_account_summary()
    assert summary.cash == 100_000.0 + (2510.0 - 2500.0) * 2
    assert summary.realized_pnl_today == (2510.0 - 2500.0) * 2
    assert "GC=F" not in b.get_positions()  # flat positions are not reported


def test_losing_trade_reduces_cash_below_starting_balance():
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("CL=F", 70.0))
    b.place_order(OrderRequest(symbol="CL=F", side=OrderSide.BUY, quantity=3))
    b.feed_bar(_bar("CL=F", 68.0))
    b.place_order(OrderRequest(symbol="CL=F", side=OrderSide.SELL, quantity=3))

    summary = b.get_account_summary()
    assert summary.cash == 100_000.0 - (70.0 - 68.0) * 3
    assert summary.cash < 100_000.0


def test_weighted_average_entry_on_adding_to_position():
    b = PaperBroker()
    b.feed_bar(_bar("ES=F", 5000.0))
    b.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))
    b.feed_bar(_bar("ES=F", 5100.0))
    b.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))

    pos = b.get_positions()["ES=F"]
    assert pos.quantity == 2
    assert pos.avg_entry_price == 5050.0


def test_short_position_pnl_direction():
    b = PaperBroker(starting_cash=50_000.0)
    b.feed_bar(_bar("CL=F", 70.0))
    b.place_order(OrderRequest(symbol="CL=F", side=OrderSide.SELL, quantity=1))
    b.feed_bar(_bar("CL=F", 65.0))  # price drops -- short wins
    b.place_order(OrderRequest(symbol="CL=F", side=OrderSide.BUY, quantity=1))

    summary = b.get_account_summary()
    assert summary.cash == 50_000.0 + (70.0 - 65.0)


def test_flip_through_flat_opens_new_position_at_fill_price():
    b = PaperBroker()
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))
    b.feed_bar(_bar("GC=F", 2520.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.SELL, quantity=2))  # closes 1, opens -1

    pos = b.get_positions()["GC=F"]
    assert pos.quantity == -1
    assert pos.avg_entry_price == 2520.0


def test_max_contracts_rejects_oversized_order():
    b = PaperBroker(max_contracts=2)
    b.feed_bar(_bar("GC=F", 2500.0))
    result = b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=3))
    assert result.status == OrderStatus.REJECTED
    assert result.reason is not None
    assert "GC=F" not in b.get_positions()


def test_max_contracts_respects_existing_position():
    b = PaperBroker(max_contracts=2)
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=2))
    result = b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))
    assert result.status == OrderStatus.REJECTED


def test_limit_order_rests_until_touched():
    b = PaperBroker()
    result = b.place_order(OrderRequest(symbol="EURUSD=X", side=OrderSide.BUY, quantity=1, limit_price=1.10))
    assert result.status == OrderStatus.SUBMITTED
    assert "EURUSD=X" not in b.get_positions()

    b.feed_bar(_bar("EURUSD=X", 1.12, low=1.115, high=1.125))  # doesn't touch 1.10
    assert "EURUSD=X" not in b.get_positions()

    b.feed_bar(_bar("EURUSD=X", 1.09, low=1.08, high=1.11))  # low touches 1.10
    pos = b.get_positions()["EURUSD=X"]
    assert pos.avg_entry_price == 1.10


def test_limit_order_fill_callback_fires():
    b = PaperBroker()
    fills = []
    b.place_order(
        OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1, limit_price=5000.0),
        on_fill=fills.append,
    )
    assert fills == []
    b.feed_bar(_bar("ES=F", 4990.0, low=4980.0, high=4995.0))
    assert len(fills) == 1
    assert fills[0].status == OrderStatus.FILLED
    assert fills[0].avg_fill_price == 5000.0


def test_cancel_order_removes_resting_order():
    b = PaperBroker()
    result = b.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1, limit_price=5000.0))
    b.cancel_order(result.broker_order_id)
    b.feed_bar(_bar("ES=F", 4990.0, low=4980.0, high=4995.0))
    assert "ES=F" not in b.get_positions()


def test_flatten_all_closes_every_open_position():
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))
    b.feed_bar(_bar("ES=F", 5000.0))
    b.place_order(OrderRequest(symbol="ES=F", side=OrderSide.BUY, quantity=1))

    b.feed_bar(_bar("GC=F", 2510.0))
    b.feed_bar(_bar("ES=F", 4990.0))
    results = b.flatten_all()

    assert len(results) == 2
    assert all(r.status == OrderStatus.FILLED for r in results)
    assert b.get_positions() == {}


def test_bracket_stop_loss_auto_closes_long_position():
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(
        symbol="GC=F", side=OrderSide.BUY, quantity=1,
        stop_loss=2490.0, take_profit=2530.0,
    ))
    b.feed_bar(_bar("GC=F", 2485.0, low=2480.0, high=2495.0))  # low touches stop

    assert "GC=F" not in b.get_positions()
    summary = b.get_account_summary()
    assert summary.cash == 100_000.0 - (2500.0 - 2490.0)


def test_bracket_take_profit_auto_closes_short_position():
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("CL=F", 70.0))
    b.place_order(OrderRequest(
        symbol="CL=F", side=OrderSide.SELL, quantity=2,
        stop_loss=72.0, take_profit=66.0,
    ))
    b.feed_bar(_bar("CL=F", 65.0, low=65.0, high=67.0))  # low touches target for a short

    assert "CL=F" not in b.get_positions()
    summary = b.get_account_summary()
    assert summary.cash == 100_000.0 + (70.0 - 66.0) * 2


def test_bracket_does_not_fire_when_neither_level_touched():
    b = PaperBroker()
    b.feed_bar(_bar("ES=F", 5000.0))
    b.place_order(OrderRequest(
        symbol="ES=F", side=OrderSide.BUY, quantity=1,
        stop_loss=4950.0, take_profit=5100.0,
    ))
    b.feed_bar(_bar("ES=F", 5010.0, low=4990.0, high=5020.0))
    pos = b.get_positions()["ES=F"]
    assert pos.quantity == 1


def test_bracket_cleared_after_manual_close_does_not_refire():
    b = PaperBroker(starting_cash=100_000.0)
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(
        symbol="GC=F", side=OrderSide.BUY, quantity=1,
        stop_loss=2490.0, take_profit=2530.0,
    ))
    b.feed_bar(_bar("GC=F", 2505.0))
    b.flatten_all()
    # A later bar that would have touched the old stop must not trigger a
    # second, phantom close on an already-flat position.
    b.feed_bar(_bar("GC=F", 2485.0, low=2480.0, high=2495.0))
    assert "GC=F" not in b.get_positions()
    assert b.get_account_summary().cash == 100_000.0 + (2505.0 - 2500.0)


def test_order_log_entries_carry_symbol_side_and_timestamp():
    b = PaperBroker()
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))

    entries = b.order_log_entries
    assert len(entries) == 1
    entry = entries[0]
    assert entry["symbol"] == "GC=F"
    assert entry["side"] == "buy"
    assert entry["status"] == "filled"
    assert entry["quantity"] == 1
    assert entry["avg_fill_price"] == 2500.0
    assert entry["timestamp"]  # non-empty ISO string


def test_unrealized_pnl_marks_to_market_on_new_bar():
    b = PaperBroker()
    b.feed_bar(_bar("GC=F", 2500.0))
    b.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))
    b.feed_bar(_bar("GC=F", 2515.0))

    pos = b.get_positions()["GC=F"]
    assert pos.unrealized_pnl == 15.0
    summary = b.get_account_summary()
    assert summary.unrealized_pnl == 15.0
    assert summary.net_liquidation == summary.cash + 15.0
