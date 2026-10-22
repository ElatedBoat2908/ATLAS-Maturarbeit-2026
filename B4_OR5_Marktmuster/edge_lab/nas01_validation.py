from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .nas01_path_plan import CENSUS_EVENTS_REL
from .nas01_variant_freeze import (
    ANALYSIS_VERSION as SELECTED_ANALYSIS_VERSION,
    CONFIG_REL as SELECTED_CONFIG_REL,
    MANIFEST_REL as SELECTED_MANIFEST_REL,
    HYPOTHESIS_KEY,
    load_selected_variant_contract,
    verify_frozen_selected_variant,
)
from .progress import TerminalProgress

PHASE = "0.7G.8.1"
MARKET_ID = "NAS100"
VALIDATION_STAGE = "VALIDATION_2023_2024"
RUNNER_SOURCE_REL = Path("atlas/edge_lab/nas01_validation.py")
RUNNER_MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_validation_runner_manifest.json"
)
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_validation_path_analysis.json"
)
EVENT_PATHS_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_validation_event_paths.jsonl"
)
_NS_PER_MINUTE = 60_000_000_000


@dataclass(frozen=True)
class NASValidationResult:
    report: dict[str, Any]
    report_path: Path
    event_paths_path: Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc(ts: str | pd.Timestamp) -> pd.Timestamp:
    out = pd.Timestamp(ts)
    out = out.tz_localize("UTC") if out.tzinfo is None else out.tz_convert("UTC")
    try:
        return out.as_unit("ns")
    except AttributeError:  # pragma: no cover
        return pd.Timestamp(out.to_datetime64().astype("datetime64[ns]"), tz="UTC")


def _seed_for(stage: str) -> int:
    raw = hashlib.sha256(
        f"{SELECTED_ANALYSIS_VERSION}|{stage}|OR5|ATLAS".encode("utf-8")
    ).digest()
    return int.from_bytes(raw[:8], "little", signed=False) % (2**32 - 1)


def _read_m1_window(project_root: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Load only validation bars: [2023-01-01, 2025-01-01)."""
    path = project_root / "data/raw/atlas05_history/NAS100/M1.parquet"
    if not path.exists():
        raise FileNotFoundError(f"NAS100 M1 history missing: {path}")
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "NAS-H001 validation requires pyarrow for IO-level start/end filtering"
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
        raise RuntimeError("validation IO boundary violation")
    return frame


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
        idx = pd.DatetimeIndex(
            idx.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]"), tz="UTC"
        )
    out["time"] = idx
    out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    for col in ("high", "low", "close"):
        out[col] = pd.to_numeric(out[col], errors="raise")
    return out, pd.DatetimeIndex(out["time"]).asi8


def _load_validation_events(
    project_root: Path, start: pd.Timestamp, end: pd.Timestamp
) -> list[dict[str, Any]]:
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


def _time_axis_as_ns(time_values: np.ndarray) -> np.ndarray:
    """Return epoch integers in nanoseconds across pandas datetime resolutions.

    pandas 2.x/3.x can expose ``DatetimeIndex.asi8`` in the index's native
    resolution (for example microseconds), while ``Timestamp.value`` is
    nanoseconds. Production M1 data is already normalized to ns by
    ``_prepare_m1``; this compatibility guard prevents a false mismatch in
    direct helper calls/tests without changing validation semantics.
    """
    values = np.asarray(time_values, dtype=np.int64)
    if values.size == 0:
        return values
    magnitude = max(abs(int(values[0])), abs(int(values[-1])))
    if magnitude >= 100_000_000_000_000_000:  # ns epoch (~1e18)
        return values
    if magnitude >= 100_000_000_000_000:      # us epoch (~1e15)
        return values * np.int64(1_000)
    if magnitude >= 100_000_000_000:          # ms epoch (~1e12)
        return values * np.int64(1_000_000)
    if magnitude >= 100_000_000:              # s epoch (~1e9)
        return values * np.int64(1_000_000_000)
    raise ValueError("unsupported timestamp integer resolution for NAS-H001 validation")


def _complete_future_window(
    time_ns: np.ndarray, start_ns: int, minutes: int
) -> tuple[bool, int]:
    axis_ns = _time_axis_as_ns(time_ns)
    pos = int(np.searchsorted(axis_ns, start_ns, side="left"))
    end = pos + int(minutes)
    if pos >= len(axis_ns) or end > len(axis_ns):
        return False, pos
    expected = start_ns + np.arange(minutes, dtype=np.int64) * _NS_PER_MINUTE
    return bool(np.array_equal(axis_ns[pos:end], expected)), pos


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
        continuation = closes >= or_high + multiple * or_width
        failure = closes <= or_high - multiple * or_width
    elif direction == "SHORT":
        continuation = closes <= or_low - multiple * or_width
        failure = closes >= or_low + multiple * or_width
    else:
        raise ValueError(f"unexpected NAS-H001 direction: {direction}")
    hit = np.flatnonzero(continuation | failure)
    if hit.size == 0:
        return 0, "UNRESOLVED", None
    i = int(hit[0])
    if bool(continuation[i]):
        return 1, "CONTINUATION", i + 1
    return -1, "FAILURE", i + 1


def _measure_validation_path(
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
        "primary_score": score,
        "primary_outcome": label,
        "primary_resolved_minute": minute,
    }

    # Diagnostics only. They may never rescue a failed primary validation gate.
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


def _week_labels(frame: pd.DataFrame) -> np.ndarray:
    ts = pd.to_datetime(frame["available_at"], utc=True)
    iso = ts.dt.isocalendar()
    return (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()


def _block_inference(frame: pd.DataFrame, *, simulations: int, seed: int) -> dict[str, float]:
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


def _ensure_runner_manifest(project_root: Path) -> Path:
    target = project_root / RUNNER_MANIFEST_REL
    selected_manifest = project_root / SELECTED_MANIFEST_REL
    selected_config = project_root / SELECTED_CONFIG_REL
    current = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "selected_analysis_version": SELECTED_ANALYSIS_VERSION,
        "validation_stage": VALIDATION_STAGE,
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "selected_variant_manifest_sha256": _sha256(selected_manifest),
        "selected_variant_config_sha256": _sha256(selected_config),
        "census_events_sha256": _sha256(project_root / CENSUS_EVENTS_REL),
        "bootstrap_seed_rule": "SHA256(selected_analysis_version|stage|OR5|ATLAS) -> uint32",
        "validation_market_data_start_inclusive": "2023-01-01T00:00:00Z",
        "validation_market_data_cutoff_exclusive": "2025-01-01T00:00:00Z",
        "confirmation_2025_accessed_before_runner_freeze": False,
        "2026_holdout_accessed_before_runner_freeze": False,
        "trade_outcomes_accessed_before_runner_freeze": False,
    }
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        for key, value in current.items():
            if frozen.get(key) != value:
                raise RuntimeError(
                    "NAS-H001 validation runner changed after freeze; create a new validation analysis version"
                )
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
    return target


def run_nas_h001_validation(
    project_root: Path, *, show_progress: bool = True
) -> NASValidationResult:
    selected_fp = verify_frozen_selected_variant(project_root)
    contract = load_selected_variant_contract(project_root)
    if contract["selection_source"]["selected_variant"] != "OR5":
        raise RuntimeError("validation runner is hard-locked to OR5")
    if contract["selection_source"]["selected_mechanism"] != "ROBUST_CONTINUATION_CANDIDATE":
        raise RuntimeError("validation runner is hard-locked to continuation")

    start = _utc(contract["chronology"]["validation"][0])
    end = _utc(contract["chronology"]["validation"][1])
    if start != _utc("2023-01-01T00:00:00Z") or end != _utc("2025-01-01T00:00:00Z"):
        raise RuntimeError("NAS-H001 validation window changed")

    runner_manifest = _ensure_runner_manifest(project_root)
    events = _load_validation_events(project_root, start, end)
    if not events:
        raise RuntimeError("no OR5 validation events found")

    # Hard IO boundary: only 2023-2024 bars are loaded; 2025 confirmation is not read.
    m1 = _read_m1_window(project_root, start, end)
    bars, time_ns = _prepare_m1(m1)
    high = bars["high"].to_numpy(dtype=float, copy=False)
    low = bars["low"].to_numpy(dtype=float, copy=False)
    close = bars["close"].to_numpy(dtype=float, copy=False)

    rows: list[dict[str, Any]] = []
    ineligible = 0
    progress = TerminalProgress(total=len(events), label="NAS-H001 OR5 validation paths") if show_progress else None
    for i, event in enumerate(events, start=1):
        row = _measure_validation_path(
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
        raise RuntimeError("no eligible OR5 validation paths")
    frame["year"] = pd.to_datetime(frame["available_at"], utc=True).dt.year.astype(int)

    bootstrap_cfg = contract["bootstrap"]
    simulations = int(bootstrap_cfg["simulations"])
    seed = _seed_for(VALIDATION_STAGE)
    inf = _block_inference(frame, simulations=simulations, seed=seed)
    n = int(len(frame))
    continuation = int((frame["primary_score"] == 1).sum())
    failure = int((frame["primary_score"] == -1).sum())
    unresolved = int((frame["primary_score"] == 0).sum())
    resolved_fraction = float((continuation + failure) / n) if n else 0.0
    year_effects = {
        str(int(year)): float(group["primary_score"].mean())
        for year, group in frame.groupby("year", sort=True)
    }
    positive_years = int(sum(1 for v in year_effects.values() if v > 0))

    gates = contract["validation_gates"]
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
            "name": "positive_calendar_years",
            "pass": positive_years >= int(gates["minimum_positive_calendar_years"]),
            "observed": positive_years,
            "required": int(gates["minimum_positive_calendar_years"]),
        },
        {
            "name": "two_sided_week_block_p",
            "pass": float(inf["p_two_sided"]) < float(gates["two_sided_block_p_value_max"]),
            "observed": float(inf["p_two_sided"]),
            "required": f"< {float(gates['two_sided_block_p_value_max'])}",
        },
    ]
    status = "PASS_TO_CONFIRMATION_FREEZE" if all(bool(x["pass"]) for x in checks) else "FAIL"

    report: dict[str, Any] = {
        "phase": PHASE,
        "budget_id": "NAS100-BUDGET-1",
        "hypothesis": HYPOTHESIS_KEY,
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "selected_variant_operational_fingerprint": selected_fp,
        "validation_window": [start.isoformat(), end.isoformat()],
        "validation_events_from_census": int(len(events)),
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
        "year_effects": year_effects,
        "positive_calendar_years": positive_years,
        "gate_checks": checks,
        "scientific_gate": status,
        "runner_manifest_sha256": _sha256(runner_manifest),
        "runner_source_sha256": _sha256(project_root / RUNNER_SOURCE_REL),
        "confirmation_2025_paths_accessed": False,
        "final_2026_holdout_accessed": False,
        "trade_entry_stop_target_r_pf_pnl_inspected": False,
        "OR15_OR30_validation_accessed": False,
        "fallback_to_nonselected_variant": False,
        "notes": [
            "Only the preregistered OR5 continuation mechanism was validated.",
            "OR15 and OR30 were not opened in validation and cannot rescue an OR5 failure.",
            "2025 confirmation and 2026+ final holdout were not read.",
            "This is still a market-path mechanism test, not an executable trading strategy test.",
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
    return NASValidationResult(report=report, report_path=report_path, event_paths_path=paths_path)
