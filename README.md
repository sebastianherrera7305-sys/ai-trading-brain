# AI Trading Brain

Market structure and liquidity detection in pure Python. No broker, no orders,
no live data feed, no dependencies — you hand it a list of OHLC candles and it
tells you what price is doing.

**Phase 1 — analysis.** Seven modules that read candles and produce labels.
None of them place an order or remember what happened yesterday.

- **Market structure** — swing points, HH/HL/LH/LL, Break of Structure, Change of Character
- **Liquidity** — equal highs/lows, session highs/lows, and liquidity sweeps
- **Displacement** — aggressive candles that create a 3-candle imbalance gap
- **Sessions** — institutional trading windows (London/NY opens, kill zones, overlap)
- **Fair Value Gap** — validates raw displacement imbalances into tradeable FVGs
- **Risk** — stop/target/invalidation validation, position sizing
- **Scoring** — combines every module into the Mandatory Checklist + 0-100 confidence tier

**Phase 2 — backtest.** The piece that turns those labels into a decision and
a memory: replay candles through all seven modules, decide when to take a
trade, follow it to its exit, and log what happened.

- **Backtest** — a walk-forward engine with a reference entry/exit strategy,
  and a trade journal you can query for win rate, total R, drawdown, and —
  the point of the exercise — every trade that lost, in one place
- **Data Loader** — turns a real CSV export into the `Candle` list every
  other module already speaks, so the backtest can run on real history

## Install

```bash
git clone <this repo> && cd ai-trading-brain
pip install -e .
```

Python 3.9+. The package itself has no third-party dependencies.

## Quick start

```python
from trading_brain import (
    Candle, find_swing_points, classify_structure, determine_trend, detect_bos_and_choch,
)

candles = [Candle(i, o, h, l, c) for i, (o, h, l, c) in enumerate(raw_ohlc)]

swings  = classify_structure(find_swing_points(candles, lookback=2))
trend   = determine_trend(swings)
signals = detect_bos_and_choch(candles, swings)

for s in signals:
    print(s.candle_index, s.event.value, s.trend_before.value, "->", s.trend_after.value)
```

Run the built-in synthetic demos for all eight modules end to end — structure,
liquidity, displacement, sessions, FVG validation, risk, scoring, and a full
backtest with a winning trade and a losing one:

```bash
python3 -m trading_brain
```

Run the tests:

```bash
python3 -m unittest discover -s tests -t .
```

## What it detects

### `trading_brain.market_structure`

| Concept | Meaning |
| --- | --- |
| Swing high / low | Fractal pivot: a candle whose high (low) exceeds the `lookback` candles on both sides |
| HH / HL / LH / LL | Each swing labeled against the previous swing of the **same** type |
| Trend | Bullish / bearish / range, voted from the most recent labeled swings |
| BOS | Close beyond the last swing level **with** the trend — continuation |
| CHoCH | Close beyond the last swing level **against** the trend — possible reversal |

CHoCH is the event that fires the Invalidation Rule: when new structure confirms
the trade is no longer valid, exit.

### `trading_brain.liquidity`

| Concept | Meaning |
| --- | --- |
| Equal highs / lows | Two or more highs (lows) within `tolerance` — resting liquidity |
| Session high / low | The extreme of each block of consecutive candles sharing a `Session` tag |
| Sweep | Price wicks **through** a level but **closes back** on the origin side — rejection |
| Break | Price wicks through and *closes* beyond — reported with `rejected=False` |

```python
from trading_brain import find_equal_highs_lows, detect_sweeps

levels = find_equal_highs_lows(candles, tolerance=0.5)
for sweep in detect_sweeps(candles, levels):
    print(sweep.candle_index, sweep.level.price, "rejected" if sweep.rejected else "broke through")
```

A level carries its own state: `detect_sweeps` stamps `swept` / `swept_at_index`
on the levels you pass in, because a level is consumed once it has been taken.
The consequence is that the call is **not idempotent** — rebuild the levels if
you need to re-scan the same candles.

### `trading_brain.displacement`

| Concept | Meaning |
| --- | --- |
| Aggressive | Candle range >= `strength_multiplier` x the trailing average range |
| Imbalance | Candle `i-1` and candle `i+1` don't overlap — the displacement candle punched a gap between them |
| Displacement | Aggressive **and** imbalanced. "Break structure" is checked separately, by `market_structure` |

```python
from trading_brain import detect_displacement

events = detect_displacement(candles, lookback=10, strength_multiplier=1.5)
for e in events:
    print(e.candle_index, e.direction.value, e.strength_ratio, "confirmed at", e.confirmed_at)
```

`direction` comes from the imbalance's gap, not the candle's open/close. A
candle can have a huge range and still close red while gapping price up past
its predecessor — the gap it leaves behind is what a Fair Value Gap gets built
from later, so that's the direction that matters, not the candle's body.

### `trading_brain.sessions`

| Concept | Meaning |
| --- | --- |
| Kill zone | The highest-participation sub-window of a session (London/NY open, etc.) |
| Overlap | London/New York running simultaneously — the highest-liquidity window of the day |
| Tradeable | Any institutional session window; `is_allowed_to_trade()` is the direct README gate |
| Preferred | The kill zones and overlap specifically — "cleanest" price action |

```python
from datetime import time
from trading_brain import tag_session, is_allowed_to_trade

tag_session(time(12, 30))       # -> New York Open, preferred, tradeable
is_allowed_to_trade(time(3, 0)) # -> False, dead Asia session
```

Windows are checked **narrowest first**. Several windows nest inside broader
ones — `NEW_YORK_OPEN` [12:00, 14:00) sits entirely inside `LONDON_NY_OVERLAP`
[12:00, 16:00), which sits inside `NEW_YORK_GENERAL` [12:00, 21:00) — so a
broader window checked before a narrower one it fully contains doesn't just
win a tiebreak, it makes that narrower label **unreachable for any input**.
`tag_session` orders every window open-to-general specifically to avoid that.

> **Naming note:** `liquidity.Session` (a plain LONDON/NEW_YORK/OVERLAP/OFF_SESSION
> tag used for grouping candles into session-high/low blocks) and
> `sessions.SessionWindow` (this module's much richer kill-zone/overlap gate) are
> two different enums that happen to share a domain. They're not interchangeable —
> pick based on which module you're calling into.

### `trading_brain.fair_value_gap`

| Concept | Meaning |
| --- | --- |
| Valid FVG | A displacement's imbalance that is trend-aligned **and** preceded by a rejected sweep |
| Unmitigated | Still open — price hasn't traded back through it |
| Partially filled | Price touched the zone but didn't fully close it |
| Mitigated | Price fully closed the gap — no longer valid per README |

```python
from trading_brain import validate_fvgs, update_mitigation

fvgs = validate_fvgs(displacement_events, sweeps, trend_at={6: Trend.BULLISH})
update_mitigation(fvgs, candles)  # mutates fvg.status / fvg.mitigated_at_index in place
```

This module doesn't detect gaps — `displacement.py` already found the raw
imbalance. It filters those down to the README's four conditions (displacement,
trend alignment, preceding sweep, unmitigated) and tracks fill state afterward.
`trend_at` must be keyed by `candle_index` (matching the displacement event, not
its `confirmed_at`) — pass incrementally-computed trend snapshots, not the final
trend for the whole dataset, or you'll evaluate alignment against information
that didn't exist yet.

**"Preceding sweep" means the correct side, not just any recent rejected
sweep.** A bullish reversal is fueled by sell-side liquidity being taken — a
swept *low* — not a swept high, however recent and rejected that swept high
was. `validate_fvgs` checks `sweep.level.is_high_side` against the
displacement's direction; a sweep on the wrong side doesn't count.

### `trading_brain.risk`

| Concept | Meaning |
| --- | --- |
| Stop beyond structure | Stop loss must sit past a real reference level, never an arbitrary distance |
| Risk/reward | `reward / risk`; a plan needs `reward > risk` to be valid — exactly 1:1 is marginal, not rejected |
| Invalidation | A tighter, earlier level than the hard stop — README: exit here, don't wait for the stop |

```python
from trading_brain import TradePlan, validate_trade_risk, position_size

plan = TradePlan(Direction.BULLISH, entry=110, stop_loss=104.5, take_profit=125,
                  invalidation_price=106, stop_reference_level=105)
result = validate_trade_risk(plan)   # .valid, .risk_reward_ratio, .reasons_rejected
size = position_size(account_balance=10_000, risk_percent=1, entry=110, stop_loss=104.5)
```

### `trading_brain.scoring`

The final assembly point. Combines every other module's boolean output into
the README's Mandatory Checklist and a 0-100 confidence tier.

```python
from trading_brain import ChecklistInputs, score_setup

result = score_setup(ChecklistInputs(
    market_structure_confirmed=True, liquidity_present=True, trend_alignment=True,
    displacement_confirmed=True, fvg_valid=True, clean_entry=True,
    risk_management_defined=True, session_time_ok=True, no_major_news=True,
))
# result.checklist_passed, result.confidence_score, result.tier
```

**Any field that isn't exactly `True` fails the checklist** — not just an
explicit `False`. This module is the last gate before a trade fires, and the
README's rule is "if even ONE fails, reject... no exceptions." A field left as
`None` because some upstream check never ran must reject just as hard as one
that came back `False` — it must not silently pass through as if it didn't
count, which is what happens if you check `is False` instead of `is not True`.
A failed checklist forces `Tier.REJECT` regardless of score, even a 95.

### `trading_brain.backtest`

The connective tissue. Everything above produces labels; this replays a
candle series through all seven of them in a single walk-forward loop,
decides whether to take a trade, and logs what happened.

```python
from trading_brain import run_backtest, BacktestConfig

result = run_backtest(candles, BacktestConfig(target_rr=2.0, min_tier=Tier.B))

result.win_rate        # None if nothing closed yet, else wins / (wins+losses+invalidated)
result.total_r         # sum of realized R across closed trades
result.max_drawdown_r  # worst peak-to-trough decline on the cumulative-R curve, <= 0
result.by_tier         # {Tier.S: TierStats(...), ...} -- does S actually outperform B?
result.losing_trades   # every LOSS or INVALIDATED trade, checklist and all -- the journal
```

**Reference strategy** (swap it out once you have a real edge to encode):
a validated FVG that clears the checklist at Tier B or better places a
*resting* order at the gap's near edge — not a market order at the next
open. Stop sits just beyond the swept liquidity level; invalidation is the
gap's far edge (checked before the stop, per the README); target is a fixed
reward-to-risk multiple. If price never retraces to fill, or invalidates the
setup before ever filling, the order expires and nothing is recorded —
`result.unfilled_setups` counts these separately from real trades. Only one
trade is open at a time.

Two things worth being deliberate about if you build on this:

- **A trade record only exists once a fill actually happens.** A setup that
  passed the checklist but never got touched is not a trade, win, or loss —
  it's a missed opportunity, tracked separately.
- **Stop-vs-target ties go to the stop.** If a single candle's range covers
  both the stop and the target, OHLC data can't say which was hit first.
  The engine assumes the stop — the conservative read, not the flattering one.

**Performance.** Recomputing every Phase 1 module from scratch on the whole
growing history at each step is correct but scales badly — measured, 500
candles ran in ~3s, 2000 took over two minutes; the O(n²) cost inside
`find_equal_highs_lows` alone, called at up to n steps, pushes the whole
walk toward O(n³). `BacktestConfig.recompute_window` (default 300) bounds
each recompute to a trailing window instead of the full history, which
turns that into roughly O(n · window²) — linear in the number of candles.
Measured after the fix: 2000 candles in ~10s, 5000 in ~26s. Set
`recompute_window=None` to disable windowing and match full-history
behavior exactly — worth doing as a one-time correctness check against a
windowed run on the same data, or on datasets small enough to afford the
full cost outright.

Building that fix surfaced a real bug, not just a performance one:
`detect_displacement` built each `DisplacementEvent.candle_index` from
`enumerate()`'s local loop position instead of `candle.index`. Every other
module in this project uses the Candle's own `.index` for exactly this
reason, and every existing test happened to pass a slice starting at
absolute index 0 — so the bug was silently invisible until a windowed slice
from the *middle* of a longer series exposed it: the reported index drifted
from the true one by the window's offset, and displacement events past the
window's start went missing entirely. Fixed to match the rest of the
codebase's convention, with a regression test that runs a 400-candle series
windowed and unwindowed and requires byte-for-byte identical trades.

A fractal swing is not knowable until `lookback` candles have printed after it,
so every `SwingPoint` carries `confirmed_at = candle_index + lookback`.
`detect_bos_and_choch` walks the candles forward and reveals each swing only at
its `confirmed_at` index — it never reacts to a level the market had not yet
formed. This matters: without it, a backtest silently reads the future and every
result it produces is fiction.

Two consequences worth knowing:

- Signals lag the actual pivot by `lookback` candles. That is the honest cost of
  confirmation, not a bug to tune away.
- Once a break establishes a new level, a swing that confirms afterwards cannot
  overwrite it with an older one.

Liquidity levels carry the same discipline in a `known_from` index. An equal-highs
level becomes tradable the moment its **second** touch prints — not its last. Keying
off the last touch would let a touch in the far future reach back and suppress a
sweep that was perfectly valid at the time.

Session extremes need no such guard: no candle inside a block can exceed that
block's own high, so a session level can only ever be swept after its block ends.

A `DisplacementEvent` is the sharpest case of this in Phase 1. Its imbalance is
defined by comparing the displacement candle's two *neighbors* — which means the
candle *after* it has to exist before the event can be confirmed. `candle_index`
still points at the candle that displaced; `confirmed_at = candle_index + 1` is
when a live system could actually have known about it. Truncate a series right
after the displacement candle and the event vanishes — that's correct, not a bug.

`run_backtest` inherits every guard above by construction — it only ever
passes `candles[:i+1]` to a Phase 1 module at step `i` — and adds its own: a
setup recognized at step `i` can only place a *resting order* from `i+1`
onward. Truncating a series right after a fill leaves the trade `OPEN`, not
silently resolved, because the outcome genuinely wasn't knowable yet — the
same "truncate it and watch the signal disappear" test used throughout this
README applies here too, and `tests/test_backtest.py` runs it directly.

## Choices baked in

- **Strict comparisons.** A flat stretch of equal highs yields no swing, instead
  of tagging every candle in it — and no candle is ever both a swing high and a
  swing low.
- **Close-based breaks.** A wick through a level is not a break; the candle has
  to close beyond it.
- **First break out of a range is a BOS,** not a CHoCH — with no established
  trend there is nothing to change character from.
- **`Candle.timestamp` is optional** (defaults to `None`, every existing
  positional call site still works unchanged). When present, the backtest
  gates entries by session; when absent, that gate is skipped entirely
  rather than rejecting every trade for lack of a clock.

### `trading_brain.data_loader`

The one module that touches the outside world — everything else takes a
`List[Candle]` and doesn't care where it came from. This turns a CSV export
(broker, MetaTrader, TradingView, stooq, whatever you've got) into one.

```python
from trading_brain import load_candles_from_csv, run_backtest

candles = load_candles_from_csv("EURUSD_daily.csv")  # any Date/Open/High/Low/Close header
result = run_backtest(candles)
```

Headers are matched case-insensitively against common spellings
(`Date`/`Time`/`Datetime` all map to the timestamp column). Rows are sorted
ascending and re-indexed `0..n-1` regardless of file order, because every
other module assumes `Candle.index` is a clean walk-forward sequence. A row
whose timestamp doesn't parse sorts **last**, not first — silently putting
unparseable data at the front of a walk-forward series would be look-ahead
by construction, the one thing every module here is built to avoid.

## Not in scope yet

Order blocks, multi-timeframe alignment, and anything that touches a broker
or a live data feed. `no_major_news` in `ChecklistInputs` is a plain boolean
you supply — there's no economic-calendar integration here to compute it for
you. The backtest's entry/exit rule is one reasonable reference strategy, not
the only one worth encoding — it's built to be swapped out. And critically:
nothing here has been paper-traded or run against live markets. A clean
backtest is a necessary check, not a sufficient one, before real capital is
anywhere near this.

## Status

Phase 1 (analysis) and Phase 2 (backtest) are both feature complete: nine
modules, covered by 150 unit tests. This produces labels, signals, and
backtested trade logs — not live trades, and it makes no claim about
profitability. Nothing here has been validated against live markets.
