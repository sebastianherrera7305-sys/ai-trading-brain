"""
Session Module — AI Trading Brain v1, Phase 1

README rule: "The AI may only open new trades during high-liquidity
institutional sessions" -> London, New York, and their overlap.
Kill zones = the highest-participation sub-windows of each session.

All times are UTC. Adjust these windows if your broker feed uses a
different timezone convention.
"""

from dataclasses import dataclass
from datetime import time
from enum import Enum


class SessionWindow(Enum):
    LONDON_OPEN = "London Open"
    LONDON_KILLZONE = "London Kill Zone"
    NEW_YORK_OPEN = "New York Open"
    NEW_YORK_KILLZONE = "New York Kill Zone"
    LONDON_NY_OVERLAP = "London/New York Overlap"
    LONDON_GENERAL = "London Session"
    NEW_YORK_GENERAL = "New York Session"
    OFF_SESSION = "Off Session"


# (start_utc, end_utc, label) — checked in priority order, most specific first.
# Every window here is a strict subset of at least one later window (e.g.
# NEW_YORK_OPEN [12,14) sits entirely inside LONDON_NY_OVERLAP [12,16), which
# sits inside NEW_YORK_GENERAL [12,21)), so narrowest-first is not cosmetic:
# put a broader window earlier and it silently swallows every narrower one
# nested inside it, and that label can never be produced again.
_WINDOWS = [
    (time(7, 0),  time(9, 0),  SessionWindow.LONDON_OPEN),
    (time(12, 0), time(14, 0), SessionWindow.NEW_YORK_OPEN),
    (time(7, 0),  time(10, 0), SessionWindow.LONDON_KILLZONE),
    (time(12, 0), time(15, 0), SessionWindow.NEW_YORK_KILLZONE),
    (time(12, 0), time(16, 0), SessionWindow.LONDON_NY_OVERLAP),
    (time(7, 0),  time(16, 0), SessionWindow.LONDON_GENERAL),
    (time(12, 0), time(21, 0), SessionWindow.NEW_YORK_GENERAL),
]

# Windows the README explicitly allows new trade ENTRIES during.
TRADEABLE_WINDOWS = {
    SessionWindow.LONDON_OPEN, SessionWindow.LONDON_KILLZONE,
    SessionWindow.NEW_YORK_OPEN, SessionWindow.NEW_YORK_KILLZONE,
    SessionWindow.LONDON_NY_OVERLAP, SessionWindow.LONDON_GENERAL,
    SessionWindow.NEW_YORK_GENERAL,
}


@dataclass
class SessionTag:
    utc_time: time
    window: SessionWindow
    is_tradeable: bool
    is_preferred: bool  # True for the "cleanest price action" kill zones/overlap


_PREFERRED = {
    SessionWindow.LONDON_OPEN, SessionWindow.LONDON_KILLZONE,
    SessionWindow.NEW_YORK_OPEN, SessionWindow.NEW_YORK_KILLZONE,
    SessionWindow.LONDON_NY_OVERLAP,
}


def tag_session(utc_time: time) -> SessionTag:
    """Most specific/preferred window wins if multiple match (checked in priority order)."""
    for start, end, label in _WINDOWS:
        if start <= utc_time < end:
            return SessionTag(utc_time, label, label in TRADEABLE_WINDOWS, label in _PREFERRED)
    return SessionTag(utc_time, SessionWindow.OFF_SESSION, False, False)


def is_allowed_to_trade(utc_time: time) -> bool:
    """Direct README gate: 'may only open new trades during high-liquidity institutional sessions'."""
    return tag_session(utc_time).is_tradeable


def run_demo() -> None:
    """Tag a spread of times across the day, including the NY open/kill-zone
    windows that only became reachable once window priority was fixed."""
    test_times = [
        time(3, 0),    # dead Asia session -> should be off
        time(7, 30),   # London open
        time(9, 30),   # London kill zone tail, past open window
        time(12, 30),  # NY open (and, not coincidentally, inside the overlap too)
        time(14, 30),  # NY kill zone specifically, after NY's own open window ends
        time(15, 30),  # overlap tail, after NY's kill zone ends but before London closes
        time(19, 0),   # late NY, general session
        time(22, 0),   # after NY close -> off
    ]
    print("=== Session Tags ===")
    for t in test_times:
        tag = tag_session(t)
        flag = "PREFERRED" if tag.is_preferred else ("tradeable" if tag.is_tradeable else "NO TRADE")
        print(f"  {t.strftime('%H:%M')} UTC  -> {tag.window.value:24s}  [{flag}]")


if __name__ == "__main__":
    run_demo()
