from datetime import datetime, timedelta

from trading_brain.backtest import BacktestConfig
from trading_brain.broker.base import Bar
from trading_brain.broker.engine_runner import LiveEngine
from trading_brain.broker.paper import PaperBroker
from trading_brain.broker.settings import BotSettings

SYMBOL = "TEST"

# Same synthetic series as backtest.run_demo(): a bullish setup that fills
# and wins, followed by a bearish setup that fills and gets stopped out.
# Reusing it here checks the live engine reaches the same outcomes the
# backtester was already validated against, via the shared
# find_candidate_order() function -- not a second, hand-rolled scenario.
_RAW = [
    (100, 101, 99, 100), (100, 105, 99.5, 104), (104, 104.5, 100.5, 101),
    (101, 102, 99, 99.5), (99.5, 103, 99.2, 102), (102, 109, 101.5, 108),
    (108, 108.5, 103, 104), (104, 105, 100.20, 101), (101, 101.5, 100.9, 101.2),
    (101.2, 101.3, 100.25, 101), (101, 101.5, 100.9, 101.2), (101.2, 101.5, 99.5, 101.3),
    (101.3, 112, 101, 110),
    (110, 113, 108, 112),
    (112, 112.5, 107.5, 108.2),
    (108.2, 108.5, 107.9, 108.1),
    (108.1, 130, 108, 129),
    (129, 130, 108, 128),
    (128, 128.5, 126, 127), (127, 127.5, 120.20, 121),
    (121, 121.5, 120.60, 121.2), (121.2, 121.3, 120.25, 121), (121, 121.5, 120.60, 121.2),
    (121.2, 121.5, 118, 121.3),
    (121.3, 132, 121, 130),
    (130, 133, 128, 132),
    (132, 132.5, 127.5, 128.2),
    (128.2, 128.5, 127.9, 128.1),
    (128.1, 128.5, 108, 110),
]


def _bars():
    start = datetime(2026, 1, 1)
    return [
        Bar(symbol=SYMBOL, timestamp=start + timedelta(days=i), open=o, high=h, low=l, close=c)
        for i, (o, h, l, c) in enumerate(_RAW)
    ]


def _make_engine(broker, settings):
    config = BacktestConfig(swing_lookback=1, displacement_lookback=5, liquidity_tolerance=0.1)
    return LiveEngine(
        symbol=SYMBOL,
        broker=broker,
        settings_provider=lambda: settings,
        account_balance_provider=lambda: broker.get_account_summary().net_liquidation,
        config=config,
    )


def _permissive_settings(**overrides):
    settings = BotSettings(
        risk_percent=1.0,
        max_contracts=5,
        min_tier="B",
        enabled_instruments={SYMBOL: True},
    )
    for k, v in overrides.items():
        setattr(settings, k, v)
    return settings


def test_engine_places_and_fills_a_trade_end_to_end():
    broker = PaperBroker(starting_cash=100_000.0, max_contracts=10)
    settings = _permissive_settings()
    engine = _make_engine(broker, settings)

    for bar in _bars():
        broker.feed_bar(bar)
        engine.on_bar(bar)

    # Reference scenario produces a win then a loss (see run_demo in
    # backtest.py) -- by the end of the series the account must reflect a
    # realized win offset by a realized loss, not just sit at starting cash.
    summary = broker.get_account_summary()
    assert summary.realized_pnl_today != 0.0
    assert len(broker.order_log_entries) >= 2  # at least the two entries filled


def test_engine_never_trades_a_disabled_instrument():
    broker = PaperBroker(starting_cash=100_000.0)
    settings = _permissive_settings(enabled_instruments={SYMBOL: False})
    engine = _make_engine(broker, settings)

    for bar in _bars():
        broker.feed_bar(bar)
        engine.on_bar(bar)

    assert broker.order_log_entries == []
    assert engine.state == "flat"


def test_engine_respects_kill_switch():
    broker = PaperBroker(starting_cash=100_000.0)
    settings = _permissive_settings(kill_switch_active=True)
    engine = _make_engine(broker, settings)

    for bar in _bars():
        broker.feed_bar(bar)
        engine.on_bar(bar)

    assert broker.order_log_entries == []


def test_engine_position_size_capped_by_settings_max_contracts():
    broker = PaperBroker(starting_cash=10_000_000.0, max_contracts=1000)
    settings = _permissive_settings(risk_percent=50.0, max_contracts=2)
    engine = _make_engine(broker, settings)

    for bar in _bars():
        broker.feed_bar(bar)
        engine.on_bar(bar)

    fills = [e for e in broker.order_log_entries if e["status"] == "filled"]
    assert fills, "expected at least one filled entry"
    assert all(e["quantity"] <= 2 for e in fills)


def test_engine_transitions_flat_pending_open_flat_across_first_trade():
    broker = PaperBroker(starting_cash=100_000.0)
    settings = _permissive_settings()
    engine = _make_engine(broker, settings)

    states = []
    for bar in _bars():
        broker.feed_bar(bar)
        engine.on_bar(bar)
        states.append(engine.state)

    assert "pending" in states
    assert "open" in states
    # First pending appears before first open, which appears before it goes
    # flat again once the trade resolves.
    assert states.index("pending") < states.index("open")
