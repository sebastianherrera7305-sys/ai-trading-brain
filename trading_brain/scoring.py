"""
Scoring Module — AI Trading Brain v1, Phase 1
The final assembly point: combines every other module's output into the
README's Mandatory Checklist, a 0-100 Confidence Score, and an S/A/B/Reject tier.

README: "Every trade MUST satisfy these conditions. If even ONE fails, reject.
Every trade receives 0-100. Execute only if Score >= Required Threshold."
"""

from dataclasses import dataclass
from enum import Enum


class Tier(Enum):
    S = "S Tier — Nearly perfect, execute immediately"
    A = "A Tier — Excellent, execute"
    B = "B Tier — Good, execute"
    REJECT = "Below B — DO NOT TRADE"


# Public and singular on purpose: this ranking was duplicated as a
# private _TIER_RANK dict in strategy.py and walk_forward.py -- exactly
# the "second hand-written copy that can silently drift" pattern this
# codebase otherwise takes care to avoid (see backtest.py's own
# find_candidate_order extraction history). Risk Engine (Subsystem 3)
# needed the same ranking a third time, which is what surfaced this.
TIER_RANK = {Tier.REJECT: 0, Tier.B: 1, Tier.A: 2, Tier.S: 3}


def meets_tier_floor(tier: Tier, floor: Tier) -> bool:
    return TIER_RANK[tier] >= TIER_RANK[floor]


@dataclass
class ChecklistInputs:
    """One boolean per README mandatory condition. All must be True to even
    be eligible for a tier -- this mirrors 'if even ONE fails, reject trade.'"""
    market_structure_confirmed: bool      # from market_structure.py: BOS in trade direction
    liquidity_present: bool                # from liquidity.py: a real level was identified
    trend_alignment: bool                  # trade direction matches determine_trend()
    displacement_confirmed: bool           # from displacement.py: qualifying aggressive move
    fvg_valid: bool                        # from fair_value_gap.py: passed all 4 conditions
    clean_entry: bool                      # entry price actually reachable / not chasing
    risk_management_defined: bool          # from risk.py: validate_trade_risk().valid
    session_time_ok: bool                  # from sessions.py: is_allowed_to_trade()
    no_major_news: bool                    # external calendar check (not modeled here yet)


@dataclass
class ScoreBreakdown:
    checklist_passed: bool
    failed_conditions: list
    confidence_score: int  # 0-100
    tier: Tier


# Confidence score weights — how much each factor contributes when present.
# These are tunable parameters, not README-mandated numbers; adjust based on
# what backtesting later shows actually correlates with win rate.
_WEIGHTS = {
    "market_structure_confirmed": 15,
    "liquidity_present": 10,
    "trend_alignment": 15,
    "displacement_confirmed": 15,
    "fvg_valid": 15,
    "clean_entry": 10,
    "risk_management_defined": 10,
    "session_time_ok": 5,
    "no_major_news": 5,
}
assert sum(_WEIGHTS.values()) == 100

# Tunable thresholds
S_TIER_THRESHOLD = 90
A_TIER_THRESHOLD = 75
B_TIER_THRESHOLD = 60  # README's minimum: "Anything below B -> DO NOT TRADE"


def evaluate_checklist(inputs: ChecklistInputs) -> tuple:
    """Returns (all_passed: bool, list of failed field names).

    Anything that isn't exactly True fails -- not just an explicit False. The
    README's own rule is "if even ONE fails, reject... no exceptions," and this
    module is the last gate before a trade fires; a field that's None because
    some upstream check never ran must reject just as hard as one that actively
    came back False, not sail through as if it silently didn't count.
    """
    failed = [field_name for field_name, value in inputs.__dict__.items() if value is not True]
    return len(failed) == 0, failed


def compute_confidence_score(inputs: ChecklistInputs) -> int:
    return sum(_WEIGHTS[name] for name, value in inputs.__dict__.items() if value is True)


def tier_from_score(score: int, checklist_passed: bool) -> Tier:
    if not checklist_passed:
        return Tier.REJECT  # README: one failed mandatory condition = automatic reject, no exceptions
    if score >= S_TIER_THRESHOLD:
        return Tier.S
    if score >= A_TIER_THRESHOLD:
        return Tier.A
    if score >= B_TIER_THRESHOLD:
        return Tier.B
    return Tier.REJECT


def score_setup(inputs: ChecklistInputs) -> ScoreBreakdown:
    passed, failed = evaluate_checklist(inputs)
    score = compute_confidence_score(inputs)
    tier = tier_from_score(score, passed)
    return ScoreBreakdown(passed, failed, score, tier)


def run_demo() -> None:
    # Case 1: everything lines up -> should be S or A tier
    strong_setup = ChecklistInputs(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=True, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    result = score_setup(strong_setup)
    print("=== Strong Setup ===")
    print(f"  checklist_passed={result.checklist_passed}  score={result.confidence_score}  tier={result.tier.value}")

    # Case 2: one mandatory condition fails (no FVG) -> automatic reject regardless of score
    weak_setup = ChecklistInputs(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=False, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    result2 = score_setup(weak_setup)
    print("\n=== Missing FVG ===")
    print(f"  checklist_passed={result2.checklist_passed}  score={result2.confidence_score}  "
          f"tier={result2.tier.value}  failed={result2.failed_conditions}")

    # Case 3: borderline B-tier
    ok_setup = ChecklistInputs(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=False, clean_entry=False,
        risk_management_defined=True, session_time_ok=True, no_major_news=True,
    )
    # note: this actually fails checklist too (fvg + clean_entry both False) -> intentionally reject
    result3 = score_setup(ok_setup)
    print("\n=== Borderline (multiple gaps) ===")
    print(f"  checklist_passed={result3.checklist_passed}  score={result3.confidence_score}  tier={result3.tier.value}")

    # Case 4: an upstream check that never ran -- None, not False. Must still reject.
    unknown_setup = ChecklistInputs(
        market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
        displacement_confirmed=True, fvg_valid=True, clean_entry=True,
        risk_management_defined=True, session_time_ok=True, no_major_news=None,
    )
    result4 = score_setup(unknown_setup)
    print("\n=== Unconfirmed Condition (None, not False) ===")
    print(f"  checklist_passed={result4.checklist_passed}  score={result4.confidence_score}  "
          f"tier={result4.tier.value}  failed={result4.failed_conditions}")


if __name__ == "__main__":
    run_demo()
