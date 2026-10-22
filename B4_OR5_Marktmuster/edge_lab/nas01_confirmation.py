from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .nas01_confirmation_freeze import (
    ANALYSIS_VERSION as CONFIRMATION_ANALYSIS_VERSION,
    CONFIG_REL as CONFIRMATION_CONFIG_REL,
    MANIFEST_REL as CONFIRMATION_MANIFEST_REL,
    load_confirmation_contract,
    verify_frozen_confirmation_contract,
)
from .nas01_path_plan import CENSUS_EVENTS_REL
from .nas01_validation import (
    _barrier_score,
    _block_inference,
    _complete_future_window,
    _prepare_m1,
    _utc,
)
from .nas01_variant_freeze import HYPOTHESIS_KEY
from .progress import TerminalProgress

PHASE = "0.7G.10"
CONFIRMATION_STAGE = "CONFIRMATION_2025"
RUNNER_SOURCE_REL = Path("atlas/edge_lab/nas01_confirmation.py")
VALIDATION_HELPER_SOURCE_REL = Path("atlas/edge_lab/nas01_validation.py")
RUNNER_MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_confirmation_runner_manifest.json"
)
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_confirmation_path_analysis.json"
)
EVENT_PATHS_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_confirmation_event_paths.jsonl"
)


@dataclass(frozen=True)
class NASConfirmationResult:
    report: dict[str, Any]
    report_path: Path
    event_paths_path: Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _seed_for_confirmation(stage: str = CONFIRMATION_STAGE) -> int:
    raw = hashlib.sha256(
        f"{CONFIRMATION_ANALYSIS_VERSION}|{stage}|OR5|ATLAS".encode("utf-8")
    ).digest()
    return int.from_bytes(raw[:8], "little", signed=False) % (2**32 - 1)


def _read_m1_confirmation_window(
    project_root: Path, start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Load only confirmation bars: [2025-01-01, 2026-01-01).

    The 2026+ final holdout is protected at IO level: no row at or after the
    exclusive cutoff is loaded. Events too close to the boundary become
    ineligible rather than borrowing future bars from 2026.
    """
    path = project_root / "data/raw/atlas05_history/NAS100/M1.parquet"
    if not path.exists():
        raise FileNotFoundError(f"NAS100 M1 history missing: {path}")
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "NAS-H001 confirmation requires pyarrow for IO-level start/end filtering"
        ) from exc
    frame = pd.read_parquet(
        path,
        engine="pyarrow",
        filters=[
            ("time", ">=", start.to_pydatetime()),
            ("time", "<", end.to_pydatetime()),
        ],
    )
    if frame.empty:
        return frame
    frame = frame.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="raise")
    frame = frame.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    if not bool(((frame["time"] >= start) & (frame["time"] < end)).all()):
        raise RuntimeError("confirmation IO boundary violation")
    return frame


def _load_confirmation_events(
    project_root: Path, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict[str, Any]]:
    """Load only already-censused OR5 event metadata for the 2025 window."""
    path = project_root / CENSUS_EVENTS_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 census events missing: {path}")
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            ctx = rec.get("context", {})
            if str(ctx.get("variant")) != "OR5":
                continue
            ts = _utc(rec["available_at"])
            if start <= ts < end:
                events.append(rec)
    events.sort(key=lambda r: _utc(r["available_at"]))
    return events


def _measure_confirmation_path(
    event: dict[str, Any],
    *,
    time_ns: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    horizon_minutes: int = 60,
) -> dict[str, Any] | None:
    """Measure the frozen OR5 confirmation path, starting at event availability."""
    ctx = event["context"]
    start = _utc(event["available_at"])
    complete, pos = _complete_future_window(time_ns, int(start.value), horizon_minutes)
    if not complete:
        return None

    h = high[pos : pos + horizon_minutes]
    l = low[pos : pos + horizon_minutes]
    c = close[pos : pos + horizon_minutes]
    direction = str(event["direction"])
    or_high = float(ctx["opening_range_high"])
    or_low = float(ctx["opening_range_low"])
    or_width = float(ctx["opening_range_width"])
    reference = float(event["reference_price"])
    atr14 = float(ctx.get("m1_atr14_at_break", np.nan))
    if not np.isfinite(or_width) or or_width <= 0:
        return None

    score, label, minute = _barrier_score(
        c,
        direction=direction,
        or_high=or_high,
        or_low=or_low,
        or_width=or_width,
        multiple=0.5,
    )
    row: dict[str, Any] = {
        "event_id": event["event_id"],
        "variant": "OR5",
        "available_at": start.isoformat(),
        "session_date": str(ctx["session_date"]),
        "direction": direction,
        "reference_price": reference,
        "opening_range_high": or_high,
        "opening_range_low": or_low,
        "opening_range_width": or_width,
        "event_atr14": atr14,
        "break_close_overshoot_or": (
            (reference - or_high) / or_width
            if direction == "LONG"
            else (or_low - reference) / or_width
        ),
        "primary_score": score,
        "primary_outcome": label,
        "primary_resolved_minute": minute,
    }

    # Diagnostics only. They may never rescue a failed primary confirmation gate.
    for horizon in (1, 3, 5, 15, 30, 60):
        last = horizon - 1
        signed = float(c[last] - reference) if direction == "LONG" else float(reference - c[last])
        row[f"signed_close_or_{horizon}m"] = signed / or_width
        if np.isfinite(atr14) and atr14 > 0:
            row[f"signed_close_atr_{horizon}m"] = signed / atr14
        if direction == "LONG":
            mfe = float(np.max(h[:horizon]) - reference)
            mae = float(reference - np.min(l[:horizon]))
        else:
            mfe = float(reference - np.min(l[:horizon]))
            mae = float(np.max(h[:horizon]) - reference)
        row[f"mfe_or_{horizon}m"] = mfe / or_width
        row[f"mae_or_{horizon}m"] = mae / or_width
    return row


def _ensure_runner_manifest(project_root: Path, confirmation_fp: str) -> Path:
    """Freeze implementation BEFORE any 2025 event path is opened."""
    target = project_root / RUNNER_MANIFEST_REL
    current = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "confirmation_analysis_version": CONFIRMATION_ANALYSIS_VERSION,
        "confirmation_stage": CONFIRMATION_STAGE,
        "confirmation_contract_operational_fingerprint": confirmation_fp,
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "validation_helper_source_sha256": _sha256(project_root / VALIDATION_HELPER_SOURCE_REL),
        "confirmation_contract_manifest_sha256": _sha256(project_root / CONFIRMATION_MANIFEST_REL),
        "confirmation_config_sha256": _sha256(project_root / CONFIRMATION_CONFIG_REL),
        "census_events_sha256": _sha256(project_root / CENSUS_EVENTS_REL),
        "bootstrap_seed_rule": (
            "SHA256(confirmation_analysis_version|CONFIRMATION_2025|OR5|ATLAS) -> uint32"
        ),
        "confirmation_market_data_start_inclusive": "2025-01-01T00:00:00Z",
        "confirmation_market_data_cutoff_exclusive": "2026-01-01T00:00:00Z",
        "2025_paths_accessed_before_runner_freeze": False,
        "2026_holdout_accessed_before_runner_freeze": False,
        "trade_outcomes_accessed_before_runner_freeze": False,
        "fallback_to_OR15_OR30": False,
    }
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        if frozen != current:
            raise RuntimeError(
                "NAS-H001 confirmation runner changed after freeze; create a new confirmation analysis version"
            )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    return target


def run_nas_h001_confirmation(
    project_root: Path, *, show_progress: bool = True
) -> NASConfirmationResult:
    # Must verify/freeze everything before the first 2025 path is read.
    confirmation_fp = verify_frozen_confirmation_contract(project_root)
    contract = load_confirmation_contract(project_root)

    source = contract["source"]
    if source["selected_variant"] != "OR5":
        raise RuntimeError("confirmation runner is hard-locked to OR5")
    if source["selected_mechanism"] != "ROBUST_CONTINUATION_CANDIDATE":
        raise RuntimeError("confirmation runner is hard-locked to continuation")
    if bool(source.get("fallback_to_OR15_or_OR30")):
        raise RuntimeError("confirmation runner forbids OR15/OR30 fallback")

    start = _utc(contract["chronology"]["confirmation"][0])
    end = _utc(contract["chronology"]["confirmation"][1])
    if start != _utc("2025-01-01T00:00:00Z") or end != _utc("2026-01-01T00:00:00Z"):
        raise RuntimeError("NAS-H001 confirmation window changed")

    runner_manifest = _ensure_runner_manifest(project_root, confirmation_fp)

    # Reading starts only after runner implementation has been frozen.
    events = _load_confirmation_events(project_root, start, end)
    if not events:
        raise RuntimeError("no OR5 confirmation events found")

    # Hard IO boundary: 2026+ is never loaded. Boundary-crossing paths are ineligible.
    m1 = _read_m1_confirmation_window(project_root, start, end)
    bars, time_ns = _prepare_m1(m1)
    high = bars["high"].to_numpy(dtype=float, copy=False)
    low = bars["low"].to_numpy(dtype=float, copy=False)
    close = bars["close"].to_numpy(dtype=float, copy=False)

    rows: list[dict[str, Any]] = []
    ineligible = 0
    progress = (
        TerminalProgress(total=len(events), label="NAS-H001 OR5 confirmation paths")
        if show_progress
        else None
    )
    for i, event in enumerate(events, start=1):
        row = _measure_confirmation_path(
            event,
            time_ns=time_ns,
            high=high,
            low=low,
            close=close,
            horizon_minutes=60,
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
        raise RuntimeError("no eligible OR5 confirmation paths")
    years = set(pd.to_datetime(frame["available_at"], utc=True).dt.year.astype(int).tolist())
    if not years.issubset({2025}):
        raise RuntimeError(f"confirmation path-year boundary violation: {sorted(years)}")

    bootstrap_cfg = contract["bootstrap"]
    simulations = int(bootstrap_cfg["simulations"])
    seed = _seed_for_confirmation()
    inf = _block_inference(frame, simulations=simulations, seed=seed)

    n = int(len(frame))
    continuation = int((frame["primary_score"] == 1).sum())
    failure = int((frame["primary_score"] == -1).sum())
    unresolved = int((frame["primary_score"] == 0).sum())
    resolved_fraction = float((continuation + failure) / n) if n else 0.0

    gates = contract["confirmation_gates"]
    checks = [
        {
            "name": "minimum_eligible_events",
            "pass": n >= int(gates["minimum_eligible_events"]),
            "observed": n,
            "required": int(gates["minimum_eligible_events"]),
        },
        {
            "name": "minimum_resolved_fraction",
            "pass": resolved_fraction >= float(gates["minimum_resolved_fraction"]),
            "observed": resolved_fraction,
            "required": float(gates["minimum_resolved_fraction"]),
        },
        {
            "name": "minimum_continuation_effect",
            "pass": float(inf["effect"]) >= float(gates["minimum_continuation_effect"]),
            "observed": float(inf["effect"]),
            "required": float(gates["minimum_continuation_effect"]),
        },
        {
            "name": "bootstrap_lower95_positive",
            "pass": float(inf["lower95"]) > 0.0,
            "observed": float(inf["lower95"]),
            "required": 0.0,
        },
        {
            "name": "two_sided_week_block_p",
            "pass": float(inf["p_two_sided"]) < float(gates["two_sided_block_p_value_max"]),
            "observed": float(inf["p_two_sided"]),
            "required": f"< {float(gates['two_sided_block_p_value_max'])}",
        },
    ]
    passed = all(bool(x["pass"]) for x in checks)
    status = (
        "CONFIRMED_MARKET_MECHANISM_ONLY__NEXT_FREEZE_EXECUTABLE_TRADE_HYPOTHESIS"
        if passed
        else "REJECT_NAS_H001_V1__DO_NOT_OPEN_2026_FOR_THIS_HYPOTHESIS"
    )

    overshoot = frame["break_close_overshoot_or"].to_numpy(dtype=float)
    report: dict[str, Any] = {
        "phase": PHASE,
        "budget_id": "NAS100-BUDGET-1",
        "hypothesis": HYPOTHESIS_KEY,
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "confirmation_contract_operational_fingerprint": confirmation_fp,
        "confirmation_window": [start.isoformat(), end.isoformat()],
        "confirmation_events_from_census": int(len(events)),
        "eligible_complete_60m_paths": n,
        "ineligible_incomplete_60m_paths": int(ineligible),
        "continuation_first": continuation,
        "failure_first": failure,
        "unresolved": unresolved,
        "resolved_fraction": resolved_fraction,
        "primary_effect": float(inf["effect"]),
        "bootstrap_lower95": float(inf["lower95"]),
        "bootstrap_upper95": float(inf["upper95"]),
        "bootstrap_p_two_sided": float(inf["p_two_sided"]),
        "bootstrap_seed": int(seed),
        "gate_checks": checks,
        "scientific_gate": status,
        "diagnostic_break_close_overshoot_or_median": float(np.median(overshoot)),
        "diagnostic_break_close_overshoot_or_p90": float(np.quantile(overshoot, 0.90)),
        "diagnostic_fraction_break_close_already_beyond_primary_continuation_barrier": float(
            np.mean(overshoot >= 0.5)
        ),
        "runner_manifest_sha256": _sha256(runner_manifest),
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "final_2026_holdout_accessed": False,
        "trade_entry_stop_target_r_pf_pnl_inspected": False,
        "OR15_OR30_confirmation_accessed": False,
        "fallback_to_nonselected_variant": False,
        "notes": [
            "Only the preregistered OR5 continuation mechanism was confirmed in 2025.",
            "OR15 and OR30 were not opened and cannot rescue an OR5 failure.",
            "2026+ final holdout was not read; paths crossing the cutoff are ineligible.",
            "This remains a market-path mechanism test, not an executable or cost-adjusted trading strategy.",
            "Break-close overshoot is reported diagnostically because a barrier already behind the known break close is not automatically monetizable from a post-signal entry.",
        ],
    }

    out_dir = project_root / "artifacts/research/atlas07_edge_lab/NAS-H001-V1"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = project_root / REPORT_REL
    paths_path = project_root / EVENT_PATHS_REL
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    with paths_path.open("w", encoding="utf-8") as handle:
        for rec in rows:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
    return NASConfirmationResult(report=report, report_path=report_path, event_paths_path=paths_path)
