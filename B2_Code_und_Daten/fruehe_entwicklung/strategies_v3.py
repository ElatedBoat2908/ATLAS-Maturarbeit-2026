import pandas as pd


def trend_pullback_strategy_v3(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Same basic volatility filter as V1
    out["atr_mean_20"] = out["atr_14"].rolling(20).mean()
    out["vol_ok"] = out["atr_14"] > out["atr_mean_20"]

    # Keep the original V1 trend logic
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

    # Session filter: avoid the quietest hours, keep broad intraday coverage
    out["session_ok"] = (out["hour"] >= 7) & (out["hour"] <= 21)

    # Entry confirmation as in V1
    out["long_signal_raw"] = (
        out["pullback_long"].shift(1).fillna(False) &
        (out["close"] > out["ma_20"])
    )

    out["short_signal_raw"] = (
        out["pullback_short"].shift(1).fillna(False) &
        (out["close"] < out["ma_20"])
    )

    # Quality filter placeholder:
    # we keep only signals during the chosen session.
    # Stop-distance quality will be enforced in the runner/backtest input stage later.
    out["long_signal"] = out["long_signal_raw"] & out["session_ok"]
    out["short_signal"] = out["short_signal_raw"] & out["session_ok"]

    return out