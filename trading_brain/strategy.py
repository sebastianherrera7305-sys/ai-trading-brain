"""
Strategy Engine — AI Trading Brain, Phase 4

Phase 1-3 built exactly one strategy -- Smart Money Concepts (a validated
Fair Value Gap, fueled by a liquidity sweep, aligned with a BOS-confirmed
trend) -- with all of its candidate-search logic embedded directly inside
backtest.find_candidate_order(). That meant run_backtest() and LiveEngine
could only ever run that one strategy, and any second strategy (trend
following, breakout, mean reversion, order blocks, ...) would have had to
be bolted on by editing that function rather than added independently.

This module is a MECHANICAL extraction, not a rewrite: find_candidate_order,
_build_levels and _window moved here unchanged, behind a Strategy interface.
Verified by the full test suite staying green with identical results before
and after (same discipline as the earlier backtest/engine_runner split --
see backtest.py's own history). SmartMoneyConceptsStrategy below is the only
concrete strategy that exists; it is the reference implementation of the
interface, not a permanent single-strategy assumption. StrategyEngine is a
thin multi-strategy container -- today it holds one strategy and behaves
identically to calling that strategy directly, but run_backtest and
LiveEngine now depend on the Strategy interface, not on this one strategy's
internals, so a second strategy is an addition, not a rewrite.

What this does NOT do (be honest about what "strategy engine" doesn't mean
yet): no confluence voting across strategies, no market-regime gate deciding
which strategies are even allowed to run, no per-strategy independent
position sizing. StrategyEngine.find_candidate() returns the first
candidate any registered strategy produces -- correct for a single strategy,
a real design decision (not yet made) for more than one.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .config import BacktestConfig
from .displacement import Direction, detect_displacement
from .fair_value_gap import ValidatedFVG, validate_fvgs
from .liquidity import LiquiditySweep, detect_sweeps, find_equal_highs_lows
from .market_structure import (
    Candle,
    StructureEvent,
    Trend,
    classify_structure,
    detect_bos_and_choch,
    determine_trend,
    find_swing_points,
)
from .risk import TradePlan, validate_trade_risk
from .scoring import TIER_RANK, ChecklistInputs, Tier, score_setup
from .sessions import is_allowed_to_trade


@dataclass
class TradeCandidate:
    """What a Strategy hands back when it finds something worth a resting
    order: everything run_backtest/LiveEngine need to place and later judge
    the trade, strategy-agnostic on the outside (direction/entry/stop/
    target/invalidation/tier) even though today's only strategy fills
    origin_displacement_index and checklist with FVG-specific detail."""
    origin_displacement_index: int
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    invalidation_price: float
    tier: Tier
    confidence_score: int
    checklist: ChecklistInputs
    placed_at_index: int
    strategy_name: str = ""


class Strategy(ABC):
    name: str = "unnamed"

    @abstractmethod
    def find_candidate(
        self, candles: List[Candle], i: int, config: BacktestConfig, seen_origins: Set[int]
    ) -> Optional[TradeCandidate]:
        """Is there a new setup worth a resting order as of candle i, given
        neither an open trade nor a pending order right now? Mutates
        seen_origins in place (implementations should add any origins they
        evaluated this call, so the same setup is never re-evaluated).
        Returns None if nothing tradeable was found."""
        raise NotImplementedError


def _window(candles: List[Candle], end: int, config: BacktestConfig) -> List[Candle]:
    """The slice of history a candidate search recomputes over, ending just
    before `end` (exclusive). See backtest.py's "Performance" note."""
    if config.recompute_window is None:
        return candles[:end]
    return candles[max(0, end - config.recompute_window):end]


def _build_levels(fvg: ValidatedFVG, sweeps: List[LiquiditySweep], config: BacktestConfig):
    """Derives entry/stop/target/invalidation from a validated FVG and the
    sweep that fueled it. Returns None if the geometry doesn't make sense
    (defensive -- shouldn't happen given validate_fvgs already enforced the
    sweep is on the correct side, but a stop must sit strictly beyond entry)."""
    sweep = next((s for s in sweeps if s.candle_index == fvg.preceding_sweep_index), None)
    if sweep is None:
        return None

    reference = sweep.level.price
    height = abs(fvg.gap_high - fvg.gap_low)
    buffer = height * config.stop_buffer_fraction

    if fvg.direction == Direction.BULLISH:
        entry = fvg.gap_high
        invalidation = fvg.gap_low
        stop_loss = reference - buffer
        risk = entry - stop_loss
        take_profit = entry + config.target_rr * risk
    else:
        entry = fvg.gap_low
        invalidation = fvg.gap_high
        stop_loss = reference + buffer
        risk = stop_loss - entry
        take_profit = entry - config.target_rr * risk

    if risk <= 0:
        return None

    return entry, stop_loss, take_profit, invalidation, reference


class SmartMoneyConceptsStrategy(Strategy):
    """Reference strategy (see backtest.py's module docstring for the full
    rationale): a freshly-validated Fair Value Gap, fueled by a liquidity
    sweep, aligned with a BOS-confirmed trend. Entry rests at the gap's near
    edge; stop sits just beyond the sweep's level; invalidation is the gap's
    far edge, checked before the stop; target is a fixed R multiple."""

    name = "smart_money_concepts"

    def find_candidate(
        self, candles: List[Candle], i: int, config: BacktestConfig, seen_origins: Set[int]
    ) -> Optional[TradeCandidate]:
        prefix = _window(candles, i + 1, config)
        swings = classify_structure(find_swing_points(prefix, config.swing_lookback))
        structure_signals = detect_bos_and_choch(prefix, swings)

        eq_levels = find_equal_highs_lows(prefix, config.liquidity_tolerance)
        sweeps = detect_sweeps(prefix, eq_levels)

        disp_events = detect_displacement(
            prefix, config.displacement_lookback, config.displacement_strength_multiplier
        )
        new_events = [e for e in disp_events if e.confirmed_at == i and e.candle_index not in seen_origins]
        if not new_events:
            return None

        # trend_at needs the trend AS OF each event's own candle_index, not the
        # trend for the whole prefix -- recompute on the shorter history ending
        # at that candle, same no-look-ahead discipline as everywhere else here.
        trend_at: Dict[int, Trend] = {}
        for event in new_events:
            sub_prefix = _window(candles, event.candle_index + 1, config)
            sub_swings = classify_structure(find_swing_points(sub_prefix, config.swing_lookback))
            trend_at[event.candle_index] = determine_trend(sub_swings)

        for event in new_events:
            seen_origins.add(event.candle_index)  # one evaluation per displacement, ever

        relevant_events = [e for e in disp_events if e.candle_index in trend_at]
        fvgs = validate_fvgs(relevant_events, sweeps, trend_at, config.sweep_lookback)
        candidate = next((f for f in fvgs if f.origin_displacement_index in trend_at), None)
        if candidate is None:
            return None

        built = _build_levels(candidate, sweeps, config)
        if built is None:
            return None
        entry, stop_loss, take_profit, invalidation, reference = built

        plan = TradePlan(
            candidate.direction, entry, stop_loss, take_profit, invalidation,
            stop_reference_level=reference,
        )
        risk_result = validate_trade_risk(plan)

        last_structure_signal = next(
            (s for s in reversed(structure_signals) if s.candle_index <= candidate.origin_displacement_index),
            None,
        )
        wanted_trend = Trend.BULLISH if candidate.direction == Direction.BULLISH else Trend.BEARISH
        market_structure_confirmed = (
            last_structure_signal is not None
            and last_structure_signal.event == StructureEvent.BOS
            and last_structure_signal.trend_after == wanted_trend
        )

        # Session gate reflects the candle the order would actually be resting
        # into, not the candle the setup was recognized on.
        session_ok = True
        gate_candle = candles[i + 1] if i + 1 < len(candles) else candles[i]
        if gate_candle.timestamp is not None:
            session_ok = is_allowed_to_trade(gate_candle.timestamp.time())

        checklist = ChecklistInputs(
            market_structure_confirmed=market_structure_confirmed,
            liquidity_present=candidate.followed_sweep,
            trend_alignment=candidate.aligned_with_trend,
            displacement_confirmed=True,
            fvg_valid=True,
            # A more sophisticated "is price still realistically reachable" check
            # is a natural later addition; not modeled here.
            clean_entry=True,
            risk_management_defined=risk_result.valid,
            session_time_ok=session_ok,
            # No economic-calendar integration yet -- see scoring.py.
            no_major_news=True,
        )
        score = score_setup(checklist)
        if TIER_RANK[score.tier] < TIER_RANK[config.min_tier]:
            return None

        return TradeCandidate(
            origin_displacement_index=candidate.origin_displacement_index,
            direction=candidate.direction,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            invalidation_price=invalidation,
            tier=score.tier,
            confidence_score=score.confidence_score,
            checklist=checklist,
            placed_at_index=i,
            strategy_name=self.name,
        )


class StrategyEngine:
    """Runs a list of strategies and returns the first candidate any of
    them produces. With one strategy (today's only real case) this is
    exactly equivalent to calling that strategy directly. Deciding how
    multiple simultaneous candidates should interact -- confluence, regime
    gating, priority -- is future work, not something this class quietly
    assumes an answer for yet."""

    def __init__(self, strategies: Optional[List[Strategy]] = None):
        self.strategies = strategies if strategies is not None else [SmartMoneyConceptsStrategy()]

    def find_candidate(
        self, candles: List[Candle], i: int, config: BacktestConfig, seen_origins: Set[int]
    ) -> Optional[TradeCandidate]:
        for strategy in self.strategies:
            candidate = strategy.find_candidate(candles, i, config, seen_origins)
            if candidate is not None:
                return candidate
        return None
