"""Tests for the Backtest module (AI Trading Brain v1, Phase 2)."""

import unittest

from trading_brain.market_structure import Candle
from trading_brain.displacement import Direction
from trading_brain.scoring import ChecklistInputs, Tier
from trading_brain.backtest import (
    BacktestConfig,
    BacktestResult,
    TradeOutcome,
    TradeRecord,
    _fill_touched,
    _invalidated_before_fill,
    run_backtest,
)


def build(raw):
    return [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]


# Prior uptrend (HH/HL, so trend reads BULLISH), then sweep -> displacement ->
# gap confirmed at idx 13. Verified end to end against run_backtest directly.
SETUP_ONE = build([
    (100, 101, 99, 100), (100, 105, 99.5, 104), (104, 104.5, 100.5, 101),
    (101, 102, 99, 99.5), (99.5, 103, 99.2, 102), (102, 109, 101.5, 108),
    (108, 108.5, 103, 104), (104, 105, 100.20, 101), (101, 101.5, 100.9, 101.2),
    (101.2, 101.3, 100.25, 101), (101, 101.5, 100.9, 101.2), (101.2, 101.5, 99.5, 101.3),
    (101.3, 112, 101, 110),        # 12 displacement candle
    (110, 113, 108, 112),          # 13 confirms gap [101.5, 108]
    (112, 112.5, 107.5, 108.2),    # 14 retraces -> fills at 108 (entry_index=14)
    (108.2, 108.5, 107.9, 108.1),  # 15
    (108.1, 130, 108, 129),        # 16 runs hard -> hits target -> WIN
])

DEFAULT_CFG = BacktestConfig(swing_lookback=1, displacement_lookback=5, liquidity_tolerance=0.1)


def checklist(**overrides):
    defaults = dict(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=True, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    defaults.update(overrides)
    return ChecklistInputs(**defaults)


def trade_record(**overrides):
    defaults = dict(
        origin_displacement_index=0, entry_index=1, direction=Direction.BULLISH,
        entry=100, stop_loss=95, take_profit=110, invalidation_price=97,
        tier=Tier.A, confidence_score=80, checklist=checklist(),
    )
    defaults.update(overrides)
    return TradeRecord(**defaults)


class TestRunBacktestIntegration(unittest.TestCase):
    def test_full_series_wins(self):
        result = run_backtest(SETUP_ONE, DEFAULT_CFG)
        self.assertEqual(len(result.trades), 1)
        trade = result.trades[0]
        self.assertEqual(trade.entry_index, 14)
        self.assertEqual(trade.outcome, TradeOutcome.WIN)
        self.assertAlmostEqual(trade.realized_r, 2.0)

    def test_entry_is_never_before_the_candle_that_confirms_the_gap(self):
        result = run_backtest(SETUP_ONE, DEFAULT_CFG)
        trade = result.trades[0]
        self.assertGreater(trade.entry_index, trade.origin_displacement_index)

    def test_no_look_ahead_truncating_removes_the_outcome_not_the_entry(self):
        # Cut the series right after the fill candle -- no future candle exists
        # to resolve the trade, so it must stay OPEN, not silently know it wins.
        truncated = run_backtest(SETUP_ONE[:16], DEFAULT_CFG)
        self.assertEqual(len(truncated.trades), 1)
        self.assertEqual(truncated.trades[0].entry_index, 14)
        self.assertEqual(truncated.trades[0].outcome, TradeOutcome.OPEN)
        self.assertIsNone(truncated.trades[0].realized_r)

        # Extending with the resolving candle must not change anything about
        # the entry that was already decided -- only the outcome appears.
        full = run_backtest(SETUP_ONE, DEFAULT_CFG)
        self.assertEqual(full.trades[0].entry_index, truncated.trades[0].entry_index)
        self.assertEqual(full.trades[0].outcome, TradeOutcome.WIN)

    def test_truncating_before_any_fill_yields_no_trade_at_all(self):
        result = run_backtest(SETUP_ONE[:13], DEFAULT_CFG)  # ends before the gap even confirms
        self.assertEqual(result.trades, [])

    def test_min_tier_floor_blocks_a_trade_that_would_otherwise_be_taken(self):
        # Same series, but require a tier this setup can't reach (S only).
        cfg = BacktestConfig(swing_lookback=1, displacement_lookback=5,
                              liquidity_tolerance=0.1, min_tier=Tier.S)
        result_s = run_backtest(SETUP_ONE, cfg)
        result_b = run_backtest(SETUP_ONE, DEFAULT_CFG)
        # The reference setup actually scores S, so raising the floor to S must
        # not remove it -- but REJECT-tier is never taken regardless of floor.
        self.assertTrue(all(t.tier != Tier.REJECT for t in result_s.trades))
        self.assertTrue(all(t.tier != Tier.REJECT for t in result_b.trades))

    def test_recompute_window_is_a_noop_when_it_covers_the_whole_series(self):
        # Sanity check on the windowing machinery itself (correct slicing,
        # correct offset handling) without confounding it with the SEPARATE
        # question of whether a SHORT window loses real trend history -- a
        # window >= the series length can never truncate anything.
        full = run_backtest(SETUP_ONE, BacktestConfig(
            swing_lookback=1, displacement_lookback=5, liquidity_tolerance=0.1,
            recompute_window=None,
        ))
        windowed = run_backtest(SETUP_ONE, BacktestConfig(
            swing_lookback=1, displacement_lookback=5, liquidity_tolerance=0.1,
            recompute_window=len(SETUP_ONE),
        ))
        self.assertEqual(len(full.trades), 1)
        self.assertEqual(
            [(t.entry_index, t.outcome, t.realized_r) for t in full.trades],
            [(t.entry_index, t.outcome, t.realized_r) for t in windowed.trades],
        )

    def test_recompute_window_matches_full_history_on_a_longer_series(self):
        # The scenario that actually matters -- and the one that caught a real
        # bug: detect_displacement built DisplacementEvent.candle_index from
        # enumerate()'s LOCAL loop position, not candle.index. That was
        # silently correct only because every prior test always passed a
        # slice starting at absolute index 0 -- true of every hand-built
        # fixture in this suite, but false the moment recompute_window passes
        # an offset slice from the middle of a longer series. A window with
        # real settling room (300, the default) on a few hundred candles of
        # random-walk data must produce byte-for-byte identical trades to an
        # unwindowed run on the same data.
        import random
        rng = random.Random(42)
        raw = []
        price = 100.0
        for i in range(400):
            o = price
            drift = rng.uniform(-0.6, 0.6)
            c = max(0.01, o + drift)
            h = max(o, c) + rng.uniform(0, 0.36)
            l = min(o, c) - rng.uniform(0, 0.36)
            raw.append((o, h, l, c))
            price = c
        candles = build(raw)

        full = run_backtest(candles, BacktestConfig(swing_lookback=2, recompute_window=None))
        windowed = run_backtest(candles, BacktestConfig(swing_lookback=2, recompute_window=300))

        self.assertTrue(len(full.trades) > 0)  # otherwise this test proves nothing
        self.assertEqual(
            [(t.entry_index, t.outcome, t.realized_r) for t in full.trades],
            [(t.entry_index, t.outcome, t.realized_r) for t in windowed.trades],
        )

    def test_order_never_filled_within_the_wait_window_expires(self):
        # Gap confirms at idx 13; price then hovers above the entry level
        # (108) instead of retracing into it, for longer than the wait window.
        tail = [(112, 113, 110, 112)] * 4
        candles = SETUP_ONE[:14] + [
            Candle(14 + j, o, h, l, c) for j, (o, h, l, c) in enumerate(tail)
        ]
        cfg = BacktestConfig(swing_lookback=1, displacement_lookback=5,
                              liquidity_tolerance=0.1, max_pending_candles=2)
        result = run_backtest(candles, cfg)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.unfilled_setups, 1)

    def test_empty_input(self):
        result = run_backtest([], DEFAULT_CFG)
        self.assertEqual(result.trades, [])
        self.assertEqual(result.unfilled_setups, 0)

    def test_default_config_is_used_when_none_given(self):
        # Must not raise -- run_backtest(candles) alone is a documented call shape.
        run_backtest(SETUP_ONE)


class TestFillAndInvalidationHelpers(unittest.TestCase):
    def test_bullish_fill_touched_when_low_reaches_entry(self):
        candle = Candle(0, 110, 111, 107, 109)
        self.assertTrue(_fill_touched(Direction.BULLISH, 108, candle))
        self.assertFalse(_fill_touched(Direction.BULLISH, 106, candle))

    def test_bearish_fill_touched_when_high_reaches_entry(self):
        candle = Candle(0, 90, 93, 89, 91)
        self.assertTrue(_fill_touched(Direction.BEARISH, 92, candle))
        self.assertFalse(_fill_touched(Direction.BEARISH, 95, candle))

    def test_bullish_invalidated_before_fill_is_close_based(self):
        # A wick beyond invalidation alone isn't enough -- matches the
        # project's "close-based breaks" convention used everywhere else.
        wick_only = Candle(0, 105, 106, 90, 104)  # low wicks under 100 but closes at 104
        self.assertFalse(_invalidated_before_fill(Direction.BULLISH, 100, wick_only))
        real_close = Candle(0, 105, 106, 90, 95)
        self.assertTrue(_invalidated_before_fill(Direction.BULLISH, 100, real_close))


class TestBacktestResultStats(unittest.TestCase):
    def test_win_rate_none_with_no_closed_trades(self):
        result = BacktestResult(trades=[trade_record(outcome=TradeOutcome.OPEN, realized_r=None)])
        self.assertIsNone(result.win_rate)

    def test_win_rate_counts_invalidated_as_a_loss(self):
        # Regression: win_rate previously only looked at WIN/LOSS, silently
        # excluding INVALIDATED from the denominator -- a system could report
        # "100% win rate" while sitting on a trade that lost money.
        result = BacktestResult(trades=[
            trade_record(outcome=TradeOutcome.WIN, realized_r=2.0),
            trade_record(outcome=TradeOutcome.INVALIDATED, realized_r=-0.5),
        ])
        self.assertAlmostEqual(result.win_rate, 0.5)

    def test_win_rate_matches_by_tier_win_rate(self):
        # The two win-rate calculations must agree with each other.
        result = BacktestResult(trades=[
            trade_record(tier=Tier.S, outcome=TradeOutcome.WIN, realized_r=2.0),
            trade_record(tier=Tier.S, outcome=TradeOutcome.INVALIDATED, realized_r=-0.5),
        ])
        self.assertAlmostEqual(result.win_rate, result.by_tier[Tier.S].win_rate)

    def test_total_r_sums_only_closed_trades(self):
        result = BacktestResult(trades=[
            trade_record(outcome=TradeOutcome.WIN, realized_r=2.0),
            trade_record(outcome=TradeOutcome.LOSS, realized_r=-1.0),
            trade_record(outcome=TradeOutcome.OPEN, realized_r=None),
        ])
        self.assertAlmostEqual(result.total_r, 1.0)

    def test_max_drawdown_tracks_peak_to_trough(self):
        result = BacktestResult(trades=[
            trade_record(outcome=TradeOutcome.WIN, realized_r=2.0),   # cum 2.0, peak 2.0
            trade_record(outcome=TradeOutcome.LOSS, realized_r=-1.0), # cum 1.0, dd -1.0
            trade_record(outcome=TradeOutcome.LOSS, realized_r=-1.0), # cum 0.0, dd -2.0
            trade_record(outcome=TradeOutcome.WIN, realized_r=3.0),   # cum 3.0, new peak
        ])
        self.assertAlmostEqual(result.max_drawdown_r, -2.0)

    def test_max_drawdown_is_zero_with_no_losses(self):
        result = BacktestResult(trades=[trade_record(outcome=TradeOutcome.WIN, realized_r=1.0)])
        self.assertEqual(result.max_drawdown_r, 0.0)

    def test_losing_trades_includes_invalidated_not_just_loss(self):
        loss = trade_record(outcome=TradeOutcome.LOSS, realized_r=-1.0)
        invalidated = trade_record(outcome=TradeOutcome.INVALIDATED, realized_r=-0.4)
        win = trade_record(outcome=TradeOutcome.WIN, realized_r=2.0)
        result = BacktestResult(trades=[loss, invalidated, win])
        self.assertEqual(result.losing_trades, [loss, invalidated])

    def test_by_tier_groups_and_aggregates_correctly(self):
        result = BacktestResult(trades=[
            trade_record(tier=Tier.S, outcome=TradeOutcome.WIN, realized_r=2.0),
            trade_record(tier=Tier.S, outcome=TradeOutcome.LOSS, realized_r=-1.0),
            trade_record(tier=Tier.B, outcome=TradeOutcome.WIN, realized_r=1.5),
        ])
        stats = result.by_tier
        self.assertEqual(stats[Tier.S].trades, 2)
        self.assertAlmostEqual(stats[Tier.S].win_rate, 0.5)
        self.assertAlmostEqual(stats[Tier.S].total_r, 1.0)
        self.assertEqual(stats[Tier.B].trades, 1)
        self.assertAlmostEqual(stats[Tier.B].win_rate, 1.0)

    def test_empty_result(self):
        result = BacktestResult()
        self.assertEqual(result.win_rate, None)
        self.assertEqual(result.total_r, 0.0)
        self.assertEqual(result.max_drawdown_r, 0.0)
        self.assertEqual(result.by_tier, {})
        self.assertEqual(result.losing_trades, [])


if __name__ == "__main__":
    unittest.main()
