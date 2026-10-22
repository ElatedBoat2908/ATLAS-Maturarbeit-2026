import math
import numpy as np
import pandas as pd

import config


def round_volume(volume: float, volume_step: float = 0.1, volume_min: float = 0.1) -> float:
    if volume <= 0:
        return 0.0
    rounded = math.floor(volume / volume_step) * volume_step
    return max(volume_min, rounded)


def run_backtest(
    df: pd.DataFrame,
    initial_equity: float = config.INITIAL_EQUITY,
    risk_per_trade: float = config.RISK_PER_TRADE,
    rr_target: float = 2.0,
    tick_value_per_point: float = 0.7825,
    volume_step: float = 0.1,
    volume_min: float = 0.1,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = df.copy().reset_index(drop=True)

    equity = initial_equity
    equity_curve = []
    trades = []

    position = None

    for i in range(1, len(data)):
        row = data.iloc[i]
        equity_curve.append({"time": row["time"], "equity": equity})

        if position is None:
            if bool(row.get("long_signal", False)):
                entry = row["close"]
                stop = row["last_swing_low"]

                if pd.isna(stop) or stop >= entry:
                    continue

                risk_points = entry - stop
                tp = entry + rr_target * risk_points

                cash_risk = equity * risk_per_trade
                risk_per_lot = risk_points * tick_value_per_point
                if risk_per_lot <= 0:
                    continue

                volume = round_volume(cash_risk / risk_per_lot, volume_step, volume_min)

                position = {
                    "side": "long",
                    "entry_time": row["time"],
                    "entry": entry,
                    "stop": stop,
                    "tp": tp,
                    "volume": volume,
                    "risk_points": risk_points,
                }

            elif bool(row.get("short_signal", False)):
                entry = row["close"]
                stop = row["last_swing_high"]

                if pd.isna(stop) or stop <= entry:
                    continue

                risk_points = stop - entry
                tp = entry - rr_target * risk_points

                cash_risk = equity * risk_per_trade
                risk_per_lot = risk_points * tick_value_per_point
                if risk_per_lot <= 0:
                    continue

                volume = round_volume(cash_risk / risk_per_lot, volume_step, volume_min)

                position = {
                    "side": "short",
                    "entry_time": row["time"],
                    "entry": entry,
                    "stop": stop,
                    "tp": tp,
                    "volume": volume,
                    "risk_points": risk_points,
                }

            continue

        # Manage open trade
        low = row["low"]
        high = row["high"]

        exit_price = None
        exit_reason = None

        if position["side"] == "long":
            if low <= position["stop"]:
                exit_price = position["stop"]
                exit_reason = "stop"
            elif high >= position["tp"]:
                exit_price = position["tp"]
                exit_reason = "tp"

            if exit_price is not None:
                pnl_points = exit_price - position["entry"]

        else:
            if high >= position["stop"]:
                exit_price = position["stop"]
                exit_reason = "stop"
            elif low <= position["tp"]:
                exit_price = position["tp"]
                exit_reason = "tp"

            if exit_price is not None:
                pnl_points = position["entry"] - exit_price

        if exit_price is not None:
            pnl_cash = pnl_points * tick_value_per_point * position["volume"]
            r_multiple = pnl_points / position["risk_points"] if position["risk_points"] > 0 else np.nan
            equity += pnl_cash

            trades.append({
                "side": position["side"],
                "entry_time": position["entry_time"],
                "exit_time": row["time"],
                "entry": position["entry"],
                "exit": exit_price,
                "stop": position["stop"],
                "tp": position["tp"],
                "volume": position["volume"],
                "risk_points": position["risk_points"],
                "pnl_cash": pnl_cash,
                "r_multiple": r_multiple,
                "exit_reason": exit_reason,
                "equity_after": equity,
            })

            position = None

    trades_df = pd.DataFrame(trades)
    equity_df = pd.DataFrame(equity_curve)

    return trades_df, equity_df


def summarize_results(trades_df: pd.DataFrame, equity_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_r": 0.0,
            "total_pnl": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
        }

    wins = trades_df.loc[trades_df["pnl_cash"] > 0, "pnl_cash"].sum()
    losses = -trades_df.loc[trades_df["pnl_cash"] < 0, "pnl_cash"].sum()

    eq = equity_df.copy()
    eq["peak"] = eq["equity"].cummax()
    eq["drawdown_pct"] = (eq["equity"] - eq["peak"]) / eq["peak"] * 100.0

    return {
        "trades": int(len(trades_df)),
        "win_rate": float((trades_df["pnl_cash"] > 0).mean()),
        "avg_r": float(trades_df["r_multiple"].mean()),
        "total_pnl": float(trades_df["pnl_cash"].sum()),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "max_drawdown_pct": float(eq["drawdown_pct"].min()) if not eq.empty else 0.0,
    }