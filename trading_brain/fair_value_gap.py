"""
Fair Value Gap (FVG) Module — AI Trading Brain v1, Phase 1

README rule: "Accept only FVGs that form after displacement, align with
trend, follow liquidity sweep, remain unmitigated. Ignore weak FVGs."

This module doesn't detect gaps itself — displacement.py already found the
raw imbalance. This module VALIDATES which of those gaps count as real,
tradeable FVGs per the README's four conditions, and tracks whether each
one has since been filled (mitigated).
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from .market_structure import Candle, Trend
from .displacement import DisplacementEvent, Direction
from .liquidity import LiquiditySweep


class MitigationStatus(Enum):
    UNMITIGATED = "unmitigated"       # still open, tradeable
    PARTIALLY_FILLED = "partial"      # price touched it but didn't fully close it
    MITIGATED = "mitigated"           # fully filled -> no longer valid per README


@dataclass
class ValidatedFVG:
    origin_displacement_index: int
    direction: Direction
    gap_low: float
    gap_high: float
    aligned_with_trend: bool
    followed_sweep: bool
    preceding_sweep_index: Optional[int]
    status: MitigationStatus = MitigationStatus.UNMITIGATED
    mitigated_at_index: Optional[int] = None


def _trend_agrees(direction: Direction, trend: Trend) -> bool:
    if direction == Direction.BULLISH:
        return trend == Trend.BULLISH
    return trend == Trend.BEARISH


def _sweep_precedes(displacement_index: int, direction: Direction, sweeps: List[LiquiditySweep],
                     max_lookback: int = 10) -> Optional[int]:
    """
    Was there a REJECTED liquidity sweep shortly before this displacement candle,
    on the side that actually fuels a reversal in `direction`? Returns the sweep's
    candle index if found, else None. Only looks backward.

    Side matters, not just recency: a bullish reversal is fueled by sell-side
    liquidity being taken (a swept LOW, stops/breakout-shorts triggered below,
    then price reverses up) — a swept HIGH shortly before a bullish displacement
    is liquidity on the wrong side and doesn't fuel it, however recent it was.
    """
    # Bullish wants a swept LOW (is_high_side False); bearish wants a swept HIGH.
    wanted_is_high_side = direction == Direction.BEARISH

    candidates = [
        s for s in sweeps
        if s.rejected and s.candle_index < displacement_index
        and displacement_index - s.candle_index <= max_lookback
        and s.level.is_high_side == wanted_is_high_side
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.candle_index).candle_index


def validate_fvgs(
    displacement_events: List[DisplacementEvent],
    sweeps: List[LiquiditySweep],
    trend_at: dict,  # {candle_index: Trend} — trend as of each displacement's index
    sweep_lookback: int = 10,
) -> List[ValidatedFVG]:
    """
    Filters raw displacement-imbalances down to README-valid FVGs.
    trend_at must give the trend that was ACTIVE at (or just before) the
    displacement candle -- pass market_structure.determine_trend() results
    computed incrementally, not the final trend for the whole dataset (avoid look-ahead).
    """
    validated: List[ValidatedFVG] = []

    for event in displacement_events:
        if event.imbalance is None:
            continue  # no inefficiency -> README says ignore

        trend = trend_at.get(event.candle_index, Trend.RANGE)
        aligned = _trend_agrees(event.direction, trend)

        sweep_idx = _sweep_precedes(event.candle_index, event.direction, sweeps, sweep_lookback)
        followed_sweep = sweep_idx is not None

        if not (aligned and followed_sweep):
            continue  # README: only accept FVGs meeting ALL conditions

        validated.append(ValidatedFVG(
            origin_displacement_index=event.candle_index,
            direction=event.direction,
            gap_low=event.imbalance.gap_low,
            gap_high=event.imbalance.gap_high,
            aligned_with_trend=aligned,
            followed_sweep=followed_sweep,
            preceding_sweep_index=sweep_idx,
        ))

    return validated


def update_mitigation(fvgs: List[ValidatedFVG], candles: List[Candle]) -> None:
    """
    Walks forward candle by candle. A bullish FVG is mitigated once price
    trades back down through gap_low (fully closes the gap); a bearish FVG
    is mitigated once price trades back up through gap_high. Mutates in place.
    """
    for fvg in fvgs:
        for candle in candles:
            if candle.index <= fvg.origin_displacement_index:
                continue
            if fvg.status == MitigationStatus.MITIGATED:
                break

            if fvg.direction == Direction.BULLISH:
                if candle.low <= fvg.gap_low:
                    fvg.status = MitigationStatus.MITIGATED
                    fvg.mitigated_at_index = candle.index
                elif candle.low < fvg.gap_high:
                    fvg.status = MitigationStatus.PARTIALLY_FILLED
            else:
                if candle.high >= fvg.gap_high:
                    fvg.status = MitigationStatus.MITIGATED
                    fvg.mitigated_at_index = candle.index
                elif candle.high > fvg.gap_low:
                    fvg.status = MitigationStatus.PARTIALLY_FILLED


def run_demo() -> None:
    # Reuse displacement's synthetic setup: bullish displacement at idx 6,
    # gap zone [101.0, 110.5]. Add a rejected sweep just before it, and
    # continue price after so we can test mitigation tracking.
    raw = [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101.5, 99, 100.5),
        (100.5, 101, 99.5, 100),
        (100, 101, 99, 100.2),
        (100.2, 101, 99.5, 100),
        (100, 112, 100, 111),
        (111, 113, 110.5, 112.5),
        (112.5, 115, 112, 114),
        (114, 114, 105, 106),    # dips back into the gap zone but NOT below 101 -> partial fill
    ]
    candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]

    from .displacement import detect_displacement
    from .liquidity import LiquidityLevel, LiquidityLevelType, LiquiditySweep as Sw

    disp_events = detect_displacement(candles, lookback=5, strength_multiplier=1.5)

    # Fake one rejected sweep right before the displacement candle (idx 5)
    fake_level = LiquidityLevel(LiquidityLevelType.EQUAL_LOWS, 99.5, [1, 3])
    fake_sweep = Sw(candle_index=5, level=fake_level, rejected=True)

    trend_lookup = {e.candle_index: Trend.BULLISH for e in disp_events}  # assume bullish trend was active

    fvgs = validate_fvgs(disp_events, [fake_sweep], trend_lookup)
    update_mitigation(fvgs, candles)

    print("=== Validated FVGs ===")
    if not fvgs:
        print("  none passed all four README conditions")
    for f in fvgs:
        print(f"  origin idx={f.origin_displacement_index}  {f.direction.value:8s}  "
              f"zone=[{f.gap_low:.1f}-{f.gap_high:.1f}]  aligned={f.aligned_with_trend}  "
              f"followed_sweep(idx {f.preceding_sweep_index})={f.followed_sweep}  "
              f"status={f.status.value}")


if __name__ == "__main__":
    run_demo()
