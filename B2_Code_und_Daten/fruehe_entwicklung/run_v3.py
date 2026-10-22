import pandas as pd

import config
from strategies_v3 import trend_pullback_strategy_v3
from backtest_engine import run_backtest, summarize_results


def main() -> None:
    in_path = config.PROCESSED_DIR / f"{config.SYMBOL}_{config.TIMEFRAME_NAME}_features.parquet"

    df = pd.read_parquet(in_path)
    df = trend_pullback_strategy_v3(df)

    trades, equity = run_backtest(df)
    summary = summarize_results(trades, equity)

    print("V3 BACKTEST SUMMARY:")
    for k, v in summary.items():
        print(f"{k}: {v}")

    trades_out = config.PROCESSED_DIR / "v3_trades.parquet"
    equity_out = config.PROCESSED_DIR / "v3_equity.parquet"
    signals_out = config.PROCESSED_DIR / "v3_signals.parquet"

    trades.to_parquet(trades_out, index=False)
    equity.to_parquet(equity_out, index=False)
    df.to_parquet(signals_out, index=False)

    print(f"\nSaved trades to: {trades_out}")
    print(f"Saved equity to: {equity_out}")
    print(f"Saved signals to: {signals_out}")

    print("\nFirst trades:")
    print(trades.head(10))


if __name__ == "__main__":
    main()