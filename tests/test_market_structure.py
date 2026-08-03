"""Tests for the Market Structure module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.market_structure import (
    Candle,
    StructureEvent,
    StructureLabel,
    SwingPoint,
    SwingType,
    Trend,
    classify_structure,
    detect_bos_and_choch,
    determine_trend,
    find_swing_points,
)


def build(raw):
    return [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]


UPTREND_THEN_REVERSAL = build([
    (100, 102, 99, 101),
    (101, 105, 100, 104),   # swing high
    (104, 104, 101, 102),
    (102, 103, 98, 99),     # swing low
    (99, 108, 99, 107),     # breaks prior high -> BOS
    (107, 109, 105, 106),   # swing high
    (106, 107, 102, 103),   # swing low (HL)
    (103, 115, 103, 114),   # another BOS
    (114, 114, 108, 109),
    (109, 110, 95, 96),     # breaks prior HL -> CHoCH
    (96, 97, 90, 91),
])


class TestSwingDetection(unittest.TestCase):
    def test_finds_expected_swings(self):
        swings = find_swing_points(UPTREND_THEN_REVERSAL, lookback=1)
        found = [(s.candle_index, s.swing_type, s.price) for s in swings]
        self.assertEqual(found, [
            (1, SwingType.HIGH, 105),
            (3, SwingType.LOW, 98),
            (5, SwingType.HIGH, 109),
            (6, SwingType.LOW, 102),
            (7, SwingType.HIGH, 115),
        ])

    def test_confirmation_lags_by_lookback(self):
        for lookback in (1, 2):
            for swing in find_swing_points(UPTREND_THEN_REVERSAL, lookback=lookback):
                self.assertEqual(swing.confirmed_at, swing.candle_index + lookback)

    def test_edges_are_never_swings(self):
        # The first and last `lookback` candles cannot be confirmed either side.
        swings = find_swing_points(UPTREND_THEN_REVERSAL, lookback=2)
        indices = [s.candle_index for s in swings]
        self.assertTrue(all(2 <= i <= len(UPTREND_THEN_REVERSAL) - 3 for i in indices))

    def test_flat_stretch_produces_no_swings(self):
        flat = build([(100, 100, 100, 100)] * 6)
        self.assertEqual(find_swing_points(flat, lookback=1), [])

    def test_one_candle_is_never_both_high_and_low(self):
        swings = find_swing_points(UPTREND_THEN_REVERSAL, lookback=1)
        highs = {s.candle_index for s in swings if s.swing_type == SwingType.HIGH}
        lows = {s.candle_index for s in swings if s.swing_type == SwingType.LOW}
        self.assertEqual(highs & lows, set())

    def test_too_few_candles(self):
        self.assertEqual(find_swing_points(build([(1, 2, 0, 1)]), lookback=2), [])


class TestClassification(unittest.TestCase):
    def test_labels_against_previous_swing_of_same_type(self):
        swings = classify_structure(find_swing_points(UPTREND_THEN_REVERSAL, lookback=1))
        labels = [s.label for s in swings]
        self.assertEqual(labels, [
            None,                    # first high, nothing to compare to
            None,                    # first low, nothing to compare to
            StructureLabel.HH,
            StructureLabel.HL,
            StructureLabel.HH,
        ])

    def test_lower_high_and_lower_low(self):
        swings = [
            SwingPoint(0, 110, SwingType.HIGH),
            SwingPoint(1, 100, SwingType.LOW),
            SwingPoint(2, 105, SwingType.HIGH),
            SwingPoint(3, 95, SwingType.LOW),
        ]
        labels = [s.label for s in classify_structure(swings)]
        self.assertEqual(labels, [None, None, StructureLabel.LH, StructureLabel.LL])


class TestTrend(unittest.TestCase):
    def test_range_when_not_enough_labels(self):
        self.assertEqual(determine_trend([]), Trend.RANGE)
        self.assertEqual(determine_trend([SwingPoint(0, 100, SwingType.HIGH)]), Trend.RANGE)

    def test_bullish(self):
        swings = classify_structure(find_swing_points(UPTREND_THEN_REVERSAL, lookback=1))
        self.assertEqual(determine_trend(swings), Trend.BULLISH)

    def test_bearish(self):
        swings = [
            SwingPoint(0, 110, SwingType.HIGH),
            SwingPoint(1, 100, SwingType.LOW),
            SwingPoint(2, 105, SwingType.HIGH),
            SwingPoint(3, 95, SwingType.LOW),
            SwingPoint(4, 101, SwingType.HIGH),
            SwingPoint(5, 90, SwingType.LOW),
        ]
        self.assertEqual(determine_trend(classify_structure(swings)), Trend.BEARISH)

    def test_two_labels_are_enough_to_call_a_trend(self):
        # HH + HL with nothing older still reads bullish, per the docstring.
        swings = [
            SwingPoint(0, 100, SwingType.HIGH),
            SwingPoint(1, 90, SwingType.LOW),
            SwingPoint(2, 110, SwingType.HIGH),   # HH
            SwingPoint(3, 95, SwingType.LOW),     # HL
        ]
        self.assertEqual(determine_trend(classify_structure(swings)), Trend.BULLISH)

    def test_mixed_labels_read_as_range(self):
        swings = [
            SwingPoint(0, 100, SwingType.HIGH),
            SwingPoint(1, 90, SwingType.LOW),
            SwingPoint(2, 110, SwingType.HIGH),   # HH
            SwingPoint(3, 85, SwingType.LOW),     # LL
            SwingPoint(4, 105, SwingType.HIGH),   # LH
            SwingPoint(5, 95, SwingType.LOW),     # HL
        ]
        self.assertEqual(determine_trend(classify_structure(swings)), Trend.RANGE)


class TestBosAndChoch(unittest.TestCase):
    def setUp(self):
        swings = classify_structure(find_swing_points(UPTREND_THEN_REVERSAL, lookback=1))
        self.signals = detect_bos_and_choch(UPTREND_THEN_REVERSAL, swings)

    def test_full_signal_sequence(self):
        actual = [(s.candle_index, s.event, s.trend_before, s.trend_after, s.broken_level)
                  for s in self.signals]
        self.assertEqual(actual, [
            (4, StructureEvent.BOS, Trend.RANGE, Trend.BULLISH, 105),
            (7, StructureEvent.BOS, Trend.BULLISH, Trend.BULLISH, 109),
            (9, StructureEvent.CHOCH, Trend.BULLISH, Trend.BEARISH, 102),
            (10, StructureEvent.BOS, Trend.BEARISH, Trend.BEARISH, 96),
        ])

    def test_choch_flips_the_trend(self):
        choch = [s for s in self.signals if s.event is StructureEvent.CHOCH]
        self.assertTrue(all(s.trend_before != s.trend_after for s in choch))

    def test_bos_never_flips_the_trend(self):
        bos = [s for s in self.signals if s.event is StructureEvent.BOS]
        for s in bos:
            self.assertIn(s.trend_before, (s.trend_after, Trend.RANGE))

    def test_no_look_ahead(self):
        # A break can only be reported once the level that was broken is knowable.
        for signal in self.signals:
            self.assertGreaterEqual(signal.candle_index, 1)
        # Truncating the series must not change the signals that already fired.
        swings = classify_structure(find_swing_points(UPTREND_THEN_REVERSAL[:8], lookback=1))
        partial = detect_bos_and_choch(UPTREND_THEN_REVERSAL[:8], swings)
        self.assertEqual([(s.candle_index, s.event) for s in partial],
                         [(s.candle_index, s.event) for s in self.signals[:len(partial)]])

    def test_no_signals_without_swings(self):
        self.assertEqual(detect_bos_and_choch(UPTREND_THEN_REVERSAL, []), [])

    def test_late_swing_does_not_resurrect_a_stale_level(self):
        # The swing high at idx 7 (115) confirms at idx 8, after the BOS at idx 7
        # already moved the live level. It must not be replaced by anything lower,
        # and must not re-trigger a break on a candle that never cleared it.
        breaks_after_bos = [s for s in self.signals if s.candle_index == 8]
        self.assertEqual(breaks_after_bos, [])


if __name__ == "__main__":
    unittest.main()
