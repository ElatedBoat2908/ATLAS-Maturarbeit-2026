from __future__ import annotations

import argparse
import json
import math
import hashlib
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: gymnasium. Install with:\n"
        "  python -m pip install stable-baselines3 gymnasium"
    ) from exc

try:
    from stable_baselines3 import PPO
    from stable_baselines3.common.utils import set_random_seed
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: stable-baselines3. Install with:\n"
        "  python -m pip install stable-baselines3 gymnasium"
    ) from exc


SEED = 42
WINDOW = 20
TRAIN_FRACTIONS = (0.55, 0.70, 0.85)
TEST_FRACTION = 0.15
INITIAL_EQUITY = 1.0
ABNORMAL_GAP_DAYS = 7.0


@dataclass(frozen=True)
class PPOConfig:
    seed: int = SEED
    window: int = WINDOW
    learning_rate: float = 3e-4
    gamma: float = 0.99
    gae_lambda: float = 0.95
    n_steps: int = 2048
    batch_size: int = 64
    policy: str = "MlpPolicy"
    min_timesteps: int = 50_000
    train_passes: int = 2
    max_timesteps: int = 200_000


REQUIRED_COLUMNS = ["time", "open", "high", "low", "close", "tick_volume"]


def project_root() -> Path:
    # Expected location: <project>/scripts/matura_ppo_minimalziel.py
    here = Path(__file__).resolve()
    if here.parent.name.lower() == "scripts":
        return here.parent.parent
    return here.parent


def find_dataset(root: Path, explicit: str | None = None) -> Path:
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Dataset not found: {p}")
        return p

    preferred = [
        root / "data" / "raw" / "USTEC_M5.parquet",
        root / "data" / "processed" / "USTEC_M5.parquet",
        root / "data" / "raw" / "USTEC.c_M5.parquet",
        root / "data" / "processed" / "USTEC.c_M5.parquet",
    ]
    for p in preferred:
        if p.exists():
            return p

    candidates = sorted(root.glob("data/**/*USTEC*M5*.parquet"))
    if not candidates:
        raise FileNotFoundError(
            "No USTEC M5 parquet file found under data/.\n"
            "Run the existing MT5 data pipeline first, e.g.:\n"
            "  python src/data_pipeline.py\n"
            "or pass --data <path-to-parquet>."
        )
    return candidates[0]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def select_longest_continuous_segment(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Split only at clearly abnormal source discontinuities (> 7 calendar days).
    Normal weekends/market holidays remain part of the series. The longest segment
    by row count is selected mechanically BEFORE any PPO training/result is seen.
    """
    delta_days = df["time"].diff().dt.total_seconds().div(86400.0)
    break_mask = delta_days > ABNORMAL_GAP_DAYS
    segment_id = break_mask.cumsum()
    counts = segment_id.value_counts().sort_index()
    selected_id = int(counts.idxmax())

    segments = []
    for sid, group in df.groupby(segment_id, sort=True):
        segments.append({
            "segment_id": int(sid),
            "rows": int(len(group)),
            "from": str(group["time"].iloc[0]),
            "to": str(group["time"].iloc[-1]),
            "selected": bool(int(sid) == selected_id),
        })

    abnormal_gaps = []
    for idx in np.flatnonzero(break_mask.to_numpy()):
        abnormal_gaps.append({
            "from": str(df.iloc[idx - 1]["time"]),
            "to": str(df.iloc[idx]["time"]),
            "gap_days": float(delta_days.iloc[idx]),
        })

    selected = df.loc[segment_id == selected_id].reset_index(drop=True)
    audit = {
        "abnormal_gap_threshold_days": ABNORMAL_GAP_DAYS,
        "abnormal_gaps": abnormal_gaps,
        "segments": segments,
        "selection_rule": "longest segment by row count; tie -> earliest segment",
        "selected_segment_id": selected_id,
        "selected_rows_before_feature_warmup": int(len(selected)),
        "selected_from": str(selected["time"].iloc[0]),
        "selected_to": str(selected["time"].iloc[-1]),
    }
    return selected, audit


def load_and_validate(path: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    df = pd.read_parquet(path).copy()
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    if df["time"].isna().any():
        raise ValueError("Dataset contains invalid or missing timestamps.")

    raw_rows = int(len(df))
    df = (
        df.sort_values("time")
        .drop_duplicates(subset=["time"], keep="first")
        .reset_index(drop=True)
    )

    numeric = ["open", "high", "low", "close", "tick_volume"]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if df[numeric].isna().any().any():
        raise ValueError("Dataset contains non-numeric/NaN OHLCV values.")

    bad = df[
        (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    ]
    if not bad.empty:
        raise ValueError(f"OHLC integrity errors: {len(bad)} rows")

    if len(df) < 5_000:
        raise ValueError(
            f"Only {len(df)} M5 rows found. Too little for the frozen 3-fold baseline."
        )

    full_meta = {
        "raw_rows": raw_rows,
        "deduplicated_rows": int(len(df)),
        "raw_from": str(df["time"].iloc[0]),
        "raw_to": str(df["time"].iloc[-1]),
        "dataset_sha256": file_sha256(path),
    }
    selected, continuity = select_longest_continuous_segment(df)
    featured = add_causal_features(selected)
    if len(featured) < 15_000:
        raise ValueError(
            f"Selected continuous segment has only {len(featured)} usable rows; "
            "too little for the frozen 3-fold baseline."
        )
    meta = {**full_meta, **continuity, "rows_after_causal_feature_warmup": int(len(featured))}
    return featured, meta


def add_causal_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)

    # All price features at row t use only row t and previous close.
    for source, dest in [
        ("open", "f_open"),
        ("high", "f_high"),
        ("low", "f_low"),
        ("close", "f_close"),
    ]:
        out[dest] = out[source] / prev_close - 1.0

    # Trailing-only volume normalization; no centred window and no future data.
    vol = np.log1p(out["tick_volume"].clip(lower=0))
    trailing_mean = vol.rolling(WINDOW, min_periods=2).mean()
    trailing_std = vol.rolling(WINDOW, min_periods=2).std(ddof=0)
    out["f_volume"] = (vol - trailing_mean) / trailing_std.replace(0.0, np.nan)

    features = ["f_open", "f_high", "f_low", "f_close", "f_volume"]
    out[features] = out[features].replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=features).reset_index(drop=True)
    return out


FEATURES = ["f_open", "f_high", "f_low", "f_close", "f_volume"]


class PPOTradingEnv(gym.Env):
    """
    Leakage-controlled M5 target-position environment.

    Decision time is an execution Open. The observation contains the WINDOW completed
    bars strictly before that Open plus the current position. The selected Flat/Long/Short
    target is executed at the current Open and earns the Open-to-next-Open return.
    Therefore every execution occurs one bar after the last bar used in the observation.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        df: pd.DataFrame,
        *,
        window: int = WINDOW,
        start_index: int | None = None,
        end_index: int | None = None,
        seed: int = SEED,
    ) -> None:
        super().__init__()
        self.df = df.reset_index(drop=True)
        self.window = int(window)
        self.start_index = self.window if start_index is None else int(start_index)
        self.end_index = len(self.df) - 1 if end_index is None else int(end_index)
        if self.start_index < self.window:
            raise ValueError("start_index does not leave enough completed history.")
        if self.end_index <= self.start_index:
            raise ValueError("end_index must be greater than start_index.")

        obs_size = self.window * len(FEATURES) + 1
        self.observation_space = spaces.Box(
            low=-20.0,
            high=20.0,
            shape=(obs_size,),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(3)  # 0 Flat, 1 Long, 2 Short
        self._seed = int(seed)
        self.cursor = self.start_index
        self.current_position = 0
        self.equity = INITIAL_EQUITY
        self.equity_curve: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.action_counts = {"flat": 0, "long": 0, "short": 0}
        self.open_trade: dict[str, Any] | None = None

    @staticmethod
    def action_to_position(action: int) -> int:
        if action == 0:
            return 0
        if action == 1:
            return 1
        if action == 2:
            return -1
        raise ValueError(f"Unknown action: {action}")

    def _observation(self) -> np.ndarray:
        # At Open[cursor], only bars 0..cursor-1 are completed.
        lo = self.cursor - self.window
        hi = self.cursor
        x = self.df.loc[lo : hi - 1, FEATURES].to_numpy(dtype=np.float32)
        x = np.clip(x, -20.0, 20.0).reshape(-1)
        pos = np.asarray([float(self.current_position)], dtype=np.float32)
        return np.concatenate([x, pos]).astype(np.float32)

    def _close_trade(self, exit_idx: int) -> None:
        if self.open_trade is None:
            return
        exit_price = float(self.df.iloc[exit_idx]["open"])
        side = int(self.open_trade["position"])
        entry_price = float(self.open_trade["entry"])
        trade_return = float(side * (exit_price / entry_price - 1.0))
        self.trades.append(
            {
                "entry_time": self.open_trade["entry_time"],
                "exit_time": str(self.df.iloc[exit_idx]["time"]),
                "side": "long" if side == 1 else "short",
                "entry": entry_price,
                "exit": exit_price,
                "return": trade_return,
                "win": bool(trade_return > 0.0),
            }
        )
        self.open_trade = None

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=self._seed if seed is None else seed)
        self.cursor = self.start_index
        self.current_position = 0
        self.equity = INITIAL_EQUITY
        self.equity_curve = [
            {
                "time": str(self.df.iloc[self.cursor]["time"]),
                "equity": self.equity,
            }
        ]
        self.trades = []
        self.action_counts = {"flat": 0, "long": 0, "short": 0}
        self.open_trade = None
        return self._observation(), {}

    def step(self, action: int):
        action = int(action)
        target_position = self.action_to_position(action)
        if self.cursor >= self.end_index:
            raise RuntimeError("step() called after episode end")

        execution_idx = self.cursor
        next_idx = self.cursor + 1
        execution_price = float(self.df.iloc[execution_idx]["open"])
        next_open = float(self.df.iloc[next_idx]["open"])
        if execution_price <= 0 or next_open <= 0:
            raise ValueError("Non-positive Open price encountered.")

        # Position changes happen at the current execution Open.
        if target_position != self.current_position:
            self._close_trade(execution_idx)
            if target_position != 0:
                self.open_trade = {
                    "position": target_position,
                    "entry": execution_price,
                    "entry_time": str(self.df.iloc[execution_idx]["time"]),
                }

        self.current_position = target_position
        if target_position == 0:
            self.action_counts["flat"] += 1
        elif target_position == 1:
            self.action_counts["long"] += 1
        else:
            self.action_counts["short"] += 1

        market_return = next_open / execution_price - 1.0
        strategy_return = float(self.current_position * market_return)
        self.equity *= 1.0 + strategy_return

        self.cursor = next_idx
        terminated = self.cursor >= self.end_index
        truncated = False

        # The final open closes any still-open OOS position segment.
        if terminated:
            self._close_trade(self.cursor)
            self.current_position = 0

        self.equity_curve.append(
            {
                "time": str(self.df.iloc[self.cursor]["time"]),
                "equity": float(self.equity),
            }
        )
        info = {
            "time": str(self.df.iloc[self.cursor]["time"]),
            "equity": float(self.equity),
            "position": self.current_position,
            "strategy_return": strategy_return,
        }
        return self._observation(), strategy_return, terminated, truncated, info


def build_folds(n: int) -> list[dict[str, int]]:
    folds: list[dict[str, int]] = []
    for i, train_fraction in enumerate(TRAIN_FRACTIONS, start=1):
        train_end = int(math.floor(n * train_fraction))
        if i < 3:
            test_end = int(math.floor(n * (train_fraction + TEST_FRACTION)))
        else:
            test_end = n
        folds.append(
            {
                "fold": i,
                "train_start": 0,
                "train_end_exclusive": train_end,
                "test_start": train_end,
                "test_end_exclusive": test_end,
            }
        )
    return folds


def timestamp_at(df: pd.DataFrame, idx: int) -> str:
    idx = max(0, min(int(idx), len(df) - 1))
    return str(df.iloc[idx]["time"])


def protocol_payload(df: pd.DataFrame, data_path: Path, cfg: PPOConfig, data_audit: dict[str, Any]) -> dict[str, Any]:
    folds = build_folds(len(df))
    enriched = []
    for f in folds:
        enriched.append(
            {
                **f,
                "train_from": timestamp_at(df, cfg.window - 1),
                "train_to": timestamp_at(df, f["train_end_exclusive"] - 1),
                "test_from": timestamp_at(df, f["test_start"]),
                "test_to": timestamp_at(df, f["test_end_exclusive"] - 1),
            }
        )
    return {
        "frozen_protocol_date": "2026-10-08",
        "protocol_revision": "v2_pre_result_continuity_correction",
        "revision_reason": (
            "Continuity audit found a 55-day source-data gap. Before any PPO OOS result "
            "was generated, the protocol was corrected to select the longest mechanically "
            "defined continuous segment, splitting only at gaps > 7 calendar days."
        ),
        "dataset": str(data_path),
        "dataset_sha256": data_audit["dataset_sha256"],
        "data_audit": data_audit,
        "rows_after_causal_feature_warmup": int(len(df)),
        "data_from": str(df.iloc[0]["time"]),
        "data_to": str(df.iloc[-1]["time"]),
        "rules": {
            "market": "USTEC / Nasdaq-100-related broker instrument",
            "timeframe": "M5",
            "observation": "last 20 completed M5 bars, causal OHLCV encoding + current position",
            "actions": ["Flat", "Long", "Short"],
            "execution": "state uses completed bars through t; target position executes at open(t+1) and earns open-to-next-open return",
            "reward": "equity percentage return from the target position over the next open-to-open interval; flat = 0",
            "transaction_costs": "excluded from contractual baseline; documented limitation",
            "walk_forward": "expanding train, 3 non-overlapping chronological OOS blocks",
            "continuity_rule": "before training, split at source gaps > 7 calendar days and select longest segment by row count",
        },
        "ppo": asdict(cfg),
        "folds": enriched,
    }


def training_timesteps(train_rows: int, cfg: PPOConfig) -> int:
    usable = max(1, train_rows - cfg.window)
    return int(
        min(
            cfg.max_timesteps,
            max(cfg.min_timesteps, cfg.train_passes * usable),
        )
    )


def max_drawdown_pct(equity_values: np.ndarray) -> float:
    peaks = np.maximum.accumulate(equity_values)
    drawdowns = equity_values / peaks - 1.0
    return float(drawdowns.min() * 100.0)


def evaluate_model(model: PPO, env: PPOTradingEnv) -> dict[str, Any]:
    obs, _ = env.reset(seed=SEED)
    terminated = False
    truncated = False
    while not (terminated or truncated):
        action, _ = model.predict(obs, deterministic=True)
        obs, _, terminated, truncated, _ = env.step(int(action))

    trades = pd.DataFrame(env.trades)
    equity_df = pd.DataFrame(env.equity_curve)
    eq = equity_df["equity"].to_numpy(dtype=float)

    trade_count = int(len(trades))
    win_rate = (
        float(trades["win"].mean() * 100.0) if trade_count else 0.0
    )
    result = {
        "return_pct": float((eq[-1] / INITIAL_EQUITY - 1.0) * 100.0),
        "win_rate_pct": win_rate,
        "max_drawdown_pct": max_drawdown_pct(eq),
        "trades": trade_count,
        "long_actions": int(env.action_counts["long"]),
        "short_actions": int(env.action_counts["short"]),
        "flat_actions": int(env.action_counts["flat"]),
        "final_equity": float(eq[-1]),
    }
    return {"metrics": result, "trades": trades, "equity": equity_df}


def save_equity_plot(equity_df: pd.DataFrame, out_path: Path, title: str) -> None:
    import matplotlib.pyplot as plt

    x = pd.to_datetime(equity_df["time"], utc=True)
    y = equity_df["equity"].astype(float)
    fig = plt.figure(figsize=(10, 5))
    ax = fig.add_subplot(111)
    ax.plot(x, y)
    ax.set_title(title)
    ax.set_xlabel("Time")
    ax.set_ylabel("Equity (start = 1.0)")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def print_protocol(protocol: dict[str, Any]) -> None:
    print("\nATLAS PPO MINIMALZIEL – FROZEN BASELINE")
    print("=" * 58)
    print(f"Dataset: {protocol['dataset']}")
    print(f"Rows:    {protocol['rows_after_causal_feature_warmup']}")
    print(f"Range:   {protocol['data_from']} -> {protocol['data_to']}")
    audit = protocol.get("data_audit", {})
    gaps = audit.get("abnormal_gaps", [])
    if gaps:
        print(f"Continuity correction: {len(gaps)} abnormal gap(s) > {audit.get('abnormal_gap_threshold_days')} days detected.")
        print(
            "Selected longest continuous segment BEFORE training: "
            f"{audit.get('selected_from')} -> {audit.get('selected_to')} "
            f"({audit.get('selected_rows_before_feature_warmup'):,} raw rows)"
        )
    for f in protocol["folds"]:
        print(
            f"Fold {f['fold']}: TRAIN {f['train_from']} -> {f['train_to']} | "
            f"OOS {f['test_from']} -> {f['test_to']}"
        )
    print("\nNo final OOS result may be used to retune the frozen baseline parameters.")


def run_experiment(df: pd.DataFrame, root: Path, data_path: Path, data_audit: dict[str, Any]) -> None:
    cfg = PPOConfig()
    out_dir = root / "artifacts" / "matura" / "ppo_minimalziel_20261008_v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    protocol = protocol_payload(df, data_path, cfg, data_audit)
    protocol_path = out_dir / "protocol.json"
    protocol_path.write_text(
        json.dumps(protocol, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "data_audit.json").write_text(
        json.dumps(data_audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    shutil.copy2(Path(__file__).resolve(), out_dir / "matura_ppo_minimalziel_frozen_v2.py")
    print_protocol(protocol)
    print(f"\nProtocol written BEFORE training: {protocol_path}")

    set_random_seed(cfg.seed)
    summary_rows: list[dict[str, Any]] = []

    for fold in protocol["folds"]:
        fold_no = int(fold["fold"])
        train_end = int(fold["train_end_exclusive"])
        test_start = int(fold["test_start"])
        test_end = int(fold["test_end_exclusive"])

        train_df = df.iloc[:train_end].reset_index(drop=True)
        # Keep exactly WINDOW completed bars before first OOS trade.
        test_slice_start = max(0, test_start - cfg.window)
        test_df = df.iloc[test_slice_start:test_end].reset_index(drop=True)
        local_start = test_start - test_slice_start
        if local_start < cfg.window:
            local_start = cfg.window

        train_env = PPOTradingEnv(
            train_df,
            window=cfg.window,
            start_index=cfg.window,
            end_index=len(train_df) - 1,
            seed=cfg.seed + fold_no,
        )

        timesteps = training_timesteps(len(train_df), cfg)
        print(f"\n--- Fold {fold_no} ---")
        print(f"Training rows: {len(train_df):,}")
        print(f"PPO timesteps: {timesteps:,}")

        model = PPO(
            cfg.policy,
            train_env,
            learning_rate=cfg.learning_rate,
            gamma=cfg.gamma,
            gae_lambda=cfg.gae_lambda,
            n_steps=cfg.n_steps,
            batch_size=cfg.batch_size,
            seed=cfg.seed + fold_no,
            verbose=0,
            device="cpu",
        )
        model.learn(total_timesteps=timesteps, progress_bar=False)

        model_path = out_dir / f"fold_{fold_no}_ppo_model"
        model.save(model_path)

        test_env = PPOTradingEnv(
            test_df,
            window=cfg.window,
            start_index=local_start,
            end_index=len(test_df) - 1,
            seed=cfg.seed + 100 + fold_no,
        )
        evaluation = evaluate_model(model, test_env)
        metrics = evaluation["metrics"]
        metrics.update(
            {
                "fold": fold_no,
                "train_from": fold["train_from"],
                "train_to": fold["train_to"],
                "test_from": fold["test_from"],
                "test_to": fold["test_to"],
                "training_timesteps": timesteps,
            }
        )

        (out_dir / f"fold_{fold_no}_metrics.json").write_text(
            json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        evaluation["trades"].to_csv(
            out_dir / f"fold_{fold_no}_trades.csv", index=False
        )
        evaluation["equity"].to_csv(
            out_dir / f"fold_{fold_no}_equity.csv", index=False
        )
        save_equity_plot(
            evaluation["equity"],
            out_dir / f"fold_{fold_no}_equity.png",
            f"ATLAS PPO Minimalziel – Walk-Forward Fold {fold_no} OOS",
        )

        summary_rows.append(metrics)
        print(
            "OOS: "
            f"Return={metrics['return_pct']:+.3f}% | "
            f"Winrate={metrics['win_rate_pct']:.2f}% | "
            f"MaxDD={metrics['max_drawdown_pct']:.3f}% | "
            f"Trades={metrics['trades']} | "
            f"L/S/F={metrics['long_actions']}/"
            f"{metrics['short_actions']}/{metrics['flat_actions']}"
        )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out_dir / "walk_forward_summary.csv", index=False)
    (out_dir / "walk_forward_summary.json").write_text(
        json.dumps(summary_rows, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n=== FINAL 3-FOLD OOS SUMMARY ===")
    print(
        summary[
            [
                "fold",
                "return_pct",
                "win_rate_pct",
                "max_drawdown_pct",
                "trades",
                "long_actions",
                "short_actions",
                "flat_actions",
            ]
        ].to_string(index=False)
    )
    print(f"\nAll evidence saved to:\n  {out_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ATLAS PPO Minimalziel – leakage-controlled 3-fold walk-forward baseline"
    )
    parser.add_argument(
        "--data",
        default=None,
        help="Optional explicit path to USTEC M5 parquet file.",
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Load data and print the frozen folds without training.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Run all three PPO walk-forward folds and save evidence.",
    )
    args = parser.parse_args()

    if not args.inspect and not args.run:
        parser.error("Choose --inspect or --run")

    root = project_root()
    data_path = find_dataset(root, args.data)
    df, data_audit = load_and_validate(data_path)
    cfg = PPOConfig()
    protocol = protocol_payload(df, data_path, cfg, data_audit)

    if args.inspect:
        print_protocol(protocol)
        return

    run_experiment(df, root, data_path, data_audit)


if __name__ == "__main__":
    main()
