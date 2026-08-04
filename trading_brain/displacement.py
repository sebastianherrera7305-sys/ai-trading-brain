"""
Displacement Module — AI Trading Brain v1, Phase 1

README definition: a valid displacement move must
  - Break structure
  - Move aggressively
  - Show imbalance
  - Create inefficiency
Weak candles are ignored.

This module measures "aggressive" relative to RECENT history only
(trailing average range) — never future candles, so that half stays
backtest-safe. The imbalance check is a different story: see the
`confirmed_at` note on DisplacementEvent below.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .market_structure import Candle


class Direction(Enum):
    BULLISH = "bullish"
    BEARISH = "bearish"


@dataclass
class ImbalanceGap:
    """
    The 3-candle imbalance pattern: candle[i-1] and candle[i+1] don't overlap,
    leaving a gap that displacement candle[i] punched through. This gap IS the
    raw material a later Fair Value Gap gets built from.
    """
    left_index: int
    right_index: int
    gap_low: float
    gap_high: float
    direction: Direction


@dataclass
class DisplacementEvent:
    candle_index: int
    direction: Direction
    candle_range: float
    avg_range_baseline: float
    strength_ratio: float  # candle_range / avg_range_baseline — how many x "normal"
    imbalance: ImbalanceGap
    confirmed_at: int = 0  # candle index at which this event becomes knowable (no look-ahead)


def rolling_average_range(candles: List[Candle], index: int, lookback: int = 10) -> Optional[float]:
    """
    Average high-low range of the `lookback` candles BEFORE `index` — never
    includes the candle being evaluated or anything after it (no look-ahead).
    """
    start = index - lookback
    if start < 0:
        return None
    window = candles[start:index]
    if not window:
        return None
    return sum(c.high - c.low for c in window) / len(window)


def find_imbalance(candles: List[Candle], index: int) -> Optional[ImbalanceGap]:
    """
    Classic ICT 3-candle FVG precursor: compare candle[index-1] and candle[index+1]
    (the displacement candle is the middle one, index).
    Bullish imbalance: candle[index-1].high < candle[index+1].low  (gap up)
    Bearish imbalance: candle[index-1].low  > candle[index+1].high (gap down)

    Needs the candle AFTER `index` to exist, so this can only tell you about a
    gap in hindsight — it is not knowable at the moment candle `index` closes.
    detect_displacement accounts for that with `confirmed_at`; callers using
    this function directly need to do the same.
    """
    if index - 1 < 0 or index + 1 >= len(candles):
        return None

    left = candles[index - 1]
    right = candles[index + 1]

    if left.high < right.low:
        return ImbalanceGap(left.index, right.index, left.high, right.low, Direction.BULLISH)
    if left.low > right.high:
        return ImbalanceGap(left.index, right.index, right.high, left.low, Direction.BEARISH)
    return None


def detect_displacement(
    candles: List[Candle],
    lookback: int = 10,
    strength_multiplier: float = 1.5,
) -> List[DisplacementEvent]:
    """
    Walks forward through candles. A candle qualifies as displacement if:
      - its range is >= strength_multiplier x the trailing average range (aggressive)
      - it produces a 3-candle imbalance gap with its neighbors (imbalance/inefficiency)
    "Break structure" is intentionally NOT checked here — that's market_structure.py's
    job; combine both modules' outputs before calling something a valid README displacement.

    NO LOOK-AHEAD: an event's `candle_index` is the displacement candle itself, but
    the imbalance that qualifies it can't be confirmed until the NEXT candle closes
    (find_imbalance reads candles[index+1]). So `confirmed_at = candle_index + 1` —
    a backtest walking forward cannot know about this event until one candle later
    than the one that caused it. Truncate the series right after the displacement
    candle and the event disappears; that's not a bug, that's the point.

    Direction is taken from the imbalance's gap, not from the displacement candle's
    open/close. A huge-range candle can close red while still gapping price up past
    its predecessor (a hard intracandle reversal) — the gap it leaves behind is what
    actually matters, and trusting open/close there would call a bullish inefficiency
    bearish.
    """
    events: List[DisplacementEvent] = []

    for i, candle in enumerate(candles):
        baseline = rolling_average_range(candles, i, lookback)
        if baseline is None or baseline == 0:
            continue

        candle_range = candle.high - candle.low
        strength_ratio = candle_range / baseline

        if strength_ratio < strength_multiplier:
            continue  # weak candle -> ignored, per the README

        imbalance = find_imbalance(candles, i)
        if imbalance is None:
            continue  # aggressive but no inefficiency created -> not a qualifying displacement

        events.append(DisplacementEvent(
            candle_index=candle.index,
            direction=imbalance.direction,
            candle_range=candle_range,
            avg_range_baseline=baseline,
            strength_ratio=strength_ratio,
            imbalance=imbalance,
            confirmed_at=candle.index + 1,
        ))

    return events


def run_demo() -> None:
    """Synthetic walkthrough: quiet chop, then one big aggressive bullish candle
    that leaves a real gap between its neighbors -> registers as displacement."""
    raw = [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101.5, 99, 100.5),
        (100.5, 101, 99.5, 100),
        (100, 101, 99, 100.2),
        (100.2, 101, 99.5, 100),   # candle[5] = the "left" neighbor, high=101
        (100, 112, 100, 111),      # candle[6] = big aggressive displacement candle
        (111, 113, 110.5, 112.5),  # candle[7] = "right" neighbor, low=110.5 > 101 -> real gap
        (112.5, 113, 112, 112.8),
    ]
    candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]

    events = detect_displacement(candles, lookback=5, strength_multiplier=1.5)

    print("=== Displacement Events ===")
    if not events:
        print("  none detected")
    for e in events:
        print(f"  idx={e.candle_index}  {e.direction.value:8s}  range={e.candle_range:.1f}  "
              f"baseline={e.avg_range_baseline:.2f}  strength={e.strength_ratio:.1f}x  "
              f"confirmed_at={e.confirmed_at}")
        gap = e.imbalance
        print(f"      imbalance: {gap.direction.value} gap between idx {gap.left_index}-{gap.right_index}, "
              f"zone [{gap.gap_low:.1f} - {gap.gap_high:.1f}]")


if __name__ == "__main__":
    run_demo()
