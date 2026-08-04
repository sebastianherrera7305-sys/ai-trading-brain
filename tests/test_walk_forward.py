from datetime import datetime, timedelta

from trading_brain.data_loader import load_candles_from_csv
from trading_brain.market_structure import Candle
from trading_brain.scoring import Tier
from trading_brain.walk_forward import (
    _add_years,
    _reindex_no_timestamp,
    build_grid,
    optimize_fold,
    walk_forward,
)

# Same synthetic bullish-then-bearish series used by backtest.run_demo() and
# test_broker_engine_runner.py -- reusing it here checks the walk-forward
# harness wires into the already-validated run_backtest() correctly, not a
# second hand-rolled scenario whose behavior nobody has checked before.
_RAW = [
    (100, 101, 99, 100), (100, 105, 99.5, 104), (104, 104.5, 100.5, 101),
    (101, 102, 99, 99.5), (99.5, 103, 99.2, 102), (102, 109, 101.5, 108),
    (108, 108.5, 103, 104), (104, 105, 100.20, 101), (101, 101.5, 100.9, 101.2),
    (101.2, 101.3, 100.25, 101), (101, 101.5, 100.9, 101.2), (101.2, 101.5, 99.5, 101.3),
    (101.3, 112, 101, 110),
    (110, 113, 108, 112),
    (112, 112.5, 107.5, 108.2),
    (108.2, 108.5, 107.9, 108.1),
    (108.1, 130, 108, 129),
    (129, 130, 108, 128),
    (128, 128.5, 126, 127), (127, 127.5, 120.20, 121),
    (121, 121.5, 120.60, 121.2), (121.2, 121.3, 120.25, 121), (121, 121.5, 120.60, 121.2),
    (121.2, 121.5, 118, 121.3),
    (121.3, 132, 121, 130),
    (130, 133, 128, 132),
    (132, 132.5, 127.5, 128.2),
    (128.2, 128.5, 127.9, 128.1),
    (128.1, 128.5, 108, 110),
]


def _dated_candles(start: datetime, days_step: int = 1):
    return [
        Candle(index=i, open=o, high=h, low=l, close=c, timestamp=start + timedelta(days=i * days_step))
        for i, (o, h, l, c) in enumerate(_RAW)
    ]


def test_add_years_handles_leap_day():
    leap_day = _add_years(datetime(2020, 2, 29).date(), 1)
    assert leap_day == datetime(2021, 2, 28).date()


def test_add_years_normal_case():
    assert _add_years(datetime(2020, 1, 15).date(), 3) == datetime(2023, 1, 15).date()


def test_reindex_no_timestamp_strips_timestamp_and_fixes_index():
    candles = _dated_candles(datetime(2020, 1, 1))
    sliced = candles[5:10]  # original indices 5..9, timestamps still real
    reindexed = _reindex_no_timestamp(sliced)

    assert [c.index for c in reindexed] == list(range(len(sliced)))
    assert all(c.timestamp is None for c in reindexed)
    # OHLC values must survive the re-stamp untouched
    assert [c.close for c in reindexed] == [c.close for c in sliced]


def test_build_grid_is_nine_combos_of_three_rr_by_three_tier():
    grid = build_grid()
    assert len(grid) == 9
    assert set(rr for rr, _ in grid) == {1.5, 2.0, 2.5}
    assert set(tier for _, tier in grid) == {Tier.S, Tier.A, Tier.B}


def test_optimize_fold_returns_none_when_no_combo_meets_min_trades():
    # Two candles can never produce enough closed trades to clear
    # MIN_TRAIN_TRADES under any grid combo.
    candles = _dated_candles(datetime(2020, 1, 1))[:2]
    grid = build_grid()
    assert optimize_fold(candles, grid, liquidity_tolerance=0.1) is None


def test_walk_forward_returns_empty_list_for_all_undated_candles():
    candles = [
        Candle(index=i, open=o, high=h, low=l, close=c, timestamp=None)
        for i, (o, h, l, c) in enumerate(_RAW)
    ]
    assert walk_forward(candles, liquidity_tolerance=0.1) == []


def test_walk_forward_returns_empty_list_when_history_shorter_than_train_plus_test():
    # ~30 days of history, default train=3y/test=1y -- window can never close.
    candles = _dated_candles(datetime(2020, 1, 1))
    assert walk_forward(candles, liquidity_tolerance=0.1) == []


def test_walk_forward_fold_dates_are_contiguous_and_non_overlapping():
    # Real 10-year gold data, same file run_walk_forward.py uses -- the
    # tiny synthetic series above never fires a setup under the default
    # BacktestConfig (it was hand-tuned in other tests with a much shorter
    # swing/displacement lookback), so this is the only fixture in this
    # file that actually exercises optimize_fold picking a real winner.
    candles = load_candles_from_csv("data/GC_F_10y.csv")

    folds = walk_forward(candles, liquidity_tolerance=5.0, train_years=1, test_years=1, step_years=1)

    assert len(folds) >= 1
    for f in folds:
        assert f.train_end == f.test_start
        assert f.train_start < f.train_end < f.test_end
