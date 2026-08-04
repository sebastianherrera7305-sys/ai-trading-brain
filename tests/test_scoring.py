"""Tests for the Scoring module (AI Trading Brain v1, Phase 1)."""

import unittest

from trading_brain.scoring import (
    ChecklistInputs,
    Tier,
    compute_confidence_score,
    evaluate_checklist,
    score_setup,
    tier_from_score,
)


def inputs(**overrides):
    defaults = dict(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=True, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    defaults.update(overrides)
    return ChecklistInputs(**defaults)


class TestEvaluateChecklist(unittest.TestCase):
    def test_all_true_passes(self):
        passed, failed = evaluate_checklist(inputs())
        self.assertTrue(passed)
        self.assertEqual(failed, [])

    def test_one_false_fails(self):
        passed, failed = evaluate_checklist(inputs(fvg_valid=False))
        self.assertFalse(passed)
        self.assertEqual(failed, ["fvg_valid"])

    def test_multiple_false_are_all_listed(self):
        passed, failed = evaluate_checklist(inputs(fvg_valid=False, clean_entry=False))
        self.assertFalse(passed)
        self.assertEqual(set(failed), {"fvg_valid", "clean_entry"})

    def test_none_fails_the_checklist(self):
        # Regression: a condition that's None (an upstream check that never ran)
        # must reject just as hard as an explicit False -- the README's rule is
        # "if even ONE fails, reject... no exceptions," and None is not a pass.
        passed, failed = evaluate_checklist(inputs(no_major_news=None))
        self.assertFalse(passed)
        self.assertEqual(failed, ["no_major_news"])


class TestComputeConfidenceScore(unittest.TestCase):
    def test_all_true_scores_100(self):
        self.assertEqual(compute_confidence_score(inputs()), 100)

    def test_missing_condition_subtracts_its_weight(self):
        self.assertEqual(compute_confidence_score(inputs(fvg_valid=False)), 85)

    def test_none_scores_the_same_as_false(self):
        # None isn't True, so it earns no points -- same as False -- even though
        # it's evaluated as a harder failure by evaluate_checklist above.
        self.assertEqual(compute_confidence_score(inputs(no_major_news=None)),
                         compute_confidence_score(inputs(no_major_news=False)))


class TestTierFromScore(unittest.TestCase):
    def test_failed_checklist_is_always_reject_regardless_of_score(self):
        self.assertEqual(tier_from_score(100, checklist_passed=False), Tier.REJECT)

    def test_s_tier_threshold(self):
        self.assertEqual(tier_from_score(90, checklist_passed=True), Tier.S)

    def test_a_tier_threshold(self):
        self.assertEqual(tier_from_score(75, checklist_passed=True), Tier.A)

    def test_b_tier_threshold(self):
        self.assertEqual(tier_from_score(60, checklist_passed=True), Tier.B)

    def test_below_b_is_reject(self):
        self.assertEqual(tier_from_score(59, checklist_passed=True), Tier.REJECT)


class TestScoreSetup(unittest.TestCase):
    def test_strong_setup_is_s_tier(self):
        result = score_setup(inputs())
        self.assertTrue(result.checklist_passed)
        self.assertEqual(result.confidence_score, 100)
        self.assertEqual(result.tier, Tier.S)

    def test_one_failed_condition_rejects_even_with_a_high_score(self):
        result = score_setup(inputs(fvg_valid=False))
        self.assertFalse(result.checklist_passed)
        self.assertEqual(result.confidence_score, 85)  # score is still reported...
        self.assertEqual(result.tier, Tier.REJECT)      # ...but tier is forced to REJECT

    def test_unconfirmed_condition_is_rejected_not_scored_through(self):
        result = score_setup(inputs(no_major_news=None))
        self.assertFalse(result.checklist_passed)
        self.assertEqual(result.tier, Tier.REJECT)
        self.assertEqual(result.failed_conditions, ["no_major_news"])


if __name__ == "__main__":
    unittest.main()
