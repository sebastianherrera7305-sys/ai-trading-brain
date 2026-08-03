"""Tests for the Liquidity module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.market_structure import Candle
from trading_brain.liquidity import (
    LiquidityLevel,
    LiquidityLevelType,
    Session,
    SessionCandle,
    detect_sweeps,
    find_equal_highs_lows,
    find_session_extremes,
)


def build(raw):
    return [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]


# Two equal highs ~110, then a wick to 113 that closes back at 107: a stop hunt.
STOP_HUNT = build([
    (100, 102, 99, 101),
    (101, 110, 100, 105),   # first equal high
    (105, 106, 102, 103),
    (103, 108, 101, 104),
    (104, 110, 103, 106),   # second equal high
    (106, 107, 104, 105),
    (105, 113, 105, 107),   # sweep + rejection
    (107, 108, 104, 105),
])


class TestEqualHighsLows(unittest.TestCase):
    def test_finds_the_equal_high_pair(self):
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        eq_highs = [l for l in levels if l.level_type is LiquidityLevelType.EQUAL_HIGHS]
        pair = [l for l in eq_highs if l.formed_at_indices == [1, 4]]
        self.assertEqual(len(pair), 1)
        self.assertAlmostEqual(pair[0].price, 110.0)

    def test_single_touch_is_not_liquidity(self):
        candles = build([(100, 105, 99, 101), (101, 120, 100, 110), (110, 130, 109, 120)])
        self.assertEqual(find_equal_highs_lows(candles, tolerance=0.5), [])

    def test_tolerance_does_not_chain(self):
        # 110.0 / 110.4 / 110.8 at tolerance 0.5: the first two group, the third
        # is left out rather than dragging the level upward.
        candles = build([
            (100, 110.0, 90, 100),
            (100, 110.4, 91, 100),
            (100, 110.8, 92, 100),
        ])
        highs = [l for l in find_equal_highs_lows(candles, tolerance=0.5)
                 if l.level_type is LiquidityLevelType.EQUAL_HIGHS]
        self.assertEqual([l.formed_at_indices for l in highs], [[0, 1]])

    def test_candle_belongs_to_one_level_only(self):
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        for level_type in (LiquidityLevelType.EQUAL_HIGHS, LiquidityLevelType.EQUAL_LOWS):
            seen = [i for l in levels if l.level_type is level_type for i in l.formed_at_indices]
            self.assertEqual(len(seen), len(set(seen)))

    def test_empty_input(self):
        self.assertEqual(find_equal_highs_lows([], tolerance=0.5), [])


class TestKnownFrom(unittest.TestCase):
    def test_level_is_tradable_from_the_second_touch(self):
        level = LiquidityLevel(LiquidityLevelType.EQUAL_HIGHS, 110.0, [1, 4])
        self.assertEqual(level.known_from, 5)

    def test_a_later_touch_does_not_delay_the_level(self):
        # The third touch at idx 9 must not reach back and suppress the level
        # between idx 5 and 9, where it was already valid liquidity.
        level = LiquidityLevel(LiquidityLevelType.EQUAL_HIGHS, 110.0, [1, 4, 9])
        self.assertEqual(level.known_from, 5)

    def test_single_index_level(self):
        level = LiquidityLevel(LiquidityLevelType.SESSION_HIGH, 110.0, [3])
        self.assertEqual(level.known_from, 4)

    def test_explicit_known_from_is_respected(self):
        level = LiquidityLevel(LiquidityLevelType.EQUAL_HIGHS, 110.0, [1, 4], known_from=99)
        self.assertEqual(level.known_from, 99)


class TestSessionExtremes(unittest.TestCase):
    def test_high_and_low_per_session_block(self):
        candles = STOP_HUNT
        tagged = ([SessionCandle(c, Session.LONDON) for c in candles[:4]]
                  + [SessionCandle(c, Session.NEW_YORK) for c in candles[4:]])
        levels = find_session_extremes(tagged)
        self.assertEqual(
            [(l.level_type, l.price, l.formed_at_indices) for l in levels],
            [
                (LiquidityLevelType.SESSION_HIGH, 110, [1]),
                (LiquidityLevelType.SESSION_LOW, 99, [0]),
                (LiquidityLevelType.SESSION_HIGH, 113, [6]),
                (LiquidityLevelType.SESSION_LOW, 103, [4]),
            ],
        )

    def test_off_session_blocks_are_skipped(self):
        candles = build([(100, 105, 95, 100)] * 4)
        tagged = ([SessionCandle(c, Session.OFF_SESSION) for c in candles[:2]]
                  + [SessionCandle(c, Session.LONDON) for c in candles[2:]])
        levels = find_session_extremes(tagged)
        self.assertEqual([l.level_type for l in levels],
                         [LiquidityLevelType.SESSION_HIGH, LiquidityLevelType.SESSION_LOW])

    def test_same_session_after_a_gap_is_a_separate_block(self):
        candles = build([
            (100, 105, 95, 100),   # london
            (100, 101, 99, 100),   # off
            (100, 120, 90, 100),   # london again -> new block
        ])
        tagged = [
            SessionCandle(candles[0], Session.LONDON),
            SessionCandle(candles[1], Session.OFF_SESSION),
            SessionCandle(candles[2], Session.LONDON),
        ]
        highs = [l.price for l in find_session_extremes(tagged)
                 if l.level_type is LiquidityLevelType.SESSION_HIGH]
        self.assertEqual(highs, [105, 120])

    def test_empty_input(self):
        self.assertEqual(find_session_extremes([]), [])

    def test_session_extreme_cannot_be_swept_from_inside_its_own_block(self):
        # No candle in a block can exceed that block's own high.
        candles = STOP_HUNT
        tagged = [SessionCandle(c, Session.LONDON) for c in candles]
        levels = find_session_extremes(tagged)
        self.assertEqual(detect_sweeps(candles, levels), [])


class TestSweeps(unittest.TestCase):
    def test_wick_through_then_close_back_is_a_rejected_sweep(self):
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        sweeps = detect_sweeps(STOP_HUNT, levels)
        self.assertEqual(len(sweeps), 1)
        sweep = sweeps[0]
        self.assertEqual(sweep.candle_index, 6)
        self.assertEqual(sweep.level.level_type, LiquidityLevelType.EQUAL_HIGHS)
        self.assertTrue(sweep.rejected)

    def test_close_beyond_the_level_is_a_break_not_a_rejection(self):
        candles = build([
            (100, 110, 99, 105),    # equal high
            (105, 106, 102, 103),
            (103, 110, 101, 104),   # equal high
            (104, 115, 103, 114),   # closes ABOVE 110 -> break
        ])
        levels = [l for l in find_equal_highs_lows(candles, tolerance=0.5)
                  if l.level_type is LiquidityLevelType.EQUAL_HIGHS]
        sweeps = detect_sweeps(candles, levels)
        self.assertEqual(len(sweeps), 1)
        self.assertEqual(sweeps[0].candle_index, 3)
        self.assertFalse(sweeps[0].rejected)

    def test_low_side_sweep(self):
        candles = build([
            (100, 105, 90, 100),    # equal low
            (100, 106, 95, 102),
            (102, 105, 90, 100),    # equal low
            (100, 104, 85, 99),     # wicks below 90, closes back above -> rejected sweep
        ])
        levels = [l for l in find_equal_highs_lows(candles, tolerance=0.5)
                  if l.level_type is LiquidityLevelType.EQUAL_LOWS]
        sweeps = detect_sweeps(candles, levels)
        self.assertEqual(len(sweeps), 1)
        self.assertEqual(sweeps[0].candle_index, 3)
        self.assertTrue(sweeps[0].rejected)

    def test_level_cannot_be_swept_before_it_exists(self):
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        sweeps = detect_sweeps(STOP_HUNT, levels)
        for sweep in sweeps:
            self.assertGreaterEqual(sweep.candle_index, sweep.level.known_from)
            self.assertGreater(sweep.candle_index, max(sweep.level.formed_at_indices[:2]))

    def test_a_level_is_consumed_by_its_first_sweep(self):
        candles = build([
            (100, 110, 99, 105),
            (105, 106, 102, 103),
            (103, 110, 101, 104),
            (104, 113, 103, 106),   # first sweep
            (106, 114, 104, 107),   # would sweep again, but the level is used up
        ])
        levels = [l for l in find_equal_highs_lows(candles, tolerance=0.5)
                  if l.level_type is LiquidityLevelType.EQUAL_HIGHS]
        sweeps = detect_sweeps(candles, levels)
        self.assertEqual([s.candle_index for s in sweeps], [3])
        self.assertTrue(levels[0].swept)
        self.assertEqual(levels[0].swept_at_index, 3)

    def test_rerunning_on_used_levels_yields_nothing(self):
        # Documented consequence of levels carrying their own swept state.
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        self.assertEqual(len(detect_sweeps(STOP_HUNT, levels)), 1)
        self.assertEqual(detect_sweeps(STOP_HUNT, levels), [])

    def test_no_levels_means_no_sweeps(self):
        self.assertEqual(detect_sweeps(STOP_HUNT, []), [])

    def test_sweeps_are_ordered_by_candle(self):
        levels = find_equal_highs_lows(STOP_HUNT, tolerance=0.5)
        sweeps = detect_sweeps(STOP_HUNT, levels)
        self.assertEqual([s.candle_index for s in sweeps],
                         sorted(s.candle_index for s in sweeps))


if __name__ == "__main__":
    unittest.main()
