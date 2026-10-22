import pandas as pd


def trend_pullback_strategy_v2(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Volatility filter
    out["atr_mean_20"] = out["atr_14"].rolling(20).mean()
    out["vol_ok"] = out["atr_14"] > out["atr_mean_20"]

    # Stronger trend filter
    out["trend_up_strong"] = (
        (out["ma_20"] > out["ma_50"]) &
        (out["ma_50"] > out["ma_200"]) &
        ((out["ma_20"] - out["ma_50"]) > out["atr_14"] * 0.5)
    )

    out["trend_down_strong"] = (
        (out["ma_20"] < out["ma_50"]) &
        (out["ma_50"] < out["ma_200"]) &
        ((out["ma_50"] - out["ma_20"]) > out["atr_14"] * 0.5)
    )

    # US session filter
    out["session_ok"] = (out["hour"] >= 13) & (out["hour"] <= 20)

    # Pullbacks
    out["pullback_long"] = (
        out["trend_up_strong"] &
        (out["close"] < out["ma_20"]) &
        (out["close"] > out["ma_50"]) &
        out["vol_ok"] &
        out["session_ok"]
    )

    out["pullback_short"] = (
        out["trend_down_strong"] &
        (out["close"] > out["ma_20"]) &
        (out["close"] < out["ma_50"]) &
        out["vol_ok"] &
        out["session_ok"]
    )

    # Entry confirmation
    out["long_signal"] = (
        out["pullback_long"].shift(1).fillna(False) &
        (out["close"] > out["ma_20"])
    )

    out["short_signal"] = (
        out["pullback_short"].shift(1).fillna(False) &
        (out["close"] < out["ma_20"])
    )

    return out