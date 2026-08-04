"""
Backtest Module — AI Trading Brain v1, Phase 2

Wires all seven Phase 1 modules into a single walk-forward loop: replay a
list of candles, decide when to take a trade, follow it to its exit, and log
what happened. Every module up to this one produces labels; this is what
turns those labels into a trade record you can look back on and learn from.

Reference strategy (swap this out once you have a real edge to encode):
  - Entry candidate: a freshly-validated Fair Value Gap (fair_value_gap.py)
    that clears the Mandatory Checklist at Tier B or better.
  - Entry: a resting order at the gap's near edge -- waits for a retracement
    back into the gap, not a market order at the next open. If price never
    comes back, or invalidates the gap first, the order expires unfilled and
    no trade is recorded.
  - Stop loss: just beyond the liquidity level the preceding sweep took out.
  - Invalidation: the gap's far edge -- if price closes the whole gap, the
    thesis that created it is dead (checked before the stop, per the README).
  - Target: a fixed reward-to-risk multiple of the stop distance.

No look-ahead: at step i, every module call below only ever sees a slice of
candles ending at i+1 (see "Performance" below on why it's a slice and not
always candles[:i+1]). A setup recognized at step i can place a resting
order from i+1 onward, but the order only becomes a trade once a later
candle's wick actually reaches the entry price -- exactly like a real limit
order, not a guaranteed fill.

Performance: recomputing every Phase 1 module from scratch on the full
growing history at every step is correct but scales badly -- find_equal_highs_lows
alone is roughly O(n^2) per call, called at up to n steps, so a naive full
recompute is close to O(n^3) overall. Measured: 500 candles ran in ~3s, 2000
candles took over two minutes. BacktestConfig.recompute_window (default 300)
bounds each recompute to a trailing window instead of the whole history --
turns O(n^3) into roughly O(n * window^2), which is linear in the number of
candles. This is an approximation, not free: detect_bos_and_choch's internal
trend tracking restarts from Trend.RANGE at the start of each window rather
than carrying the true accumulated state, so in principle a BOS/CHoCH read
near the very start of a window could differ from a full-history run before
the state reconverges. In practice this settles within a handful of swings,
and 300 candles is enormously larger than the default lookback parameters
(10-20), so convergence room is not the tight constraint. Set
recompute_window=None to disable windowing and match full-history behavior
exactly -- fine for datasets small enough to afford the cost, and useful as
a correctness check against a windowed run on the same data.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

from .market_structure import Candle
from .displacement import Direction
from .config import BacktestConfig
from .scoring import ChecklistInputs, Tier
from .strategy import SmartMoneyConceptsStrategy, Strategy, TradeCandidate


class TradeOutcome(Enum):
    WIN = "win"
    LOSS = "loss"
    INVALIDATED = "invalidated"
    OPEN = "open"  # backtest ended before the trade resolved


@dataclass
class TradeRecord:
    origin_displacement_index: int
    entry_index: int
    direction: Direction
    entry: float
    stop_loss: float
    take_profit: float
    invalidation_price: float
    tier: Tier
    confidence_score: int
    checklist: ChecklistInputs
    exit_index: Optional[int] = None
    exit_price: Optional[float] = None
    outcome: TradeOutcome = TradeOutcome.OPEN
    realized_r: Optional[float] = None


@dataclass
class TierStats:
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_r: float = 0.0

    @property
    def win_rate(self) -> Optional[float]:
        decided = self.wins + self.losses
        return self.wins / decided if decided else None


@dataclass
class BacktestResult:
    trades: List[TradeRecord] = field(default_factory=list)
    unfilled_setups: int = 0  # candidates that passed the checklist but never got a fill

    @property
    def closed_trades(self) -> List[TradeRecord]:
        return [t for t in self.trades if t.outcome != TradeOutcome.OPEN]

    @property
    def losing_trades(self) -> List[TradeRecord]:
        """The record 'know the times it lost' actually means: every trade that
        lost or got invalidated, so you can go look at what they had in common."""
        return [t for t in self.closed_trades if t.outcome in (TradeOutcome.LOSS, TradeOutcome.INVALIDATED)]

    @property
    def win_rate(self) -> Optional[float]:
        # INVALIDATED counts as a loss here, same as TierStats.win_rate below --
        # a trade that got cut on invalidation still lost money and must not be
        # excluded from the denominator just because it wasn't a stop-loss exit.
        decided = [t for t in self.closed_trades
                   if t.outcome in (TradeOutcome.WIN, TradeOutcome.LOSS, TradeOutcome.INVALIDATED)]
        if not decided:
            return None
        return sum(1 for t in decided if t.outcome == TradeOutcome.WIN) / len(decided)

    @property
    def total_r(self) -> float:
        return sum(t.realized_r for t in self.closed_trades if t.realized_r is not None)

    @property
    def max_drawdown_r(self) -> float:
        """Largest peak-to-trough decline on the cumulative-R equity curve.
        Always <= 0; e.g. -3.5 means a 3.5R peak-to-trough drawdown occurred."""
        peak = 0.0
        cumulative = 0.0
        worst = 0.0
        for t in self.closed_trades:
            if t.realized_r is None:
                continue
            cumulative += t.realized_r
            peak = max(peak, cumulative)
            worst = min(worst, cumulative - peak)
        return worst

    @property
    def by_tier(self) -> Dict[Tier, TierStats]:
        stats: Dict[Tier, TierStats] = {}
        for t in self.closed_trades:
            s = stats.setdefault(t.tier, TierStats())
            s.trades += 1
            if t.outcome == TradeOutcome.WIN:
                s.wins += 1
            elif t.outcome in (TradeOutcome.LOSS, TradeOutcome.INVALIDATED):
                s.losses += 1
            if t.realized_r is not None:
                s.total_r += t.realized_r
        return stats


def _resolve_r(direction: Direction, entry: float, stop_loss: float, exit_price: float) -> float:
    risk_per_unit = abs(entry - stop_loss)
    if risk_per_unit == 0:
        return 0.0
    signed_move = (exit_price - entry) if direction == Direction.BULLISH else (entry - exit_price)
    return signed_move / risk_per_unit


def _fill_touched(direction: Direction, entry: float, candle: Candle) -> bool:
    if direction == Direction.BULLISH:
        return candle.low <= entry
    return candle.high >= entry


def _invalidated_before_fill(direction: Direction, invalidation: float, candle: Candle) -> bool:
    # Close-based, matching the project's convention elsewhere (a wick alone
    # isn't a break; the candle has to close beyond the level).
    if direction == Direction.BULLISH:
        return candle.close <= invalidation
    return candle.close >= invalidation


def _close_trade(trade: TradeRecord, candle: Candle, exit_price: float, outcome: TradeOutcome) -> None:
    trade.exit_index = candle.index
    trade.exit_price = exit_price
    trade.outcome = outcome
    trade.realized_r = _resolve_r(trade.direction, trade.entry, trade.stop_loss, exit_price)


def _resolve_exit(trade: TradeRecord, candle: Candle) -> bool:
    """Checks invalidation first, per the README's own rule: exit on
    invalidation before the hard stop. If both stop and target are touched in
    the same candle, OHLC alone can't say which came first -- the stop wins,
    the conservative assumption."""
    bullish = trade.direction == Direction.BULLISH

    invalidated = (candle.close <= trade.invalidation_price) if bullish else (candle.close >= trade.invalidation_price)
    if invalidated:
        _close_trade(trade, candle, trade.invalidation_price, TradeOutcome.INVALIDATED)
        return True

    stopped = (candle.low <= trade.stop_loss) if bullish else (candle.high >= trade.stop_loss)
    if stopped:
        _close_trade(trade, candle, trade.stop_loss, TradeOutcome.LOSS)
        return True

    targeted = (candle.high >= trade.take_profit) if bullish else (candle.low <= trade.take_profit)
    if targeted:
        _close_trade(trade, candle, trade.take_profit, TradeOutcome.WIN)
        return True

    return False


def run_backtest(
    candles: List[Candle],
    config: Optional[BacktestConfig] = None,
    strategy: Optional[Strategy] = None,
) -> BacktestResult:
    config = config or BacktestConfig()
    strategy = strategy or SmartMoneyConceptsStrategy()
    result = BacktestResult()

    pending: Optional[TradeCandidate] = None
    open_trade: Optional[TradeRecord] = None
    seen_origins: Set[int] = set()

    for i in range(len(candles)):
        candle = candles[i]

        if open_trade is not None:
            if candle.index > open_trade.entry_index and _resolve_exit(open_trade, candle):
                result.trades.append(open_trade)
                open_trade = None
            continue

        if pending is not None:
            if candle.index <= pending.placed_at_index:
                continue
            if _fill_touched(pending.direction, pending.entry, candle):
                open_trade = TradeRecord(
                    origin_displacement_index=pending.origin_displacement_index,
                    entry_index=candle.index,
                    direction=pending.direction,
                    entry=pending.entry,
                    stop_loss=pending.stop_loss,
                    take_profit=pending.take_profit,
                    invalidation_price=pending.invalidation_price,
                    tier=pending.tier,
                    confidence_score=pending.confidence_score,
                    checklist=pending.checklist,
                )
                pending = None
                continue
            if _invalidated_before_fill(pending.direction, pending.invalidation_price, candle):
                result.unfilled_setups += 1
                pending = None
                continue
            if candle.index - pending.placed_at_index > config.max_pending_candles:
                result.unfilled_setups += 1
                pending = None
                continue
            continue

        # Neither a pending order nor an open trade -- look for a new candidate.
        candidate_order = strategy.find_candidate(candles, i, config, seen_origins)
        if candidate_order is not None:
            pending = candidate_order

    if open_trade is not None:
        result.trades.append(open_trade)  # still open when the data ran out

    return result


def run_demo() -> None:
    """Synthetic walkthrough: a bullish setup that fills on a retracement and
    wins, followed by one that fills and gets stopped out -- so the summary
    stats below actually have a win and a loss to report on."""
    raw = [
        # --- Prior uptrend (HH/HL), so the first setup has a confirmed trend ---
        (100, 101, 99, 100), (100, 105, 99.5, 104), (104, 104.5, 100.5, 101),
        (101, 102, 99, 99.5), (99.5, 103, 99.2, 102), (102, 109, 101.5, 108),
        (108, 108.5, 103, 104), (104, 105, 100.20, 101), (101, 101.5, 100.9, 101.2),
        (101.2, 101.3, 100.25, 101), (101, 101.5, 100.9, 101.2), (101.2, 101.5, 99.5, 101.3),
        # --- Setup #1: sweep -> displacement -> fill -> runs to target -> WIN ---
        (101.3, 112, 101, 110),        # 12 displacement candle
        (110, 113, 108, 112),          # 13 confirms gap [101.5, 108]
        (112, 112.5, 107.5, 108.2),    # 14 retraces -> fills at 108
        (108.2, 108.5, 107.9, 108.1),  # 15
        (108.1, 130, 108, 129),        # 16 runs hard -> hits target -> WIN
        # --- Setup #2: fresh sweep -> displacement -> fill -> reverses -> LOSS ---
        (129, 130, 108, 128),          # 17 pulls back -- low overlaps candle 15's high, so this
                                        #    move does NOT leave its own gap behind
        (128, 128.5, 126, 127), (127, 127.5, 120.20, 121),
        (121, 121.5, 120.60, 121.2), (121.2, 121.3, 120.25, 121), (121, 121.5, 120.60, 121.2),
        (121.2, 121.5, 118, 121.3),    # 23 sweep candle
        (121.3, 132, 121, 130),        # 24 displacement candle
        (130, 133, 128, 132),          # 25 confirms gap [121.5, 128]
        (132, 132.5, 127.5, 128.2),    # 26 retraces
        (128.2, 128.5, 127.9, 128.1),  # 27 fills at 128
        (128.1, 128.5, 108, 110),      # 28 reverses hard -> hits stop -> LOSS
    ]
    candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw)]

    result = run_backtest(
        candles, BacktestConfig(swing_lookback=1, displacement_lookback=5, liquidity_tolerance=0.1)
    )

    print("=== Trades ===")
    if not result.trades:
        print("  none taken")
    for t in result.trades:
        print(f"  entry_idx={t.entry_index}  {t.direction.value:8s}  tier={t.tier.name}  "
              f"score={t.confidence_score}  entry={t.entry:.2f}  outcome={t.outcome.value:12s}  "
              f"R={'n/a' if t.realized_r is None else f'{t.realized_r:+.2f}'}")

    print(f"\n=== Summary ===")
    print(f"  closed trades: {len(result.closed_trades)}   unfilled setups: {result.unfilled_setups}")
    win_rate = result.win_rate
    print(f"  win rate: {'n/a' if win_rate is None else f'{win_rate:.0%}'}")
    print(f"  total R: {result.total_r:+.2f}   max drawdown: {result.max_drawdown_r:.2f}R")

    print("\n=== By tier ===")
    for tier, stats in result.by_tier.items():
        wr = stats.win_rate
        print(f"  {tier.name}: {stats.trades} trades, "
              f"win rate {'n/a' if wr is None else f'{wr:.0%}'}, total R {stats.total_r:+.2f}")

    print("\n=== Losing trades (what to learn from) ===")
    if not result.losing_trades:
        print("  none")
    for t in result.losing_trades:
        print(f"  entry_idx={t.entry_index}  outcome={t.outcome.value}  R={t.realized_r:+.2f}  "
              f"checklist={t.checklist}")


if __name__ == "__main__":
    run_demo()
