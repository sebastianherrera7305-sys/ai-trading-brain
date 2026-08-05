# Example 01 — Trading Expectancy and Position Sizing

## Research question

A momentum strategy was backtested on 200 trades. It won 112 and lost 88,
with a payoff ratio of 1.25 (a win pays +1.25 per unit risked, a loss costs
1.0).

* Is the expectancy positive and material?
* Is the observed win rate distinguishable from 50%?
* What fraction of capital should be risked per trade?
* How many trades does a study need to *detect* an edge of this size?

This walkthrough answers those questions with the probability module.

## Mathematical approach

**Expectancy** is the mean P&L per unit risked:

    E = p * gain - (1 - p) * loss

**Win-rate inference.** The frequentist view uses the Clopper-Pearson
binomial confidence interval (exact, inversion of the binomial CDF). The
Bayesian view puts a Beta(1, 1) prior on the win rate and updates it to
Beta(1 + wins, 1 + losses); `P(win_rate > 0.5 | data)` is then a tail
probability of the posterior. The sample size needed to detect an edge is
given by the power function of a two-sided z-test.

**Kelly criterion** maximizes expected log-growth: with win rate `p` and
net odds `b` (win of b:1, loss of 1), bet the fraction
`f* = (p(1+b) - 1) / b`.

## Why this matters

Expectancy is the *economic* question (does the strategy make money?) and
the win-rate distribution is the *statistical* question (can we trust the
estimate?). The Kelly fraction is the answer to "how big" — the single
most consequential decision in a portfolio, because overbetting by 2x
turns a profitable strategy into a guaranteed loss. These numbers are the
first things a principal reviews before allocating capital.

## Code

```python
import numpy as np
from quant_research import probability as prob
from quant_research import statistics as stats

wins, losses = 112, 88
n, p_hat = wins + losses, wins / (wins + losses)
payoff = 1.25
```

```python
# --- 1. Expectancy and win-rate confidence --------------------------------
ev = prob.expected_value(p_hat, gain=payoff, loss=1.0)
assert abs(ev - 0.26) < 1e-9                       # 0.26 per unit risked
print(f"expectancy per unit risked: {ev:.3f}")

lo, hi = prob.binomial_ci(wins, n)                 # Clopper-Pearson 95%
assert abs(lo - 0.4883) < 1e-3 and abs(hi - 0.6299) < 1e-3
print(f"win-rate 95% CI: [{lo:.4f}, {hi:.4f}]")

# One-sided frequentist p-value against p = 0.5
p_wins_le_111 = prob.binomial_cdf(111, n, 0.5)
assert abs(p_wins_le_111 - 0.9482) < 1e-3
one_sided_p = 1.0 - p_wins_le_111
print(f"one-sided p-value vs p=0.5: {one_sided_p:.4f}")

# Exact PMF at the estimate (peak of the likelihood)
pmf_at_est = prob.binomial_pmf(wins, n, p_hat)
assert abs(pmf_at_est - 0.0568) < 1e-3
print(f"P(X=112 | p=0.56) = {pmf_at_est:.4f}")
```

```python
# --- 2. Bayesian win-rate posterior ---------------------------------------
a, b = prob.beta_posterior(1.0, 1.0, wins, losses)     # Beta(113, 89)
assert (a, b) == (113.0, 89.0)
post_mean = prob.beta_mean(a, b)
post_var = prob.beta_var(a, b)
assert abs(post_mean - 0.5594) < 1e-3 and abs(post_var - 0.00121) < 1e-4
prob_edge = prob.probability_edge_above(wins, losses, threshold=0.5)
assert abs(prob_edge - 0.9549) < 1e-3
print(f"posterior mean {post_mean:.4f}, sd {np.sqrt(post_var):.4f}, "
      f"P(edge > 50%) = {prob_edge:.3f}")
```

```python
# --- 3. Sample size: power to detect the edge -----------------------------
sigma_win = 0.5                                    # sd of a Bernoulli trial
for n_study in (200, 546, 1000):
    power = prob.normal_power(effect=p_hat - 0.5, sigma=sigma_win, n=n_study)
    print(f"n = {n_study:5d}: power {power:.3f}")
assert abs(prob.normal_power(0.06, 0.5, 200) - 0.396) < 1e-2
assert abs(prob.normal_power(0.06, 0.5, 546) - 0.801) < 1e-2
assert prob.normal_power(0.06, 0.5, 1000) > 0.95

# Two-sided z cutoff used by the power formula
assert abs(stats.normal_z_score(0.05) - 1.96) < 1e-3
```

```python
# --- 4. Kelly position sizing ---------------------------------------------
k = prob.kelly_fraction(p_hat, payoff)
assert abs(k - 0.208) < 1e-3
half = prob.fractional_kelly(p_hat, payoff, 0.5)
assert abs(half - 0.104) < 1e-3

g_full = prob.kelly_expected_growth(p_hat, payoff, k)
g_half = prob.kelly_expected_growth(p_hat, payoff, half)
g_over = prob.kelly_expected_growth(p_hat, payoff, 0.5)
assert abs(g_full - 0.0268) < 1e-3 and abs(g_half - 0.0201) < 1e-3
assert g_over < 0.0                                 # overbetting destroys growth
print(f"full Kelly {k:.3f}: E[log growth] {g_full:.4f}/trade")
print(f"half Kelly {half:.3f}: E[log growth] {g_half:.4f}/trade")
print(f"overbet  0.500 : E[log growth] {g_over:.4f}/trade  <- negative!")
```

## Interpretation

* Expectancy is +0.26 per unit risked — the strategy makes money if the
  estimates hold.
* The frequentist CI `[0.488, 0.630]` includes 0.50 and the one-sided
  p-value is 0.052: **barely** significant. The Bayesian posterior gives
  `P(edge > 50%) = 0.955` — more encouraging, but a 4.5% risk of error is
  not institutional-grade.
* Power at n = 200 is only 0.40. The backtest is *underpowered*: even an
  honest 56% win rate would fail to show up as significant half the time.
  ~550 trades are needed for 80% power. This is why the CI/posterior
  tension matters — with 200 trades we simply cannot conclude much.
* Full Kelly says 20.8% of capital per trade. That is aggressive and
  requires the estimates to be exactly right. Half Kelly (10.4%) captures
  75% of the growth (`0.0201 / 0.0268`) at roughly half the variance — the
  standard institutional compromise. Betting 50% is a *guaranteed* long-run
  loss (`g < 0`) even though the strategy is profitable — overbetting is
  more dangerous than no edge at all.

## Limitations

* The win rate and payoff are assumed constant and estimated from one
  regime; real strategies degrade. Kelly assumes iid bets with known
  parameters — it is a sizing *reference*, not a mandate.
* The binomial CI/posterior ignore trade-to-trade dependence (momentum
  trades are clustered). Use the block bootstrap (Example 06) on the
  return series for a dependence-aware interval.
* The power calculation uses a normal approximation; for very small
  samples the exact binomial power is more accurate.
