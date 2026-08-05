"""
Risk Engine — AI Trading Brain, Subsystem 3 (see docs/specs/03-risk-engine.md)

ARCHITECTURE.md §11: "risk management must always override every
strategy," enforced structurally here by RiskEngine.evaluate() stopping
at the first REJECT, not by convention. A rejection is a normal,
returned RiskCheckResult -- never an exception; exceptions here mean a
programmer error (a validator called with malformed input), never "the
answer is no" (mirrors registry.py's precedent: exceptions for genuine
misuse, not for ordinary decision outcomes).

RiskPolicy is deliberately its own type, not broker.settings.BotSettings
reused directly -- ARCHITECTURE.md §6's dependency graph draws risk_engine
and broker as independent, both feeding engine_runner. Importing
BotSettings here would invert that. Reconciling the two configuration
shapes is later wiring work; see the spec doc's §1.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ..scoring import Tier
from ..strategy import TradeCandidate


class RiskCheckStatus(str, Enum):
    APPROVE = "approve"
    RESIZE = "resize"
    REJECT = "reject"


@dataclass(frozen=True)
class RiskCheckResult:
    validator_name: str
    status: RiskCheckStatus
    reason: str
    resized_quantity: Optional[int] = None


@dataclass(frozen=True)
class RiskPolicy:
    risk_percent: float
    max_contracts: int
    min_tier: Tier
    daily_loss_limit_percent: float
    weekly_loss_limit_percent: float


@dataclass(frozen=True)
class AccountState:
    equity: float
    daily_loss_limit_breached: bool
    weekly_loss_limit_breached: bool
    kill_switch_active: bool
    instrument_enabled: bool


class RiskValidator(ABC):
    name: str = "unnamed"

    @abstractmethod
    def check(
        self, candidate: TradeCandidate, policy: RiskPolicy, account: AccountState,
        unit_value_per_point: float = 1.0,
    ) -> RiskCheckResult:
        raise NotImplementedError


def overall_status(results: List[RiskCheckResult]) -> RiskCheckStatus:
    """REJECT wins if any validator rejected (and by construction, a
    REJECT is always the last result, since evaluate() stops there).
    Otherwise RESIZE wins if any validator resized -- a RESIZE is NOT
    terminal (later validators still run against the resized quantity's
    implications, e.g. account rules), so a later APPROVE must not bury
    an earlier RESIZE. Checking only results[-1] was this module's first
    draft and is wrong for exactly that reason -- caught by
    tests/test_risk_engine.py's own resize-then-approve case, not by
    inspection."""
    if any(r.status == RiskCheckStatus.REJECT for r in results):
        return RiskCheckStatus.REJECT
    if any(r.status == RiskCheckStatus.RESIZE for r in results):
        return RiskCheckStatus.RESIZE
    return RiskCheckStatus.APPROVE


def effective_quantity(results: List[RiskCheckResult]) -> Optional[int]:
    """The quantity implied by the run: the last RESIZE's resized_quantity
    if any validator resized, else the last APPROVE that carried a
    resized_quantity (PositionSizeValidator's own approval path also sets
    it), else None."""
    for r in reversed(results):
        if r.status in (RiskCheckStatus.RESIZE, RiskCheckStatus.APPROVE) and r.resized_quantity is not None:
            return r.resized_quantity
    return None


class RiskEngine:
    """Runs validators in the order given -- default order matches
    ARCHITECTURE.md §11's stated sequence (cheapest/most-restrictive
    first), assembled in __init__.py, not hardcoded here, so a caller can
    substitute a different order/set for testing without touching this
    class. Read the overall verdict via overall_status(results) /
    effective_quantity(results) above, not results[-1] directly -- a
    REJECT is always last by construction, but a RESIZE is not."""

    def __init__(self, validators: List[RiskValidator]):
        self.validators = validators

    def evaluate(
        self, candidate: TradeCandidate, policy: RiskPolicy, account: AccountState,
        unit_value_per_point: float = 1.0,
    ) -> List[RiskCheckResult]:
        results: List[RiskCheckResult] = []
        for validator in self.validators:
            result = validator.check(candidate, policy, account, unit_value_per_point)
            results.append(result)
            if result.status == RiskCheckStatus.REJECT:
                break
        return results
