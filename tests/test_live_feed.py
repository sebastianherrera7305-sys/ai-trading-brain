import asyncio

import pandas as pd
import pytest

from service.live_feed import _row_to_bar, run_live_feed
from trading_brain.backtest import BacktestConfig
from trading_brain.broker.base import Bar
from trading_brain.broker.engine_runner import LiveEngine
from trading_brain.broker.paper import PaperBroker
from trading_brain.broker.settings import BotSettings


class _FakeConnectionManager:
    def __init__(self):
        self.broadcasts = []

    async def broadcast(self, kind, data):
        self.broadcasts.append((kind, data))


class _FakeAppState:
    def __init__(self, broker, symbols):
        self.broker = broker
        self.connection_manager = _FakeConnectionManager()
        settings = BotSettings(enabled_instruments={s: True for s in symbols})
        self.engines = {
            s: LiveEngine(
                symbol=s, broker=broker,
                settings_provider=lambda: settings,
                account_balance_provider=lambda: broker.get_account_summary().net_liquidation,
                config=BacktestConfig(),
            )
            for s in symbols
        }
        # Mirrors AppState.wire_broker() -- without this, feed_bar() has no
        # callback to invoke and the engine would silently never see a bar.
        for s, engine in self.engines.items():
            broker.subscribe_bars(s, engine.on_bar)


def _fake_history(closes):
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D")
    return pd.DataFrame({
        "Open": closes, "High": [c + 1 for c in closes],
        "Low": [c - 1 for c in closes], "Close": closes,
    }, index=index)


def test_row_to_bar_converts_a_pandas_row():
    history = _fake_history([100.0, 101.0])
    bar = _row_to_bar("GC=F", history.iloc[-1], history.index[-1])
    assert bar.symbol == "GC=F"
    assert bar.close == 101.0
    assert bar.high == 102.0
    assert bar.low == 100.0


async def _run_one_pass(app_state):
    task = asyncio.create_task(run_live_feed(app_state, interval_seconds=1000))
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_live_feed_marks_price_and_broadcasts_without_touching_engine(monkeypatch):
    broker = PaperBroker(starting_cash=100_000.0)
    app_state = _FakeAppState(broker, ["GC=F"])
    engine = app_state.engines["GC=F"]

    history = _fake_history([2500.0, 2510.0])  # [completed, still-forming today]

    def fake_fetch(symbol):
        return history

    monkeypatch.setattr("service.live_feed._fetch_recent_daily_bars", fake_fetch)

    asyncio.run(_run_one_pass(app_state))

    # Price got marked from the forming bar's close.
    assert broker._last_price["GC=F"] == 2510.0
    # A candle broadcast went out for the dashboard's chart.
    kinds = [k for k, _ in app_state.connection_manager.broadcasts]
    assert "candle" in kinds

    # The completed prior bar reached the engine exactly once (first poll
    # always has a "new" completed date relative to the empty state).
    assert len(engine.candles) == 1
    assert engine.candles[0].close == 2500.0


def test_live_feed_does_not_refeed_the_same_completed_bar_twice(monkeypatch):
    broker = PaperBroker(starting_cash=100_000.0)
    app_state = _FakeAppState(broker, ["GC=F"])
    engine = app_state.engines["GC=F"]

    history = _fake_history([2500.0, 2510.0])
    monkeypatch.setattr("service.live_feed._fetch_recent_daily_bars", lambda symbol: history)

    async def _run_two_passes():
        task = asyncio.create_task(run_live_feed(app_state, interval_seconds=0.05))
        await asyncio.sleep(0.3)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_run_two_passes())

    # Multiple polls of the SAME completed bar must feed the engine once,
    # not once per poll.
    assert len(engine.candles) == 1


def test_live_feed_skips_a_symbol_cleanly_when_fetch_returns_none(monkeypatch):
    broker = PaperBroker(starting_cash=100_000.0)
    app_state = _FakeAppState(broker, ["GC=F"])

    monkeypatch.setattr("service.live_feed._fetch_recent_daily_bars", lambda symbol: None)

    asyncio.run(_run_one_pass(app_state))

    assert app_state.connection_manager.broadcasts == []
    assert "GC=F" not in broker._last_price
