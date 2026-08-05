"""
Portfolio Engine — AI Trading Brain, Subsystem 4 (see docs/specs/04-portfolio-engine.md)

ARCHITECTURE.md §12: "Cross-instrument exposure, correlation, capital
allocation... arbitrates when several approved trades compete for
capital/exposure budget." Closes a real, currently-live gap stated
plainly in §12's own text: nothing before this subsystem has any
cross-instrument view -- each LiveEngine only knows its own symbol, so
nothing stops four correlated positions opening simultaneously.

Independent of broker.py by design (ARCHITECTURE.md §6's dependency
graph draws no edge between BROKER2 and PORTFOLIO) -- PortfolioState is
assembled by a caller from broker.get_positions(), not read by this
module directly. Same precedent as risk_engine staying independent of
broker.settings.BotSettings (see risk_engine/pipeline.py's own docstring
and docs/specs/03-risk-engine.md §1).

Built partly as a direct consequence of ADR-0003
(docs/adr/0003-max-concurrent-positions-belongs-to-portfolio-not-risk.md):
max_simultaneous_positions is this module's job, not Risk Engine's.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Set


@dataclass(frozen=True)
class OpenPosition:
    symbol: str


@dataclass(frozen=True)
class PendingOrder:
    symbol: str


@dataclass(frozen=True)
class PortfolioState:
    open_positions: List[OpenPosition]
    pending_orders: List[PendingOrder]

    def all_symbols(self) -> Set[str]:
        """Every symbol with live exposure, open or pending -- both count
        toward every cap below, since a resting order is a real
        commitment of intended risk even before it fills."""
        return {p.symbol for p in self.open_positions} | {p.symbol for p in self.pending_orders}


@dataclass(frozen=True)
class PortfolioPolicy:
    max_simultaneous_positions: int
    correlation_groups: Dict[str, str]
    correlation_group_caps: Dict[str, int]

    def group_of(self, symbol: str) -> str:
        """A symbol nobody has explicitly grouped defaults to its own
        singleton group -- the conservative case (no assumed correlation
        benefit), not an exemption from group caps."""
        return self.correlation_groups.get(symbol, symbol)

    def cap_for_group(self, group: str) -> int:
        """An ungrouped/singleton group with no configured cap defaults
        to 1 -- one position at a time in an instrument nobody has
        explicitly told the policy is safe to concentrate in."""
        return self.correlation_group_caps.get(group, 1)


class PortfolioDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True)
class PortfolioCheckResult:
    decision: PortfolioDecision
    reason: str


class PortfolioEngine:
    def evaluate(self, symbol: str, state: PortfolioState, policy: PortfolioPolicy) -> PortfolioCheckResult:
        """Never raises for an ordinary rejection -- same precedent as
        Registry.promote()/RiskEngine.evaluate(): exceptions mean misuse,
        not 'the answer is no'."""
        active_symbols = state.all_symbols()

        # 1. Same-symbol overlap, checked first and independent of the
        # numeric caps -- LiveEngine is strictly one-position-per-symbol
        # by construction (see docs/specs/04-portfolio-engine.md §1), so
        # this matches an existing constraint rather than inventing one.
        if symbol in active_symbols:
            return PortfolioCheckResult(
                PortfolioDecision.REJECT,
                f"{symbol!r} already has an open or pending position",
            )

        # 2. Platform-wide cap.
        if len(active_symbols) >= policy.max_simultaneous_positions:
            return PortfolioCheckResult(
                PortfolioDecision.REJECT,
                f"already at max_simultaneous_positions ({len(active_symbols)}/{policy.max_simultaneous_positions})",
            )

        # 3. Correlation-group cap.
        group = policy.group_of(symbol)
        group_count = sum(1 for s in active_symbols if policy.group_of(s) == group)
        group_cap = policy.cap_for_group(group)
        if group_count >= group_cap:
            return PortfolioCheckResult(
                PortfolioDecision.REJECT,
                f"correlation group {group!r} already at its cap ({group_count}/{group_cap})",
            )

        return PortfolioCheckResult(PortfolioDecision.APPROVE, "within platform and correlation-group limits")
