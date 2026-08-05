"""probability — binomial math, Kelly, expected value, Bayesian
Beta-Bernoulli updating, credible intervals, Brier score, Wald SPRT.

The decision-theoretic layer: everything that turns observed trade
outcomes into "should we still believe the edge exists" statements
(docs/research/05, sections 2.7-2.8).
"""

import math
from typing import Dict, Optional, Tuple

import numpy as np

from ._input import as_binary, as_float_array, check_min
from .statistics import normal_cdf, normal_inv_cdf, regularized_incomplete_beta

__all__ = [
    "binomial_pmf",
    "binomial_cdf",
    "binomial_ci",
    "beta_cdf",
    "beta_inv_cdf",
    "beta_mean",
    "beta_var",
    "beta_posterior",
    "probability_edge_above",
    "expected_value",
    "kelly_fraction",
    "fractional_kelly",
    "kelly_expected_growth",
    "brier_score",
    "brier_skill_score",
    "sprt_bernoulli",
    "sprt_expected_sample_size",
    "normal_power",
]


# ---------------------------------------------------------------------------
# Binomial
# ---------------------------------------------------------------------------

def binomial_pmf(k: int, n: int, p: float) -> float:
    """P(X = k) for X ~ Binomial(n, p).

    Definition
        C(n,k) p^k (1-p)^(n-k), evaluated in log space
        (lgamma differences) to avoid overflow for large n. Exact for
        the small trade counts this package works with.

    Raises
        ValueError if p not in [0, 1]. k < 0 or k > n return 0.0 (an
        impossible event, not an error).

    Complexity
        O(1).

    Examples
        >>> round(binomial_pmf(5, 10, 0.5), 6)
        0.246094
        >>> binomial_pmf(-1, 10, 0.5)
        0.0
    """
    if not (0 <= p <= 1):
        raise ValueError("p must be in [0, 1]")
    if k < 0 or k > n:
        return 0.0
    if p == 0.0:
        return 1.0 if k == 0 else 0.0
    if p == 1.0:
        return 1.0 if k == n else 0.0
    log_like = (
        math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
        + k * math.log(p) + (n - k) * math.log1p(-p)
    )
    return math.exp(log_like)


def binomial_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p).

    Definition
        Sum of PMFs from 0 to k — exact, and cheap because n here is a
        trade count, not a scientific-sample count. k < 0 gives 0.0;
        k >= n gives 1.0.

    Complexity
        O(min(k, n)) time, O(1) memory.

    Examples
        >>> round(binomial_cdf(4, 10, 0.5), 6)
        0.376953
    """
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(binomial_pmf(j, n, p) for j in range(0, int(k) + 1))


def binomial_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Exact (Clopper-Pearson) two-sided confidence interval for a
    success probability.

    Definition
        The exact binomial interval via the beta identity
        (Clopper-Pearson 1934): the honest interval for a win rate on
        a small trade count — the normal approximation is not.
        Boundary successes (k=0 or k=n) give 0.0 / 1.0 endpoints
        respectively.

    Raises
        ValueError if confidence not in (0, 1) or n < 1.

    Complexity
        O(200) beta-CDF evaluations (bisection).

    References
        Clopper & Pearson (1934), "The use of confidence or fiducial
        limits illustrated in the case of the binomial", Biometrika 26.

    Examples
        >>> lo, hi = binomial_ci(5, 10, 0.95)
        >>> round(lo, 6), round(hi, 6)
        (0.187086, 0.812914)
    """
    if not (0.0 < confidence < 1.0):
        raise ValueError("confidence must be in (0, 1)")
    if n <= 0:
        raise ValueError("n must be >= 1")
    alpha = (1.0 - confidence) / 2.0
    lo = 0.0 if k == 0 else beta_inv_cdf(alpha, k, n - k + 1)
    hi = 1.0 if k == n else beta_inv_cdf(1.0 - alpha, k + 1, n - k)
    return lo, hi


# ---------------------------------------------------------------------------
# Beta distribution (conjugate prior for Bernoulli win rates)
# ---------------------------------------------------------------------------

def beta_cdf(x: float, a: float, b: float) -> float:
    """P(X <= x) for X ~ Beta(a, b).

    Definition
        The regularized incomplete beta function I_x(a, b); the
        conjugate-prior CDF for Bernoulli win rates.

    Raises
        ValueError if a <= 0 or b <= 0.

    Complexity
        O(max_iter) on the 2F1 series kernel.

    Examples
        >>> round(beta_cdf(0.5, 2, 2), 9)
        0.5
    """
    return regularized_incomplete_beta(x, a, b)


def beta_inv_cdf(p: float, a: float, b: float) -> float:
    """Quantile of Beta(a, b): x with P(X <= x) = p.

    Definition
        Deterministic bisection on beta_cdf — 200 halvings bring the
        bracket below float precision on [0, 1].

    Raises
        ValueError if p not in [0, 1], a <= 0 or b <= 0.

    Complexity
        O(200) beta-CDF evaluations.

    Examples
        >>> round(beta_inv_cdf(0.5, 2, 2), 6)
        0.5
        >>> round(beta_inv_cdf(1.0 / 3.0, 0.5, 0.5), 6)
        0.25
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1]")
    if p == 0.0:
        return 0.0
    if p == 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if beta_cdf(mid, a, b) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def beta_mean(a: float, b: float) -> float:
    """E[X] = a / (a + b) for X ~ Beta(a, b).

    Complexity
        O(1).

    Examples
        >>> beta_mean(2.0, 3.0)
        0.4
    """
    return a / (a + b)


def beta_var(a: float, b: float) -> float:
    """Var[X] = ab / ((a+b)^2 (a+b+1)) for X ~ Beta(a, b).

    Complexity
        O(1).

    Examples
        >>> round(beta_var(2.0, 3.0), 4)
        0.04
    """
    s = a + b
    return a * b / (s * s * (s + 1.0))


def beta_posterior(
    prior_alpha: float, prior_beta: float, successes: int, failures: int
) -> Tuple[float, float]:
    """Beta-Bernoulli conjugate update: Beta(a + k, b + n - k).

    Definition
        Posterior parameters after observing `successes` wins and
        `failures` losses under a Beta(prior_alpha, prior_beta) prior
        on the win rate.

    Complexity
        O(1).

    Examples
        >>> beta_posterior(1.0, 1.0, 8, 2)
        (9.0, 3.0)
    """
    return prior_alpha + successes, prior_beta + failures


def probability_edge_above(
    successes: int,
    failures: int,
    threshold: float = 0.5,
    prior_alpha: float = 1.0,
    prior_beta: float = 1.0,
) -> float:
    """P(true win rate > threshold | data) under the Beta-Bernoulli
    model.

    Definition
        1 - beta_cdf(threshold, a + k, b + n - k) — the Bayesian
        answer to "is there still an edge?" and the central readout of
        the Edge Monitor (docs/research/05 section 2.7). A Uniform(0,1)
        prior (a = b = 1) is the default.

    Complexity
        O(max_iter) on the beta kernel.

    Examples
        >>> round(probability_edge_above(8, 2), 4)
        0.9673
    """
    a, b = beta_posterior(prior_alpha, prior_beta, successes, failures)
    return 1.0 - beta_cdf(threshold, a, b)


# ---------------------------------------------------------------------------
# Expected value and Kelly
# ---------------------------------------------------------------------------

def expected_value(p: float, gain: float, loss: float) -> float:
    """EV of a unit bet: p * gain - (1 - p) * loss.

    Definition
        E[X] for a bet that pays `gain` with probability p and loses
        `loss` otherwise. Positive EV is the necessary (not sufficient)
        condition for a tradeable edge.

    Raises
        ValueError if p not in [0, 1].

    Complexity
        O(1).

    Examples
        >>> round(expected_value(0.6, 1.0, 1.0), 6)
        0.2
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1]")
    return p * gain - (1.0 - p) * loss


def kelly_fraction(p: float, b: float) -> float:
    """Full Kelly fraction: f* = (bp - (1-p)) / b.

    Definition
        The fraction of capital that maximizes expected log growth for
        a bet paying b:1 with win probability p (Kelly 1956; Thorp's
        betting formulation). Returns 0.0 for non-positive-edge bets
        (no growth-optimal bet exists); raises for degenerate inputs.

    Raises
        ValueError if p not in (0, 1) or b <= 0.

    Complexity
        O(1).

    References
        J. L. Kelly (1956), "A New Interpretation of Information Rate",
        Bell System Technical Journal 35.

    Examples
        >>> round(kelly_fraction(0.6, 1.0), 6)
        0.2
        >>> kelly_fraction(0.4, 1.0)
        0.0
    """
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    if b <= 0:
        raise ValueError("b must be > 0")
    edge = b * p - (1.0 - p)
    return max(edge / b, 0.0)


def fractional_kelly(p: float, b: float, fraction: float) -> float:
    """fraction * full Kelly.

    Definition
        f = fraction * f*; fraction in (0, 1]. 0.25 is the classic
        conservative choice for live sizing (lower growth, far lower
        drawdown risk; see MacLean-Thorp-Ziemba on fractional Kelly).

    Raises
        ValueError if fraction not in (0, 1].

    Complexity
        O(1).

    Examples
        >>> round(fractional_kelly(0.6, 1.0, 0.25), 6)
        0.05
    """
    if not (0.0 < fraction <= 1.0):
        raise ValueError("fraction must be in (0, 1]")
    return fraction * kelly_fraction(p, b)


def kelly_expected_growth(p: float, b: float, f: float) -> float:
    """Expected log growth rate E[log(1 + f*X)] for a bet sized at f.

    Definition
        p * log(1 + f*b) + (1 - p) * log(1 - f) for a b:1 bet with win
        probability p. As a function of f the maximum sits exactly at
        the Kelly fraction; f beyond the point where the loser's term
        goes to 0 (f >= 1) returns -inf (certain ruin).

    Raises
        ValueError if p not in [0, 1], or b <= 0, or f <= 0.

    Complexity
        O(1).

    Examples
        >>> round(kelly_expected_growth(0.6, 1.0, 0.2), 6)
        0.020136
    """
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1]")
    if b <= 0 or f <= 0:
        raise ValueError("b and f must be > 0")
    if 1.0 + f * b <= 0.0 or 1.0 - f <= 0.0:
        return float("-inf")
    return p * math.log(1.0 + f * b) + (1.0 - p) * math.log(1.0 - f)


# ---------------------------------------------------------------------------
# Probabilistic calibration and scoring
# ---------------------------------------------------------------------------

def brier_score(probabilities: np.ndarray, outcomes: np.ndarray) -> float:
    """Brier score: mean squared error of probability forecasts.

    Definition
        BS = E[(p_i - y_i)^2] for binary outcomes y in {0, 1}. 0 =
        perfect; 0.25 = always predicting 0.5; 1 = always wrong with
        certainty. The calibration component of every probabilistic
        model output this package scores.

    Raises
        ValueError if the arrays differ in length, or outcomes are not
        0/1.

    Complexity
        O(n) time, O(n) memory.

    References
        G. Brier (1950), "Verification of forecasts expressed in terms
        of probability", Monthly Weather Review 78.

    Examples
        >>> import numpy as np
        >>> round(brier_score(np.array([0.7, 0.2, 0.1]),
        ...                   np.array([1.0, 0.0, 0.0])), 6)
        0.046667
    """
    p = as_float_array(probabilities, "probabilities")
    y = as_binary(outcomes, "outcomes")
    if p.shape != y.shape:
        raise ValueError("probabilities and outcomes must have equal shape")
    if len(p) == 0:
        raise ValueError("probabilities must not be empty")
    return float(np.mean((p - y) ** 2))


def brier_skill_score(
    probabilities: np.ndarray,
    outcomes: np.ndarray,
    climatology: Optional[float] = None,
) -> float:
    """Brier Skill Score: 1 - BS_model / BS_climatology.

    Definition
        Positive = better than predicting the constant base rate;
        climatology defaults to the sample mean win rate. Perfect
        forecast scores 1.0, a tie with the base rate scores 0.0, and
        worse-than-base-rate forecasts go negative.

    Raises
        ValueError if the arrays differ in length, or outcomes are not
        0/1.

    Complexity
        O(n) time, O(n) memory.

    References
        Wilks (2011), Statistical Methods in the Atmospheric Sciences,
        §8.5.2 (Brier Skill Score).

    Examples
        >>> import numpy as np
        >>> round(brier_skill_score(np.array([1.0, 1.0, 0.0]),
        ...                         np.array([1.0, 1.0, 0.0])), 4)
        1.0
    """
    p = as_float_array(probabilities, "probabilities")
    y = as_binary(outcomes, "outcomes")
    if p.shape != y.shape:
        raise ValueError("probabilities and outcomes must have equal shape")
    if len(y) == 0:
        raise ValueError("probabilities must not be empty")
    if climatology is None:
        climatology = float(np.mean(y))
    b_model = brier_score(p, y)
    b_clim = brier_score(np.full_like(y, climatology), y)
    if b_clim == 0.0:
        return 0.0
    return 1.0 - b_model / b_clim


# ---------------------------------------------------------------------------
# Wald SPRT — sequential edge monitoring (docs/research/05 section 2.8)
# ---------------------------------------------------------------------------

def sprt_bernoulli(
    outcomes: np.ndarray,
    p0: float,
    p1: float,
    alpha: float = 0.05,
    beta: float = 0.05,
) -> Dict[str, float]:
    """Wald's Sequential Probability Ratio Test for Bernoulli outcomes.

    Definition
        Tests H0: p = p0 (edge dead / at threshold) vs H1: p = p1
        (edge alive) with type-I error alpha and type-II error beta.
        Returns a dict with:

        - llr_path: cumulative log-likelihood ratio after each trade
        - upper_bound: ln((1-beta)/alpha) — accept H1 above this
        - lower_bound: ln(beta/(1-alpha)) — accept H0 below this
        - decision: "continue" | "accept_edge" | "reject_edge" (the
          first boundary crossed, Wald's stopping rule)
        - final_llr, n

        Note: the LL ratio is compared after every trade, so the
        boundaries can be crossed mid-series; the decision reflects
        the FIRST crossing.

    Raises
        ValueError if outcomes are not 0/1, p0/p1 not in
        0 < p0 < p1 < 1, or alpha/beta not in (0, 1).

    Complexity
        O(n) time, O(n) memory.

    References
        A. Wald (1945), "Sequential Tests of Statistical Hypotheses",
        Annals of Mathematical Statistics 16.

    Examples
        >>> import numpy as np
        >>> r = sprt_bernoulli(np.ones(17), p0=0.5, p1=0.6)
        >>> r["decision"]
        'accept_edge'
        >>> r = sprt_bernoulli(np.zeros(14), p0=0.5, p1=0.6)
        >>> r["decision"]
        'reject_edge'
    """
    outcomes = as_binary(outcomes, "outcomes")
    if not (0.0 < p0 < p1 < 1.0):
        raise ValueError("need 0 < p0 < p1 < 1")
    if not (0.0 < alpha < 1.0 and 0.0 < beta < 1.0):
        raise ValueError("alpha and beta must be in (0, 1)")

    llr_per_trade = np.where(
        outcomes == 1,
        math.log(p1 / p0),
        math.log((1.0 - p1) / (1.0 - p0)),
    )
    llr = np.cumsum(llr_per_trade)

    upper = math.log((1.0 - beta) / alpha)
    lower = math.log(beta / (1.0 - alpha))

    decision = "continue"
    hits_upper = np.flatnonzero(llr >= upper)
    hits_lower = np.flatnonzero(llr <= lower)
    if len(hits_upper) > 0 or len(hits_lower) > 0:
        first_upper = hits_upper[0] if len(hits_upper) > 0 else len(llr) + 1
        first_lower = hits_lower[0] if len(hits_lower) > 0 else len(llr) + 1
        if first_upper < first_lower:
            decision = "accept_edge"
        else:
            decision = "reject_edge"

    return {
        "llr_path": llr,
        "upper_bound": upper,
        "lower_bound": lower,
        "decision": decision,
        "final_llr": float(llr[-1]) if len(llr) else 0.0,
        "n": int(len(outcomes)),
    }


def sprt_expected_sample_size(
    p: float, p0: float, p1: float, alpha: float = 0.05, beta: float = 0.05
) -> float:
    """Wald's approximation of the expected sample size to a decision.

    Definition
        E_p[n] when the true Bernoulli probability is p (Wald 1945,
        §5.3): the design-time tool for "how many trades until the
        monitor can rule?" — inf when p sits exactly at the
        indifference point (no drift, boundaries never approached on
        average).

    Raises
        ValueError unless 0 < p0 < p1 < 1.

    Complexity
        O(1).

    References
        A. Wald (1945), "Sequential Tests of Statistical Hypotheses",
        Annals of Mathematical Statistics 16, eq. (5.12).

    Examples
        >>> round(sprt_expected_sample_size(0.6, 0.5, 0.6), 2)
        131.61
    """
    if not (0.0 < p0 < p1 < 1.0):
        raise ValueError("need 0 < p0 < p1 < 1")
    a = math.log((1.0 - beta) / alpha)
    b = math.log(beta / (1.0 - alpha))
    z = p * math.log(p1 / p0) + (1.0 - p) * math.log((1.0 - p1) / (1.0 - p0))
    # At the exact indifference point z is zero; floating-point
    # roundoff can leave a residue of ~1e-16, so test against epsilon.
    if abs(z) < 1e-15:
        return float("inf")
    if z > 0:
        return ((1.0 - beta) * a + beta * b) / z
    return ((1.0 - alpha) * b + alpha * a) / z


def normal_power(
    effect: float, sigma: float, n: int, alpha: float = 0.05
) -> float:
    """Power of a one-sample z-test for a mean of `effect` vs 0.

    Definition
        P(reject | true effect) = 1 - Phi(z_{1-alpha/2} - effect / SE)
        with SE = sigma / sqrt(n). The pre-study sizing tool: run
        enough trades so the power of the test you will run is not an
        embarrassment.

    Raises
        ValueError if sigma <= 0 or n < 1.

    Complexity
        O(1).

    Examples
        >>> round(normal_power(0.2, 1.0, 100), 4)
        0.516
    """
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    if n < 1:
        raise ValueError("n must be >= 1")
    se = sigma / math.sqrt(n)
    return 1.0 - normal_cdf(normal_inv_cdf(1.0 - alpha / 2.0) - effect / se)
