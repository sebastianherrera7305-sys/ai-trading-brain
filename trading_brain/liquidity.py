"""
Liquidity Module — AI Trading Brain v1, Phase 1

Detects: Equal Highs / Equal Lows, Session High / Session Low,
and Liquidity Sweeps (price takes a level, then rejects back through it).

Depends on nothing but raw candles + a session tag per candle.
No look-ahead: everything here only uses candles up to "now".
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .market_structure import Candle


class Session(Enum):
    LONDON = "london"
    NEW_YORK = "new_york"
    OVERLAP = "london_ny_overlap"
    OFF_SESSION = "off_session"


class LiquidityLevelType(Enum):
    EQUAL_HIGHS = "Equal Highs"
    EQUAL_LOWS = "Equal Lows"
    SESSION_HIGH = "Session High"
    SESSION_LOW = "Session Low"


@dataclass
class SessionCandle:
    """A candle tagged with which trading session it belongs to."""
    candle: Candle
    session: Session


@dataclass
class LiquidityLevel:
    level_type: LiquidityLevelType
    price: float
    formed_at_indices: List[int]  # candle indices that make up this level
    swept: bool = False
    swept_at_index: Optional[int] = None
    known_from: Optional[int] = None  # first candle index at which this level is tradable

    def __post_init__(self):
        if self.known_from is None:
            touches = sorted(self.formed_at_indices)
            # An equal-highs/lows level is liquidity the moment the SECOND touch
            # prints. Keying off the last touch would let a later touch reach back
            # and suppress a sweep that was valid in real time.
            anchor = touches[1] if len(touches) >= 2 else touches[-1]
            self.known_from = anchor + 1

    @property
    def is_high_side(self) -> bool:
        return self.level_type in (LiquidityLevelType.EQUAL_HIGHS,
                                   LiquidityLevelType.SESSION_HIGH)


@dataclass
class LiquiditySweep:
    candle_index: int
    level: LiquidityLevel
    rejected: bool  # True = price swept the level then closed back through it (valid sweep)


# --- Equal Highs / Equal Lows -------------------------------------------------

def _group_equal(candles: List[Candle], price_of, level_type: LiquidityLevelType,
                 tolerance: float) -> List[LiquidityLevel]:
    """Cluster candles whose `price_of` values sit within `tolerance` of each other."""
    levels: List[LiquidityLevel] = []
    ordered = sorted(candles, key=price_of)
    used = set()

    for i, c in enumerate(ordered):
        if c.index in used:
            continue
        group = [c]
        for other in ordered[i + 1:]:
            if other.index in used:
                continue
            if abs(price_of(other) - price_of(c)) <= tolerance:
                group.append(other)
        if len(group) >= 2:
            avg_price = sum(price_of(g) for g in group) / len(group)
            levels.append(LiquidityLevel(level_type, avg_price,
                                         sorted(g.index for g in group)))
            used.update(g.index for g in group)

    return levels


def find_equal_highs_lows(candles: List[Candle], tolerance: float = 0.05) -> List[LiquidityLevel]:
    """
    Two or more highs (or lows) within `tolerance` (price units, e.g. 0.05 = 5 pips
    on a 4-decimal forex pair — adjust per instrument) count as an "equal" level.
    Only groups of 2+ are returned; a single untouched high isn't liquidity yet.

    Every member is compared against the group's anchor rather than its neighbour,
    so tolerance never chains: 110.0 / 110.4 / 110.8 at tolerance 0.5 groups the
    first two and drops the third, instead of drifting into one wide level.
    """
    return (_group_equal(candles, lambda c: c.high, LiquidityLevelType.EQUAL_HIGHS, tolerance)
            + _group_equal(candles, lambda c: c.low, LiquidityLevelType.EQUAL_LOWS, tolerance))


# --- Session High / Low --------------------------------------------------------

def find_session_extremes(session_candles: List[SessionCandle]) -> List[LiquidityLevel]:
    """
    For each session block (consecutive candles sharing the same Session tag,
    excluding OFF_SESSION), find that session's high and low.
    """
    levels: List[LiquidityLevel] = []
    if not session_candles:
        return levels

    def flush(block: List[SessionCandle], session: Optional[Session]) -> None:
        if not block or session in (None, Session.OFF_SESSION):
            return
        highest = max(block, key=lambda sc: sc.candle.high)
        lowest = min(block, key=lambda sc: sc.candle.low)
        levels.append(LiquidityLevel(LiquidityLevelType.SESSION_HIGH, highest.candle.high,
                                      [highest.candle.index]))
        levels.append(LiquidityLevel(LiquidityLevelType.SESSION_LOW, lowest.candle.low,
                                      [lowest.candle.index]))

    block: List[SessionCandle] = []
    current_session: Optional[Session] = None

    for sc in session_candles:
        if sc.session != current_session:
            flush(block, current_session)
            block = []
            current_session = sc.session
        block.append(sc)
    flush(block, current_session)

    return levels


# --- Liquidity Sweeps -----------------------------------------------------------

def detect_sweeps(candles: List[Candle], levels: List[LiquidityLevel]) -> List[LiquiditySweep]:
    """
    A sweep = price trades THROUGH a level (wick beyond it) but CLOSES back
    on the origin side (rejection) -> matches README: "Was liquidity swept?
    Did price reject?" A close that stays beyond the level is a break, not a sweep;
    it is still reported, with rejected=False, so the caller can tell them apart.

    Only considers a level once it exists (from `known_from`) and only once, at
    its first sweep — a level is "used up" after being taken.

    NOTE: this MUTATES the levels it is given, stamping `swept` / `swept_at_index`.
    That state is the point (a level is consumed once taken), but it means the
    call is not idempotent: re-running on the same level objects returns nothing.
    Rebuild the levels if you need to re-scan.
    """
    sweeps: List[LiquiditySweep] = []

    for level in levels:
        if level.swept:
            continue

        for candle in candles:
            if candle.index < level.known_from:
                continue

            if level.is_high_side:
                wicked_through = candle.high > level.price
                rejected = candle.close < level.price
            else:
                wicked_through = candle.low < level.price
                rejected = candle.close > level.price

            if wicked_through:
                level.swept = True
                level.swept_at_index = candle.index
                sweeps.append(LiquiditySweep(candle.index, level, rejected))
                break  # the level is consumed; stop scanning it

    return sorted(sweeps, key=lambda s: s.candle_index)


def run_demo() -> None:
    """Synthetic walkthrough: two equal highs, then a classic stop-hunt sweep."""
    raw = [
        (100, 102, 99, 101),
        (101, 110, 100, 105),   # first "equal" high ~110
        (105, 106, 102, 103),
        (103, 108, 101, 104),
        (104, 110, 103, 106),   # second equal high ~110 (within tolerance)
        (106, 107, 104, 105),
        (105, 113, 105, 107),   # sweep: wicks to 113 (above 110) but CLOSES back at 107 -> rejection
        (107, 108, 104, 105),
    ]
    candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]

    eq_levels = find_equal_highs_lows(candles, tolerance=0.5)
    print("=== Equal Highs/Lows ===")
    for lvl in eq_levels:
        print(f"  {lvl.level_type.value:12s} price~{lvl.price:.1f}  formed at idx {lvl.formed_at_indices}"
              f"  tradable from idx {lvl.known_from}")

    sweeps = detect_sweeps(candles, eq_levels)
    print("\n=== Sweeps ===")
    for sw in sweeps:
        status = "REJECTED (valid sweep)" if sw.rejected else "closed through (this is a BREAK, not a sweep)"
        print(f"  idx={sw.candle_index}  swept {sw.level.level_type.value} @ {sw.level.price:.1f}  -> {status}")

    # Session extremes demo
    print("\n=== Session Highs/Lows ===")
    sessions = (
        [SessionCandle(c, Session.LONDON) for c in candles[:4]] +
        [SessionCandle(c, Session.NEW_YORK) for c in candles[4:]]
    )
    for lvl in find_session_extremes(sessions):
        print(f"  {lvl.level_type.value:14s} price={lvl.price:.1f}  at idx {lvl.formed_at_indices}")


if __name__ == "__main__":
    run_demo()
