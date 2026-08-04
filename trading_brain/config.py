"""
Strategy configuration — AI Trading Brain, Phase 4

BacktestConfig lives in its own module (moved out of backtest.py) so both
backtest.py and strategy.py can depend on it without importing each other --
strategy.py needs it to type its find_candidate() signature, and backtest.py
needs it to build a default strategy. Nothing about the config itself
changed in the move.
"""

from dataclasses import dataclass
from typing import Optional

from .scoring import Tier


@dataclass
class BacktestConfig:
    swing_lookback: int = 2
    liquidity_tolerance: float = 0.05
    sweep_lookback: int = 10
    displacement_lookback: int = 10
    displacement_strength_multiplier: float = 1.5
    stop_buffer_fraction: float = 0.1   # fraction of the FVG's height used as stop buffer beyond structure
    target_rr: float = 2.0
    min_tier: Tier = Tier.B             # README's own floor: below B, do not trade
    max_pending_candles: int = 20       # give up waiting for a retracement fill after this many candles
    recompute_window: Optional[int] = 300  # see backtest.py's "Performance" note
