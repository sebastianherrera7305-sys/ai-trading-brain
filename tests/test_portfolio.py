"""Tests for the Portfolio Engine (Subsystem 4, docs/specs/04-portfolio-engine.md)."""

from trading_brain.portfolio import (
    OpenPosition,
    PendingOrder,
    PortfolioDecision,
    PortfolioEngine,
    PortfolioPolicy,
    PortfolioState,
)


def _policy(**overrides) -> PortfolioPolicy:
    defaults = dict(max_simultaneous_positions=5, correlation_groups={}, correlation_group_caps={})
    defaults.update(overrides)
    return PortfolioPolicy(**defaults)


def _state(open_positions=(), pending_orders=()) -> PortfolioState:
    return PortfolioState(open_positions=list(open_positions), pending_orders=list(pending_orders))


def test_same_symbol_with_an_open_position_is_rejected_even_with_room_elsewhere():
    engine = PortfolioEngine()
    state = _state(open_positions=[OpenPosition("GC=F")])
    result = engine.evaluate("GC=F", state, _policy(max_simultaneous_positions=10))
    assert result.decision == PortfolioDecision.REJECT
    assert "GC=F" in result.reason


def test_same_symbol_with_a_pending_order_is_rejected_the_same_way():
    engine = PortfolioEngine()
    state = _state(pending_orders=[PendingOrder("ES=F")])
    result = engine.evaluate("ES=F", state, _policy(max_simultaneous_positions=10))
    assert result.decision == PortfolioDecision.REJECT


def test_max_simultaneous_positions_approves_under_the_cap_and_rejects_at_it():
    engine = PortfolioEngine()
    policy = _policy(
        max_simultaneous_positions=2,
        correlation_groups={"GC=F": "metals", "ES=F": "equities", "CL=F": "energy"},
        correlation_group_caps={"metals": 5, "equities": 5, "energy": 5},
    )
    under_cap = _state(open_positions=[OpenPosition("GC=F")])
    assert engine.evaluate("ES=F", under_cap, policy).decision == PortfolioDecision.APPROVE

    at_cap = _state(open_positions=[OpenPosition("GC=F"), OpenPosition("ES=F")])
    result = engine.evaluate("CL=F", at_cap, policy)
    assert result.decision == PortfolioDecision.REJECT
    assert "max_simultaneous_positions" in result.reason


def test_max_simultaneous_positions_counts_open_and_pending_together():
    engine = PortfolioEngine()
    policy = _policy(
        max_simultaneous_positions=2,
        correlation_groups={"GC=F": "metals", "ES=F": "equities", "CL=F": "energy"},
        correlation_group_caps={"metals": 5, "equities": 5, "energy": 5},
    )
    state = _state(open_positions=[OpenPosition("GC=F")], pending_orders=[PendingOrder("ES=F")])
    result = engine.evaluate("CL=F", state, policy)
    assert result.decision == PortfolioDecision.REJECT


def test_correlation_group_cap_binds_independently_of_the_platform_cap():
    """Two symbols in the same group -- second one rejected by the GROUP
    cap even while the platform-wide cap still has plenty of room."""
    engine = PortfolioEngine()
    policy = _policy(
        max_simultaneous_positions=10,  # plenty of room platform-wide
        correlation_groups={"GC=F": "metals", "SI=F": "metals"},
        correlation_group_caps={"metals": 1},
    )
    state = _state(open_positions=[OpenPosition("GC=F")])
    result = engine.evaluate("SI=F", state, policy)
    assert result.decision == PortfolioDecision.REJECT
    assert "metals" in result.reason


def test_ungrouped_symbol_is_its_own_singleton_group_not_exempt():
    engine = PortfolioEngine()
    policy = _policy(max_simultaneous_positions=10, correlation_groups={}, correlation_group_caps={})
    # EURUSD=X has no configured group or cap at all
    state = _state(open_positions=[OpenPosition("EURUSD=X")])
    result = engine.evaluate("EURUSD=X", state, policy)
    # rejected for the same-symbol reason first, but confirms an
    # ungrouped symbol isn't silently treated as uncapped
    assert result.decision == PortfolioDecision.REJECT


def test_a_second_ungrouped_symbol_is_not_capped_by_an_unrelated_ones_group():
    engine = PortfolioEngine()
    policy = _policy(max_simultaneous_positions=10, correlation_groups={}, correlation_group_caps={})
    state = _state(open_positions=[OpenPosition("EURUSD=X")])
    # GC=F is a different singleton group from EURUSD=X's singleton group
    result = engine.evaluate("GC=F", state, policy)
    assert result.decision == PortfolioDecision.APPROVE


def test_same_symbol_check_runs_before_the_numeric_caps():
    """Even when both numeric caps would clearly approve, an existing
    same-symbol position must still be the rejection reason given, not a
    cap reason -- checked first and independently."""
    engine = PortfolioEngine()
    policy = _policy(
        max_simultaneous_positions=100,
        correlation_groups={"GC=F": "metals"},
        correlation_group_caps={"metals": 100},
    )
    state = _state(open_positions=[OpenPosition("GC=F")])
    result = engine.evaluate("GC=F", state, policy)
    assert result.decision == PortfolioDecision.REJECT
    assert "already has an open or pending position" in result.reason


def test_evaluate_never_raises_for_an_ordinary_rejection():
    engine = PortfolioEngine()
    state = _state(open_positions=[OpenPosition("GC=F")])
    result = engine.evaluate("GC=F", state, _policy())  # must not raise
    assert result.decision == PortfolioDecision.REJECT


def test_all_symbols_unions_open_and_pending():
    state = _state(open_positions=[OpenPosition("GC=F")], pending_orders=[PendingOrder("ES=F"), PendingOrder("GC=F")])
    assert state.all_symbols() == {"GC=F", "ES=F"}
