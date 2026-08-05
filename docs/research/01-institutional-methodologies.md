# 01 — Institutional Quantitative Trading Methodologies

Research summary of the mathematical ideas behind the ten most established
institutional trading methodologies. No code — mathematical intuition,
assumptions, regimes, failure modes, and integration paths into AI Trading Brain.

---

## 1. Trend Following

**Mathematical intuition.** Price trends are modeled as a stochastic process
with a drift term that is *occasionally* non-zero and persistent. Signals come
from estimates of the conditional drift:
`E[r_t | F_{t-1}] ≈ sign(slow_fast_difference)`. Concretely, trend models are
usually moving-average crossovers, breakout systems (Donchian), or linear
regression slope on a lookback window. Position is proportional to signal
strength (volatility-scaled): `position ∝ signal / σ_t`, so the P&L is
bounded in volatility terms.

**Assumptions.** (1) Markets exhibit long memory / positive autocorrelation
over horizons of weeks-months. (2) Volatility clustering makes risk-scaled
positioning feasible (GARCH-like dynamics). (3) Small positive expected move
per trade with negative skew and positive kurtosis — compensated by asymmetry
of payoff (big winners, many small losers).

**Strengths.** Most robust documented edge of the classic CTA set; works across
equities, futures, FX, rates. Survives regime changes (trends appear in
crises). Low capacity constraints relative to HFT.

**Weaknesses.** Low win rate (30-40%), long flat/negative periods, vulnerability
to whipsaws in ranging markets, tail-heavy losses (e.g., 2020 March spike
reversals).

**Market regimes.** Thrives: trending with sustained momentum (risk-on rallies,
crisis crashes). Struggles: low-volatility range-bound, mean-reverting chop.

**Common failure modes.** Over-optimization of lookback windows (multiple
comparisons); stop-loss too tight (death by noise); parameter instability
across assets; sizing that ignores vol regimes (overtrading in low-vol).

**Integration into AI Trading Brain.** Baseline `TrendFollow` strategy already
exists in trading-bot. Research package should add: rolling-window Sharpe
stability tests, regime-labeled backtest segmentation, vol-scaled position
sizing (Parkinson/EWMA vol).

## 2. CTA Models (Managed Futures)

**Mathematical intuition.** Portfolio-level approach: combine multiple
diversifying signals (trend, carry, momentum, seasonality) across many markets;
position sizing from inverse-volatility or risk-parity weights so the portfolio
volatility target is hit: `w_i = (1/σ_i) / Σ(1/σ_j)`, scaled by `λ/σ_portfolio`.
Returns are approximately a "volatility insurance" premium — convex payoff
relative to equity market.

**Assumptions.** Cross-asset diversification reduces drawdowns; vol is
mean-reverting and forecastable short-term; correlations rise in crises but
trend signals still pay.

**Strengths.** Diversification across 50-100+ markets; crisis alpha; long
track record (1970s-). Risk-parity style sizing is theoretically justified via
Kelly on the portfolio.

**Weaknesses.** Fee drag; crowding among CTAs; regime dependence on
sustained trends; execution costs on less liquid markets.

**Market regimes.** Best: high cross-market dispersion, trending. Worst:
synchronized low-vol grinds where all signals sit near zero.

**Failure modes.** Concentrated risk when correlations spike (Feb 2021, bond
crash; 2020 QT); signal decay from crowding; overfitting the risk model.

**Integration.** The Portfolio Engine (Subsystem 4) is the natural home for
CTA-style multi-strategy sizing: per-strategy risk budgets, inverse-vol
weights, portfolio vol targeting.

## 3. Mean Reversion

**Mathematical intuition.** Assume returns follow a stationary AR(1) process
`r_t = ρ r_{t-1} + ε_t` with `|ρ| < 1`, or price deviations from a moving
equilibrium: `z_t = (P_t - MA_k) / σ_t` (z-score). Trade when `|z| > threshold`,
expecting pull toward the mean. At the portfolio level, pair the long/short so
only the relative deviation is exposed.

**Assumptions.** Stationarity of the spread; the mean is a valid anchor;
transaction costs smaller than the expected reversion move; no structural
breaks during the trade.

**Strengths.** High win rate (60-80%) with small winners; short holding
periods; good in range-bound regimes; high Sharpe before costs when capacity
is small.

**Weaknesses.** Catastrophic left tail when the "mean" moves (structural
breaks — 2008, COVID gaps, 2022 bond crash); heavy dependence on accurate
cost modeling; capacity-limited.

**Market regimes.** Thrives: range-bound, high mean-reversion autocorrelation
negative. Fails: strong trends, crisis gaps (gap-through-stop).

**Failure modes.** Picking up falling knives (no anchor validity check);
death by 1000 cuts if costs > edge; using backtested means that ignore regime
breaks.

**Integration.** FVG/market-structure approach already built in ai-trading-brain
is a mean-reversion cousin. Research package should add: stationarity tests
(ADF), half-life of mean reversion (Ornstein-Uhlenbeck fit), gap risk metrics.

## 4. Statistical Arbitrage

**Mathematical intuition.** Exploit mispricing between *statistically*
related instruments without economic justification. Core tool: cointegration
(Engle-Granger) — find linear combination `u_t = y_t - β x_t` that is
stationary (ADF test on residuals). Trade the deviation: buy when
`u_t < μ - kσ`, sell when `u_t > μ + kσ` (Ornstein-Uhlenbeck model
`du = θ(μ-u)dt + σ dW`; half-life `T = ln2/θ` sets the holding window).

**Assumptions.** Cointegration is structural (not spurious); β stable over
the holding period; residual process is mean-reverting OU; tradeable at cost
level.

**Strengths.** Market-neutral; high Sharpe in calm markets; well-studied
academic base; capacity scales with number of pairs/baskets.

**Weaknesses.** Tail risk when cointegration breaks (basis blow-ups — LTCM
1998, quant meltdown Aug 2007); exposure to funding/spread shifts; model
selection overfitting (many candidate pairs → FDR needed).

**Regimes.** Thrives: normal vol, stable correlations. Fails: correlation
regime shifts, forced deleveraging.

**Failure modes.** Pairs that passed in-sample ADF but break OOS; β instability
causing pseudo-arb; crowding.

**Integration.** Requires a universe of correlated instruments (ES vs NQ vs
index ETFs vs micros). The research data platform's correlation module
(doc 04) feeds the cointegration screening; FDR (doc 05) gates pair selection.

## 5. Pairs Trading

**Mathematical intuition.** Special case of stat arb with N=2. Distance-based
variant: normalize both series, trade when spread exceeds kσ. Stochastic
spread model: OU on the log-price ratio `log(S1/S2)`. Expected holding time
from OU parameters: `E[τ] ≈ (1/θ) ln(kσ / threshold)`.

**Assumptions.** Same as stat arb; both assets respond to the same factor
(sector, liquidity, index membership).

**Strengths.** Simple, transparent, easily hedged; market-neutral; classic
academic edge (Gatev-Goetzmann-Rouwenhorst 2006 documented ~11%/yr pre-cost
with daily rebalance).

**Weaknesses.** Transaction cost erosion for frequent rebalancing; spread
widening during stress (Aug 2007 quant crisis: correlations → 1).

**Regimes.** Best: stable sector correlations. Worst: macro shocks breaking
relative value (e.g., one name gets idiosyncratic news).

**Failure modes.** Regression to a stale mean; half-life mis-estimation;
ignoring dividends/corporate actions; cost model too optimistic.

**Integration.** The AI Decision Engine's probability calibration (ADD §14)
can gate pairs entries with a deviation-probability; Edge Monitor tracks the
spread's regime (stable vs broken).

## 6. Volatility Targeting

**Mathematical intuition.** Set portfolio risk in volatility units, not
notional: choose `w_t` such that `w_t σ̂_t = σ_target` where `σ̂_t` is a
forecast (EWMA, GARCH, realized vol). This makes P&L scale with risk: each
position sized so that a 1σ daily move costs `σ_target` dollars.

**Assumptions.** Volatility is forecastable (strong empirical evidence —
vol clustering, GARCH persistence); returns scale with vol; no relationship
between vol level and direction.

**Strengths.** Reduces drawdowns (sells off in crashes); improves Sharpe
consistently across strategies; mechanically simple; the closest thing to a
free lunch in risk management.

**Weaknesses.** Whipsawing around vol spikes (buying back after crash);
unrealistic assumption of instantaneous rebalancing; increases turnover and
costs.

**Regimes.** Neutral benefit in all; largest benefit in high-vol, crisis
regimes.

**Failure modes.** Vol forecast lag (reducing size after the crash already
happened); cost drag exceeding benefit in choppy markets; sizing to a
volatility that the instrument cannot sustain (position limits).

**Integration.** Direct fit: the Risk Engine (Subsystem 3) can add a
vol-targeting rule (position = risk_budget / (σ × stop_distance)); Edge
Monitor tracks realized vs forecast vol (regime detector, doc 01's regime
statistics).

## 7. Risk Parity

**Mathematical intuition.** Allocate risk, not capital: `w_i ∝ (1/σ_i)`
so each asset contributes equal marginal risk: `w_i σ_i ρ_{i,p} = const`.
Solve `argmin_w (1/2)w'Σw` subject to `w_i σ_i = c` (equal risk contribution).
The classic portfolio is bond-heavy in capital terms — risk, not dollars,
is equalized.

**Assumptions.** Asset risk (vol, corr) is stationary enough to estimate;
leverage available at low cost; tail risks symmetric across assets (violated
in bond crashes).

**Strengths.** Diversification across risk sources; smooth equity curves;
theoretically optimal under incomplete information (no return forecasts
needed — only covariance).

**Weaknesses.** Requires leverage to hit target returns; concentration in
whatever has lowest vol (bonds in 2022 = disaster); hidden tail risks when
correlations → 1.

**Regimes.** Best: normal, low correlation between stocks/bonds. Worst:
inflation shocks, bond-equity correlation flip (2022).

**Failure modes.** Vol/corr estimation errors; leverage constraints binding
in crises; underweighting high-vol high-return assets forever.

**Integration.** Portfolio Engine (Subsystem 4) should expose risk-contribution
analytics (`risk_contribution_i = w_i (Σw)_i / (w'Σw)`); the research layer's
covariance module (shrinkage estimators) is the input.

## 8. Factor Investing

**Mathematical intuition.** Returns decompose into exposures to common
factors: `r_i = α_i + β_i1 f1 + β_i2 f2 + ... + ε_i`. Long-short portfolios
take zero beta to market and load on factors with documented risk premia:
value, size, momentum, quality, low-vol. Cross-sectional momentum:
`rank(returns over T)` minus the cross-sectional mean, scaled by inverse vol.

**Assumptions.** Factor premia persist (rational risk premium or behavioral
mispricing); exposures can be measured; costs < premium; no crowding collapse.

**Strengths.** Massive academic evidence base (Fama-French, Carhart, Novy-Marx);
diversification across factors; transparent and testable.

**Weaknesses.** Long horizons of underperformance (value 2010-2020); factor
crowding and momentum crashes; implementation slippage on illiquid legs;
factor zoo problem (hundreds of published factors → FDR needed).

**Regimes.** Momentum: strong in trending, crashes on reversals (Jan 2001, Mar
2009, 2020 March). Value: works in reflation cycles. Quality/low-vol: defensive
in drawdowns, lags in rallies.

**Failure modes.** Data-snooped factor construction; double-counting correlated
factors; ignoring transaction costs of rebalancing.

**Integration.** The Hypothesis Engine (Part II §35) should treat factor
research like the "factor zoo": new factors pass FDR (doc 05) before reaching
the Registry. The AI Decision Engine's features (ADD §14) map to factor
exposures.

## 9. Momentum (Cross-sectional and Time-series)

**Mathematical intuition.** Cross-sectional: long past winners, short past
losers (rank-based, 3-12 month lookback, 1-month skip). Time-series: long
asset if its own trailing return > 0 (risk-adjusted by vol). The edge is
attributed to underreaction/overreaction (behavioral) or factor risk premia.
Position `w_i = (r_i,ret - r̄) / Σ |r_j - r̄|` (dollar-neutral, vol-scaled).

**Assumptions.** Persistence of relative performance over weeks-months;
reversals at horizons > 1 year; manageable crowding.

**Strengths.** Among the strongest standalone documented premia across asset
classes (Jegadeesh-Titman 1993; AQR cross-asset momentum); simple to
implement; complements mean reversion (different horizons).

**Weaknesses.** Crash risk (momentum crashes on sharp reversals);
capacity/implementation costs; look-ahead in portfolio formation.

**Regimes.** Thrives: sustained trends. Crashes: sharp market reversals
(2020 Mar-Apr, 2009 March).

**Failure modes.** Ignoring the skip-month (short-term reversal contaminating
the signal); running momentum and mean-reversion on the same asset/horizon
canceling out; not controlling market beta.

**Integration.** Existing TrendFollow (time-series momentum) is a building
block; cross-sectional momentum needs multi-asset data (research data
platform doc 04) and a ranking module in the Feature Store.

## 10. Adaptive Position Sizing

**Mathematical intuition.** The size of a bet should depend on the estimated
edge and uncertainty, not just a fixed fraction. Kelly growth-optimal:
`f* = (p b - q) / b` (binary) or `f* = μ/σ²` (continuous normal approximation).
Fractional Kelly (25-50%) preserves most growth while cutting variance.
Adaptive versions update the estimate of `(p, b, μ, σ)` online (Bayesian
posterior updating, EWMA of win rate and payoff) so size converges to the
true edge as evidence accumulates — while a prior/conservative floor prevents
oversizing on noise.

**Assumptions.** Edge parameters are stationary or slowly varying; wealth
growth is the objective; estimation error is quantifiable.

**Strengths.** Theoretically growth-optimal; prevents ruin; automatically
shrinks in low-confidence regimes; empirically improves long-term
compounding (documented in sports betting, trading systems).

**Weaknesses.** Kelly is sensitive to estimation error (overestimates edge →
overbets); assumes stationarity; ignores drawdown utility preferences
(drawdown-averse investors prefer < half Kelly).

**Regimes.** Works in all; critical in high-vol/high-uncertainty regimes where
naive fixed sizing overtrades.

**Failure modes.** Estimating edge from too few samples (small-sample
overconfidence); full Kelly on noisy estimates; ignoring correlation between
concurrent positions (stacked correlated bets = one big Kelly bet).

**Integration.** Direct fit for AI Trading Brain: the AI Decision Engine
outputs calibrated win probabilities (ADD §14) → Risk Engine sizes via
fractional Kelly with a Bayesian prior on edge (quant_research bayesian
module) → Portfolio Engine handles cross-position correlation (ADR-0003).

---

## Cross-cutting synthesis

| Methodology | Horizon | Edge source | Best regime | Worst regime |
|---|---|---|---|---|
| Trend following | weeks-months | drift persistence | trending | range-bound |
| CTA portfolio | weeks-months | diversification + vol premium | high dispersion | low-vol grind |
| Mean reversion | days | stationarity | range-bound | structural breaks |
| Stat arb | days-weeks | cointegration | normal vol | correlation shifts |
| Pairs | days | relative value | stable corr | macro shocks |
| Vol targeting | days | vol forecastability | all (esp. crises) | whipsaw markets |
| Risk parity | months | risk equalization | low corr | inflation shocks |
| Factor investing | months-years | factor premia | factor rotations | crowded factors |
| Momentum | months | persistence | trends | sharp reversals |
| Adaptive sizing | all | Kelly optimality | all | overconfidence |

**Recommendation for AI Trading Brain:** adopt vol targeting + fractional
Kelly sizing (Risk Engine), factor-style validation via FDR (Hypothesis
Engine), and regime labeling (Edge Monitor) as the common spine; strategies
plug in as Registry-gated plugins (Part I §10).
