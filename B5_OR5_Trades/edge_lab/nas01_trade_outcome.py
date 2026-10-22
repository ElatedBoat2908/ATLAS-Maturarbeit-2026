from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .nas01_execution_calibration import (
    MANIFEST_REL as EXECUTION_COST_MANIFEST_REL,
    REPORT_REL as EXECUTION_COST_REPORT_REL,
    SPREAD_AUDIT_REL as ENTRY_SPREAD_AUDIT_REL,
    verify_frozen_execution_cost_calibration,
)
from .nas01_trade_hypothesis_freeze import (
    MANIFEST_REL as TRADE_HYPOTHESIS_MANIFEST_REL,
    verify_frozen_trade_hypothesis,
)
from .progress import TerminalProgress

PHASE = "0.7G.13"
ANALYSIS_VERSION = "NAS-H001-V1-TRADE-RUNNER-V1"
HYPOTHESIS_KEY = "NAS-H001-V1"
CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-trade-runner.json")
SOURCE_REL = Path("atlas/edge_lab/nas01_trade_outcome.py")
SCRIPT_REL = Path("scripts/atlas07_nas_h001_trade_outcomes.py")
CENSUS_EVENTS_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_opening_range_break_events_pre2026.jsonl"
)
RUNNER_MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_trade_runner_manifest.json"
)
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_executable_trade_research_2019_2025.json"
)
TRADES_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_executable_trades_2019_2025.jsonl"
)
M1_REL = Path("data/raw/atlas05_history/NAS100/M1.parquet")
_NS_PER_MINUTE = 60_000_000_000


@dataclass(frozen=True)
class FrozenCosts:
    symbol_point: float
    commission_price_per_side: float


@dataclass(frozen=True)
class TradeCandidate:
    event_id: str
    session_date: str
    available_at: pd.Timestamp
    direction: str
    or_high: float
    or_low: float
    or_width: float


@dataclass(frozen=True)
class ExecutionResult:
    row: dict[str, Any] | None
    ineligible_reason: str | None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    try:
        return ts.as_unit("ns")
    except AttributeError:  # pragma: no cover
        return pd.Timestamp(ts.to_datetime64().astype("datetime64[ns]"), tz="UTC")


def _seed() -> int:
    token = f"{ANALYSIS_VERSION}|MEAN_COST_ADJUSTED_R|ATLAS"
    return int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)


def load_trade_runner_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 trade-runner contract missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_trade_runner_contract(contract: dict[str, Any]) -> None:
    errors: list[str] = []
    if contract.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("unexpected analysis_version")
    if contract.get("hypothesis") != HYPOTHESIS_KEY:
        errors.append("unexpected hypothesis")

    source = contract.get("candidate_source") or {}
    required_source = {
        "artifact": CENSUS_EVENTS_REL.as_posix(),
        "variant": "OR5",
        "window": ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
        "maximum_candidates_per_xnys_session": 1,
        "post_break_path_fields_as_inputs": "FORBIDDEN",
    }
    for key, value in required_source.items():
        if source.get(key) != value:
            errors.append(f"candidate source changed: {key}")

    io = contract.get("market_data_io") or {}
    required_io = {
        "market_id": "NAS100",
        "timeframe": "M1",
        "start_inclusive": "2019-01-01T00:00:00Z",
        "end_exclusive": "2026-01-01T00:00:00Z",
        "require_pyarrow_filter_pushdown": True,
        "required_columns": ["time", "open", "high", "low", "close", "spread"],
        "require_exact_entry_timestamp": True,
        "require_60_consecutive_m1_bars_from_entry": True,
        "read_2026_plus": False,
    }
    for key, value in required_io.items():
        if io.get(key) != value:
            errors.append(f"market data IO changed: {key}")

    execution = contract.get("execution") or {}
    required_execution = {
        "entry_bar": "M1_BAR_TIMESTAMP_EQUAL_TO_EVENT_AVAILABLE_AT",
        "long_entry_fill": "BID_OPEN + ENTRY_SPREAD_PRICE + BASELINE_ENTRY_SLIPPAGE",
        "short_entry_fill": "BID_OPEN - BASELINE_ENTRY_SLIPPAGE",
        "long_target": "OR_HIGH + 0.5 * OR_WIDTH",
        "long_stop": "OR_HIGH - 0.5 * OR_WIDTH",
        "short_target": "OR_LOW - 0.5 * OR_WIDTH",
        "short_stop": "OR_LOW + 0.5 * OR_WIDTH",
        "primary_geometry_gate": "TARGET_STRICTLY_FAVORABLE_TO_BASELINE_ENTRY_AND_STOP_STRICTLY_ADVERSE_TO_BASELINE_ENTRY",
        "geometry_failure": "NO_TRADE_INEXECUTABLE_GEOMETRY",
        "barrier_trigger_basis": "CANONICAL_M1_BID_HIGH_LOW",
        "same_bar_stop_and_target": "STOP_FIRST_CONSERVATIVE",
        "maximum_holding_minutes": 60,
        "time_exit": "CLOSE_OF_60TH_CONSECUTIVE_M1_BAR_FROM_ENTRY",
        "long_barrier_exit_fill": "FROZEN_BID_BARRIER_PRICE - BASELINE_EXIT_SLIPPAGE",
        "long_time_exit_fill": "BID_CLOSE - BASELINE_EXIT_SLIPPAGE",
        "short_barrier_exit_fill": "FROZEN_BID_BARRIER_PRICE + EXIT_SPREAD_PRICE + BASELINE_EXIT_SLIPPAGE",
        "short_time_exit_fill": "BID_CLOSE + EXIT_SPREAD_PRICE + BASELINE_EXIT_SLIPPAGE",
        "commission": "SUBTRACT_FROZEN_PRICE_EQUIVALENT_PER_SIDE_AT_ENTRY_AND_EXIT",
        "initial_risk": "ABS(BASELINE_EXECUTABLE_ENTRY_FILL - FROZEN_STOP_REFERENCE)",
        "normalized_return": "NET_PRICE_PNL_AFTER_COMMISSION / INITIAL_RISK",
        "position_sizing": "NONE_NORMALIZED_R_ONLY",
    }
    for key, value in required_execution.items():
        if execution.get(key) != value:
            errors.append(f"execution rule changed: {key}")

    stress = contract.get("stress_costs") or {}
    required_stress = {
        "same_candidate_set_as_primary": True,
        "same_market_path_and_exit_kind_as_primary": True,
        "entry_slippage": "max(1 * symbol_point, 0.50 * entry_spread_price)",
        "exit_slippage": "max(1 * symbol_point, 0.50 * exit_spread_price)",
        "stress_geometry_does_not_change_primary_eligibility": True,
        "stress_cannot_rescue_primary": True,
    }
    for key, value in required_stress.items():
        if stress.get(key) != value:
            errors.append(f"stress rule changed: {key}")

    stats = contract.get("statistics") or {}
    required_stats = {
        "primary_metric": "MEAN_COST_ADJUSTED_R",
        "profit_factor_basis": "COST_ADJUSTED_R",
        "bootstrap_simulations": 5000,
        "bootstrap_block": "ISO_CALENDAR_WEEK",
        "bootstrap_confidence_interval": 0.95,
        "bootstrap_seed_rule": "SHA256(analysis_version|MEAN_COST_ADJUSTED_R|ATLAS) -> uint32",
        "calendar_years": [2019, 2020, 2021, 2022, 2023, 2024, 2025],
    }
    for key, value in required_stats.items():
        if stats.get(key) != value:
            errors.append(f"statistics changed: {key}")

    gates = contract.get("hard_gates") or {}
    required_gates = {
        "minimum_executed_trades": 1000,
        "minimum_mean_cost_adjusted_R": 0.05,
        "bootstrap_lower95_must_be_positive": True,
        "minimum_profit_factor_R": 1.10,
        "minimum_positive_calendar_years": 5,
        "minimum_2019_2022_mean_R": 0.0,
        "minimum_2023_2025_mean_R": 0.0,
        "minimum_stress_mean_R": 0.0,
    }
    for key, value in required_gates.items():
        if gates.get(key) != value:
            errors.append(f"hard gate changed: {key}")

    decision = contract.get("decision") or {}
    if decision.get("if_any_gate_fails") != "REJECT_EXECUTABLE_MAPPING_V1_WITHOUT_OPENING_2026":
        errors.append("failure decision changed")
    if decision.get("if_all_gates_pass") != "PASS_TO_FINAL_HOLDOUT_CONTRACT_FREEZE_WITH_2026_STILL_LOCKED":
        errors.append("pass decision changed")

    forbidden = contract.get("forbidden_before_runner_freeze") or {}
    for key in (
        "trade_entry_fill_results",
        "trade_exit_results",
        "trade_R_PF_PnL",
        "parameter_search",
        "OR15_OR30_fallback",
        "2026_plus_market_data_access",
    ):
        if forbidden.get(key) is not True:
            errors.append(f"pre-freeze prohibition changed: {key}")

    if errors:
        raise RuntimeError("NAS-H001 trade-runner contract invalid: " + "; ".join(errors))


def _required_frozen_inputs(project_root: Path) -> dict[str, str]:
    verify_frozen_trade_hypothesis(project_root)
    verify_frozen_execution_cost_calibration(project_root)
    required = {
        "trade_hypothesis_manifest_sha256": _sha256(project_root / TRADE_HYPOTHESIS_MANIFEST_REL),
        "execution_cost_manifest_sha256": _sha256(project_root / EXECUTION_COST_MANIFEST_REL),
        "execution_cost_report_sha256": _sha256(project_root / EXECUTION_COST_REPORT_REL),
        "entry_spread_audit_sha256": _sha256(project_root / ENTRY_SPREAD_AUDIT_REL),
        "census_events_sha256": _sha256(project_root / CENSUS_EVENTS_REL),
        "runner_contract_sha256": _sha256(project_root / CONFIG_REL),
        "runner_source_sha256": _sha256(project_root / SOURCE_REL),
        "runner_script_sha256": _sha256(project_root / SCRIPT_REL),
    }
    return required


def freeze_trade_runner(project_root: Path) -> tuple[Path, dict[str, Any]]:
    contract = load_trade_runner_contract(project_root)
    validate_trade_runner_contract(contract)
    hashes = _required_frozen_inputs(project_root)
    manifest = {
        "phase": PHASE,
        "analysis_version": ANALYSIS_VERSION,
        "hypothesis": HYPOTHESIS_KEY,
        **hashes,
        "research_window": ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "bootstrap_seed": _seed(),
        "trade_outcomes_accessed_before_runner_freeze": False,
        "final_2026_holdout_accessed_before_runner_freeze": False,
        "parameter_search_before_runner_freeze": False,
        "OR15_OR30_fallback_before_runner_freeze": False,
        "next_step": "RUN_FROZEN_2019_2025_EXECUTABLE_TRADE_RESEARCH_WITH_2026_STILL_LOCKED",
    }
    target = project_root / RUNNER_MANIFEST_REL
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        if frozen != manifest:
            raise RuntimeError("NAS-H001 trade-runner manifest exists but current frozen inputs differ; create a new analysis version")
        return target, frozen
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return target, manifest


def verify_frozen_trade_runner(project_root: Path) -> str:
    target = project_root / RUNNER_MANIFEST_REL
    if not target.exists():
        raise RuntimeError("NAS-H001 executable trade runner is not frozen")
    contract = load_trade_runner_contract(project_root)
    validate_trade_runner_contract(contract)
    hashes = _required_frozen_inputs(project_root)
    frozen = json.loads(target.read_text(encoding="utf-8"))
    for key, value in hashes.items():
        if frozen.get(key) != value:
            raise RuntimeError(f"NAS-H001 frozen trade-runner input changed after freeze: {key}")
    token = "\n".join(f"{k}:{hashes[k]}" for k in sorted(hashes))
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_frozen_costs(project_root: Path) -> FrozenCosts:
    report = json.loads((project_root / EXECUTION_COST_REPORT_REL).read_text(encoding="utf-8"))
    if report.get("decision") != "PASS_TO_2019_2025_TRADE_RUNNER_FREEZE":
        raise RuntimeError("execution-cost calibration did not pass")
    point = float((report.get("symbol") or {}).get("point", 0.0))
    commission = float((report.get("commission") or {}).get("median_price_per_side", -1.0))
    if not np.isfinite(point) or point <= 0:
        raise RuntimeError("invalid frozen symbol point")
    if not np.isfinite(commission) or commission < 0:
        raise RuntimeError("invalid frozen commission")
    return FrozenCosts(point, commission)


def _load_entry_spread_map(project_root: Path) -> dict[str, float]:
    path = project_root / ENTRY_SPREAD_AUDIT_REL
    out: dict[str, float] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            event_id = str(rec["event_id"])
            if not bool(rec.get("spread_valid")):
                continue
            spread = float(rec["spread_price"])
            if np.isfinite(spread) and spread >= 0:
                out[event_id] = spread
    return out


def load_or5_candidates(project_root: Path) -> list[TradeCandidate]:
    start = _utc("2019-01-01T00:00:00Z")
    end = _utc("2026-01-01T00:00:00Z")
    rows: list[TradeCandidate] = []
    seen_sessions: set[str] = set()
    with (project_root / CENSUS_EVENTS_REL).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rec = json.loads(line)
            ctx = rec.get("context") or {}
            if ctx.get("variant") != "OR5":
                continue
            available = _utc(rec["available_at"])
            if not (start <= available < end):
                continue
            session_date = str(ctx["session_date"])
            if session_date in seen_sessions:
                raise RuntimeError(f"more than one OR5 candidate in XNYS session {session_date}")
            seen_sessions.add(session_date)
            direction = str(rec["direction"]).upper()
            if direction not in {"LONG", "SHORT"}:
                raise RuntimeError(f"invalid OR5 direction: {direction}")
            high = float(ctx["opening_range_high"])
            low = float(ctx["opening_range_low"])
            width = float(ctx["opening_range_width"])
            if not np.isfinite(high) or not np.isfinite(low) or not np.isfinite(width) or high <= low or width <= 0:
                raise RuntimeError(f"invalid OR geometry in {rec['event_id']}")
            rows.append(
                TradeCandidate(
                    event_id=str(rec["event_id"]),
                    session_date=session_date,
                    available_at=available,
                    direction=direction,
                    or_high=high,
                    or_low=low,
                    or_width=width,
                )
            )
    rows.sort(key=lambda x: x.available_at.value)
    return rows


def _read_research_m1(project_root: Path) -> pd.DataFrame:
    path = project_root / M1_REL
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("pyarrow is required for IO-level 2019-2025 holdout filtering") from exc
    start = _utc("2019-01-01T00:00:00Z")
    end = _utc("2026-01-01T00:00:00Z")
    frame = pd.read_parquet(
        path,
        engine="pyarrow",
        columns=["time", "open", "high", "low", "close", "spread"],
        filters=[
            ("time", ">=", start.to_pydatetime()),
            ("time", "<", end.to_pydatetime()),
        ],
    )
    if frame.empty:
        raise RuntimeError("NAS100 M1 2019-2025 research window is empty")
    frame = frame.copy()
    frame["time"] = pd.to_datetime(frame["time"], utc=True, errors="raise")
    frame = frame.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    if not bool(((frame["time"] >= start) & (frame["time"] < end)).all()):
        raise RuntimeError("trade runner IO boundary violation")
    for col in ("open", "high", "low", "close", "spread"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if frame[["open", "high", "low", "close", "spread"]].isna().any().any():
        raise RuntimeError("NAS100 trade-research M1 contains missing/non-numeric values")
    if bool((frame["spread"] < 0).any()):
        raise RuntimeError("NAS100 trade-research M1 contains negative spread")
    return frame


def _prepare_arrays(frame: pd.DataFrame, *, point: float) -> dict[str, np.ndarray]:
    idx = pd.DatetimeIndex(frame["time"])
    try:
        idx = idx.as_unit("ns")
    except AttributeError:  # pragma: no cover
        idx = pd.DatetimeIndex(idx.astype("datetime64[ns, UTC]"))
    return {
        "time_ns": idx.asi8.astype(np.int64, copy=False),
        "open": frame["open"].to_numpy(dtype=float, copy=False),
        "high": frame["high"].to_numpy(dtype=float, copy=False),
        "low": frame["low"].to_numpy(dtype=float, copy=False),
        "close": frame["close"].to_numpy(dtype=float, copy=False),
        "spread_price": frame["spread"].to_numpy(dtype=float, copy=False) * float(point),
    }


def _contiguous_60(time_ns: np.ndarray, start_ns: int) -> tuple[bool, int]:
    pos = int(np.searchsorted(time_ns, start_ns, side="left"))
    end = pos + 60
    if pos >= len(time_ns) or end > len(time_ns):
        return False, pos
    expected = start_ns + np.arange(60, dtype=np.int64) * _NS_PER_MINUTE
    return bool(np.array_equal(time_ns[pos:end], expected)), pos


def _baseline_entry_fill(direction: str, bid_open: float, spread: float, slip: float) -> float:
    return float(bid_open + spread + slip) if direction == "LONG" else float(bid_open - slip)


def _stress_entry_fill(direction: str, bid_open: float, spread: float, slip: float) -> float:
    return _baseline_entry_fill(direction, bid_open, spread, slip)


def _barriers(candidate: TradeCandidate) -> tuple[float, float]:
    if candidate.direction == "LONG":
        return (
            candidate.or_high + 0.5 * candidate.or_width,
            candidate.or_high - 0.5 * candidate.or_width,
        )
    return (
        candidate.or_low - 0.5 * candidate.or_width,
        candidate.or_low + 0.5 * candidate.or_width,
    )


def _geometry_ok(direction: str, entry: float, target: float, stop: float) -> bool:
    return bool(stop < entry < target) if direction == "LONG" else bool(target < entry < stop)


def _exit_fill(
    *,
    direction: str,
    exit_kind: str,
    target: float,
    stop: float,
    bid_close: float,
    spread: float,
    slippage: float,
) -> float:
    if direction == "LONG":
        reference = stop if exit_kind == "STOP" else target if exit_kind == "TARGET" else bid_close
        return float(reference - slippage)
    reference = stop if exit_kind == "STOP" else target if exit_kind == "TARGET" else bid_close
    return float(reference + spread + slippage)


def _normalized_r(
    *, direction: str, entry: float, exit_fill: float, risk: float, commission_per_side: float
) -> float:
    gross = exit_fill - entry if direction == "LONG" else entry - exit_fill
    net = gross - 2.0 * commission_per_side
    return float(net / risk)


def evaluate_candidate(
    candidate: TradeCandidate,
    arrays: dict[str, np.ndarray],
    *,
    entry_spread_price: float,
    costs: FrozenCosts,
) -> ExecutionResult:
    if not np.isfinite(entry_spread_price) or entry_spread_price < 0:
        return ExecutionResult(None, "MISSING_OR_INVALID_ENTRY_SPREAD")
    start_ns = int(candidate.available_at.value)
    complete, pos = _contiguous_60(arrays["time_ns"], start_ns)
    if not complete:
        return ExecutionResult(None, "INCOMPLETE_60M_M1_PATH")

    bid_open = float(arrays["open"][pos])
    target, stop = _barriers(candidate)
    base_entry_slip = max(costs.symbol_point, 0.25 * entry_spread_price)
    stress_entry_slip = max(costs.symbol_point, 0.50 * entry_spread_price)
    entry = _baseline_entry_fill(candidate.direction, bid_open, entry_spread_price, base_entry_slip)
    if not _geometry_ok(candidate.direction, entry, target, stop):
        return ExecutionResult(None, "NO_TRADE_INEXECUTABLE_GEOMETRY")
    risk = abs(entry - stop)
    if not np.isfinite(risk) or risk <= 0:
        return ExecutionResult(None, "NON_POSITIVE_INITIAL_RISK")

    hi = arrays["high"][pos : pos + 60]
    lo = arrays["low"][pos : pos + 60]
    if candidate.direction == "LONG":
        stop_hits = lo <= stop
        target_hits = hi >= target
    else:
        stop_hits = hi >= stop
        target_hits = lo <= target
    sidx = np.flatnonzero(stop_hits)
    tidx = np.flatnonzero(target_hits)
    first_stop = int(sidx[0]) if sidx.size else None
    first_target = int(tidx[0]) if tidx.size else None
    same_bar = first_stop is not None and first_target is not None and first_stop == first_target
    if first_stop is not None and (first_target is None or first_stop <= first_target):
        exit_kind = "STOP"
        local_exit = first_stop
    elif first_target is not None:
        exit_kind = "TARGET"
        local_exit = first_target
    else:
        exit_kind = "TIME"
        local_exit = 59

    idx = pos + local_exit
    exit_spread = float(arrays["spread_price"][idx])
    if not np.isfinite(exit_spread) or exit_spread < 0:
        return ExecutionResult(None, "MISSING_OR_INVALID_EXIT_SPREAD")
    base_exit_slip = max(costs.symbol_point, 0.25 * exit_spread)
    stress_exit_slip = max(costs.symbol_point, 0.50 * exit_spread)
    exit_fill = _exit_fill(
        direction=candidate.direction,
        exit_kind=exit_kind,
        target=target,
        stop=stop,
        bid_close=float(arrays["close"][idx]),
        spread=exit_spread,
        slippage=base_exit_slip,
    )
    primary_r = _normalized_r(
        direction=candidate.direction,
        entry=entry,
        exit_fill=exit_fill,
        risk=risk,
        commission_per_side=costs.commission_price_per_side,
    )

    stress_entry = _stress_entry_fill(
        candidate.direction, bid_open, entry_spread_price, stress_entry_slip
    )
    stress_risk = abs(stress_entry - stop)
    stress_exit_fill = _exit_fill(
        direction=candidate.direction,
        exit_kind=exit_kind,
        target=target,
        stop=stop,
        bid_close=float(arrays["close"][idx]),
        spread=exit_spread,
        slippage=stress_exit_slip,
    )
    stress_r = _normalized_r(
        direction=candidate.direction,
        entry=stress_entry,
        exit_fill=stress_exit_fill,
        risk=stress_risk,
        commission_per_side=costs.commission_price_per_side,
    )

    row = {
        "event_id": candidate.event_id,
        "session_date": candidate.session_date,
        "available_at": candidate.available_at.isoformat(),
        "direction": candidate.direction,
        "entry_bid_open": bid_open,
        "entry_spread_price": float(entry_spread_price),
        "baseline_entry_slippage": float(base_entry_slip),
        "stress_entry_slippage": float(stress_entry_slip),
        "entry_fill": float(entry),
        "target": float(target),
        "stop": float(stop),
        "initial_risk": float(risk),
        "exit_kind": exit_kind,
        "same_bar_stop_target": bool(same_bar),
        "holding_minutes": int(local_exit + 1),
        "exit_time": pd.Timestamp(arrays["time_ns"][idx], unit="ns", tz="UTC").isoformat(),
        "exit_spread_price": float(exit_spread),
        "baseline_exit_slippage": float(base_exit_slip),
        "stress_exit_slippage": float(stress_exit_slip),
        "exit_fill": float(exit_fill),
        "R": float(primary_r),
        "stress_R": float(stress_r),
        "year": int(candidate.available_at.year),
    }
    return ExecutionResult(row, None)


def _week_labels(frame: pd.DataFrame) -> np.ndarray:
    ts = pd.to_datetime(frame["available_at"], utc=True)
    iso = ts.dt.isocalendar()
    return (iso["year"].astype(str) + "-W" + iso["week"].astype(str).str.zfill(2)).to_numpy()


def week_block_bootstrap_mean_r(frame: pd.DataFrame, *, simulations: int = 5000, seed: int | None = None) -> dict[str, float]:
    if frame.empty:
        return {"mean": float("nan"), "lower95": float("nan"), "upper95": float("nan")}
    values = frame["R"].to_numpy(dtype=float)
    labels = _week_labels(frame)
    unique = np.unique(labels)
    groups = [values[labels == key] for key in unique]
    sums = np.asarray([g.sum() for g in groups], dtype=float)
    counts = np.asarray([len(g) for g in groups], dtype=np.int64)
    rng = np.random.default_rng(_seed() if seed is None else seed)
    boot = np.empty(simulations, dtype=float)
    for i in range(simulations):
        picks = rng.integers(0, len(groups), size=len(groups))
        den = int(counts[picks].sum())
        boot[i] = float(sums[picks].sum() / den) if den else np.nan
    boot = boot[np.isfinite(boot)]
    lower, upper = np.quantile(boot, [0.025, 0.975])
    return {"mean": float(np.mean(values)), "lower95": float(lower), "upper95": float(upper)}


def _profit_factor_r(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    gains = float(arr[arr > 0].sum())
    losses = float(-arr[arr < 0].sum())
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def _gate(name: str, passed: bool, observed: Any, required: Any) -> dict[str, Any]:
    return {"name": name, "pass": bool(passed), "observed": observed, "required": required}


def run_trade_research(project_root: Path, *, show_progress: bool = True) -> tuple[Path, Path, dict[str, Any]]:
    runner_fp = verify_frozen_trade_runner(project_root)
    contract = load_trade_runner_contract(project_root)
    costs = _load_frozen_costs(project_root)
    spread_map = _load_entry_spread_map(project_root)
    candidates = load_or5_candidates(project_root)
    if not candidates:
        raise RuntimeError("no frozen OR5 candidates found for 2019-2025")

    m1 = _read_research_m1(project_root)
    arrays = _prepare_arrays(m1, point=costs.symbol_point)

    rows: list[dict[str, Any]] = []
    ineligible: dict[str, int] = {}
    progress = TerminalProgress(total=len(candidates), label="NAS-H001 executable trades") if show_progress else None
    for i, candidate in enumerate(candidates, start=1):
        result = evaluate_candidate(
            candidate,
            arrays,
            entry_spread_price=spread_map.get(candidate.event_id, float("nan")),
            costs=costs,
        )
        if result.row is None:
            reason = result.ineligible_reason or "UNKNOWN"
            ineligible[reason] = ineligible.get(reason, 0) + 1
        else:
            rows.append(result.row)
        if progress and (i == 1 or i == len(candidates) or i % 25 == 0):
            progress.update(i)
    if progress:
        progress.finish()

    frame = pd.DataFrame(rows)
    if frame.empty:
        raise RuntimeError("no executable NAS-H001 trades after frozen eligibility rules")
    inference = week_block_bootstrap_mean_r(
        frame,
        simulations=int(contract["statistics"]["bootstrap_simulations"]),
        seed=_seed(),
    )
    mean_r = float(frame["R"].mean())
    stress_mean_r = float(frame["stress_R"].mean())
    pf = _profit_factor_r(frame["R"].to_numpy(float))
    year_means = {str(int(y)): float(g["R"].mean()) for y, g in frame.groupby("year", sort=True)}
    positive_years = int(sum(v > 0 for v in year_means.values()))
    early = frame[(frame["year"] >= 2019) & (frame["year"] <= 2022)]
    late = frame[(frame["year"] >= 2023) & (frame["year"] <= 2025)]
    early_mean = float(early["R"].mean()) if not early.empty else float("nan")
    late_mean = float(late["R"].mean()) if not late.empty else float("nan")
    gates = contract["hard_gates"]
    checks = [
        _gate("minimum_executed_trades", len(frame) >= int(gates["minimum_executed_trades"]), len(frame), gates["minimum_executed_trades"]),
        _gate("minimum_mean_cost_adjusted_R", mean_r >= float(gates["minimum_mean_cost_adjusted_R"]), mean_r, gates["minimum_mean_cost_adjusted_R"]),
        _gate("bootstrap_lower95_positive", float(inference["lower95"]) > 0.0, inference["lower95"], 0.0),
        _gate("minimum_profit_factor_R", pf >= float(gates["minimum_profit_factor_R"]), pf, gates["minimum_profit_factor_R"]),
        _gate("minimum_positive_calendar_years", positive_years >= int(gates["minimum_positive_calendar_years"]), positive_years, gates["minimum_positive_calendar_years"]),
        _gate("minimum_2019_2022_mean_R", early_mean >= float(gates["minimum_2019_2022_mean_R"]), early_mean, gates["minimum_2019_2022_mean_R"]),
        _gate("minimum_2023_2025_mean_R", late_mean >= float(gates["minimum_2023_2025_mean_R"]), late_mean, gates["minimum_2023_2025_mean_R"]),
        _gate("minimum_stress_mean_R", stress_mean_r >= float(gates["minimum_stress_mean_R"]), stress_mean_r, gates["minimum_stress_mean_R"]),
    ]
    passed = all(bool(x["pass"]) for x in checks)
    decision = contract["decision"]["if_all_gates_pass"] if passed else contract["decision"]["if_any_gate_fails"]

    exits = frame["exit_kind"].value_counts().to_dict()
    direction_stats = {
        d: {
            "n": int(len(g)),
            "mean_R": float(g["R"].mean()),
            "stress_mean_R": float(g["stress_R"].mean()),
        }
        for d, g in frame.groupby("direction", sort=True)
    }
    report = {
        "phase": PHASE,
        "analysis_version": ANALYSIS_VERSION,
        "hypothesis": HYPOTHESIS_KEY,
        "runner_operational_fingerprint": runner_fp,
        "window": ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
        "candidate_count": int(len(candidates)),
        "executed_trades": int(len(frame)),
        "ineligible_count": int(len(candidates) - len(frame)),
        "ineligible_by_reason": dict(sorted(ineligible.items())),
        "mean_cost_adjusted_R": mean_r,
        "median_R": float(frame["R"].median()),
        "total_R": float(frame["R"].sum()),
        "profit_factor_R": pf,
        "win_rate_R_gt_0": float((frame["R"] > 0).mean()),
        "stress_mean_R": stress_mean_r,
        "bootstrap_mean_R": inference,
        "year_mean_R": year_means,
        "positive_calendar_years": positive_years,
        "mean_R_2019_2022": early_mean,
        "mean_R_2023_2025": late_mean,
        "exit_kinds": {str(k): int(v) for k, v in exits.items()},
        "same_bar_stop_target_count": int(frame["same_bar_stop_target"].sum()),
        "direction_diagnostics": direction_stats,
        "gate_checks": checks,
        "scientific_gate": decision,
        "final_2026_holdout_accessed": False,
        "OR15_OR30_fallback_used": False,
        "parameter_search_used": False,
        "interpretation": (
            "Research viability test of one frozen executable mapping. 2019-2025 are not an independent trade-edge confirmation because they were used to discover/confirm the market mechanism. A pass only permits freezing a separate 2026+ final-holdout contract."
        ),
    }

    out_dir = project_root / "artifacts/research/atlas07_edge_lab/NAS-H001-V1"
    out_dir.mkdir(parents=True, exist_ok=True)
    trades_path = project_root / TRADES_REL
    report_path = project_root / REPORT_REL
    with trades_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report_path, trades_path, report
