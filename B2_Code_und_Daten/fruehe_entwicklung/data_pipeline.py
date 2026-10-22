import MetaTrader5 as mt5
import pandas as pd

import config
from validate_data import validate_bars


TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1,
    "M5": mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1": mt5.TIMEFRAME_H1,
    "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1,
}


def initialize_mt5() -> None:
    if not mt5.initialize():
        raise RuntimeError(f"initialize() failed: {mt5.last_error()}")


def ensure_symbol(symbol: str) -> None:
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"symbol_info({symbol}) failed: {mt5.last_error()}")

    if not info.visible:
        if not mt5.symbol_select(symbol, True):
            raise RuntimeError(f"symbol_select({symbol}) failed: {mt5.last_error()}")


def fetch_recent_bars(symbol: str, timeframe_name: str, count: int = 100000) -> pd.DataFrame:
    timeframe = TIMEFRAME_MAP[timeframe_name]

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None:
        raise RuntimeError(f"copy_rates_from_pos() failed: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    if df.empty:
        raise RuntimeError("No bars returned from MT5")

    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)

    return df


def save_raw_data(df: pd.DataFrame, out_path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)


def main() -> None:
    initialize_mt5()
    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"account_info() failed: {mt5.last_error()}")

        print("CONNECTED ACCOUNT:")
        print(account)

        ensure_symbol(config.SYMBOL)

        df = fetch_recent_bars(
            symbol=config.SYMBOL,
            timeframe_name=config.TIMEFRAME_NAME,
            count=100000,
        )

        validate_bars(df)

        out_path = config.RAW_DIR / f"{config.SYMBOL}_{config.TIMEFRAME_NAME}.parquet"
        save_raw_data(df, out_path)

        print(f"Saved raw data to: {out_path}")
        print("\nFIRST 5 ROWS:")
        print(df.head())
        print("\nLAST 5 ROWS:")
        print(df.tail())

    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()