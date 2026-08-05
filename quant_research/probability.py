"""probability — binomial math, Kelly, expected value, Bayesian
Beta-Bernoulli updating, credible intervals, Brier score, Wald SPRT.

The decision-theoretic layer: everything that turns observed trade
outcomes into "should we still believe the edge exists" statements
(docs/research/05, sections 2.7-2.8).
"""

import math
from typing import Dict, Optional, Tuple

import numpy as np

from .statistics import normal_cdf, normal_inv_cdf, regularized_incomplete_beta


# ---------------------------------------------------------------------------
# Binomial
# ---------------------------------------------------------------------------

def binomial_pmf(k: int, n: int, p: float) -> float:
    """P(X = k) for X ~ Binomial(n, p). Log-gamma formulation avoids
    overflow for large n."""
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
    """P(X <= k). Summed PMF (exact; n here is a trade count, not a
    scientific-sample count, so direct summation is fine)."""
    if k < 0:
        return 0.0
    if k >= n:
        return 1.0
    return sum(binomial_pmf(j, n, p) for j in range(0, int(k) + 1))


def binomial_ci(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Exact (Clopper-Pearson) two-sided confidence interval for the
    success probability, via the beta distribution identity. This is the
    honest interval for a win rate on a small trade count — the normal
    approximation is not."""
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
    """P(X <= x) for X ~ Beta(a, b)."""
    return regularized_incomplete_beta(x, a, b)


def beta_inv_cdf(p: float, a: float, b: float) -> float:
    """Quantile of Beta(a, b) — deterministic bisection on beta_cdf."""
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
    """E[X] = a / (a + b)."""
    return a / (a + b)


def beta_var(a: float, b: float) -> float:
    """Var[X] = ab / ((a+b)^2 (a+b+1))."""
    s = a + b
    return a * b / (s * s * (s + 1.0))


def beta_posterior(
    prior_alpha: float, prior_beta: float, successes: int, failures: int
) -> Tuple[float, float]:
    """Beta-Bernoulli conjugate update: Beta(a + k, b + n - k)."""
    return prior_alpha + successes, prior_beta + failures


def probability_edge_above(
    successes: int, failures: int, threshold: float = 0.5,
    prior_alpha: float = 1.0, prior_beta: float = 1.0,
) -> float:
    """P(true win rate > threshold | data) under the Beta-Bernoulli
    model with a Beta(prior_alpha, prior_beta) prior. The Bayesian
    answer to "is there still an edge?" — central readout of the Edge
    Monitor (docs/research/05 section 2.7)."""
    a, b = beta_posterior(prior_alpha, prior_beta, successes, failures)
    return 1.0 - beta_cdf(threshold, a, b)


# ---------------------------------------------------------------------------
# Expected value and Kelly
# ---------------------------------------------------------------------------

def expected_value(p: float, gain: float, loss: float) -> float:
    """EV of a unit bet: p*gain - (1-p)*loss."""
    if not (0.0 <= p <= 1.0):
        raise ValueError("p must be in [0, 1]")
    return p * gain - (1.0 - p) * loss


def kelly_fraction(p: float, b: float) -> float:
    """Full Kelly: f* = (bp - (1-p)) / b, the fraction of capital that
    maximizes expected log growth for a bet paying b:1 with win
    probability p. Returns 0 for non-positive-edge bets; raises for
    degenerate inputs."""
    if not (0.0 < p < 1.0):
        raise ValueError("p must be in (0, 1)")
    if b <= 0:
        raise ValueError("b must be > 0")
    edge = b * p - (1.0 - p)
    return max(edge / b, 0.0)


def fractional_kelly(p: float, b: float, fraction: float) -> float:
    """fraction * full Kelly. fraction in (0, 1] — 0.25 is the classic
    conservative choice for live sizing."""
    if not (0.0 < fraction <= 1.0):
        raise ValueError("fraction must be in (0, 1]")
    return fraction * kelly_fraction(p, b)


def kelly_expected_growth(p: float, b: float, f: float) -> float:
    """Expected log growth rate E[log(1 + f*X)] for a bet at b:1 odds,
    win prob p, sizing fraction f. Peak is at f = Kelly."""
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
    """Mean squared error between predicted probabilities and binary
    outcomes: E[(p_i - y_i)^2]. 0 = perfect, 0.25 = always predicting
    0.5, 1 = always wrong with certainty."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    if p.shape != y.shape:
        raise ValueError("probabilities and outcomes must have equal shape")
    if np.any((y != 0) & (y != 1)):
        raise ValueError("outcomes must be binary (0/1)")
    return float(np.mean((p - y) ** 2))


def brier_skill_score(probabilities: np.ndarray, outcomes: np.ndarray, climatology: Optional[float] = None) -> float:
    """Brier Skill Score: 1 - BSS_model / BSS_climatology. Positive =
    better than predicting the base rate. climatology defaults to the
    sample mean win rate."""
    p = np.asarray(probabilities, dtype=float)
    y = np.asarray(outcomes, dtype=float)
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

    Tests H0: p = p0 (edge dead / at threshold) vs H1: p = p1 (edge
    alive) with type-I error alpha and type-II error beta. Returns the
    log-likelihood ratio path, the decision and the cumulative evidence.

    Decision rules (Wald): LLR >= ln((1-beta)/alpha)  => accept H1;
    LLR <= ln(beta/(1-alpha)) => accept H0; otherwise continue.
    """
    outcomes = np.asarray(outcomes, dtype=float)
    if np.any((outcomes != 0) & (outcomes != 1)):
        raise ValueError("outcomes must be binary (0/1)")
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


def sprt_expected_sample_size(p: float, p0: float, p1: float, alpha: float = 0.05, beta: float = 0.05) -> float:
    """Wald's approximation of the expected number of observations to a
    decision when the true Bernoulli probability is p."""
    if not (0.0 < p0 < p1 < 1.0):
        raise ValueError("need 0 < p0 < p1 < 1")
    a = math.log((1.0 - beta) / alpha)
    b = math.log(beta / (1.0 - alpha))
    z = p * math.log(p1 / p0) + (1.0 - p) * math.log((1.0 - p1) / (1.0 - p0))
    if z == 0.0:
        return float("inf")
    if z > 0:
        return ((1.0 - beta) * a + beta * b) / z
    return ((1.0 - alpha) * b + alpha * a) / z


def normal_power_simple(
    effect: float, sigma: float, n: int, alpha: float = 0.05
) -> float:
    """Power of a one-sample z-test for a mean of `effect` vs 0 with
    known sigma: P(reject | true effect). Handy for sizing research
    studies before running them (do we have enough trades?)."""
    if sigma <= 0:
        raise ValueError("sigma must be > 0")
    if n < 1:
        raise ValueError("n must be >= 1")
    se = sigma / math.sqrt(n)
    return 1.0 - normal_cdf(normal_inv_cdf(1.0 - alpha / 2.0) - effect / se)
