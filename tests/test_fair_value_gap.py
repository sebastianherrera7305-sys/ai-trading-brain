"""Tests for the Fair Value Gap module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.market_structure import Candle, Trend
from trading_brain.displacement import Direction, detect_displacement
from trading_brain.liquidity import LiquidityLevel, LiquidityLevelType, LiquiditySweep
from trading_brain.fair_value_gap import (
    MitigationStatus,
    update_mitigation,
    validate_fvgs,
)


def build(raw):
    return [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]


# Same shape as displacement's canonical example: bullish displacement at idx 6,
# gap zone [101.0, 110.5].
CANDLES = build([
    (100, 101, 99, 100),
    (100, 101, 99, 100),
    (100, 101.5, 99, 100.5),
    (100.5, 101, 99.5, 100),
    (100, 101, 99, 100.2),
    (100.2, 101, 99.5, 100),
    (100, 112, 100, 111),      # displacement candle
    (111, 113, 110.5, 112.5),
    (112.5, 115, 112, 114),
    (114, 114, 105, 106),      # dips into the gap zone but not below 101 -> partial
])


def displacement_events():
    return detect_displacement(CANDLES, lookback=5, strength_multiplier=1.5)


def rejected_sweep(at_index=5):
    level = LiquidityLevel(LiquidityLevelType.EQUAL_LOWS, 99.5, [1, 3])
    return LiquiditySweep(candle_index=at_index, level=level, rejected=True)


class TestValidateFvgs(unittest.TestCase):
    def test_all_four_conditions_met_validates(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        self.assertEqual(len(fvgs), 1)
        fvg = fvgs[0]
        self.assertEqual(fvg.origin_displacement_index, 6)
        self.assertEqual(fvg.direction, Direction.BULLISH)
        self.assertTrue(fvg.aligned_with_trend)
        self.assertTrue(fvg.followed_sweep)
        self.assertEqual(fvg.preceding_sweep_index, 5)

    def test_sweep_on_the_wrong_side_does_not_count(self):
        # Regression: a bullish reversal is fueled by a swept LOW (sell-side
        # liquidity), not a swept HIGH. A recent, rejected sweep of the WRONG
        # side must not satisfy "followed_sweep" just because it was rejected
        # and recent -- side matters, not just those two things.
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        wrong_side_level = LiquidityLevel(LiquidityLevelType.EQUAL_HIGHS, 101.0, [1, 4])
        wrong_side_sweep = LiquiditySweep(candle_index=5, level=wrong_side_level, rejected=True)
        fvgs = validate_fvgs(events, [wrong_side_sweep], trend_at)
        self.assertEqual(fvgs, [])

    def test_bearish_displacement_wants_a_swept_high(self):
        # Mirror of the above: a bearish displacement must pair with a swept
        # HIGH, not a swept low.
        candles = build([
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101.5, 99, 100.5),
            (100.5, 101, 99.5, 100),
            (100, 100.2, 99, 99.5),   # left neighbor: high=100.2
            (105, 106, 90, 91),       # bearish displacement candle
            (85, 89, 80, 88),         # right neighbor: high=89 < 99 -> bearish gap
        ])
        events = detect_displacement(candles, lookback=4, strength_multiplier=1.5)
        trend_at = {e.candle_index: Trend.BEARISH for e in events}

        low_side_level = LiquidityLevel(LiquidityLevelType.EQUAL_LOWS, 99.0, [1, 3])
        low_side_sweep = LiquiditySweep(candle_index=4, level=low_side_level, rejected=True)
        self.assertEqual(validate_fvgs(events, [low_side_sweep], trend_at), [])

        high_side_level = LiquidityLevel(LiquidityLevelType.EQUAL_HIGHS, 101.0, [1, 3])
        high_side_sweep = LiquiditySweep(candle_index=4, level=high_side_level, rejected=True)
        fvgs = validate_fvgs(events, [high_side_sweep], trend_at)
        self.assertEqual(len(fvgs), 1)
        self.assertEqual(fvgs[0].direction, Direction.BEARISH)

    def test_misaligned_trend_is_rejected(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BEARISH for e in events}  # bullish event, bearish trend
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        self.assertEqual(fvgs, [])

    def test_missing_trend_defaults_to_range_and_is_rejected(self):
        events = displacement_events()
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at={})
        self.assertEqual(fvgs, [])

    def test_no_preceding_sweep_is_rejected(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [], trend_at)
        self.assertEqual(fvgs, [])

    def test_unrejected_sweep_does_not_count(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        level = LiquidityLevel(LiquidityLevelType.EQUAL_LOWS, 99.5, [1, 3])
        unrejected = LiquiditySweep(candle_index=5, level=level, rejected=False)
        fvgs = validate_fvgs(events, [unrejected], trend_at)
        self.assertEqual(fvgs, [])

    def test_sweep_too_far_back_does_not_count(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep(at_index=5)], trend_at, sweep_lookback=0)
        self.assertEqual(fvgs, [])

    def test_sweep_after_displacement_does_not_count(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep(at_index=7)], trend_at)
        self.assertEqual(fvgs, [])

    def test_no_events_means_no_fvgs(self):
        self.assertEqual(validate_fvgs([], [], {}), [])


class TestUpdateMitigation(unittest.TestCase):
    def test_partial_fill_when_price_dips_into_the_zone(self):
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        update_mitigation(fvgs, CANDLES)
        self.assertEqual(fvgs[0].status, MitigationStatus.PARTIALLY_FILLED)
        self.assertIsNone(fvgs[0].mitigated_at_index)

    def test_full_close_below_gap_low_mitigates(self):
        extended = CANDLES + [Candle(10, 106, 107, 95, 96)]  # trades through 101 -> full close
        events = detect_displacement(extended, lookback=5, strength_multiplier=1.5)
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        update_mitigation(fvgs, extended)
        self.assertEqual(fvgs[0].status, MitigationStatus.MITIGATED)
        self.assertEqual(fvgs[0].mitigated_at_index, 10)

    def test_candles_at_or_before_origin_are_never_considered(self):
        # Regression sanity check: mitigation must not look at the displacement
        # candle itself or anything before it.
        events = displacement_events()
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        update_mitigation(fvgs, CANDLES)
        self.assertNotEqual(fvgs[0].mitigated_at_index, fvgs[0].origin_displacement_index)

    def test_mitigated_status_is_terminal(self):
        extended = CANDLES + [
            Candle(10, 106, 107, 95, 96),    # fully mitigates
            Candle(11, 96, 120, 96, 119),    # would "un-mitigate" if status weren't terminal
        ]
        events = detect_displacement(extended, lookback=5, strength_multiplier=1.5)
        trend_at = {e.candle_index: Trend.BULLISH for e in events}
        fvgs = validate_fvgs(events, [rejected_sweep()], trend_at)
        update_mitigation(fvgs, extended)
        self.assertEqual(fvgs[0].status, MitigationStatus.MITIGATED)
        self.assertEqual(fvgs[0].mitigated_at_index, 10)

    def test_no_fvgs_is_a_no_op(self):
        update_mitigation([], CANDLES)  # must not raise


if __name__ == "__main__":
    unittest.main()
