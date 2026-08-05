from typing import Optional

from .account_rules import AccountRulesValidator, NoOpAccountRules
from .pipeline import (
    AccountState,
    RiskCheckResult,
    RiskCheckStatus,
    RiskEngine,
    RiskPolicy,
    RiskValidator,
    effective_quantity,
    overall_status,
)
from .validators import (
    DEFAULT_VALIDATORS,
    DailyLossLimitValidator,
    InstrumentEnabledValidator,
    KillSwitchValidator,
    PositionSizeValidator,
    TierFloorValidator,
    WeeklyLossLimitValidator,
)


def default_risk_engine(account_rules: Optional[AccountRulesValidator] = None) -> RiskEngine:
    """Assembles the standard pipeline in ARCHITECTURE.md §11's stated
    order, ending with the pluggable account-rules validator -- NoOpAccountRules
    unless a caller passes a funded-account implementation."""
    validators = list(DEFAULT_VALIDATORS) + [account_rules or NoOpAccountRules()]
    return RiskEngine(validators)


__all__ = [
    "RiskCheckStatus",
    "RiskCheckResult",
    "RiskPolicy",
    "AccountState",
    "RiskValidator",
    "RiskEngine",
    "overall_status",
    "effective_quantity",
    "KillSwitchValidator",
    "InstrumentEnabledValidator",
    "TierFloorValidator",
    "PositionSizeValidator",
    "DailyLossLimitValidator",
    "WeeklyLossLimitValidator",
    "DEFAULT_VALIDATORS",
    "AccountRulesValidator",
    "NoOpAccountRules",
    "default_risk_engine",
]
