import pandas as pd


def trend_pullback_strategy(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Basic volatility filter
    out["atr_mean_20"] = out["atr_14"].rolling(20).mean()
    out["vol_ok"] = out["atr_14"] > out["atr_mean_20"]

    # Pullback definitions
    out["pullback_long"] = (
        (out["trend_state"] == "up") &
        (out["close"] < out["ma_20"]) &
        (out["close"] > out["ma_50"]) &
        out["vol_ok"]
    )

    out["pullback_short"] = (
        (out["trend_state"] == "down") &
        (out["close"] > out["ma_20"]) &
        (out["close"] < out["ma_50"]) &
        out["vol_ok"]
    )

    # Entry confirmation on the next bar
    out["long_signal"] = (
        out["pullback_long"].shift(1).fillna(False) &
        (out["close"] > out["ma_20"])
    )

    out["short_signal"] = (
        out["pullback_short"].shift(1).fillna(False) &
        (out["close"] < out["ma_20"])
    )

    return out