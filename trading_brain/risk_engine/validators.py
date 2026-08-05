"""
Concrete RiskValidators — AI Trading Brain, Subsystem 3

Order matters: ARCHITECTURE.md §11 specifies cheapest/most-restrictive
checks first. DEFAULT_VALIDATORS below is that order; RiskEngine itself
doesn't hardcode it (see pipeline.py) so tests can substitute a different
set without touching this module.
"""

from ..risk import position_size
from ..scoring import meets_tier_floor
from ..strategy import TradeCandidate
from .pipeline import AccountState, RiskCheckResult, RiskCheckStatus, RiskPolicy, RiskValidator


class KillSwitchValidator(RiskValidator):
    name = "kill_switch"

    def check(self, candidate, policy, account: AccountState, unit_value_per_point=1.0) -> RiskCheckResult:
        if account.kill_switch_active:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, "kill switch is active")
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, "kill switch not active")


class InstrumentEnabledValidator(RiskValidator):
    name = "instrument_enabled"

    def check(self, candidate, policy, account: AccountState, unit_value_per_point=1.0) -> RiskCheckResult:
        if not account.instrument_enabled:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, "instrument is not enabled")
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, "instrument enabled")


class TierFloorValidator(RiskValidator):
    name = "tier_floor"

    def check(self, candidate: TradeCandidate, policy: RiskPolicy, account, unit_value_per_point=1.0) -> RiskCheckResult:
        if not meets_tier_floor(candidate.tier, policy.min_tier):
            return RiskCheckResult(
                self.name, RiskCheckStatus.REJECT,
                f"tier {candidate.tier.value!r} is below the configured floor {policy.min_tier.value!r}",
            )
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, f"tier {candidate.tier.value!r} meets the floor")


class DailyLossLimitValidator(RiskValidator):
    name = "daily_loss_limit"

    def check(self, candidate, policy, account: AccountState, unit_value_per_point=1.0) -> RiskCheckResult:
        if account.daily_loss_limit_breached:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, "daily loss limit already breached today")
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, "daily loss limit not breached")


class WeeklyLossLimitValidator(RiskValidator):
    name = "weekly_loss_limit"

    def check(self, candidate, policy, account: AccountState, unit_value_per_point=1.0) -> RiskCheckResult:
        if account.weekly_loss_limit_breached:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, "weekly loss limit already breached this week")
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, "weekly loss limit not breached")


class PositionSizeValidator(RiskValidator):
    """The one validator that can RESIZE instead of only approve/reject --
    computes fixed-fractional size from policy.risk_percent, caps it at
    policy.max_contracts, and rejects (does not silently resize to zero)
    when the computed size rounds below one contract."""

    name = "position_size"

    def check(
        self, candidate: TradeCandidate, policy: RiskPolicy, account: AccountState, unit_value_per_point: float = 1.0,
    ) -> RiskCheckResult:
        try:
            raw_size = position_size(
                account.equity, policy.risk_percent, candidate.entry, candidate.stop_loss, unit_value_per_point,
            )
        except ValueError as exc:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, f"could not size position: {exc}")

        quantity = int(raw_size)
        if quantity < 1:
            return RiskCheckResult(self.name, RiskCheckStatus.REJECT, f"computed size rounds below 1 contract ({raw_size:.4f})")

        if quantity > policy.max_contracts:
            return RiskCheckResult(
                self.name, RiskCheckStatus.RESIZE,
                f"computed size {quantity} exceeds max_contracts {policy.max_contracts}, resized down",
                resized_quantity=policy.max_contracts,
            )
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, f"sized at {quantity} contract(s)", resized_quantity=quantity)


# ARCHITECTURE.md §11's stated order: kill switch and instrument-enabled
# first (cheapest, most-restrictive, no arithmetic), then tier floor,
# then position sizing, then the loss-limit checks, ending with the
# pluggable account-rules validator (added by the caller -- see
# risk_engine/__init__.py for where NoOpAccountRules/TopstepAccountRules
# would be appended). Platform-wide concurrent-position exposure is
# Portfolio Engine's job, not Risk Engine's -- see ADR-0003.
DEFAULT_VALIDATORS = [
    KillSwitchValidator(),
    InstrumentEnabledValidator(),
    TierFloorValidator(),
    PositionSizeValidator(),
    DailyLossLimitValidator(),
    WeeklyLossLimitValidator(),
]
