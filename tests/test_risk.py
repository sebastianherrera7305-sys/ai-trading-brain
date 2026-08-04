"""Tests for the Risk module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.displacement import Direction
from trading_brain.risk import (
    RiskRejectReason,
    TradePlan,
    check_invalidation,
    position_size,
    validate_trade_risk,
)


def plan(**overrides):
    defaults = dict(
        direction=Direction.BULLISH, entry=110, stop_loss=104.5, take_profit=125,
        invalidation_price=106, stop_reference_level=105,
    )
    defaults.update(overrides)
    return TradePlan(**defaults)


class TestValidateTradeRisk(unittest.TestCase):
    def test_good_plan_is_valid(self):
        result = validate_trade_risk(plan())
        self.assertTrue(result.valid)
        self.assertAlmostEqual(result.risk_reward_ratio, 15 / 5.5)
        self.assertEqual(result.reasons_rejected, [])

    def test_missing_stop_loss(self):
        result = validate_trade_risk(plan(stop_loss=None))
        self.assertFalse(result.valid)
        self.assertIn(RiskRejectReason.NO_STOP_LOSS, result.reasons_rejected)

    def test_missing_take_profit(self):
        result = validate_trade_risk(plan(take_profit=None))
        self.assertIn(RiskRejectReason.NO_TAKE_PROFIT, result.reasons_rejected)

    def test_missing_invalidation(self):
        result = validate_trade_risk(plan(invalidation_price=None))
        self.assertIn(RiskRejectReason.NO_INVALIDATION, result.reasons_rejected)

    def test_missing_core_fields_skips_rr_entirely(self):
        result = validate_trade_risk(plan(stop_loss=None))
        self.assertIsNone(result.risk_reward_ratio)

    def test_stop_not_beyond_structure_bullish(self):
        # stop_loss sits ABOVE the reference level -- not beyond it for a long.
        result = validate_trade_risk(plan(stop_loss=106, stop_reference_level=105))
        self.assertIn(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE, result.reasons_rejected)

    def test_stop_not_beyond_structure_bearish(self):
        result = validate_trade_risk(plan(
            direction=Direction.BEARISH, entry=110, stop_loss=104, take_profit=95,
            invalidation_price=108, stop_reference_level=105,
        ))
        self.assertIn(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE, result.reasons_rejected)

    def test_no_stop_reference_level_fails(self):
        result = validate_trade_risk(plan(stop_reference_level=None))
        self.assertIn(RiskRejectReason.STOP_NOT_BEYOND_STRUCTURE, result.reasons_rejected)

    def test_zero_risk_is_rejected(self):
        result = validate_trade_risk(plan(entry=110, stop_loss=110, stop_reference_level=109))
        self.assertIn(RiskRejectReason.NEGATIVE_OR_ZERO_RR, result.reasons_rejected)
        self.assertIsNone(result.risk_reward_ratio)

    def test_reward_less_than_risk_is_rejected(self):
        result = validate_trade_risk(plan(entry=110, stop_loss=105, take_profit=113,
                                           stop_reference_level=105.5))
        self.assertIn(RiskRejectReason.RISK_EXCEEDS_REWARD, result.reasons_rejected)

    def test_exactly_1_to_1_rr_is_not_flagged_as_exceeding(self):
        # Regression: reward == risk was previously rejected with "risk EXCEEDS
        # reward," which is false at exact parity.
        result = validate_trade_risk(plan(entry=110, stop_loss=105, take_profit=115,
                                           stop_reference_level=105.5))
        self.assertAlmostEqual(result.risk_reward_ratio, 1.0)
        self.assertNotIn(RiskRejectReason.RISK_EXCEEDS_REWARD, result.reasons_rejected)
        self.assertTrue(result.valid)


class TestPositionSize(unittest.TestCase):
    def test_basic_sizing(self):
        size = position_size(account_balance=10_000, risk_percent=1, entry=110, stop_loss=104.5)
        self.assertAlmostEqual(size, 100 / 5.5)

    def test_invalid_risk_percent_raises(self):
        with self.assertRaises(ValueError):
            position_size(account_balance=10_000, risk_percent=0, entry=110, stop_loss=104.5)
        with self.assertRaises(ValueError):
            position_size(account_balance=10_000, risk_percent=101, entry=110, stop_loss=104.5)

    def test_equal_entry_and_stop_raises(self):
        with self.assertRaises(ValueError):
            position_size(account_balance=10_000, risk_percent=1, entry=110, stop_loss=110)


class TestCheckInvalidation(unittest.TestCase):
    def test_bullish_invalidated_below_level(self):
        p = plan(direction=Direction.BULLISH, invalidation_price=106)
        self.assertTrue(check_invalidation(105.5, p))
        self.assertFalse(check_invalidation(108, p))

    def test_bearish_invalidated_above_level(self):
        p = plan(direction=Direction.BEARISH, entry=110, stop_loss=115, take_profit=95,
                  invalidation_price=112, stop_reference_level=116)
        self.assertTrue(check_invalidation(113, p))
        self.assertFalse(check_invalidation(109, p))

    def test_no_invalidation_price_never_invalidates(self):
        p = plan(invalidation_price=None)
        self.assertFalse(check_invalidation(0, p))


if __name__ == "__main__":
    unittest.main()
