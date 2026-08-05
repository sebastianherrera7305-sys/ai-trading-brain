# 03 — Nasdaq Futures: Mathematical Specification

Technical specification for trading the E-mini Nasdaq-100 (NQ) and Micro
E-mini Nasdaq-100 (MNQ) futures. Documentation only — no implementation.

---

## 1. Contract basics (verified against CME, Aug 2026)

| Parameter | NQ (E-mini Nasdaq-100) | MNQ (Micro E-mini) |
|---|---|---|
| Contract size | $20 × Nasdaq-100 index | $2 × Nasdaq-100 index |
| Tick size | 0.25 index points | 0.25 index points |
| Tick value | $5.00 | $0.50 |
| Point value | $20.00 | $2.00 |
| Settlement | Cash (index-based), T+1 mark-to-market | Same |
| Contract months | H, M, U, Z (Mar, Jun, Sep, Dec) | Same |
| Last trading day | Third Friday of contract month | Same |
| Listing cycle | Up to 2 years | Same |
| Venue | CME Globex (MDP 3.0) | Same |
| Hours (CT) | Sun 5pm – Fri 4pm; daily 5pm–4pm; settle 3pm | Same |

**Tick/point identity:** at index level P, notional = `M × P` (M = $20 or $2).
Price moves in units of 0.25 pts → a 1-point move = 4 ticks = $20 × 4 = $80 on
NQ (and $8 on MNQ). At P ≈ 22,000: NQ notional ≈ $440,000; a 1% index move ≈
$4,400/contract.

## 2. Margins (vary with volatility — verify current values)

| Type | NQ (approx.) | MNQ (approx.) |
|---|---|---|
| Exchange initial (overnight) | $18K-$45K (vol-dependent; ~$42K observed Aug 2026) | $1.8K-$4.5K |
| Maintenance | ~10% below initial (e.g., $38K) | same ratio |
| Broker day-trading margin | typically 50-75% of overnight, broker-defined (IBKR ~$1.5K-$3K day / NQ) | ~$150-$300 |

Margin model: daily mark-to-market; if equity drops below maintenance,
variation margin is called or positions are reduced. For risk sizing, use
overnight margin as the conservative bound, day margin as the operational one.

## 3. Session structure (CT)

- **Globex session:** Sun 5:00pm → Fri 4:00pm (continuous), daily reset 5:00pm.
- **Settlement:** 3:00pm CT (official daily settlement price — volume-weighted
  average of the last ~30 seconds by default; used for margin and daily P&L).
- **Trading sessions for analytics:** overnight 5pm-9:30am; RTH 9:30am-4pm.
  Index-fair-value drift around 9:30am; high volume at 3:00-3:15pm (settlement
  period) and 3:50-4:00pm (rolling close).
- **Halts:** index circuit breakers (7%/13%/20%) inherited from the underlying
  index apply to NQ; price band limits per CME.

## 4. Contract rollover & continuous series

**Roll dates:** contracts expire the third Friday (H/M/U/Z); liquidity migrates
~5-15 days before expiry. A standard research roll: the Friday 1-2 weeks
before expiry, or when the front contract's volume falls below the next
contract's.

**Roll gap:** at roll date t*, the price jumps `G = F_new(t*) − F_old(t*)`.
Continuous series methods:
- **Difference (back) adjustment:** add `ΣG` to all earlier prices. Preserves
  absolute levels; distorts returns at the roll (returns mix two contracts).
- **Ratio (proportional) adjustment:** multiply earlier prices by
  `Π(1 + G_i/F_old)` — preserves continuity of returns (preferred for return
  research).
- **Unadjusted / spliced:** keep each contract's own prices; returns use each
  contract's local data (cleanest for trade simulation, requires per-contract
  data storage — the correct choice for our data lake per doc 02).

## 5. VWAP mathematics

Session-cumulative volume-weighted average price:

```
VWAP(t) = Σ_{s≤t} P_s V_s / Σ_{s≤t} V_s
```

where (P_s, V_s) are transaction prices/volumes at event time s. Properties:
- Depends on session anchor: reset at 5pm CT (or 9:30am for RTH-VWAP).
- **Dollar-weighted deviation:** `D(t) = (P(t) − VWAP(t)) × ΣV_s` — a popular
  imbalance measure (interpreted as net buying pressure in dollar terms).
- **Institutional note:** large orders are commonly benchmarked to VWAP;
  deviation from VWAP correlates with institutional participation and is a
  useful feature (not a signal by itself).

## 6. Volume Profile mathematics

Discretize price into bins (e.g., 1 point, or the contract's tick) over a
session; each bin accumulates the volume traded at prices in that bin:
`V(bin) = Σ P_t ∈ bin V_t`. Derived quantities:
- **POC (Point of Control):** the bin with max V(bin) — the price level with
  the most accepted trade.
- **Value Area:** the narrowest set of bins around the POC containing 70% of
  total session volume (VAH/VAL = value area high/low).
- **HVN/LVN:** bins with volume significantly above/below the local average —
  high-volume nodes act as support/resistance; low-volume nodes are
  gap-prone "vacuum" zones.
- **Profile shape:** P-shape (single acceptance), D/b-shape (double
  distribution — range extension), etc. Shape + range extension encode
  whether the market is balanced or trending.

## 7. Market Profile mathematics

TPO (Time-Price Opportunity) framework: divide the session into 30-minute
brackets; each bracket's price range is marked with a letter (A, B, C...).
The profile is the vertical histogram of letters per price level. Analytics:
- **Initial Balance (IB):** the price range of the first hour (usually
  first 60 min of RTH); IB high/low are reference levels.
- **Range extension:** price beyond the IB high/low (up/down extension)
  signals trend day development; failure to extend → balance day.
- **One-time frame vs open-drive:** rotation away from the overnight
  settlement into the IB, then whether value shifts (trend) or returns
  (balance).
- **Composite profiles:** multi-day profiles (e.g., week) identify
  distribution levels that persist across sessions.

## 8. Opening Range & Initial Balance

- **Opening Range (OR):** the high/low over the first N minutes of RTH
  (typical N = 5/15/30/60). A breakout of the OR high/low with volume
  confirmation is a classic directional trigger; OR midpoint acts as a
  magnet/gravity level.
- **Initial Balance:** N = 60 min, per Market Profile convention. The
  IB is the highest-confidence level set each day: it contains the
  post-open discovery process; IB range + overnight range jointly define
  the day's fair-value context.

## 9. Data model implications for the research layer

- Store per-contract raw data (no auto-rolling) + an explicit roll map
  (contract, roll date, gap). Build continuous series only at analysis time.
- Store event-level trades and quotes separately from OHLCV aggregates;
  derive everything else (VWAP, profiles) from the same immutable source so
  metrics are reproducible (ADD §40 content-hashed snapshots).
- Session boundary timestamps in UTC + exchange timezone; tag every bar with
  session type (Overnight / RTH / Settlement) to avoid cross-session leakage.
