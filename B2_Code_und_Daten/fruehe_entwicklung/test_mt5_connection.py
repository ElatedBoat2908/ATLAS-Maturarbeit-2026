import MetaTrader5 as mt5
import pandas as pd

SYMBOL = "USTEC"

def main():
    if not mt5.initialize():
        raise RuntimeError(f"initialize() failed: {mt5.last_error()}")

    try:
        account = mt5.account_info()
        if account is None:
            raise RuntimeError(f"account_info() failed: {mt5.last_error()}")

        print("CONNECTED ACCOUNT:")
        print(account)

        symbol_info = mt5.symbol_info(SYMBOL)
        if symbol_info is None:
            raise RuntimeError(f"symbol_info({SYMBOL}) failed: {mt5.last_error()}")

        if not symbol_info.visible:
            if not mt5.symbol_select(SYMBOL, True):
                raise RuntimeError(f"symbol_select({SYMBOL}) failed: {mt5.last_error()}")

        print("\nSYMBOL INFO:")
        print(symbol_info)

        # Get the latest 2000 M5 bars
        rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M5, 0, 2000)
        if rates is None:
            raise RuntimeError(f"copy_rates_from_pos() failed: {mt5.last_error()}")

        df = pd.DataFrame(rates)
        if df.empty:
            raise RuntimeError("No data returned from MT5.")

        df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)

        print(f"\nROWS RETURNED: {len(df)}")
        print("\nFIRST 5 ROWS:")
        print(df.head())

        print("\nLAST 5 ROWS:")
        print(df.tail())

    finally:
        mt5.shutdown()

if __name__ == "__main__":
    main()