"""
Shared application state for the trading service: the broker, the current
settings, one LiveEngine per instrument, and the WebSocket fan-out. api.py
and main.py both hold a reference to a single AppState instance -- this is
intentionally not a framework-managed dependency-injection graph, just one
object, because there is exactly one broker connection and one settings
file per running service.
"""

import asyncio
import logging
from typing import Dict, Optional

from trading_brain.backtest import BacktestConfig
from trading_brain.broker.base import Bar, Broker, ConnectionState
from trading_brain.broker.engine_runner import LiveEngine
from trading_brain.broker.settings import BotSettings, SettingsStore

from . import serialize

logger = logging.getLogger("service.state")

# The four instruments every backtest in this project has been run and
# validated against (see dashboard_data.json / backtest_report.html).
# Adding a fifth here without a corresponding validated backtest would be
# trading an untested setup -- deliberately not made dynamic/config-driven
# for that reason.
INSTRUMENTS = ["GC=F", "ES=F", "CL=F", "EURUSD=X"]


class AppState:
    def __init__(self, broker: Broker, settings_store: Optional[SettingsStore] = None):
        self.broker = broker
        self.settings_store = settings_store or SettingsStore()
        self.settings: BotSettings = self.settings_store.load()
        self.connection_manager = None  # set by main.py once the app is built
        self.engines: Dict[str, LiveEngine] = {
            symbol: LiveEngine(
                symbol=symbol,
                broker=broker,
                settings_provider=self.get_settings,
                account_balance_provider=self.account_balance,
                config=BacktestConfig(),
            )
            for symbol in INSTRUMENTS
        }
        self._wired = False
        self._order_log_watermark = 0

    def get_settings(self) -> BotSettings:
        return self.settings

    def update_settings(self, data: dict) -> BotSettings:
        merged = self.settings.to_dict()
        merged.update(data)
        self.settings = BotSettings.from_dict(merged)
        self.settings_store.save(self.settings)
        return self.settings

    def account_balance(self) -> float:
        return self.broker.get_account_summary().net_liquidation

    def wire_broker(self) -> None:
        """Subscribes every instrument's engine to its bar stream, plus a
        broadcaster that fires after the engine has processed each bar so
        connected dashboards see the result. Idempotent -- safe to call
        once at startup even if the service is re-initialized."""
        if self._wired:
            return
        self._wired = True
        self.broker.on_connection_state_change(self._on_connection_change)
        for symbol, engine in self.engines.items():
            self.broker.subscribe_bars(symbol, engine.on_bar)
            self.broker.subscribe_bars(symbol, self._make_broadcaster())

    def _make_broadcaster(self):
        async def _after_bar() -> None:
            await self.broadcast_full_state()
            self._order_log_watermark = await self.broadcast_new_orders(self._order_log_watermark)

        def _broadcast(bar: Bar) -> None:
            self._schedule(_after_bar())
        return _broadcast

    def _on_connection_change(self, state: ConnectionState) -> None:
        self._schedule(self._broadcast_connection(state))

    def _schedule(self, coro) -> None:
        """Bar/connection callbacks fire synchronously from the broker
        (ib_async's own event loop, or PaperBroker's direct call) -- this
        hands the resulting broadcast off to whatever asyncio loop the
        service is running under. Outside a running loop (e.g. a script or
        a test driving bars directly) there's nothing to schedule onto, so
        this is a deliberate no-op rather than a crash."""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
        if loop.is_running():
            loop.create_task(coro)
        else:
            coro.close()

    async def _broadcast_connection(self, state: ConnectionState) -> None:
        if self.connection_manager is None:
            return
        await self.connection_manager.broadcast("connection", {"state": state.value})

    def build_snapshot(self) -> dict:
        positions = {s: serialize.position_to_dict(p) for s, p in self.broker.get_positions().items()}
        account = serialize.account_to_dict(self.broker.get_account_summary())
        orders = list(getattr(self.broker, "order_log_entries", []))[-100:]
        return {
            "positions": positions,
            "account": account,
            "orders": orders,
            "settings": self.settings.to_dict(),
            "connection_state": self.broker.connection_state.value,
        }

    async def broadcast_full_state(self) -> None:
        if self.connection_manager is None:
            return
        positions = {s: serialize.position_to_dict(p) for s, p in self.broker.get_positions().items()}
        account = serialize.account_to_dict(self.broker.get_account_summary())
        await self.connection_manager.broadcast("positions", positions)
        await self.connection_manager.broadcast("account", account)

    async def broadcast_settings(self) -> None:
        if self.connection_manager is None:
            return
        await self.connection_manager.broadcast("settings", self.settings.to_dict())

    async def broadcast_new_orders(self, since_count: int) -> int:
        """Broadcasts any order-log entries added since `since_count`.
        Returns the new total so callers can track their own watermark.
        No-ops (returns since_count unchanged) for brokers that don't
        expose order_log_entries -- IBKR's own trade events are the
        real source of truth there and aren't wired to this yet."""
        entries = getattr(self.broker, "order_log_entries", None)
        if entries is None or self.connection_manager is None:
            return since_count
        for entry in entries[since_count:]:
            await self.connection_manager.broadcast("order", entry)
        return len(entries)
