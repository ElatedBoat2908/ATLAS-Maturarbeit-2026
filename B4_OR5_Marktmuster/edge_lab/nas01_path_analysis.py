from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .history import SafeHistoryWindow
from .nas01_path_plan import (
    ANALYSIS_VERSION,
    CENSUS_EVENTS_REL,
    HYPOTHESIS_KEY,
    PATH_MANIFEST_REL,
    load_nas_h001_path_plan,
    verify_frozen_nas_h001_path_plan,
)
from .progress import TerminalProgress

PHASE = "0.7G.6"
MARKET_ID = "NAS100"
RUNNER_SOURCE_REL = Path("atlas/edge_lab/nas01_path_analysis.py")
RUNNER_MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_runner_manifest.json"
)
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_analysis.json"
)
EVENT_PATHS_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_event_paths.jsonl"
)
_NS_PER_MINUTE = 60_000_000_000


@dataclass(frozen=True)
class NASPathAnalysisResult:
    report: dict[str, Any]
    report_path: Path
    event_paths_path: Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _seed_for(label: str) -> int:
    raw = hashlib.sha256(f"{ANALYSIS_VERSION}|{label}|ATLAS".encode("utf-8")).digest()
    return int.from_bytes(raw[:8], "little", signed=False) % (2**32 - 1)


def _utc(ts: str | pd.Timestamp) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    out = out.tz_localize("UTC") if out.tzinfo is None else out.tz_convert("UTC")
    try:
        return out.as_unit("ns")
    except AttributeError:  # pragma: no cover
        return pd.Timestamp(out.to_datetime64().astype("datetime64[ns]"), tz="UTC")


def _prepare_m1(frame: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    required = {"time", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"NAS100 M1 missing required columns: {sorted(missing)}")
    out = frame.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out["time"], utc=True, errors="raise"))
    try:
        idx = idx.as_unit("ns")
    except AttributeError:  # pragma: no cover
        idx = pd.DatetimeIndex(idx.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]"), tz="UTC")
    out["time"] = idx
    out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    for col in ("high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="raise")
    return out, pd.DatetimeIndex(out["time"]).asi8


def _load_development_events(project_root: Path, start: pd.Timestamp, end: pd.Timestamp) -> list[dict[str, Any]]:
    path = project_root / CENSUS_EVENTS_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 census events missing: {path}")
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            ts = _utc(rec["available_at"])
            if start <= ts < end:
                events.append(rec)
    events.sort(key=lambda r: (_utc(r["available_at"]), str(r.get("context", {}).get("variant", ""))))
    return events


def _complete_future_window(time_ns: np.ndarray, start_ns: int, minutes: int) -> tuple[bool, int]:
    """Require exactly `minutes` consecutive M1 bar opens beginning at start_ns."""
    pos = int(np.searchsorted(time_ns, start_ns, side="left"))
    end = pos + int(minutes)
    if pos >= len(time_ns) or end > len(time_ns):
        return False, pos
    expected = start_ns + np.arange(minutes, dtype=np.int64) * _NS_PER_MINUTE
    return bool(np.array_equal(time_ns[pos:end], expected)), pos


def _barrier_score(
    closes: np.ndarray,
    *,
    direction: str,
    or_high: float,
    or_low: float,
    or_width: float,
    multiple: float,
) -> tuple[int, str, int | None]:
    if direction == "LONG":
        cont = closes >= or_high + multiple * or_width
        fail = closes <= or_high - multiple * or_width
    elif direction == "SHORT":
        cont = closes <= or_low - multiple * or_width
        fail = closes >= or_low + multiple * or_width
    else:
        raise ValueError(f"unexpected NAS-H001 direction: {direction}")
    hit = np.flatnonzero(cont | fail)
    if hit.size == 0:
        return 0, "UNRESOLVED", None
    i = int(hit[0])
    if bool(cont[i]):
        return 1, "CONTINUATION", i + 1
    return -1, "FAILURE", i + 1


def _signed_close(value: float, reference: float, direction: str, scale: float) -> float:
    if scale <= 0 or not np.isfinite(scale):
        return float("nan")
    return float((value - reference) / scale) if direction == "LONG" else float((reference - value) / scale)


def _measure_event_path(
    event: dict[str, Any],
    *,
    time_ns: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    horizon_minutes: int = 60,
) -> dict[str, Any] | None:
    ctx = event["context"]
    start = _utc(event["available_at"])
    complete, pos = _complete_future_window(time_ns, int(start.value), horizon_minutes)
    if not complete:
        return None

    h = high[pos:pos + horizon_minutes]
    l = low[pos:pos + horizon_minutes]
    c = close[pos:pos + horizon_minutes]
    direction = str(event["direction"])
    or_high = float(ctx["opening_range_high"])
    or_low = float(ctx["opening_range_low"])
    or_width = float(ctx["opening_range_width"])
    atr14 = float(ctx["m1_atr14_at_break"])
    reference = float(event["reference_price"])
    if not np.isfinite(or_width) or or_width <= 0 or not np.isfinite(atr14) or atr14 <= 0:
        return None

    primary_score, primary_label, primary_minute = _barrier_score(
        c,
        direction=direction,
        or_high=or_high,
        or_low=or_low,
        or_width=or_width,
        multiple=0.5,
    )

    item: dict[str, Any] = {
        "event_id": event["event_id"],
        "variant": str(ctx["variant"]),
        "session_date": str(ctx["session_date"]),
        "available_at": start.isoformat(),
        "direction": direction,
        "reference_price": reference,
        "opening_range_high": or_high,
        "opening_range_low": or_low,
        "opening_range_width": or_width,
        "event_atr14": atr14,
        "primary_score": primary_score,
        "primary_outcome": primary_label,
        "primary_resolved_minute": primary_minute,
        "break_delay_minutes": int(ctx["break_delay_minutes_after_range_end"]),
        "break_overshoot_or_width": float(ctx["close_overshoot_points"]) / or_width,
        "or_width_atr14": or_width / atr14,
    }

    # Secondary close-barrier diagnostics use the same broken-boundary geometry.
    for multiple in (0.25, 1.0):
        s, label, minute = _barrier_score(
            c,
            direction=direction,
            or_high=or_high,
            or_low=or_low,
            or_width=or_width,
            multiple=multiple,
        )
        key = str(multiple).replace(".", "_")
        item[f"barrier_{key}or_score"] = s
        item[f"barrier_{key}or_outcome"] = label
        item[f"barrier_{key}or_minute"] = minute

    for horizon in (1, 3, 5, 15, 30, 60):
        last = horizon - 1
        item[f"signed_close_or_{horizon}m"] = _signed_close(float(c[last]), reference, direction, or_width)
        item[f"signed_close_atr_{horizon}m"] = _signed_close(float(c[last]), reference, direction, atr14)
        if direction == "LONG":
            mfe = float(np.max(h[:horizon]) - reference)
            mae = float(reference - np.min(l[:horizon]))
        else:
            mfe = float(reference - np.min(l[:horizon]))
            mae = float(np.max(h[:horizon]) - reference)
        item[f"mfe_or_{horizon}m"] = mfe / or_width
        item[f"mae_or_{horizon}m"] = mae / or_width
        item[f"mfe_atr_{horizon}m"] = mfe / atr14
        item[f"mae_atr_{horizon}m"] = mae / atr14

    inside = (c >= or_low) & (c <= or_high)
    inside_hits = np.flatnonzero(inside)
    item["first_close_back_inside_or_minute"] = int(inside_hits[0] + 1) if inside_hits.size else None
    return item


def _week_labels(frame: pd.DataFrame) -> np.ndarray:
    ts = pd.to_datetime(frame["available_at"], utc=True)
    iso = ts.dt.isocalendar()
    return (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()


def _block_inference(frame: pd.DataFrame, *, simulations: int, seed: int) -> dict[str, float]:
    if frame.empty:
        return {
            "effect": float("nan"),
            "lower95": float("nan"),
            "upper95": float("nan"),
            "p_two_sided": float("nan"),
        }
    scores = frame["primary_score"].to_numpy(dtype=float)
    effect = float(np.mean(scores))
    labels = _week_labels(frame)
    unique = np.unique(labels)
    groups = [scores[labels == key] for key in unique]
    sums = np.array([float(np.sum(g)) for g in groups], dtype=float)
    counts = np.array([int(len(g)) for g in groups], dtype=np.int64)

    rng = np.random.default_rng(seed)
    boot = np.empty(simulations, dtype=float)
    null = np.empty(simulations, dtype=float)
    n_blocks = len(groups)
    total_n = float(np.sum(counts))
    for i in range(simulations):
        picks = rng.integers(0, n_blocks, size=n_blocks)
        den = float(np.sum(counts[picks]))
        boot[i] = float(np.sum(sums[picks]) / den) if den > 0 else np.nan
        signs = rng.choice(np.array([-1.0, 1.0]), size=n_blocks, replace=True)
        null[i] = float(np.sum(signs * sums) / total_n) if total_n > 0 else np.nan
    boot = boot[np.isfinite(boot)]
    null = null[np.isfinite(null)]
    lower, upper = np.quantile(boot, [0.025, 0.975])
    p = (float(np.count_nonzero(np.abs(null) >= abs(effect))) + 1.0) / (float(len(null)) + 1.0)
    return {
        "effect": effect,
        "lower95": float(lower),
        "upper95": float(upper),
        "p_two_sided": float(p),
    }


def _holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda kv: (float(kv[1]), kv[0]))
    m = len(ordered)
    adjusted_sorted: list[tuple[str, float]] = []
    running = 0.0
    for rank, (key, p) in enumerate(ordered, start=1):
        raw = min(1.0, (m - rank + 1) * float(p))
        running = max(running, raw)
        adjusted_sorted.append((key, min(1.0, running)))
    return dict(adjusted_sorted)


def _ci_distance_from_zero(lower: float, upper: float) -> float:
    if lower > 0:
        return float(lower)
    if upper < 0:
        return float(abs(upper))
    return 0.0


def _ensure_runner_manifest(project_root: Path) -> Path:
    """Freeze the concrete runner implementation before market-path IO."""
    target = project_root / RUNNER_MANIFEST_REL
    current = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "path_plan_manifest_sha256": _sha256(project_root / PATH_MANIFEST_REL),
        "bootstrap_seed_rule": "SHA256(analysis_version|variant|ATLAS) -> uint32",
        "bootstrap_simulations": 5000,
        "development_market_data_cutoff_exclusive": "2023-01-01T00:00:00Z",
        "post_break_paths_inspected_before_runner_freeze": False,
        "validation_2023_2024_accessed_before_runner_freeze": False,
        "confirmation_2025_accessed_before_runner_freeze": False,
        "2026_holdout_accessed_before_runner_freeze": False,
    }
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        for key in (
            "runner_source_sha256",
            "path_plan_manifest_sha256",
            "bootstrap_seed_rule",
            "bootstrap_simulations",
            "development_market_data_cutoff_exclusive",
        ):
            if frozen.get(key) != current[key]:
                raise RuntimeError("NAS-H001 development path runner changed after its first freeze; create a new analysis version")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    return target


def run_nas_h001_development_path_analysis(
    project_root: Path,
    *,
    show_progress: bool = True,
) -> NASPathAnalysisResult:
    # Verify conceptual freeze before creating/fixing the runner implementation.
    frozen_fp = verify_frozen_nas_h001_path_plan(project_root)
    plan = load_nas_h001_path_plan(project_root)
    runner_manifest = _ensure_runner_manifest(project_root)

    start = _utc(plan["development_window"][0])
    end = _utc(plan["market_data_cutoff_exclusive"])
    if end != _utc("2023-01-01T00:00:00Z"):
        raise RuntimeError("NAS-H001 development runner is hard-locked before 2023-01-01")

    events = _load_development_events(project_root, start, end)
    if not events:
        raise RuntimeError("no NAS-H001 development events found")

    # IO-level cutoff: validation/confirmation/final-holdout bars are never loaded.
    reader = SafeHistoryWindow(project_root=project_root, market_id=MARKET_ID)
    m1 = reader.read_before("M1", end)
    bars, time_ns = _prepare_m1(m1)
    high = bars["high"].to_numpy(dtype=float, copy=False)
    low = bars["low"].to_numpy(dtype=float, copy=False)
    close = bars["close"].to_numpy(dtype=float, copy=False)

    rows: list[dict[str, Any]] = []
    ineligible = 0
    progress = TerminalProgress(total=len(events), label="NAS-H001 development paths") if show_progress else None
    for i, event in enumerate(events, start=1):
        row = _measure_event_path(
            event,
            time_ns=time_ns,
            high=high,
            low=low,
            close=close,
            horizon_minutes=int(plan["primary_mechanism_test"]["horizon_minutes"]),
        )
        if row is None:
            ineligible += 1
        else:
            rows.append(row)
        if progress and (i == 1 or i == len(events) or i % 25 == 0):
            progress.update(i)
    if progress:
        progress.finish()

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no eligible NAS-H001 development paths")
    frame["year"] = pd.to_datetime(frame["available_at"], utc=True).dt.year.astype(int)

    simulations = int(plan["bootstrap"]["simulations"])
    variants: dict[str, dict[str, Any]] = {}
    pvals: dict[str, float] = {}
    gates_cfg = plan["development_gates_per_variant"]

    for variant in plan["variants"]:
        sub = frame[frame["variant"] == variant].copy()
        inf = _block_inference(sub, simulations=simulations, seed=_seed_for(variant))
        n = int(len(sub))
        continuation = int((sub["primary_score"] == 1).sum())
        failure = int((sub["primary_score"] == -1).sum())
        unresolved = int((sub["primary_score"] == 0).sum())
        resolved = continuation + failure
        resolved_fraction = float(resolved / n) if n else 0.0
        year_effects = {
            str(int(year)): float(g["primary_score"].mean())
            for year, g in sub.groupby("year", sort=True)
        }
        sign = 1 if inf["effect"] > 0 else -1 if inf["effect"] < 0 else 0
        same_sign_years = int(sum(1 for v in year_effects.values() if (v > 0 and sign > 0) or (v < 0 and sign < 0)))
        pvals[variant] = float(inf["p_two_sided"])
        variants[variant] = {
            "eligible_events": n,
            "continuation_first": continuation,
            "failure_first": failure,
            "unresolved": unresolved,
            "resolved_fraction": resolved_fraction,
            "primary_effect": float(inf["effect"]),
            "bootstrap_lower95": float(inf["lower95"]),
            "bootstrap_upper95": float(inf["upper95"]),
            "bootstrap_p_two_sided_unadjusted": float(inf["p_two_sided"]),
            "bootstrap_seed": int(_seed_for(variant)),
            "year_effects": year_effects,
            "same_sign_calendar_years": same_sign_years,
            "directional_event_counts": {
                str(k): int(v) for k, v in sub["direction"].value_counts().sort_index().items()
            },
            "secondary": _secondary_summary(sub),
        }

    holm = _holm_adjust(pvals)
    passing: list[str] = []
    for variant in plan["variants"]:
        v = variants[variant]
        v["holm_adjusted_p"] = float(holm[variant])
        checks = [
            {
                "name": "minimum_eligible_events",
                "pass": int(v["eligible_events"]) >= int(gates_cfg["minimum_eligible_events"]),
                "observed": int(v["eligible_events"]),
                "required": int(gates_cfg["minimum_eligible_events"]),
            },
            {
                "name": "minimum_resolved_fraction",
                "pass": float(v["resolved_fraction"]) >= float(gates_cfg["minimum_resolved_fraction"]),
                "observed": float(v["resolved_fraction"]),
                "required": float(gates_cfg["minimum_resolved_fraction"]),
            },
            {
                "name": "minimum_absolute_effect",
                "pass": abs(float(v["primary_effect"])) >= float(gates_cfg["minimum_absolute_effect"]),
                "observed": abs(float(v["primary_effect"])),
                "required": float(gates_cfg["minimum_absolute_effect"]),
            },
            {
                "name": "bootstrap_interval_excludes_zero",
                "pass": bool(float(v["bootstrap_lower95"]) > 0 or float(v["bootstrap_upper95"]) < 0),
                "observed": [float(v["bootstrap_lower95"]), float(v["bootstrap_upper95"])],
                "required": "95% interval entirely above or below zero",
            },
            {
                "name": "same_sign_calendar_years",
                "pass": int(v["same_sign_calendar_years"]) >= int(gates_cfg["minimum_same_sign_calendar_years"]),
                "observed": int(v["same_sign_calendar_years"]),
                "required": int(gates_cfg["minimum_same_sign_calendar_years"]),
            },
            {
                "name": "holm_adjusted_p",
                "pass": float(v["holm_adjusted_p"]) < float(gates_cfg["holm_adjusted_alpha_across_three_variants"]),
                "observed": float(v["holm_adjusted_p"]),
                "required": f"< {float(gates_cfg['holm_adjusted_alpha_across_three_variants'])}",
            },
        ]
        v["gate_checks"] = checks
        passed = all(bool(x["pass"]) for x in checks)
        v["gate_status"] = "PASS" if passed else "FAIL"
        if passed:
            v["mechanism_classification"] = (
                "ROBUST_CONTINUATION_CANDIDATE" if float(v["primary_effect"]) > 0
                else "ROBUST_FAILED_AUCTION_REVERSAL_CANDIDATE"
            )
            v["ci_distance_from_zero"] = _ci_distance_from_zero(
                float(v["bootstrap_lower95"]), float(v["bootstrap_upper95"])
            )
            passing.append(variant)
        else:
            v["mechanism_classification"] = "NO_ROBUST_PRIMARY_ASYMMETRY"
            v["ci_distance_from_zero"] = 0.0

    selected: str | None = None
    if passing:
        duration = {"OR5": 5, "OR15": 15, "OR30": 30}
        selected = sorted(
            passing,
            key=lambda k: (
                -float(variants[k]["ci_distance_from_zero"]),
                -int(variants[k]["continuation_first"] + variants[k]["failure_first"]),
                duration[k],
            ),
        )[0]

    report: dict[str, Any] = {
        "phase": PHASE,
        "budget_id": "NAS100-BUDGET-1",
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "path_plan_operational_fingerprint": frozen_fp,
        "path_plan_manifest_sha256": _sha256(project_root / PATH_MANIFEST_REL),
        "runner_manifest_sha256": _sha256(runner_manifest),
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "development_window": [start.isoformat(), end.isoformat()],
        "market_data_cutoff_exclusive": end.isoformat(),
        "development_events_from_census": int(len(events)),
        "eligible_complete_60m_paths": int(len(frame)),
        "ineligible_incomplete_60m_paths": int(ineligible),
        "primary_mechanism": "0.5 OR-width close barrier first within 60m, starting next M1 bar",
        "variants": variants,
        "holm_family": list(plan["variants"]),
        "variants_passing_all_development_gates": passing,
        "selected_variant": selected,
        "selected_mechanism": variants[selected]["mechanism_classification"] if selected else None,
        "scientific_gate": "PASS_TO_VARIANT_FREEZE_BEFORE_VALIDATION" if selected else "NO_ROBUST_PRIMARY_ASYMMETRY",
        "validation_2023_2024_paths_accessed": False,
        "confirmation_2025_paths_accessed": False,
        "final_2026_holdout_accessed": False,
        "trade_entry_stop_target_r_pf_pnl_inspected": False,
        "secondary_diagnostics_may_rescue_primary": False,
        "notes": [
            "OR5/OR15/OR30 remain separate and were Holm-corrected as one three-test family.",
            "Unresolved events are scored 0 in the primary effect exactly as preregistered.",
            "No executable trade, cost model, stop, target, R, PF or PnL is inferred from this market-mechanism test.",
            "If no variant passes, 2023-2025 remains locked and NAS-H001-V1 ends without a trade hypothesis.",
        ],
    }

    out_dir = project_root / "artifacts/research/atlas07_edge_lab/NAS-H001-V1"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = project_root / REPORT_REL
    event_paths_path = project_root / EVENT_PATHS_REL
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with event_paths_path.open("w", encoding="utf-8") as handle:
        for rec in rows:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
    return NASPathAnalysisResult(report=report, report_path=report_path, event_paths_path=event_paths_path)


def _secondary_summary(sub: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {
        "barriers": {},
        "signed_close": {},
        "mfe_mae": {},
        "context": {},
    }
    for mult in (0.25, 1.0):
        key = str(mult).replace(".", "_")
        s = sub[f"barrier_{key}or_score"].astype(float)
        out["barriers"][str(mult)] = {
            "continuation_first_fraction": float((s == 1).mean()),
            "failure_first_fraction": float((s == -1).mean()),
            "unresolved_fraction": float((s == 0).mean()),
            "effect": float(s.mean()),
        }
    for horizon in (1, 3, 5, 15, 30, 60):
        out["signed_close"][str(horizon)] = {
            "mean_or_width": float(sub[f"signed_close_or_{horizon}m"].mean()),
            "mean_atr14": float(sub[f"signed_close_atr_{horizon}m"].mean()),
        }
        out["mfe_mae"][str(horizon)] = {
            "mean_mfe_or_width": float(sub[f"mfe_or_{horizon}m"].mean()),
            "mean_mae_or_width": float(sub[f"mae_or_{horizon}m"].mean()),
            "mean_mfe_atr14": float(sub[f"mfe_atr_{horizon}m"].mean()),
            "mean_mae_atr14": float(sub[f"mae_atr_{horizon}m"].mean()),
        }
    inside = pd.to_numeric(sub["first_close_back_inside_or_minute"], errors="coerce")
    out["context"] = {
        "return_inside_or_fraction_60m": float(inside.notna().mean()),
        "median_minutes_to_return_inside_or": float(inside.dropna().median()) if inside.notna().any() else None,
        "mean_break_delay_minutes": float(sub["break_delay_minutes"].mean()),
        "mean_break_overshoot_or_width": float(sub["break_overshoot_or_width"].mean()),
        "mean_or_width_atr14": float(sub["or_width_atr14"].mean()),
    }
    return out
