"""
Service entry point — AI Trading Brain, Phase 3

Run with: uvicorn service.main:app --host 127.0.0.1 --port 8000
(from the ai-trading-brain/ directory, with the venv active).

Broker selection is env-driven and defaults to the safe choice:
  TRADING_BROKER=paper (default) -- in-memory simulator, no external
    connection, safe to run anywhere including this sandbox.
  TRADING_BROKER=ibkr -- connects to a real IB Gateway/TWS instance.
    Requires IB Gateway/TWS running on the SAME machine or reachable
    network (IBKR's API is a local socket, not a public endpoint).
    IBKR_HOST (default 127.0.0.1), IBKR_PORT (default 7497, TWS paper),
    IBKR_CLIENT_ID (default 1) configure the connection. There is no env
    var that defaults this to a live account port -- switching off paper
    trading is an explicit, deliberate config change, not an accident.
"""

import asyncio
import logging
import os
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from trading_brain.broker.paper import PaperBroker
from trading_brain.broker.settings import SettingsStore

from . import api
from .live_feed import DEFAULT_INTERVAL_SECONDS, run_live_feed
from .state import AppState
from .ws import ConnectionManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("service.main")

BASE_DIR = Path(__file__).resolve().parent.parent
DASHBOARD_DIR = BASE_DIR / "dashboard"


def _build_broker():
    kind = os.environ.get("TRADING_BROKER", "paper").lower()
    if kind == "paper":
        starting_cash = float(os.environ.get("PAPER_STARTING_CASH", "100000"))
        max_contracts = int(os.environ.get("PAPER_MAX_CONTRACTS", "10"))
        return PaperBroker(starting_cash=starting_cash, max_contracts=max_contracts)
    if kind == "ibkr":
        from trading_brain.broker.ibkr import IBKRBroker  # local import: ib_async only needed here

        return IBKRBroker(
            host=os.environ.get("IBKR_HOST", "127.0.0.1"),
            port=int(os.environ.get("IBKR_PORT", "7497")),
            client_id=int(os.environ.get("IBKR_CLIENT_ID", "1")),
        )
    raise ValueError(f"Unknown TRADING_BROKER={kind!r}, expected 'paper' or 'ibkr'")


def create_app() -> FastAPI:
    broker = _build_broker()
    settings_path = os.environ.get("SETTINGS_PATH")
    settings_store = SettingsStore(Path(settings_path)) if settings_path else None
    app_state = AppState(broker, settings_store)
    app_state.connection_manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_state.wire_broker()
        try:
            app_state.broker.connect()
        except Exception:
            logger.exception("broker connect() failed at startup -- service is up, broker is not")

        live_feed_task = None
        if os.environ.get("TRADING_BROKER", "paper").lower() == "paper" \
                and os.environ.get("LIVE_FEED", "true").lower() != "false":
            interval = int(os.environ.get("LIVE_FEED_INTERVAL_SECONDS", str(DEFAULT_INTERVAL_SECONDS)))
            live_feed_task = asyncio.create_task(run_live_feed(app_state, interval))
            logger.info("live_feed: polling real quotes every %ss (set LIVE_FEED=false to disable)", interval)

        yield

        if live_feed_task is not None:
            live_feed_task.cancel()
            try:
                await live_feed_task
            except asyncio.CancelledError:
                pass
        try:
            app_state.broker.disconnect()
        except Exception:
            logger.exception("broker disconnect() failed at shutdown")

    app = FastAPI(title="AI Trading Brain", lifespan=lifespan)
    app.state.app_state = app_state
    app.include_router(api.router)

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        manager = app_state.connection_manager
        await manager.connect(websocket)
        try:
            await manager.send_snapshot(websocket, app_state.build_snapshot())
            while True:
                # The dashboard doesn't send anything over this socket today;
                # this just keeps the connection open and detects disconnects.
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    if DASHBOARD_DIR.exists():
        app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

    return app


app = create_app()
