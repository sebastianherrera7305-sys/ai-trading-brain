"""AI Trading Brain — pure market structure logic."""

from .market_structure import (
    Candle,
    StructureEvent,
    StructureLabel,
    StructureSignal,
    SwingPoint,
    SwingType,
    Trend,
    classify_structure,
    detect_bos_and_choch,
    determine_trend,
    find_swing_points,
)
from .liquidity import (
    LiquidityLevel,
    LiquidityLevelType,
    LiquiditySweep,
    Session,
    SessionCandle,
    detect_sweeps,
    find_equal_highs_lows,
    find_session_extremes,
)
from .displacement import (
    Direction,
    DisplacementEvent,
    ImbalanceGap,
    detect_displacement,
    find_imbalance,
    rolling_average_range,
)
from .sessions import (
    SessionTag,
    SessionWindow,
    TRADEABLE_WINDOWS,
    is_allowed_to_trade,
    tag_session,
)
from .fair_value_gap import (
    MitigationStatus,
    ValidatedFVG,
    update_mitigation,
    validate_fvgs,
)
from .risk import (
    RiskAssessment,
    RiskRejectReason,
    TradePlan,
    check_invalidation,
    position_size,
    validate_trade_risk,
)
from .scoring import (
    ChecklistInputs,
    ScoreBreakdown,
    Tier,
    compute_confidence_score,
    evaluate_checklist,
    score_setup,
    tier_from_score,
)
from .backtest import (
    BacktestConfig,
    BacktestResult,
    TierStats,
    TradeOutcome,
    TradeRecord,
    run_backtest,
)
from .data_loader import load_candles_from_csv

__all__ = [
    # market structure
    "Candle",
    "StructureEvent",
    "StructureLabel",
    "StructureSignal",
    "SwingPoint",
    "SwingType",
    "Trend",
    "classify_structure",
    "detect_bos_and_choch",
    "determine_trend",
    "find_swing_points",
    # liquidity
    "LiquidityLevel",
    "LiquidityLevelType",
    "LiquiditySweep",
    "Session",
    "SessionCandle",
    "detect_sweeps",
    "find_equal_highs_lows",
    "find_session_extremes",
    # displacement
    "Direction",
    "DisplacementEvent",
    "ImbalanceGap",
    "detect_displacement",
    "find_imbalance",
    "rolling_average_range",
    # sessions
    "SessionTag",
    "SessionWindow",
    "TRADEABLE_WINDOWS",
    "is_allowed_to_trade",
    "tag_session",
    # fair value gap
    "MitigationStatus",
    "ValidatedFVG",
    "update_mitigation",
    "validate_fvgs",
    # risk
    "RiskAssessment",
    "RiskRejectReason",
    "TradePlan",
    "check_invalidation",
    "position_size",
    "validate_trade_risk",
    # scoring
    "ChecklistInputs",
    "ScoreBreakdown",
    "Tier",
    "compute_confidence_score",
    "evaluate_checklist",
    "score_setup",
    "tier_from_score",
    # backtest
    "BacktestConfig",
    "BacktestResult",
    "TierStats",
    "TradeOutcome",
    "TradeRecord",
    "run_backtest",
    # data loader
    "load_candles_from_csv",
]

__version__ = "0.1.0"
