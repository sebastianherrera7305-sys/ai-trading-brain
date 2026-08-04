"""
Walk-forward runner — AI Trading Brain, Phase 3

Loads each instrument's 10-year daily CSV, runs walk_forward() (train/test
split, parameters chosen on train, judged on test only), and prints the
out-of-sample results per fold plus an honest aggregate. This is the FVG
strategy's first out-of-sample test on real market data -- nothing here has
been run before this script existed.

liquidity_tolerance below is a price-scale parameter (how close two levels
have to be to count as "equal highs/lows"), not something the grid search
picks -- it stays fixed per instrument, same values used in this project's
earlier honest single-window backtests: gold and ES tolerate a few points of
noise, crude and EURUSD trade in much smaller price units.

Uso:
    python3 run_walk_forward.py
"""

from trading_brain.data_loader import load_candles_from_csv
from trading_brain.walk_forward import walk_forward

INSTRUMENTS = {
    "GC=F": ("data/GC_F_10y.csv", 5.0),
    "ES=F": ("data/ES_F_10y.csv", 8.0),
    "CL=F": ("data/CL_F_10y.csv", 0.3),
    "EURUSD=X": ("data/EURUSD_X_10y.csv", 0.005),
}


def main() -> int:
    for symbol, (path, liquidity_tolerance) in INSTRUMENTS.items():
        print(f"\n=== {symbol} (liquidity_tolerance={liquidity_tolerance}) ===")
        candles = load_candles_from_csv(path)
        folds = walk_forward(candles, liquidity_tolerance)

        if not folds:
            print("  sin folds -- historia insuficiente para train+test con esta ventana")
            continue

        total_test_r = 0.0
        total_test_trades = 0
        for f in folds:
            wr = "n/a" if f.test_win_rate is None else f"{f.test_win_rate:.0%}"
            print(
                f"  train {f.train_start}..{f.train_end} (R={f.train_total_r:+.2f}, "
                f"{f.train_trades} trades, rr={f.chosen_target_rr}, tier>={f.chosen_min_tier.value}) "
                f"-> test {f.test_start}..{f.test_end}: "
                f"R={f.test_total_r:+.2f}  trades={f.test_trades}  win_rate={wr}  "
                f"max_dd={f.test_max_drawdown_r:.2f}R"
            )
            total_test_r += f.test_total_r
            total_test_trades += f.test_trades

        folds_with_trades = [f for f in folds if f.test_trades > 0]
        profitable_folds = [f for f in folds if f.test_total_r > 0]
        print(
            f"  -- agregado OOS: {len(folds)} folds, {total_test_trades} trades, "
            f"R total={total_test_r:+.2f}, "
            f"{len(profitable_folds)}/{len(folds)} folds positivos, "
            f"{len(folds_with_trades)}/{len(folds)} folds con al menos 1 trade cerrado"
        )

    print(
        "\nRecordatorio: esto es una sola corrida walk-forward, sin benchmark de "
        "buy-and-hold ni test de nulidad (eso lo esta agregando la sesion del Mac "
        "sobre trading-bot). Pocos trades por fold = ruido con forma de numero, "
        "no lo trates como ventaja confirmada."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
