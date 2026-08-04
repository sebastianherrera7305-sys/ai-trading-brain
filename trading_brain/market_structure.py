"""
Market Structure Module — AI Trading Brain v1, Phase 1

Detects: swing highs/lows, HH/HL/LH/LL classification,
Break of Structure (BOS), and Change of Character (CHoCH).

This is pure logic — no broker, no money, no live data.
Feed it a list of OHLC candles, it tells you what the structure is doing.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional


class SwingType(Enum):
    HIGH = "high"
    LOW = "low"


class StructureLabel(Enum):
    HH = "Higher High"
    HL = "Higher Low"
    LH = "Lower High"
    LL = "Lower Low"


class Trend(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    RANGE = "range"


class StructureEvent(Enum):
    BOS = "Break of Structure"
    CHOCH = "Change of Character"


@dataclass
class Candle:
    index: int
    open: float
    high: float
    low: float
    close: float
    timestamp: Optional[datetime] = None  # optional; enables session-time gating in backtest.py


@dataclass
class SwingPoint:
    candle_index: int
    price: float
    swing_type: SwingType
    label: Optional[StructureLabel] = None
    confirmed_at: int = 0  # candle index at which this swing becomes knowable (no look-ahead)


@dataclass
class StructureSignal:
    candle_index: int
    event: StructureEvent
    trend_before: Trend
    trend_after: Trend
    broken_level: float


def find_swing_points(candles: List[Candle], lookback: int = 2) -> List[SwingPoint]:
    """
    Fractal-style swing detection: a candle is a swing high if its high
    is greater than `lookback` candles on both sides; swing low is the mirror.

    Comparisons are strict, so a flat stretch of equal highs produces no swing
    rather than tagging every candle in it (and never tags one candle as both
    a swing high and a swing low).
    """
    swings: List[SwingPoint] = []
    n = len(candles)

    for i in range(lookback, n - lookback):
        current = candles[i]
        neighbors = candles[i - lookback: i] + candles[i + 1: i + lookback + 1]

        confirmed_at = current.index + lookback  # need `lookback` candles AFTER it to confirm

        if all(current.high > c.high for c in neighbors):
            swings.append(SwingPoint(current.index, current.high, SwingType.HIGH,
                                     confirmed_at=confirmed_at))

        if all(current.low < c.low for c in neighbors):
            swings.append(SwingPoint(current.index, current.low, SwingType.LOW,
                                     confirmed_at=confirmed_at))

    return swings


def classify_structure(swings: List[SwingPoint]) -> List[SwingPoint]:
    """
    Labels each swing HH/HL/LH/LL relative to the previous swing of the SAME type.
    """
    last_high: Optional[SwingPoint] = None
    last_low: Optional[SwingPoint] = None

    for swing in swings:
        if swing.swing_type == SwingType.HIGH:
            if last_high is not None:
                swing.label = StructureLabel.HH if swing.price > last_high.price else StructureLabel.LH
            last_high = swing
        else:
            if last_low is not None:
                swing.label = StructureLabel.HL if swing.price > last_low.price else StructureLabel.LL
            last_low = swing

    return swings


def determine_trend(swings: List[SwingPoint]) -> Trend:
    """
    Simple trend read from the most recent labeled swings:
    consecutive HH+HL => bullish, consecutive LH+LL => bearish, else range.
    """
    labeled = [s for s in swings if s.label is not None]
    if len(labeled) < 2:
        return Trend.RANGE

    recent = labeled[-4:]
    # Majority of the window, but never more votes than the window can hold.
    needed = min(3, len(recent))
    bullish_votes = sum(1 for s in recent if s.label in (StructureLabel.HH, StructureLabel.HL))
    bearish_votes = sum(1 for s in recent if s.label in (StructureLabel.LH, StructureLabel.LL))

    if bullish_votes >= needed:
        return Trend.BULLISH
    if bearish_votes >= needed:
        return Trend.BEARISH
    return Trend.RANGE


def _supersedes(candidate: SwingPoint, current: SwingPoint) -> bool:
    """True if `candidate` should replace `current` as the live structural level."""
    if candidate.candle_index != current.candle_index:
        return candidate.candle_index > current.candle_index
    if candidate.swing_type == SwingType.HIGH:
        return candidate.price > current.price
    return candidate.price < current.price


def detect_bos_and_choch(candles: List[Candle], swings: List[SwingPoint]) -> List[StructureSignal]:
    """
    BOS: price closes beyond the last swing high/low IN the direction of the
         current trend -> trend continuation confirmed.
    CHoCH: price closes beyond the last swing high/low AGAINST the current
           trend -> possible reversal, matches the README's Invalidation Rule
           trigger ("if new structure confirms the trade is no longer valid, exit").

    Swings are revealed candle by candle at their `confirmed_at` index, so the
    walk never uses information that was not available at that point in time.
    """
    signals: List[StructureSignal] = []
    sorted_swings = sorted(swings, key=lambda s: s.confirmed_at)

    trend = Trend.RANGE
    last_swing_high: Optional[SwingPoint] = None
    last_swing_low: Optional[SwingPoint] = None
    swing_cursor = 0

    for candle in candles:
        # Reveal only swings that are confirmed as of THIS candle (no look-ahead)
        while swing_cursor < len(sorted_swings) and sorted_swings[swing_cursor].confirmed_at <= candle.index:
            newly_known = sorted_swings[swing_cursor]
            swing_cursor += 1
            # A swing confirmed late must not overwrite a more recent level (e.g.
            # the one a BOS just established). On the same candle the true swing
            # extreme wins, since that is the level price actually has to clear.
            if newly_known.swing_type == SwingType.HIGH:
                if last_swing_high is None or _supersedes(newly_known, last_swing_high):
                    last_swing_high = newly_known
            else:
                if last_swing_low is None or _supersedes(newly_known, last_swing_low):
                    last_swing_low = newly_known

        current_trend_before = trend

        if last_swing_high and candle.close > last_swing_high.price:
            if trend == Trend.BEARISH:
                trend = Trend.BULLISH
                signals.append(StructureSignal(candle.index, StructureEvent.CHOCH,
                                                current_trend_before, trend, last_swing_high.price))
            else:
                trend = Trend.BULLISH
                signals.append(StructureSignal(candle.index, StructureEvent.BOS,
                                                current_trend_before, trend, last_swing_high.price))
            last_swing_high = SwingPoint(candle.index, candle.close, SwingType.HIGH,
                                          StructureLabel.HH, confirmed_at=candle.index)

        elif last_swing_low and candle.close < last_swing_low.price:
            if trend == Trend.BULLISH:
                trend = Trend.BEARISH
                signals.append(StructureSignal(candle.index, StructureEvent.CHOCH,
                                                current_trend_before, trend, last_swing_low.price))
            else:
                trend = Trend.BEARISH
                signals.append(StructureSignal(candle.index, StructureEvent.BOS,
                                                current_trend_before, trend, last_swing_low.price))
            last_swing_low = SwingPoint(candle.index, candle.close, SwingType.LOW,
                                         StructureLabel.LL, confirmed_at=candle.index)

    return signals


def run_demo() -> None:
    """Synthetic walkthrough: clean uptrend (HH/HL), two BOS, then a CHoCH."""
    raw_prices = [
        (100, 102, 99, 101),
        (101, 105, 100, 104),   # swing high forming
        (104, 104, 101, 102),
        (102, 103, 98, 99),     # swing low
        (99, 108, 99, 107),     # HH - breaks prior high -> BOS in uptrend
        (107, 109, 105, 106),
        (106, 107, 102, 103),   # HL
        (103, 115, 103, 114),   # another HH -> BOS
        (114, 114, 108, 109),
        (109, 110, 95, 96),     # sharp drop breaking prior HL -> CHoCH (bearish reversal)
        (96, 97, 90, 91),
    ]
    candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw_prices)]

    swings = find_swing_points(candles, lookback=1)
    swings = classify_structure(swings)
    trend = determine_trend(swings)
    signals = detect_bos_and_choch(candles, swings)

    print("=== Swing Points ===")
    for s in swings:
        label = s.label.value if s.label else "unlabeled (first of its type)"
        print(f"  idx={s.candle_index:2d}  {s.swing_type.value:5s}  price={s.price:6.1f}  -> {label}")

    print(f"\n=== Trend Read ===\n  {trend.value}")

    print("\n=== Structure Events (BOS / CHoCH) ===")
    if not signals:
        print("  none detected")
    for sig in signals:
        print(f"  idx={sig.candle_index:2d}  {sig.event.value:20s}  "
              f"{sig.trend_before.value} -> {sig.trend_after.value}  broke level {sig.broken_level:.1f}")


if __name__ == "__main__":
    run_demo()
