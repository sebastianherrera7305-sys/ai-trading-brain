"""Tests for the Risk Engine (Subsystem 3, docs/specs/03-risk-engine.md)."""

from trading_brain.displacement import Direction
from trading_brain.risk_engine import (
    AccountState,
    DailyLossLimitValidator,
    InstrumentEnabledValidator,
    KillSwitchValidator,
    NoOpAccountRules,
    PositionSizeValidator,
    RiskCheckStatus,
    RiskEngine,
    RiskPolicy,
    TierFloorValidator,
    WeeklyLossLimitValidator,
    default_risk_engine,
    effective_quantity,
    overall_status,
)
from trading_brain.scoring import ChecklistInputs, Tier
from trading_brain.strategy import TradeCandidate


def _checklist(**overrides) -> ChecklistInputs:
    defaults = dict(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=True, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    defaults.update(overrides)
    return ChecklistInputs(**defaults)


def _candidate(tier=Tier.A, entry=100.0, stop_loss=95.0) -> TradeCandidate:
    return TradeCandidate(
        origin_displacement_index=0, direction=Direction.BULLISH, entry=entry, stop_loss=stop_loss,
        take_profit=110.0, invalidation_price=94.0, tier=tier, confidence_score=80,
        checklist=_checklist(), placed_at_index=0,
    )


def _policy(**overrides) -> RiskPolicy:
    defaults = dict(
        risk_percent=1.0, max_contracts=10, min_tier=Tier.B, daily_loss_limit_percent=3.0,
        weekly_loss_limit_percent=6.0,
    )
    defaults.update(overrides)
    return RiskPolicy(**defaults)


def _account(**overrides) -> AccountState:
    defaults = dict(
        equity=100_000.0, daily_loss_limit_breached=False,
        weekly_loss_limit_breached=False, kill_switch_active=False, instrument_enabled=True,
    )
    defaults.update(overrides)
    return AccountState(**defaults)


# --- individual validators -------------------------------------------------

def test_kill_switch_rejects_when_active():
    v = KillSwitchValidator()
    approved = v.check(_candidate(), _policy(), _account(kill_switch_active=False))
    rejected = v.check(_candidate(), _policy(), _account(kill_switch_active=True))
    assert approved.status == RiskCheckStatus.APPROVE
    assert rejected.status == RiskCheckStatus.REJECT


def test_instrument_enabled_rejects_when_disabled():
    v = InstrumentEnabledValidator()
    rejected = v.check(_candidate(), _policy(), _account(instrument_enabled=False))
    assert rejected.status == RiskCheckStatus.REJECT


def test_tier_floor_rejects_below_floor_and_approves_at_or_above():
    v = TierFloorValidator()
    policy = _policy(min_tier=Tier.A)
    assert v.check(_candidate(tier=Tier.B), policy, _account()).status == RiskCheckStatus.REJECT
    assert v.check(_candidate(tier=Tier.A), policy, _account()).status == RiskCheckStatus.APPROVE
    assert v.check(_candidate(tier=Tier.S), policy, _account()).status == RiskCheckStatus.APPROVE


def test_daily_and_weekly_loss_limit_validators_reject_when_breached():
    daily, weekly = DailyLossLimitValidator(), WeeklyLossLimitValidator()
    assert daily.check(_candidate(), _policy(), _account(daily_loss_limit_breached=True)).status == RiskCheckStatus.REJECT
    assert daily.check(_candidate(), _policy(), _account(daily_loss_limit_breached=False)).status == RiskCheckStatus.APPROVE
    assert weekly.check(_candidate(), _policy(), _account(weekly_loss_limit_breached=True)).status == RiskCheckStatus.REJECT
    assert weekly.check(_candidate(), _policy(), _account(weekly_loss_limit_breached=False)).status == RiskCheckStatus.APPROVE


def test_no_op_account_rules_always_approves():
    v = NoOpAccountRules()
    assert v.check(_candidate(), _policy(), _account()).status == RiskCheckStatus.APPROVE


def test_position_size_resizes_down_to_max_contracts():
    v = PositionSizeValidator()
    # entry=100, stop=95 -> risk 5/unit; 1% of 1,000,000 = 10,000 -> 2,000 units, way over max_contracts
    result = v.check(_candidate(entry=100.0, stop_loss=95.0), _policy(risk_percent=1.0, max_contracts=10), _account(equity=1_000_000.0))
    assert result.status == RiskCheckStatus.RESIZE
    assert result.resized_quantity == 10


def test_position_size_rejects_when_computed_size_rounds_below_one():
    v = PositionSizeValidator()
    # tiny equity, wide stop -> computed size < 1
    result = v.check(_candidate(entry=100.0, stop_loss=50.0), _policy(risk_percent=0.01, max_contracts=10), _account(equity=1_000.0))
    assert result.status == RiskCheckStatus.REJECT
    assert result.resized_quantity is None


def test_position_size_approves_within_bounds():
    v = PositionSizeValidator()
    # entry=100, stop=95 -> risk 5/unit; 1% of 10,000 = 100 -> 20 units... still over 10; use smaller equity
    result = v.check(_candidate(entry=100.0, stop_loss=95.0), _policy(risk_percent=1.0, max_contracts=10), _account(equity=1_000.0))
    assert result.status == RiskCheckStatus.APPROVE
    assert result.resized_quantity == 2  # (1000 * 0.01) / 5 = 2


# --- the pipeline itself ----------------------------------------------------

def test_default_pipeline_starts_with_kill_switch():
    engine = default_risk_engine()
    assert isinstance(engine.validators[0], KillSwitchValidator)


def test_evaluate_returns_one_approve_per_validator_when_everything_passes():
    engine = default_risk_engine()
    results = engine.evaluate(_candidate(tier=Tier.A, entry=100.0, stop_loss=95.0), _policy(min_tier=Tier.B), _account(equity=1_000.0))
    assert len(results) == len(engine.validators)
    assert all(r.status in (RiskCheckStatus.APPROVE, RiskCheckStatus.RESIZE) for r in results)


def test_evaluate_stops_at_the_first_rejection_and_never_calls_later_validators():
    class ExplodingValidator:
        name = "should_never_run"

        def check(self, *args, **kwargs):
            raise AssertionError("this validator must never be called after a rejection")

    engine = RiskEngine([KillSwitchValidator(), ExplodingValidator()])
    results = engine.evaluate(_candidate(), _policy(), _account(kill_switch_active=True))

    assert len(results) == 1
    assert results[0].status == RiskCheckStatus.REJECT
    assert results[0].validator_name == "kill_switch"


def test_a_resize_is_not_buried_by_a_later_approve():
    """The bug this pipeline's first draft actually had: PositionSizeValidator
    isn't last in the default order, so a RESIZE followed by later
    APPROVEs must still surface as an overall RESIZE via overall_status(),
    not silently read as a plain APPROVE off results[-1]."""
    engine = default_risk_engine()
    results = engine.evaluate(
        _candidate(tier=Tier.A, entry=100.0, stop_loss=95.0),
        _policy(min_tier=Tier.B, risk_percent=1.0, max_contracts=1),
        _account(equity=1_000_000.0),
    )
    # PositionSizeValidator itself did resize...
    assert any(r.validator_name == "position_size" and r.status == RiskCheckStatus.RESIZE for r in results)
    # ...but is not the last validator to run (account_rules runs after it)
    assert results[-1].validator_name != "position_size"
    # overall_status must still report the resize, not the trailing APPROVE
    assert overall_status(results) == RiskCheckStatus.RESIZE
    assert effective_quantity(results) == 1


def test_overall_status_is_reject_if_any_validator_rejected_regardless_of_position():
    engine = RiskEngine([KillSwitchValidator()])
    results = engine.evaluate(_candidate(), _policy(), _account(kill_switch_active=True))
    assert overall_status(results) == RiskCheckStatus.REJECT


def test_overall_status_is_approve_when_nothing_rejects_or_resizes():
    engine = default_risk_engine()
    results = engine.evaluate(
        _candidate(tier=Tier.A, entry=100.0, stop_loss=95.0),
        _policy(min_tier=Tier.B, risk_percent=1.0, max_contracts=10),
        _account(equity=1_000.0),
    )
    assert overall_status(results) == RiskCheckStatus.APPROVE
    assert effective_quantity(results) == 2


def test_evaluate_never_raises_for_an_ordinary_rejection():
    engine = default_risk_engine()
    # must not raise -- rejection is a normal RiskCheckResult, not an exception
    results = engine.evaluate(_candidate(), _policy(), _account(kill_switch_active=True))
    assert overall_status(results) == RiskCheckStatus.REJECT
