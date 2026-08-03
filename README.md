# AI Trading Brain

Market structure detection in pure Python. No broker, no orders, no live data
feed, no dependencies — you hand it a list of OHLC candles and it tells you what
the structure is doing.

**Phase 1 (this release): market structure.** Swing points, HH/HL/LH/LL,
Break of Structure, Change of Character.

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

Run the built-in synthetic demo — an uptrend, two BOS, then a CHoCH reversal:

```bash
python3 -m trading_brain
```

Run the tests:

```bash
python3 -m unittest discover -s tests -t .
```

## What it detects

| Concept | Meaning |
| --- | --- |
| Swing high / low | Fractal pivot: a candle whose high (low) exceeds the `lookback` candles on both sides |
| HH / HL / LH / LL | Each swing labeled against the previous swing of the **same** type |
| Trend | Bullish / bearish / range, voted from the most recent labeled swings |
| BOS | Close beyond the last swing level **with** the trend — continuation |
| CHoCH | Close beyond the last swing level **against** the trend — possible reversal |

CHoCH is the event that fires the Invalidation Rule: when new structure confirms
the trade is no longer valid, exit.

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

## Choices baked in

- **Strict comparisons.** A flat stretch of equal highs yields no swing, instead
  of tagging every candle in it — and no candle is ever both a swing high and a
  swing low.
- **Close-based breaks.** A wick through a level is not a break; the candle has
  to close beyond it.
- **First break out of a range is a BOS,** not a CHoCH — with no established
  trend there is nothing to change character from.

## Not in scope for Phase 1

Order blocks, fair value gaps, liquidity sweeps, multi-timeframe alignment,
position sizing, and anything that touches a broker.

## Status

Phase 1 is feature complete and covered by 19 unit tests. This is analysis
logic only — it produces labels and signals, not trades. Nothing here has been
validated against live markets, and it makes no claim about profitability.
