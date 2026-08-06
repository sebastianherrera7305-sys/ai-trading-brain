# Dataset Quality Registry

Every dataset used by the laboratory carries a scientific quality assessment.
**No experiment may use an undocumented dataset.**

Quality grades:

| Grade | Meaning |
|---|---|
| **A** | Registered, checksummed, integrity-verified, used in ≥1 campaign |
| **B** | Integrity-verified clean; needs registration before experiments |
| **C** | Usable only with documented preprocessing / for sanity checks |
| **D** | Not research-ready |

Assessment performed: 2026-08-06 (this file is the single source of truth;
re-run checks before changing a grade).

---

## DS-001 — ES daily OHLC 10y (`es-f-10y-ohlc-v1`) — **Grade A**

| Field | Value |
|---|---|
| Source | `data/ES_F_10y.csv` → registered `es-f-10y-ohlc-v1` (id `8d2a7d6b…9a84`) |
| Coverage | 2,513 bars, 2016-08-04 → 2026-08-04 |
| Timeframe | 1d (daily session bars) |
| Markets | ES (E-mini S&P 500 futures), continuous front month |
| Timezone | America/New_York (session) |
| Missing values | 0 (verified); no duplicate dates; strictly ascending |
| Preprocessing | CSV → float64 OHLC + int64 epoch days; no imputation, no adjustment |
| Survivorship bias | Front-month continuous — no delisted contracts; tradable at all dates |
| Look-ahead risk | None — historical OHLC only; features computed causally |
| Continuous-contract methodology | **Undocumented (provider)** — roll dates/rules unknown; price jumps at rolls possible |
| Checksum | `b3159e9df856660ae94ddd3a8b962c0f487b3890b1205030de9947dc69824276` (101,024 B) |
| Research readiness | Ready; used in C001 (2,513 bars confirmed in reproductions) |
| Known limitations | Roll-gap contamination risk for gap/range features; no volume; front-month may trade overnight hours not reflected in daily open/close attribution |

## DS-002 — Gap Continuation trial matrix (`es-gap-trial-matrix-v1`) — **Grade A**

| Field | Value |
|---|---|
| Source | `data/es_gap_trial_matrix_v1.npz` → registered (id `3dec8c36…c535a2`) |
| Coverage | 36 strategy cells × 2,513 days; 16 benchmark series |
| Preprocessing | Assembled from registered experiment artifacts (`assemble_trial_matrix.py`); data engineering only, no statistics |
| Look-ahead risk | None — rows are campaign daily P&L |
| Continuous-contract methodology | Inherits DS-001 caveat |
| Checksum | `519cb85d7aa313a578dc092e0961507c149137f17782d4e160dc4951b1a00520` (105,979 B) |
| Research readiness | Ready; consumed by gap_meta (26 metrics reproduced) |

## DS-003 — CL daily OHLC 10y (`data/CL_F_10y.csv`) — **Grade B**

| Field | Value |
|---|---|
| Coverage | 2,512 bars, 2016-08-04 → 2026-08-04 |
| Integrity | 0 missing, 0 duplicates, ascending (verified) |
| Missing values | 0 |
| Timezone | America/New_York (session) |
| Survivorship / look-ahead | Front-month continuous; none (historical) |
| Continuous-contract methodology | **Undocumented (provider)** |
| Research readiness | Needs registration (mirror DS-001 pipeline); ready for C003/C004/C007 |

## DS-004 — GC daily OHLC 10y (`data/GC_F_10y.csv`) — **Grade B**

As DS-003: 2,511 bars, 2016-08-04 → 2026-08-04, 0 missing/duplicates, ascending. Needs registration.

## DS-005 — EURUSD daily OHLC 10y (`data/EURUSD_X_10y.csv`) — **Grade C**

| Field | Value |
|---|---|
| Coverage | 2,601 bars, 2016-08-03 → 2026-08-04 |
| Missing values | 0; no duplicates; ascending |
| **Weekend bars** | **305** — spot series trades on some weekend/holiday sessions |
| Markets | EURUSD spot (X), NOT a futures contract |
| Timezone | UTC/spot session — different calendar from CME futures |
| Research readiness | Requires preprocessing: weekend filtering + alignment to CME trading calendar before any cross-market use |
| Known limitations | Different date axis vs ES/CL/GC (2,601 vs ~2,512 bars); spot, not roll-adjusted |

## DS-006..009 — 2y daily files (`ES_F`, `CL_F`, `GC_F`, `EURUSD_X`) — **Grade C**

Coverage ~2024-08 → 2026-08 (501–517 bars, EURUSD with 60 weekend bars).
Integrity clean (0 missing, no duplicates). These are tails of the 10y series;
use only for sanity checks or as a held-out window, never as the primary
dataset. If used for out-of-sample work, the overlap with DS-001..005 must be
documented.

---

## Registry rules

1. A dataset enters an experiment only after: registered in the store +
   checksum recorded + quality grade ≥ B (A preferred) + entry in this file.
2. Any preprocessing step is recorded in the manifest `pipeline` field at
   registration time.
3. Grade changes are edits to this file with a dated reason; the underlying
   registered blob is immutable.
4. New acquisitions (VIX, intraday, term structure) get entries here before
   any catalog hypothesis can reference them.

## Open quality questions

- Q1: Roll methodology of the provider's continuous series (all four markets)
  — ask provider / detect roll dates empirically (H-FUT-02).
- Q2: EURUSD source/calendar (weekend bars) — document before C003/C007 use.
- Q3: Whether CL/GC daily open reflects the full overnight session (affects
  gap-feature semantics across markets).
