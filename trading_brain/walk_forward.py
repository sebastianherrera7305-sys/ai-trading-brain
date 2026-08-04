"""
Walk-forward — AI Trading Brain, Phase 3

Same idea as trading-bot's bot/backtest/walk_forward.py: choosing
parameters by looking at the whole history and then reporting
performance on that SAME history mixes selection with judgment. This
always separates the window where parameters are chosen (train) from
the window where they're judged (test) -- only the out-of-sample result
is ever reported as "how good is this."

Why this lives here and not in trading-bot, even though it runs against
the same 10-year CSVs trading-bot already had: the FVG/market-structure
strategy needs a resting limit order, an explicit take-profit, and a
close-based invalidation check that fires before the stop -- none of
which trading-bot's Backtester models (market-order entries and a fixed
percentage stop-loss only). Porting the STRATEGY into trading-bot's
simpler order model would have quietly turned it into a different,
unvalidated strategy wearing the same name. run_backtest() here is
where the real order model already exists and is already tested (218
tests, see tests/).
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

from .backtest import BacktestConfig, run_backtest
from .market_structure import Candle
from .scoring import Tier

# Descarta combinaciones que cerraron muy pocos trades en el tramo de
# entrenamiento -- su total_r no es confiable, es ruido con forma de numero.
MIN_TRAIN_TRADES = 3

_TIER_RANK = {Tier.REJECT: 0, Tier.B: 1, Tier.A: 2, Tier.S: 3}


@dataclass
class FoldResult:
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    chosen_target_rr: float
    chosen_min_tier: Tier
    train_total_r: float
    train_trades: int
    test_total_r: float
    test_trades: int
    test_win_rate: Optional[float]
    test_max_drawdown_r: float


def _add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)  # 29 feb sin destino bisiesto


def _reindex_no_timestamp(candles: List[Candle]) -> List[Candle]:
    """run_backtest expects Candle.index to be a clean 0..n-1 sequence
    matching list position -- slicing by date breaks that, so re-stamp
    the index before handing a slice to run_backtest. Timestamp is
    stripped to None deliberately, matching every backtest already run
    on this project's real data: session-time gating checks intraday
    windows that a daily bar's timestamp never falls inside (see the
    honest-backtest work this walk-forward builds on), so a real
    timestamp here would silently start enforcing a rule this strategy
    has never been calibrated against."""
    return [
        Candle(index=i, open=c.open, high=c.high, low=c.low, close=c.close, timestamp=None)
        for i, c in enumerate(candles)
    ]


def build_grid() -> List[Tuple[float, Tier]]:
    """Modesta a proposito: 3 target_rr x 3 min_tier = 9 combinaciones por
    ventana. liquidity_tolerance NO se busca aqui -- es una escala de
    precio por instrumento ya calibrada (ver run_walk_forward.py), no un
    parametro de la estrategia en si."""
    target_rrs = [1.5, 2.0, 2.5]
    tiers = [Tier.S, Tier.A, Tier.B]
    return [(rr, tier) for rr in target_rrs for tier in tiers]


def _run_once(candles: List[Candle], target_rr: float, min_tier: Tier, liquidity_tolerance: float):
    config = BacktestConfig(
        liquidity_tolerance=liquidity_tolerance,
        target_rr=target_rr,
        min_tier=min_tier,
    )
    return run_backtest(_reindex_no_timestamp(candles), config)


def optimize_fold(candles: List[Candle], grid, liquidity_tolerance: float) -> Optional[tuple]:
    best = None
    for target_rr, min_tier in grid:
        result = _run_once(candles, target_rr, min_tier, liquidity_tolerance)
        trades = len(result.closed_trades)
        if trades < MIN_TRAIN_TRADES:
            continue
        total_r = result.total_r
        if best is None or total_r > best[0]:
            best = (total_r, target_rr, min_tier, trades)
    return best


def walk_forward(
    candles: List[Candle],
    liquidity_tolerance: float,
    train_years: int = 3,
    test_years: int = 1,
    step_years: int = 1,
) -> List[FoldResult]:
    dated = [c for c in candles if c.timestamp is not None]
    if not dated:
        return []
    dated.sort(key=lambda c: c.timestamp)
    grid = build_grid()
    end_date = dated[-1].timestamp.date()

    folds: List[FoldResult] = []
    train_start = dated[0].timestamp.date()
    while True:
        train_end = _add_years(train_start, train_years)
        test_end = _add_years(train_end, test_years)
        if test_end > end_date:
            break

        train_candles = [c for c in dated if train_start <= c.timestamp.date() < train_end]
        test_candles = [c for c in dated if train_end <= c.timestamp.date() < test_end]

        chosen = optimize_fold(train_candles, grid, liquidity_tolerance)
        if chosen is not None:
            train_total_r, target_rr, min_tier, train_trades = chosen
            test_result = _run_once(test_candles, target_rr, min_tier, liquidity_tolerance)
            folds.append(FoldResult(
                train_start=str(train_start), train_end=str(train_end),
                test_start=str(train_end), test_end=str(test_end),
                chosen_target_rr=target_rr, chosen_min_tier=min_tier,
                train_total_r=train_total_r, train_trades=train_trades,
                test_total_r=test_result.total_r,
                test_trades=len(test_result.closed_trades),
                test_win_rate=test_result.win_rate,
                test_max_drawdown_r=test_result.max_drawdown_r,
            ))

        train_start = _add_years(train_start, step_years)

    return folds
