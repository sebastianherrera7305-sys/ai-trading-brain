# AI Trading Brain

Market structure and liquidity detection in pure Python. No broker, no orders,
no live data feed, no dependencies — you hand it a list of OHLC candles and it
tells you what price is doing.

**Phase 1 (this release):**

- **Market structure** — swing points, HH/HL/LH/LL, Break of Structure, Change of Character
- **Liquidity** — equal highs/lows, session highs/lows, and liquidity sweeps

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

Run the built-in synthetic demos — an uptrend with two BOS and a CHoCH reversal,
then a stop hunt through a pair of equal highs:

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

## No look-ahead

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

## Choices baked in

- **Strict comparisons.** A flat stretch of equal highs yields no swing, instead
  of tagging every candle in it — and no candle is ever both a swing high and a
  swing low.
- **Close-based breaks.** A wick through a level is not a break; the candle has
  to close beyond it.
- **First break out of a range is a BOS,** not a CHoCH — with no established
  trend there is nothing to change character from.

## Not in scope for Phase 1

Order blocks, fair value gaps, multi-timeframe alignment, position sizing,
and anything that touches a broker.

## Status

Phase 1 is feature complete and covered by 41 unit tests. This is analysis
logic only — it produces labels and signals, not trades. Nothing here has been
validated against live markets, and it makes no claim about profitability.
