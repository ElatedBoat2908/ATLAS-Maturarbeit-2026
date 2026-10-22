import pandas as pd


def validate_bars(df: pd.DataFrame) -> None:
    required = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    if df.empty:
        raise ValueError("DataFrame is empty")

    if df["time"].isna().any():
        raise ValueError("Found missing timestamps")

    if not df["time"].is_monotonic_increasing:
        raise ValueError("Timestamps are not sorted ascending")

    dupes = int(df["time"].duplicated().sum())
    if dupes > 0:
        raise ValueError(f"Found {dupes} duplicate timestamps")

    bad = df[
        (df["high"] < df[["open", "close", "low"]].max(axis=1)) |
        (df["low"] > df[["open", "close", "high"]].min(axis=1))
    ]
    if not bad.empty:
        raise ValueError(f"Found {len(bad)} OHLC integrity errors")

    print("Validation passed.")
    print(f"Rows: {len(df)}")
    print(f"From: {df['time'].min()}")
    print(f"To:   {df['time'].max()}")