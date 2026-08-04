"""End-to-end check: the FastAPI service, wired to the in-memory paper
broker, actually does what the dashboard expects -- settings round-trip,
flatten-all works, and a WebSocket client gets a snapshot on connect."""

import os
import tempfile
import uuid

os.environ["TRADING_BROKER"] = "paper"
os.environ["PAPER_STARTING_CASH"] = "50000"

from starlette.testclient import TestClient  # noqa: E402

from service.main import create_app  # noqa: E402
from trading_brain.broker.base import Bar, OrderRequest, OrderSide  # noqa: E402


def _client():
    # Isolated settings.json per test -- otherwise every test shares (and
    # mutates) the real repo-level settings.json, making test order matter
    # and leaving stray state behind after the suite runs.
    os.environ["SETTINGS_PATH"] = os.path.join(tempfile.gettempdir(), f"settings-{uuid.uuid4().hex}.json")
    app = create_app()
    return TestClient(app), app


def test_settings_round_trip():
    client, app = _client()
    with client:
        got = client.get("/api/settings").json()
        assert got["account_mode"] == "paper"

        updated = client.put("/api/settings", json={"risk_percent": 2.5, "kill_switch_active": True})
        assert updated.status_code == 200
        body = updated.json()
        assert body["risk_percent"] == 2.5
        assert body["kill_switch_active"] is True

        # Persisted, not just held in memory for this one response.
        again = client.get("/api/settings").json()
        assert again["risk_percent"] == 2.5


def test_status_reports_paper_mode_and_connected_after_startup():
    client, app = _client()
    with client:
        status = client.get("/api/status").json()
        assert status["account_mode"] == "paper"
        assert status["connection_state"] == "connected"


def test_websocket_receives_snapshot_on_connect():
    client, app = _client()
    with client:
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
            assert msg["type"] == "snapshot"
            data = msg["data"]
            assert "positions" in data
            assert "account" in data
            assert "settings" in data
            assert data["connection_state"] == "connected"


def test_flatten_all_closes_positions_and_broadcasts():
    client, app = _client()
    with client:
        broker = app.state.app_state.broker
        broker.feed_bar(Bar(symbol="GC=F", timestamp=None, open=2500, high=2500, low=2500, close=2500))
        broker.place_order(OrderRequest(symbol="GC=F", side=OrderSide.BUY, quantity=1))

        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            resp = client.post("/api/flatten-all")
            assert resp.status_code == 200
            results = resp.json()
            assert len(results) == 1
            assert results[0]["status"] == "filled"

            # Positions/account pushed as a result of the flatten.
            seen_kinds = set()
            for _ in range(4):
                msg = ws.receive_json()
                seen_kinds.add(msg["type"])
            assert "positions" in seen_kinds
            assert "account" in seen_kinds

        assert app.state.app_state.broker.get_positions() == {}


def test_settings_change_broadcasts_to_connected_clients():
    client, app = _client()
    with client:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()  # snapshot
            client.put("/api/settings", json={"risk_percent": 3.0})
            msg = ws.receive_json()
            assert msg["type"] == "settings"
            assert msg["data"]["risk_percent"] == 3.0


def test_engines_are_wired_for_every_backtested_instrument():
    client, app = _client()
    with client:
        state = app.state.app_state
        assert set(state.engines.keys()) == {"GC=F", "ES=F", "CL=F", "EURUSD=X"}


def test_candles_endpoint_returns_ohlc_history():
    client, app = _client()
    with client:
        resp = client.get("/api/candles/GC=F", params={"limit": 5})
        assert resp.status_code == 200
        bars = resp.json()
        assert len(bars) == 5
        for bar in bars:
            assert set(bar.keys()) == {"time", "open", "high", "low", "close"}
        # chronological order, not reversed
        assert bars[0]["time"] < bars[-1]["time"]


def test_candles_endpoint_unknown_symbol_returns_empty_not_error():
    client, app = _client()
    with client:
        resp = client.get("/api/candles/NOPE=X")
        assert resp.status_code == 200
        assert resp.json() == []


def test_instruments_endpoint_lists_the_four_backtested_symbols():
    client, app = _client()
    with client:
        resp = client.get("/api/instruments")
        assert resp.status_code == 200
        assert set(resp.json()) == {"GC=F", "ES=F", "CL=F", "EURUSD=X"}
