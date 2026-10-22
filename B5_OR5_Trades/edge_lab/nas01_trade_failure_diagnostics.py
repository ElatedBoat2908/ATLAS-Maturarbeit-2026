from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .nas01_trade_outcome import (
    REPORT_REL as TRADE_REPORT_REL,
    TRADES_REL as TRADES_REL,
    verify_frozen_trade_runner,
)

PHASE = "0.7G.14"
ANALYSIS_VERSION = "NAS-H001-V1-TRADE-FAILURE-DIAGNOSTICS-V1"
HYPOTHESIS_KEY = "NAS-H001-V1"
PATH_PLAN_REL = Path("config/edge_lab/analysis/NAS-H001-V1-development-path.json")
TRADE_RUNNER_CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-trade-runner.json")
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_trade_failure_diagnostics_2019_2025.json"
)


@dataclass(frozen=True)
class GeometryMetrics:
    boundary: float
    or_width: float
    entry_progress_or: float
    reward_distance: float
    gross_reward_r: float


def _utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts


def geometry_metrics(row: dict[str, Any]) -> GeometryMetrics:
    direction = str(row["direction"]).upper()
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")
    target = float(row["target"])
    stop = float(row["stop"])
    entry = float(row["entry_fill"])
    risk = float(row["initial_risk"])
    width = abs(target - stop)
    if not np.isfinite(width) or width <= 0:
        raise ValueError("invalid OR width inferred from target/stop")
    if not np.isfinite(risk) or risk <= 0:
        raise ValueError("invalid initial risk")
    boundary = 0.5 * (target + stop)
    if direction == "LONG":
        progress = (entry - boundary) / width
        reward = target - entry
    else:
        progress = (boundary - entry) / width
        reward = entry - target
    return GeometryMetrics(
        boundary=float(boundary),
        or_width=float(width),
        entry_progress_or=float(progress),
        reward_distance=float(reward),
        gross_reward_r=float(reward / risk),
    )


def required_target_probability(mean_target_r: float, mean_stop_r: float) -> float:
    """Break-even target probability using observed average TARGET and STOP R.

    TIME exits are excluded.  This is descriptive only; it is not a trading gate.
    """
    win = float(mean_target_r)
    loss = abs(float(mean_stop_r))
    if not np.isfinite(win) or not np.isfinite(loss) or win <= 0 or loss <= 0:
        return float("nan")
    return float(loss / (win + loss))


def _load_trade_artifacts(project_root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    verify_frozen_trade_runner(project_root)
    report_path = project_root / TRADE_REPORT_REL
    trades_path = project_root / TRADES_REL
    if not report_path.exists() or not trades_path.exists():
        raise RuntimeError("frozen executable trade research must be run before failure diagnostics")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("scientific_gate") != "REJECT_EXECUTABLE_MAPPING_V1_WITHOUT_OPENING_2026":
        raise RuntimeError("failure diagnostics are only valid after the frozen V1 mapping is rejected")
    if report.get("final_2026_holdout_accessed") is not False:
        raise RuntimeError("2026+ holdout contamination detected in trade report")
    rows: list[dict[str, Any]] = []
    with trades_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    if not rows:
        raise RuntimeError("trade artifact is empty")
    frame = pd.DataFrame(rows)
    ts = pd.to_datetime(frame["available_at"], utc=True, errors="raise")
    if bool((ts >= pd.Timestamp("2026-01-01T00:00:00Z")).any()):
        raise RuntimeError("2026+ trade row detected; diagnostics refuse to continue")
    return report, frame


def _semantics_audit(project_root: Path) -> dict[str, Any]:
    path_plan = json.loads((project_root / PATH_PLAN_REL).read_text(encoding="utf-8"))
    trade_cfg = json.loads((project_root / TRADE_RUNNER_CONFIG_REL).read_text(encoding="utf-8"))
    mechanism_basis = str((path_plan.get("primary_mechanism_test") or {}).get("price_basis"))
    trade_basis = str((trade_cfg.get("execution") or {}).get("barrier_trigger_basis"))
    return {
        "confirmed_mechanism_price_basis": mechanism_basis,
        "executable_mapping_barrier_trigger_basis": trade_basis,
        "same_basis": mechanism_basis == trade_basis,
        "interpretation": (
            "The confirmed mechanism is close-based, while executable V1 uses intrabar high/low touches. "
            "This is a deliberate execution translation, not a coding error, but it means V1 is not a literal execution of the confirmed close-based statistic."
        ),
    }


def _fixed_progress_bin(value: float) -> str:
    if value < 0.0:
        return "ENTRY_INSIDE_BROKEN_BOUNDARY_<0.00"
    if value < 0.10:
        return "0.00_TO_<0.10_OR"
    if value < 0.25:
        return "0.10_TO_<0.25_OR"
    if value < 0.40:
        return "0.25_TO_<0.40_OR"
    return "0.40_TO_<0.50_OR"


def _group_stats(frame: pd.DataFrame, key: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for value, group in frame.groupby(key, sort=True):
        barrier = group[group["exit_kind"].isin(["TARGET", "STOP"])]
        target_rate = float((barrier["exit_kind"] == "TARGET").mean()) if not barrier.empty else float("nan")
        out[str(value)] = {
            "n": int(len(group)),
            "mean_R": float(group["R"].mean()),
            "median_R": float(group["R"].median()),
            "target_rate_among_target_stop": target_rate,
            "median_entry_progress_OR": float(group["entry_progress_OR"].median()),
            "median_gross_reward_R_before_exit_cost": float(group["gross_reward_R_before_exit_cost"].median()),
            "median_entry_spread_over_risk": float(group["entry_spread_over_risk"].median()),
        }
    return out


def run_failure_diagnostics(project_root: Path) -> tuple[Path, dict[str, Any]]:
    prior_report, frame = _load_trade_artifacts(project_root)

    geom = [geometry_metrics(rec) for rec in frame.to_dict(orient="records")]
    frame = frame.copy()
    frame["entry_progress_OR"] = [g.entry_progress_or for g in geom]
    frame["gross_reward_R_before_exit_cost"] = [g.gross_reward_r for g in geom]
    frame["entry_spread_over_risk"] = frame["entry_spread_price"].astype(float) / frame["initial_risk"].astype(float)
    frame["entry_slippage_over_risk"] = frame["baseline_entry_slippage"].astype(float) / frame["initial_risk"].astype(float)
    frame["exit_spread_over_risk"] = frame["exit_spread_price"].astype(float) / frame["initial_risk"].astype(float)
    frame["exit_slippage_over_risk"] = frame["baseline_exit_slippage"].astype(float) / frame["initial_risk"].astype(float)
    frame["entry_progress_bin"] = frame["entry_progress_OR"].map(_fixed_progress_bin)

    target = frame[frame["exit_kind"] == "TARGET"]
    stop = frame[frame["exit_kind"] == "STOP"]
    time = frame[frame["exit_kind"] == "TIME"]
    barrier = frame[frame["exit_kind"].isin(["TARGET", "STOP"])]
    target_rate = float((barrier["exit_kind"] == "TARGET").mean()) if not barrier.empty else float("nan")
    mean_target_r = float(target["R"].mean()) if not target.empty else float("nan")
    mean_stop_r = float(stop["R"].mean()) if not stop.empty else float("nan")
    required_p = required_target_probability(mean_target_r, mean_stop_r)

    ineligible = int(prior_report.get("ineligible_count", 0))
    candidates = int(prior_report.get("candidate_count", 0))
    geometry_rejects = int((prior_report.get("ineligible_by_reason") or {}).get("NO_TRADE_INEXECUTABLE_GEOMETRY", 0))

    diagnostics = {
        "phase": PHASE,
        "analysis_version": ANALYSIS_VERSION,
        "hypothesis": HYPOTHESIS_KEY,
        "scope": "POST_HOC_FAILURE_DIAGNOSTICS_ONLY__2019_2025_ALREADY_OPENED",
        "2026_plus_holdout_accessed": False,
        "new_parameter_search": False,
        "new_filter_selection": False,
        "new_trade_hypothesis_selected": False,
        "prior_frozen_result": {
            "status": prior_report.get("scientific_gate"),
            "candidates": candidates,
            "executed_trades": int(prior_report.get("executed_trades", len(frame))),
            "mean_R": float(prior_report.get("mean_cost_adjusted_R")),
            "profit_factor_R": float(prior_report.get("profit_factor_R")),
            "bootstrap_lower95": float((prior_report.get("bootstrap_mean_R") or {}).get("lower95")),
            "bootstrap_upper95": float((prior_report.get("bootstrap_mean_R") or {}).get("upper95")),
            "positive_years": int(prior_report.get("positive_calendar_years", 0)),
        },
        "eligibility_geometry": {
            "ineligible_total": ineligible,
            "geometry_rejects": geometry_rejects,
            "geometry_reject_fraction_of_all_candidates": float(geometry_rejects / candidates) if candidates else float("nan"),
            "interpretation": "These candidates had already advanced so far that the frozen target was no longer strictly favorable to the executable next-bar entry.",
        },
        "payoff_geometry": {
            "target_exits": int(len(target)),
            "stop_exits": int(len(stop)),
            "time_exits": int(len(time)),
            "target_rate_among_target_stop": target_rate,
            "positive_R_fraction_all_executed": float((frame["R"] > 0).mean()),
            "positive_R_fraction_of_target_exits": float((target["R"] > 0).mean()) if not target.empty else float("nan"),
            "mean_R_target_exit": mean_target_r,
            "median_R_target_exit": float(target["R"].median()) if not target.empty else float("nan"),
            "mean_R_stop_exit": mean_stop_r,
            "median_R_stop_exit": float(stop["R"].median()) if not stop.empty else float("nan"),
            "required_target_probability_from_observed_average_target_stop_R": required_p,
            "actual_minus_required_target_probability": float(target_rate - required_p) if np.isfinite(required_p) else float("nan"),
            "median_entry_progress_OR": float(frame["entry_progress_OR"].median()),
            "p90_entry_progress_OR": float(frame["entry_progress_OR"].quantile(0.90)),
            "median_gross_reward_R_before_exit_cost": float(frame["gross_reward_R_before_exit_cost"].median()),
            "p10_gross_reward_R_before_exit_cost": float(frame["gross_reward_R_before_exit_cost"].quantile(0.10)),
            "median_entry_spread_over_initial_risk": float(frame["entry_spread_over_risk"].median()),
            "median_entry_slippage_over_initial_risk": float(frame["entry_slippage_over_risk"].median()),
            "median_exit_spread_over_initial_risk": float(frame["exit_spread_over_risk"].median()),
            "median_exit_slippage_over_initial_risk": float(frame["exit_slippage_over_risk"].median()),
            "mean_target_R_haircut_vs_gross_reward_R": float((target["gross_reward_R_before_exit_cost"] - target["R"]).mean()) if not target.empty else float("nan"),
            "mean_stop_R_beyond_minus_one": float((-1.0 - stop["R"]).mean()) if not stop.empty else float("nan"),
        },
        "semantic_mapping_audit": _semantics_audit(project_root),
        "fixed_geometry_bins_DIAGNOSTIC_ONLY": _group_stats(frame, "entry_progress_bin"),
        "by_year_DIAGNOSTIC_ONLY": _group_stats(frame, "year"),
        "by_direction_DIAGNOSTIC_ONLY": _group_stats(frame, "direction"),
        "scientific_interpretation": {
            "v1_rejection_strength": "STRUCTURAL_NOT_BORDERLINE",
            "reason": (
                "The bootstrap interval is entirely negative, every calendar year is negative, and PF_R is far below 1. "
                "The confirmed close-based continuation mechanism therefore did not survive this next-open fixed-barrier executable translation."
            ),
            "diagnostic_use_only": (
                "The bins and subgroup summaries may explain failure but must not be converted directly into filters or thresholds and retested as if they were pre-registered evidence."
            ),
            "next_research_question": (
                "Whether one mechanism-faithful executable mapping can preserve the confirmed CLOSE-based acceptance signal without the fixed-target reward compression of V1."
            ),
            "2026_policy": "KEEP_LOCKED",
        },
        "status": "V1_REJECTED__FAILURE_DIAGNOSTICS_COMPLETE__KEEP_2026_LOCKED",
    }

    out = project_root / REPORT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(diagnostics, indent=2, sort_keys=True), encoding="utf-8")
    return out, diagnostics
