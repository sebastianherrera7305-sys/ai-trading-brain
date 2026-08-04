"""
Live feed for paper mode — AI Trading Brain, Phase 3

Closes a gap flagged since the chart/service were first built: paper
mode had no market-data source wired in at all, so nothing ever moved on
its own -- positions, the strategy engine, and the chart all sat static
until a test or a manual script called feed_bar() by hand.

This polls real quotes from Yahoo Finance (via yfinance, no API key) and
feeds them into the paper broker -- but NOT uniformly. Two distinct
things happen on two different cadences, and conflating them would be a
real bug, not a style choice:

  - Every poll (default 60s): the day's still-forming daily bar is
    fetched and passed to broker.mark_price() -- updates last price and
    unrealized P&L, and gets broadcast to the dashboard's chart as a
    live-updating "today" candle. This does NOT reach the strategy
    engine.
  - Once per real trading day, when a new completed daily bar appears:
    THAT bar goes through broker.feed_bar(), which is what actually
    reaches LiveEngine via the existing subscribe_bars wiring.

Why the split matters: LiveEngine and every BacktestConfig default in
this project were validated exclusively against daily bars (see
engine_runner.py's module docstring). Feeding 1-minute or continuously-
updating intraday ticks into feed_bar() would silently start running
this strategy at a timeframe it has never been calibrated for.

Honesty notes:
  - Outside trading hours, polls legitimately find nothing new -- this
    does not fabricate movement to make the dashboard look alive.
  - A single failed fetch (rate limit, network blip, Yahoo schema
    change) logs and skips that symbol for that cycle rather than
    crashing the whole service.
"""

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Dict, Optional

from trading_brain.broker.base import Bar

logger = logging.getLogger("service.live_feed")

DEFAULT_INTERVAL_SECONDS = 60


def _fetch_recent_daily_bars(symbol: str):
    """Blocking (yfinance does its own HTTP under the hood) -- always run
    via run_in_executor, never directly on the event loop. Returns the
    last few daily rows so the caller can tell 'today, still forming'
    apart from 'yesterday, now final' without a second network round
    trip."""
    import yfinance as yf  # local import: only paper mode needs this dependency

    try:
        history = yf.Ticker(symbol).history(period="5d", interval="1d")
    except Exception:
        logger.exception("live_feed: fetch failed for %s", symbol)
        return None
    if history is None or history.empty:
        return None
    return history


def _row_to_bar(symbol: str, row, ts) -> Optional[Bar]:
    try:
        timestamp = ts.to_pydatetime()
    except AttributeError:
        timestamp = datetime.now(timezone.utc)
    try:
        return Bar(
            symbol=symbol,
            timestamp=timestamp,
            open=float(row["Open"]), high=float(row["High"]),
            low=float(row["Low"]), close=float(row["Close"]),
        )
    except (KeyError, ValueError, TypeError):
        logger.exception("live_feed: malformed bar for %s", symbol)
        return None


async def run_live_feed(app_state, interval_seconds: int = DEFAULT_INTERVAL_SECONDS) -> None:
    """Runs until cancelled -- one pass per interval."""
    loop = asyncio.get_event_loop()
    symbols = list(app_state.engines.keys())
    last_completed_date: Dict[str, date] = {}

    while True:
        for symbol in symbols:
            try:
                history = await loop.run_in_executor(None, _fetch_recent_daily_bars, symbol)
            except Exception:
                logger.exception("live_feed: unexpected error fetching %s", symbol)
                continue
            if history is None or len(history) == 0:
                continue

            # Order matters: feed_bar() (a completed prior day, reaching the
            # engine) also updates the broker's last price as a side effect.
            # Doing that first and mark_price() (today's still-forming bar,
            # display-only) second means the freshest price is always what's
            # left showing -- reversed, feed_bar would silently clobber the
            # more current mark_price() update with yesterday's close.
            if len(history) >= 2:
                completed_row = history.iloc[-2]
                completed_ts = history.index[-2]
                completed_date = completed_ts.date() if hasattr(completed_ts, "date") else None
                if completed_date is not None and last_completed_date.get(symbol) != completed_date:
                    completed_bar = _row_to_bar(symbol, completed_row, completed_ts)
                    if completed_bar is not None:
                        last_completed_date[symbol] = completed_date
                        try:
                            app_state.broker.feed_bar(completed_bar)
                        except Exception:
                            logger.exception("live_feed: broker.feed_bar failed for %s", symbol)

            today_bar = _row_to_bar(symbol, history.iloc[-1], history.index[-1])
            if today_bar is not None:
                app_state.broker.mark_price(symbol, today_bar.close)
                if app_state.connection_manager is not None:
                    await app_state.connection_manager.broadcast("candle", {
                        "symbol": symbol,
                        "time": today_bar.timestamp.strftime("%Y-%m-%d"),
                        "open": today_bar.open, "high": today_bar.high,
                        "low": today_bar.low, "close": today_bar.close,
                    })

        await asyncio.sleep(interval_seconds)
