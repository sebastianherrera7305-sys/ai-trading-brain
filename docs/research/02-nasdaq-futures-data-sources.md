# 02 — Nasdaq Futures Historical Data: Source Comparison

Comparison of nine public sources of Nasdaq futures (NQ/MNQ family) historical
data, evaluated for institutional quantitative research. Prices verified
against public sources June-Aug 2026; exchange margins and fees change with
volatility — re-verify before purchase.

---

## Summary table

| Source | Historical depth | Tick | 1-sec | 1-min | Continuous | Roll adj. | Latency | Cost | Licensing | API quality | Python |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Databento** | 16+ yr (CME L1) | ✅ full (L1/L2/L3 opt) | ✅ | ✅ | ✅ (custom) | ✅ ratio/diff | ~ms (raw exchange) | $0-199/mo std; usage $/GB; $125 free credits | CME license included in plans | Excellent, modern, streaming+batch | ✅ first-class (SDK) |
| **CME DataMine** | Full official history | ✅ | ✅ | ✅ | ⚠️ must build | manual | n/a (files) | $100s-1000s/mo + $15k/yr license opt | Direct CME license (strict, per-entity) | Official, batch/FTP only | ⚠️ raw files, no SDK |
| **dxFeed** | Deep (multi-exchange) | ✅ full depth | ✅ | ✅ | ✅ | ✅ | ~ms institutional | Custom/enterprise (opaque) | Exchange + vendor | Enterprise-grade | ✅ API + SDK |
| **Polygon (Massive)** | 2-7+ yr depending on tier | trades/quotes (no full depth) | ✅ (sec agg) | ✅ | ⚠️ build from contracts | manual | ~100-500ms | $0-199/mo | Exchange fees via vendor | Good REST+WS | ✅ solid SDK |
| **NinjaTrader (Kinetick)** | 10+ yr daily, ~4 yr 1-min, 30-60 d tick (continuous included) | ⚠️ limited window | ⚠️ | ✅ | ✅ built-in | ✅ (option) | ~100-500ms | $0-110/mo (free w/ funded acct) | Platform license | Proprietary DLL | ⚠️ Python only via wrappers |
| **IQFeed (DTN)** | 10+ yr daily; ~6-12 mo tick; ~2 yr 1-min | ✅ full tick | ✅ | ✅ | ✅ | ✅ | ~50-200ms | ~$108/mo + $25 futures surcharge + exchange fees | Retail exchange fees | Mature, chat/API | ⚠️ via external libs (no official) |
| **Barchart** | Deep (decades) | ✅ | ✅ | ✅ | ✅ | ✅ | ~100-500ms | API credits/plans (usage) | Exchange fees | Good REST | ✅ official |
| **Interactive Brokers** | ~1 yr daily (1 day bars), ~10 yr weekly; intraday via TWS | ❌ | ❌ | ✅ recent only | ⚠️ | manual | slow (via TWS, ~100ms-1s) | $0 (with account) | Personal use | Legacy API (ib_async) | ✅ (ib_async) |
| **Yahoo Finance** | 10+ yr daily | ❌ | ❌ | ✅ recent (60-90 d) | ✅ (=F) | ⚠️ non-transparent | n/a (EOD) | Free | Personal | Unofficial, breaking changes | ✅ (yfinance) |

---

## Per-source evaluation

### Databento — RECOMMENDED PRIMARY
- **Depth:** 16+ years of CME Globex MDP 3.0 L1; L2/L3 depth history on paid tiers; definitions and statistics included.
- **Ticks/seconds/minutes:** native schemas for all (MBP-1/MBO for depth, TBBO, OHLCV at 1s/1m/1h/1d).
- **Continuous contracts:** buildable from definitions (per-contract mapping incl. roll dates); Databento documents the roll math.
- **Latency:** historical = batch/streaming download; live feed = raw exchange latency (not "fast enough for HFT" but honest about it).
- **Cost (Jun 2026):** $125 free credits; usage-based $/GB (billed on uncompressed binary size); Standard $199/mo (16+ yr OHLCV-1s, 12 mo L1, 1 mo L2/L3); Plus $1,750/mo (16+ yr L1); Unlimited $4,500/mo (everything). CME license fees are bundled.
- **API:** modern SDKs (Python/Rust/C++), streaming + batch download, clean docs.
- **Verdict:** best price/quality for a serious research platform at our scale. Start free, buy Standard, download NQ/MNQ history once, store locally versioned (doc 04 snapshot discipline).

### CME DataMine — CANONICAL SOURCE
- **Depth:** the exchange's own archive — the ground truth every vendor resells.
- **Cost:** per-product packages, typically hundreds to thousands $/mo, plus a yearly redistribution license for republishing; strict per-entity licensing.
- **API:** batch FTP/S3, no SDK; you build the pipeline.
- **Verdict:** overkill for now; revisit when (a) we need authoritative corporate-action/roll data or (b) live exchange redistribution rights become legally necessary.

### dxFeed — INSTITUTIONAL-STANDARD FEED
- Enterprise-grade, multi-exchange (CME, ICE, Eurex...), full depth, sub-10ms, custom/opaque pricing; usually accessed through a platform/broker embed, not purchased directly.
- **Verdict:** the "when we're institutional" option; not now.

### Polygon.io (now "Massive") — GOOD MID-TIER
- CME-Group only (CME, CBOT, NYMEX, COMEX). Futures tiers (2026): Basic $0 (5 calls/min, historical only, ~2 yr), Starter $29 (unlimited, 10-min delayed), Developer $79 (5 yr history), Advanced $199 (real-time). Trades/quotes/aggregates (sec + min), daily flat-file S3 dumps.
- **Verdict:** fine for prototyping and live paper-trading of CME products; no full depth, history shallower than Databento at same price; two separate subscriptions needed if equities added.

### NinjaTrader — RETAIL-SIMPLE
- Built-in continuous charts (Kinetick), free with funded account or ~$50-110/mo; tick history only ~30-60 days; excellent UX, proprietary API.
- **Verdict:** good for manual research and strategy prototyping; wrong foundation for a research data lake.

### IQFeed (DTN) — RETAIL FULL-TICK
- ~$108/mo core + $25 futures surcharge + exchange fees; true full tick + fast; historical tick window limited (~6-12 mo) but deep daily/min; chat-based API, third-party Python bindings.
- **Verdict:** best retail full-tick stream; acceptable for live feed + short-window studies; history too shallow for 10-yr backtests.

### Barchart — COMMERCIAL API
- Deep history, good REST coverage of CME, roll-adjusted continuous contracts; usage-based credit plans; exchange-fee pass-through.
- **Verdict:** solid alternative to Polygon for API-driven research; less well documented in Python community.

### Interactive Brokers — FREE PRACTICAL SOURCE
- Free historical via TWS/Gateway (ib_async): ~1 yr of 1-day bars, ~10 yr of weekly/monthly; intraday bars limited to recent months; no tick history; latency through TWS.
- **Verdict:** keep as the free validation path for daily/weekly work and live paper execution (already integrated in trading-bot), never as the research archive.

### Yahoo Finance — FREE, LOW TRUST
- 10+ yr daily OHLCV (restated silently — dataset versioning problem, ADD Part III §40); continuous `=F` symbols exist but with non-transparent roll logic; no ticks, 1-min only ~60-90 days; unofficial API, breaking changes.
- **Verdict:** the 10-yr CSVs currently in trading-bot's data/ came from this class of source — good enough for smoke tests, NOT for edge conclusions. Migrate to Databento before drawing statistical conclusions.

---

## Recommendation: long-term dataset architecture

1. **Primary research archive (now):** Databento Standard ($199/mo) — one-time batch downloads of NQ, MNQ (and ES, MES, GC, CL, EURUSD for cross-asset) at 1-min and 1-sec OHLCV + L1 trades/quotes, stored in our own versioned DuckDB lake (content-hashed snapshots per ADD §40). Keep the source files immutable; derive everything else.
2. **Live feed (paper + production):** start with IBKR (free, already integrated) → upgrade to Databento live (CME license bundled, sub-100ms) when the Edge Monitor shows live performance worth protecting; Polygon Advanced ($199) is the cheaper live alternative for CME-only needs.
3. **Authoritative checks:** CME DataMine only when contract specifications, roll dates, or legal redistribution matter.
4. **Explicitly rejected for research:** NinjaTrader (proprietary), IQFeed (shallow history), Yahoo (no provenance). Keep Yahoo only for quick daily visual checks.

**Budget path:** Databento $125 credits now → download 1-min history for 6 months free → decide on $199/mo after the edge-validation pipeline (doc 05) is in place. Total first-year cost target: < $600.
