import pandas as pd

import config
from features import add_basic_features, add_swing_points, add_trend_state


def main() -> None:
    in_path = config.RAW_DIR / f"{config.SYMBOL}_{config.TIMEFRAME_NAME}.parquet"
    out_path = config.PROCESSED_DIR / f"{config.SYMBOL}_{config.TIMEFRAME_NAME}_features.parquet"

    df = pd.read_parquet(in_path)

    df = add_basic_features(df)
    df = add_swing_points(df, left=3, right=3)
    df = add_trend_state(df)

    df.to_parquet(out_path, index=False)

    print(f"Saved features to: {out_path}")
    print("\nColumns:")
    print(df.columns.tolist())

    print("\nPreview:")
    print(df[[
        "time", "open", "high", "low", "close",
        "ma_20", "ma_50", "ma_200",
        "atr_14", "swing_high", "swing_low",
        "last_swing_high", "last_swing_low",
        "trend_state"
    ]].tail(10))


if __name__ == "__main__":
    main()