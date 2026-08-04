"""Tests for the Displacement module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.market_structure import Candle
from trading_brain.displacement import (
    Direction,
    detect_displacement,
    find_imbalance,
    rolling_average_range,
)


def build(raw):
    return [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]


# Quiet chop, then one big aggressive bullish candle leaving a real gap
# between its neighbors — the README's canonical displacement example.
CHOP_THEN_DISPLACEMENT = build([
    (100, 101, 99, 100),
    (100, 101, 99, 100),
    (100, 101.5, 99, 100.5),
    (100.5, 101, 99.5, 100),
    (100, 101, 99, 100.2),
    (100.2, 101, 99.5, 100),   # candle 5: left neighbor, high=101
    (100, 112, 100, 111),      # candle 6: displacement candle
    (111, 113, 110.5, 112.5),  # candle 7: right neighbor, low=110.5 > 101 -> real gap
    (112.5, 113, 112, 112.8),
])


class TestRollingAverageRange(unittest.TestCase):
    def test_none_without_enough_history(self):
        candles = build([(100, 101, 99, 100)] * 5)
        self.assertIsNone(rolling_average_range(candles, 3, lookback=10))

    def test_averages_the_window_before_index(self):
        candles = build([(100, 105, 95, 100), (100, 103, 97, 100), (100, 110, 90, 100)])
        # window is candles[0:2]: ranges 10 and 6 -> average 8. Candle 2 itself excluded.
        self.assertAlmostEqual(rolling_average_range(candles, 2, lookback=2), 8.0)

    def test_index_zero_is_never_computable(self):
        candles = build([(100, 101, 99, 100)])
        self.assertIsNone(rolling_average_range(candles, 0, lookback=1))


class TestFindImbalance(unittest.TestCase):
    def test_bullish_gap(self):
        candles = build([(100, 100.2, 99, 100), (100, 112, 100, 111), (111, 113, 110.5, 112.5)])
        gap = find_imbalance(candles, 1)
        self.assertEqual(gap.direction, Direction.BULLISH)
        self.assertEqual((gap.gap_low, gap.gap_high), (100.2, 110.5))

    def test_bearish_gap(self):
        candles = build([(100, 105, 103, 104), (105, 106, 90, 92), (90, 91, 88, 89)])
        gap = find_imbalance(candles, 1)
        self.assertEqual(gap.direction, Direction.BEARISH)

    def test_no_gap_when_neighbors_overlap(self):
        candles = build([(100, 102, 98, 100), (100, 103, 97, 101), (100, 102, 98, 100)])
        self.assertIsNone(find_imbalance(candles, 1))

    def test_none_at_the_series_edges(self):
        candles = build([(100, 101, 99, 100), (100, 101, 99, 100)])
        self.assertIsNone(find_imbalance(candles, 0))
        self.assertIsNone(find_imbalance(candles, 1))


class TestDetectDisplacement(unittest.TestCase):
    def test_finds_the_canonical_displacement(self):
        events = detect_displacement(CHOP_THEN_DISPLACEMENT, lookback=5, strength_multiplier=1.5)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.candle_index, 6)
        self.assertEqual(event.direction, Direction.BULLISH)

    def test_weak_candles_are_ignored(self):
        # Same shape but the "big" candle is barely bigger than baseline.
        candles = build([
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100),
            (100, 101, 99, 100), (100, 101, 99, 100),
            (100, 101.2, 99.2, 100.5),  # only marginally larger than baseline
            (100.5, 101, 99.5, 100.2),
        ])
        events = detect_displacement(candles, lookback=5, strength_multiplier=1.5)
        self.assertEqual(events, [])

    def test_aggressive_without_imbalance_does_not_qualify(self):
        # A big candle whose neighbors still overlap it -> no inefficiency created.
        candles = build([
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101, 99, 100),
            (100, 101, 99, 100), (100, 101, 99, 100),
            (100, 112, 100, 111),        # big range, but...
            (100.5, 101, 99.5, 100.2),   # ...right neighbor overlaps left neighbor's high
        ])
        events = detect_displacement(candles, lookback=5, strength_multiplier=1.5)
        self.assertEqual(events, [])

    def test_direction_comes_from_the_gap_not_the_candle_body(self):
        # Displacement candle closes red (open > close) but still gaps price UP
        # past its predecessor -- a hard intracandle reversal. The gap it leaves
        # is bullish, and that must be what the event reports.
        candles = build([
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101.5, 99, 100.5),
            (100.5, 101, 99.5, 100),
            (100, 100.2, 99, 99.5),   # left neighbor: high=100.2
            (105, 120, 95, 98),       # displacement candle: bearish body, huge range
            (110, 115, 108, 112),     # right neighbor: low=108 > 100.2 -> bullish gap
        ])
        events = detect_displacement(candles, lookback=4, strength_multiplier=1.5)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, Direction.BULLISH)
        self.assertEqual(events[0].imbalance.direction, Direction.BULLISH)

    def test_confirmed_at_is_one_candle_after_the_displacement_candle(self):
        events = detect_displacement(CHOP_THEN_DISPLACEMENT, lookback=5, strength_multiplier=1.5)
        self.assertEqual(events[0].confirmed_at, events[0].candle_index + 1)

    def test_no_look_ahead_event_is_absent_before_its_confirming_candle(self):
        # Truncate the series to end exactly on the displacement candle. At that
        # point in a live walk-forward, the confirming neighbor hasn't printed yet,
        # so the event must not appear.
        truncated = CHOP_THEN_DISPLACEMENT[:7]  # ends at candle 6, the displacement candle
        self.assertEqual(detect_displacement(truncated, lookback=5, strength_multiplier=1.5), [])

        with_confirmation = CHOP_THEN_DISPLACEMENT[:8]  # candle 7 now exists
        events = detect_displacement(with_confirmation, lookback=5, strength_multiplier=1.5)
        self.assertEqual([e.candle_index for e in events], [6])

    def test_last_candle_cannot_be_a_displacement(self):
        # No candle after it exists, so no imbalance can ever be confirmed.
        events = detect_displacement(CHOP_THEN_DISPLACEMENT, lookback=5, strength_multiplier=1.5)
        self.assertNotIn(len(CHOP_THEN_DISPLACEMENT) - 1, [e.candle_index for e in events])

    def test_empty_input(self):
        self.assertEqual(detect_displacement([], lookback=5), [])

    def test_zero_baseline_is_skipped_not_a_crash(self):
        flat = build([(100, 100, 100, 100)] * 6 + [(100, 110, 90, 105)])
        # Should not raise ZeroDivisionError even though every prior candle has zero range.
        detect_displacement(flat, lookback=5, strength_multiplier=1.5)

    def test_candle_index_is_absolute_not_list_position(self):
        # Regression: detect_displacement used to build DisplacementEvent from
        # enumerate()'s LOCAL loop position instead of candle.index. That was
        # silently correct only because every caller always passed a slice
        # starting at absolute index 0 -- true in every other test here, but
        # false the moment a windowed/offset slice is passed (as backtest.py's
        # recompute_window now does for performance). Build the same shape as
        # CHOP_THEN_DISPLACEMENT but with every Candle's .index offset by 100,
        # as if this were a slice out of the middle of a longer series.
        offset_raw = [
            (100, 101, 99, 100), (100, 101, 99, 100), (100, 101.5, 99, 100.5),
            (100.5, 101, 99.5, 100), (100, 101, 99, 100.2), (100.2, 101, 99.5, 100),
            (100, 112, 100, 111), (111, 113, 110.5, 112.5), (112.5, 113, 112, 112.8),
        ]
        offset_candles = [Candle(100 + i, o, h, l, c) for i, (o, h, l, c) in enumerate(offset_raw)]
        events = detect_displacement(offset_candles, lookback=5, strength_multiplier=1.5)
        self.assertEqual(len(events), 1)
        # The displacement candle is at local position 6, absolute index 106.
        self.assertEqual(events[0].candle_index, 106)
        self.assertEqual(events[0].confirmed_at, 107)
        self.assertEqual(events[0].imbalance.left_index, 105)
        self.assertEqual(events[0].imbalance.right_index, 107)


if __name__ == "__main__":
    unittest.main()
