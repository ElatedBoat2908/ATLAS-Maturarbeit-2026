import numpy as np
import pandas as pd


def add_basic_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    # Basic returns
    out["ret_1"] = out["close"].pct_change(1)
    out["ret_5"] = out["close"].pct_change(5)

    # Candle structure
    out["range"] = out["high"] - out["low"]
    out["body"] = (out["close"] - out["open"]).abs()
    out["direction"] = np.where(out["close"] >= out["open"], 1, -1)

    # Moving averages
    out["ma_20"] = out["close"].rolling(20).mean()
    out["ma_50"] = out["close"].rolling(50).mean()
    out["ma_200"] = out["close"].rolling(200).mean()

    # True Range / ATR
    prev_close = out["close"].shift(1)
    tr1 = out["high"] - out["low"]
    tr2 = (out["high"] - prev_close).abs()
    tr3 = (out["low"] - prev_close).abs()
    out["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    out["atr_14"] = out["tr"].rolling(14).mean()

    # Time features in UTC
    out["hour"] = out["time"].dt.hour
    out["minute"] = out["time"].dt.minute
    out["weekday"] = out["time"].dt.weekday

    return out


def add_swing_points(df: pd.DataFrame, left: int = 3, right: int = 3) -> pd.DataFrame:
    out = df.copy()

    out["swing_high"] = False
    out["swing_low"] = False

    highs = out["high"].values
    lows = out["low"].values

    for i in range(left, len(out) - right):
        is_swing_high = highs[i] == max(highs[i - left:i + right + 1])
        is_swing_low = lows[i] == min(lows[i - left:i + right + 1])

        if is_swing_high:
            out.at[i, "swing_high"] = True
        if is_swing_low:
            out.at[i, "swing_low"] = True

    # Last confirmed swing prices
    out["last_swing_high"] = np.where(out["swing_high"], out["high"], np.nan)
    out["last_swing_low"] = np.where(out["swing_low"], out["low"], np.nan)

    out["last_swing_high"] = out["last_swing_high"].ffill()
    out["last_swing_low"] = out["last_swing_low"].ffill()

    return out


def add_trend_state(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["trend_up"] = (
        (out["ma_20"] > out["ma_50"]) &
        (out["ma_50"] > out["ma_200"])
    )

    out["trend_down"] = (
        (out["ma_20"] < out["ma_50"]) &
        (out["ma_50"] < out["ma_200"])
    )

    out["trend_state"] = np.where(
        out["trend_up"],
        "up",
        np.where(out["trend_down"], "down", "neutral")
    )

    return out