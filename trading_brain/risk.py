"""
Risk Module — AI Trading Brain v1, Phase 1

README rule: "Every trade must have Defined Stop Loss, Defined Take Profit,
Defined Invalidation. No trade without all three."
Stop Loss: never random -> always beyond Structure/Liquidity/Swing High/Low.
Take Profit: next liquidity, next major structure, or higher-timeframe objective.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .displacement import Direction


class RiskRejectReason(Enum):
    NO_STOP_LOSS = "No stop loss defined"
    NO_TAKE_PROFIT = "No take profit defined"
    NO_INVALIDATION = "No invalidation level defined"
    STOP_NOT_BEYOND_STRUCTURE = "Stop loss is not placed beyond a real structure/liquidity level"
    NEGATIVE_OR_ZERO_RR = "Risk/reward is zero or negative"
    RISK_EXCEEDS_REWARD = "Risk exceeds expected reward (README early-exit condition)"


@dataclass
class TradePlan:
    direction: Direction
    entry: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    invalidation_price: Optional[float]
    stop_reference_level: Optional[float] = None  # the structure/liquidity price the SL sits beyond


@dataclass
class RiskAssessment:
    valid: bool
    risk_reward_ratio: Optional[float]
    reasons_rejected: list


def validate_trade_risk(plan: TradePlan) -> RiskAssessment:
    reasons = []

    if plan.stop_loss is None:
        reasons.append(RiskRejectReason.NO_STOP_LOSS)
    if plan.take_profit is None:
        reasons.append(RiskRejectReason.NO_TAKE_PROFIT)
    if plan.invalidation_price is None:
        reasons.append(RiskRejectReason.NO_INVALIDATION)

    if reasons:
        return RiskAssessment(False, None, reasons)

    # Stop loss must sit beyond a real reference level, not be arbitrary
    if plan.stop_reference_level is None:
        reasons.append(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE)
    else:
        if plan.direction == Direction.BULLISH and plan.stop_loss >= plan.stop_reference_level:
            reasons.append(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE)
        if plan.direction == Direction.BEARISH and plan.stop_loss <= plan.stop_reference_level:
            reasons.append(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE)

    risk = abs(plan.entry - plan.stop_loss)
    reward = abs(plan.take_profit - plan.entry)

    if risk <= 0:
        reasons.append(RiskRejectReason.NEGATIVE_OR_ZERO_RR)
        rr = None
    else:
        rr = reward / risk
        # Strict: a trade with reward exactly equal to risk (1:1) is marginal,
        # not one where "risk exceeds reward" -- that claim would be false at
        # exactly 1:1, and this is the only condition that produces it.
        if reward < risk:
            reasons.append(RiskRejectReason.RISK_EXCEEDS_REWARD)

    return RiskAssessment(valid=len(reasons) == 0, risk_reward_ratio=rr, reasons_rejected=reasons)


def position_size(account_balance: float, risk_percent: float, entry: float, stop_loss: float,
                   unit_value_per_point: float = 1.0) -> float:
    """
    Basic fixed-fractional sizing: how many units to trade so that if the
    stop loss is hit, the loss equals `risk_percent` of account_balance.
    unit_value_per_point converts price-distance into account-currency terms
    (depends on instrument — e.g. pip value for forex, $/point for indices).
    """
    if risk_percent <= 0 or risk_percent > 100:
        raise ValueError("risk_percent must be between 0 and 100")
    dollar_risk = account_balance * (risk_percent / 100)
    price_distance = abs(entry - stop_loss)
    if price_distance == 0:
        raise ValueError("entry and stop_loss cannot be equal")
    return dollar_risk / (price_distance * unit_value_per_point)


def check_invalidation(current_price: float, plan: TradePlan) -> bool:
    """
    README Invalidation Rule: 'If market structure shifts against the position
    before take profit is reached: immediately re-evaluate... Exit. Do NOT hope.
    Do NOT wait for stop loss.' This checks price against the invalidation level,
    which should be tighter/earlier than the hard stop loss.
    """
    if plan.invalidation_price is None:
        return False
    if plan.direction == Direction.BULLISH:
        return current_price <= plan.invalidation_price
    return current_price >= plan.invalidation_price


def run_demo() -> None:
    # Valid plan: long entry 110, stop beyond swing low at 105, target 125 -> RR 3:1
    good_plan = TradePlan(Direction.BULLISH, entry=110, stop_loss=104.5, take_profit=125,
                           invalidation_price=106, stop_reference_level=105)
    result = validate_trade_risk(good_plan)
    print("=== Good Plan ===")
    print(f"  valid={result.valid}  RR={result.risk_reward_ratio:.2f}  reasons={result.reasons_rejected}")

    size = position_size(account_balance=10_000, risk_percent=1, entry=110, stop_loss=104.5)
    print(f"  position size for 1% risk on $10,000: {size:.2f} units")

    # Bad plan: no invalidation, stop is random (not beyond any structure), poor RR
    bad_plan = TradePlan(Direction.BULLISH, entry=110, stop_loss=108, take_profit=112,
                          invalidation_price=None, stop_reference_level=None)
    bad_result = validate_trade_risk(bad_plan)
    print("\n=== Bad Plan ===")
    print(f"  valid={bad_result.valid}")
    for r in bad_result.reasons_rejected:
        print(f"    - {r.value}")

    # Exactly 1:1 RR, everything else valid -> marginal, not "risk exceeds reward"
    breakeven_plan = TradePlan(Direction.BULLISH, entry=110, stop_loss=105, take_profit=115,
                                invalidation_price=107, stop_reference_level=105.5)
    breakeven_result = validate_trade_risk(breakeven_plan)
    print("\n=== Exactly 1:1 RR ===")
    print(f"  valid={breakeven_result.valid}  RR={breakeven_result.risk_reward_ratio:.2f}  "
          f"reasons={breakeven_result.reasons_rejected}")

    print("\n=== Invalidation Check ===")
    print(f"  price=105.5 -> invalidated? {check_invalidation(105.5, good_plan)}")
    print(f"  price=108.0 -> invalidated? {check_invalidation(108.0, good_plan)}")


if __name__ == "__main__":
    run_demo()
