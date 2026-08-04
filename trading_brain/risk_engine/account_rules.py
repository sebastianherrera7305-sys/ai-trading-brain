"""
Account rules — AI Trading Brain, Subsystem 3

Pluggable per-account-type validator (ARCHITECTURE.md §7, §11): a
personal account has no extra rules beyond the standard pipeline
(NoOpAccountRules); a Topstep-funded account's EOD-trailing-drawdown and
consistency-fraction rules plug in here later, ported from
trading-bot/bot/propfirm/calculator.py's already-tested _floor_for()
logic -- deliberately NOT built in this increment (docs/specs/03-risk-engine.md
§1's explicit scope boundary: that's a cross-repo port of real, already-
validated logic and deserves its own parity check against the source,
not a rushed inline reimplementation here).
"""

from .pipeline import AccountState, RiskCheckResult, RiskCheckStatus, RiskPolicy, RiskValidator


class AccountRulesValidator(RiskValidator):
    """Base for per-account-type rules. Subclass and override check()."""

    name = "account_rules"


class NoOpAccountRules(AccountRulesValidator):
    """The only implementation this increment ships -- a personal,
    non-funded account has no rules beyond the standard pipeline."""

    name = "account_rules_noop"

    def check(self, candidate, policy: RiskPolicy, account: AccountState, unit_value_per_point: float = 1.0) -> RiskCheckResult:
        return RiskCheckResult(self.name, RiskCheckStatus.APPROVE, "no account-specific rules configured")
