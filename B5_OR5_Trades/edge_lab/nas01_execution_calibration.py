from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .nas01_path_plan import verify_frozen_nas_h001_path_plan
from .nas01_trade_hypothesis_freeze import (
    MANIFEST_REL as TRADE_MANIFEST_REL,
    verify_frozen_trade_hypothesis,
)

PHASE = "0.7G.12"
ANALYSIS_VERSION = "NAS-H001-V1-EXECUTION-COST-CALIBRATION-V1"
HYPOTHESIS_KEY = "NAS-H001-V1"
CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-execution-costs.json")
SOURCE_REL = Path("atlas/edge_lab/nas01_execution_calibration.py")
CENSUS_EVENTS_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_opening_range_break_events_pre2026.jsonl"
)
REPORT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_execution_cost_calibration.json"
)
SPREAD_AUDIT_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_or5_entry_spread_calibration.jsonl"
)
MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_execution_cost_calibration_manifest.json"
)
M1_REL = Path("data/raw/atlas05_history/NAS100/M1.parquet")


@dataclass(frozen=True)
class CommissionCalibration:
    resolved: bool
    usable_deals: int
    median_price_per_side: float | None
    p90_price_per_side: float | None
    zero_commission_confirmed: bool
    reason: str
    source_type: str
    source_title: str | None = None
    source_url: str | None = None
    source_verified_date: str | None = None
    scope: str | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _utc_ns(series: pd.Series) -> pd.Series:
    ts = pd.to_datetime(series, utc=True, errors="raise")
    return ts.astype("datetime64[ns, UTC]")


def load_execution_cost_policy(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 execution-cost policy missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_execution_cost_policy(payload)
    return payload


def validate_execution_cost_policy(policy: dict[str, Any]) -> None:
    errors: list[str] = []
    if policy.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("unexpected analysis_version")
    if policy.get("hypothesis") != HYPOTHESIS_KEY:
        errors.append("unexpected hypothesis")
    if policy.get("broker_symbol") != "USTEC.c":
        errors.append("broker_symbol must remain USTEC.c")
    if policy.get("research_window") != ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]:
        errors.append("research window changed")
    if policy.get("entry_spread_source") != "CANONICAL_NAS100_M1_SPREAD_COLUMN_AT_FROZEN_AVAILABLE_AT_ENTRY_TIMESTAMP":
        errors.append("entry spread source changed")
    if policy.get("exit_spread_source_frozen_for_later_trade_test") != "CANONICAL_NAS100_M1_SPREAD_COLUMN_AT_EVENTUAL_EXIT_TIMESTAMP":
        errors.append("exit spread source changed")
    if policy.get("spread_price_conversion") != "spread_points * symbol_point":
        errors.append("spread price conversion changed")
    if policy.get("valid_spread_rule") != "finite spread_points >= 0":
        errors.append("valid spread rule changed")
    if float(policy.get("minimum_entry_spread_coverage", -1.0)) != 0.99:
        errors.append("entry spread coverage gate changed")

    slip = policy.get("slippage") or {}
    if slip.get("baseline_one_way_price_rule") != "max(1 * symbol_point, 0.25 * contemporaneous_spread_price)":
        errors.append("baseline slippage rule changed")
    if slip.get("stress_one_way_price_rule") != "max(1 * symbol_point, 0.50 * contemporaneous_spread_price)":
        errors.append("stress slippage rule changed")
    if slip.get("stress_cannot_rescue_primary") is not True:
        errors.append("stress result must not rescue primary")

    commission = policy.get("commission") or {}
    if commission.get("primary_source_order") != [
        "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
        "AUTHORITATIVE_CURRENT_GBE_INDEX_CFD_SCHEDULE",
    ]:
        errors.append("commission source order changed")
    mt5_cfg = commission.get("mt5_deal_history") or {}
    if int(mt5_cfg.get("minimum_usable_deals", -1)) != 2:
        errors.append("minimum usable deal count changed")
    if mt5_cfg.get("window") != ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]:
        errors.append("commission deal-history window changed")
    fallback = commission.get("official_broker_fallback") or {}
    if fallback.get("enabled") is not True:
        errors.append("official broker fallback must remain enabled")
    if fallback.get("symbol") != "USTEC.c":
        errors.append("official fallback symbol changed")
    if float(fallback.get("commission_price_per_side", -1.0)) != 0.0:
        errors.append("official fallback commission changed")
    if fallback.get("verified_date") != "2026-08-20":
        errors.append("official fallback verification date changed")

    forbidden = policy.get("forbidden_during_calibration") or {}
    for key in (
        "read_entry_bid_open",
        "read_post_entry_OHLC",
        "read_stop_target_result",
        "read_trade_R_PF_PnL",
        "read_2026_plus_market_data",
        "parameter_search",
        "OR15_OR30_fallback",
    ):
        if forbidden.get(key) is not True:
            errors.append(f"forbidden calibration action changed: {key}")

    if errors:
        raise RuntimeError("NAS-H001 execution-cost policy invalid: " + "; ".join(errors))


def load_or5_events(project_root: Path) -> pd.DataFrame:
    # This artifact is part of the already-frozen NAS-H001 chain. Verifying the
    # path-plan fingerprint protects the census event file from silent changes.
    verify_frozen_nas_h001_path_plan(project_root)
    path = project_root / CENSUS_EVENTS_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 census event artifact missing: {path}")
    events = pd.read_json(path, lines=True)
    if events.empty:
        raise RuntimeError("NAS-H001 census event artifact is empty")
    events["available_at"] = _utc_ns(events["available_at"])
    events["variant"] = events["context"].map(lambda x: str((x or {}).get("variant")))
    events = events[events["variant"] == "OR5"].copy()
    start = pd.Timestamp("2019-01-01T00:00:00Z")
    end = pd.Timestamp("2026-01-01T00:00:00Z")
    events = events[(events["available_at"] >= start) & (events["available_at"] < end)].copy()
    if events.empty:
        raise RuntimeError("no OR5 events in frozen 2019-2025 research window")
    if (events["available_at"] >= end).any():
        raise RuntimeError("2026+ event leaked into execution calibration")
    if events["available_at"].duplicated().any():
        raise RuntimeError("duplicate OR5 available_at timestamps in frozen census events")
    events["year"] = events["available_at"].dt.year.astype(int)
    return events.sort_values("available_at").reset_index(drop=True)


def merge_entry_spreads(events: pd.DataFrame, spread_bars: pd.DataFrame, *, point: float) -> pd.DataFrame:
    if point <= 0 or not np.isfinite(point):
        raise ValueError("symbol point must be finite and > 0")
    required = {"time", "spread"}
    missing = required.difference(spread_bars.columns)
    if missing:
        raise ValueError(f"spread bars missing columns: {sorted(missing)}")
    bars = spread_bars[["time", "spread"]].copy()
    bars["time"] = _utc_ns(bars["time"])
    bars = bars.sort_values("time").drop_duplicates("time", keep="last")

    left = events[["event_id", "available_at", "direction", "year"]].copy()
    out = left.merge(bars, left_on="available_at", right_on="time", how="left", validate="one_to_one")
    out.drop(columns=["time"], inplace=True)
    raw = pd.to_numeric(out["spread"], errors="coerce")
    valid = np.isfinite(raw.to_numpy(dtype=float)) & (raw.to_numpy(dtype=float) >= 0.0)
    out["spread_points"] = raw.astype(float)
    out["spread_valid"] = valid
    out["spread_price"] = np.where(valid, out["spread_points"].to_numpy(dtype=float) * float(point), np.nan)
    return out


def calibrate_commission_from_deals(
    deals: Iterable[Any],
    *,
    tick_size: float,
    tick_value: float,
    minimum_usable_deals: int,
) -> CommissionCalibration:
    raw_rows: list[tuple[float, float]] = []
    for deal in deals:
        volume = float(getattr(deal, "volume", 0.0) or 0.0)
        if volume <= 0 or not np.isfinite(volume):
            continue
        commission = abs(float(getattr(deal, "commission", 0.0) or 0.0))
        fee = abs(float(getattr(deal, "fee", 0.0) or 0.0))
        raw = commission + fee
        if np.isfinite(raw) and raw >= 0:
            raw_rows.append((volume, raw))

    if len(raw_rows) < minimum_usable_deals:
        return CommissionCalibration(
            False,
            len(raw_rows),
            None,
            None,
            False,
            f"only {len(raw_rows)} usable USTEC.c pre-2026 deals; need >= {minimum_usable_deals}",
            "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
        )

    raw_costs = np.asarray([raw for _, raw in raw_rows], dtype=float)
    if np.all(raw_costs == 0.0):
        return CommissionCalibration(
            True,
            len(raw_rows),
            0.0,
            0.0,
            True,
            "resolved as zero from pre-2026 MT5 USTEC.c deal history",
            "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
        )

    if tick_size <= 0 or tick_value <= 0 or not np.isfinite(tick_size) or not np.isfinite(tick_value):
        return CommissionCalibration(
            False,
            len(raw_rows),
            None,
            None,
            False,
            "non-zero MT5 commission observed but tick size/value is invalid for price-equivalent conversion",
            "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
        )

    values = np.asarray(
        [(raw / (volume * tick_value)) * tick_size for volume, raw in raw_rows],
        dtype=float,
    )
    values = values[np.isfinite(values) & (values >= 0.0)]
    if len(values) < minimum_usable_deals:
        return CommissionCalibration(
            False,
            len(values),
            None,
            None,
            False,
            "too few usable commission price-equivalent observations after conversion",
            "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
        )
    return CommissionCalibration(
        True,
        int(len(values)),
        float(np.median(values)),
        float(np.quantile(values, 0.90)),
        False,
        "resolved from pre-2026 MT5 USTEC.c deal history",
        "MT5_ACCOUNT_USTEC_C_DEAL_HISTORY_PRE2026",
    )


def resolve_commission(
    deals: Iterable[Any],
    *,
    tick_size: float,
    tick_value: float,
    policy: dict[str, Any],
    broker_symbol: str,
    account_company: str | None,
    account_server: str | None,
) -> CommissionCalibration:
    cpol = policy["commission"]
    empirical = calibrate_commission_from_deals(
        deals,
        tick_size=tick_size,
        tick_value=tick_value,
        minimum_usable_deals=int(cpol["mt5_deal_history"]["minimum_usable_deals"]),
    )
    if empirical.resolved:
        return empirical

    fallback = cpol["official_broker_fallback"]
    if not bool(fallback.get("enabled")):
        return empirical
    if str(broker_symbol).upper() != str(fallback.get("symbol", "")).upper():
        return CommissionCalibration(
            False,
            empirical.usable_deals,
            None,
            None,
            False,
            f"official fallback symbol mismatch: {broker_symbol}",
            "UNRESOLVED",
        )
    identity = " ".join(x for x in [account_company or "", account_server or ""] if x).upper()
    tokens = [str(x).upper() for x in fallback.get("broker_identity_tokens", []) if str(x).strip()]
    if not tokens or not any(token in identity for token in tokens):
        return CommissionCalibration(
            False,
            empirical.usable_deals,
            None,
            None,
            False,
            f"official fallback broker identity mismatch: company={account_company!r} server={account_server!r}",
            "UNRESOLVED",
        )
    value = float(fallback["commission_price_per_side"])
    if value < 0 or not np.isfinite(value):
        raise RuntimeError("invalid official broker fallback commission")
    return CommissionCalibration(
        True,
        empirical.usable_deals,
        value,
        value,
        bool(value == 0.0),
        "resolved from preregistered authoritative current GBE index-CFD schedule because usable pre-2026 USTEC.c deal evidence was insufficient",
        "AUTHORITATIVE_CURRENT_GBE_INDEX_CFD_SCHEDULE",
        str(fallback.get("source_title") or ""),
        str(fallback.get("source_url") or ""),
        str(fallback.get("verified_date") or ""),
        str(fallback.get("scope") or ""),
    )


def _spread_stats(values: pd.Series) -> dict[str, float | None]:
    arr = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    if arr.empty:
        return {"median": None, "p75": None, "p90": None, "p95": None, "max": None}
    return {
        "median": float(arr.median()),
        "p75": float(arr.quantile(0.75)),
        "p90": float(arr.quantile(0.90)),
        "p95": float(arr.quantile(0.95)),
        "max": float(arr.max()),
    }


def build_report(
    *,
    project_root: Path,
    policy: dict[str, Any],
    spreads: pd.DataFrame,
    broker_symbol: str,
    point: float,
    digits: int,
    tick_size: float,
    tick_value: float,
    contract_size: float,
    volume_min: float,
    volume_step: float,
    account_currency: str | None,
    account_company: str | None,
    account_server: str | None,
    commission: CommissionCalibration,
) -> dict[str, Any]:
    n = int(len(spreads))
    valid = spreads["spread_valid"].astype(bool)
    coverage = float(valid.mean()) if n else 0.0
    valid_rows = spreads.loc[valid].copy()
    by_year: dict[str, Any] = {}
    for year, group in spreads.groupby("year", sort=True):
        gv = group[group["spread_valid"].astype(bool)]
        by_year[str(int(year))] = {
            "events": int(len(group)),
            "valid_spreads": int(len(gv)),
            "coverage": float(len(gv) / len(group)) if len(group) else 0.0,
            "spread_points": _spread_stats(gv["spread_points"]),
            "spread_price": _spread_stats(gv["spread_price"]),
        }

    coverage_gate = float(policy["minimum_entry_spread_coverage"])
    ready = bool(coverage >= coverage_gate and commission.resolved)
    return {
        "phase": PHASE,
        "analysis_version": ANALYSIS_VERSION,
        "hypothesis": HYPOTHESIS_KEY,
        "broker_symbol": broker_symbol,
        "research_window": policy["research_window"],
        "or5_frozen_entry_events": n,
        "entry_spread_valid": int(valid.sum()),
        "entry_spread_invalid_or_missing": int((~valid).sum()),
        "entry_spread_coverage": coverage,
        "minimum_entry_spread_coverage": coverage_gate,
        "entry_spread_points": _spread_stats(valid_rows["spread_points"]),
        "entry_spread_price": _spread_stats(valid_rows["spread_price"]),
        "entry_spread_by_year": by_year,
        "symbol": {
            "point": float(point),
            "digits": int(digits),
            "trade_tick_size": float(tick_size),
            "trade_tick_value_account_currency": float(tick_value),
            "trade_contract_size": float(contract_size),
            "volume_min": float(volume_min),
            "volume_step": float(volume_step),
        },
        "account": {
            "currency": account_currency,
            "company": account_company,
            "server": account_server,
        },
        "commission": asdict(commission),
        "frozen_cost_semantics": {
            "entry_spread_source": policy["entry_spread_source"],
            "exit_spread_source": policy["exit_spread_source_frozen_for_later_trade_test"],
            "spread_price_conversion": policy["spread_price_conversion"],
            "baseline_slippage": policy["slippage"]["baseline_one_way_price_rule"],
            "stress_slippage": policy["slippage"]["stress_one_way_price_rule"],
            "commission_price_per_side": commission.median_price_per_side,
            "commission_source": commission.source_type,
        },
        "trade_hypothesis_manifest_sha256": _sha256(project_root / TRADE_MANIFEST_REL),
        "census_events_sha256": _sha256(project_root / CENSUS_EVENTS_REL),
        "policy_sha256": _sha256(project_root / CONFIG_REL),
        "calibration_source_sha256": _sha256(project_root / SOURCE_REL),
        "entry_bid_open_read": False,
        "post_entry_OHLC_read": False,
        "trade_stop_target_result_read": False,
        "trade_R_PF_PnL_read": False,
        "final_2026_holdout_accessed": False,
        "parameter_search_performed": False,
        "OR15_OR30_fallback_used": False,
        "ready_to_freeze_trade_runner": ready,
        "decision": "PASS_TO_2019_2025_TRADE_RUNNER_FREEZE" if ready else "STOP_EXECUTION_COST_CALIBRATION_UNRESOLVED",
    }


def run_execution_cost_calibration(project_root: Path) -> tuple[dict[str, Any], Path, Path]:
    verify_frozen_trade_hypothesis(project_root)
    policy = load_execution_cost_policy(project_root)
    events = load_or5_events(project_root)

    m1_path = project_root / M1_REL
    if not m1_path.exists():
        raise FileNotFoundError(f"canonical NAS100 M1 history not found: {m1_path}")
    # Calibration is deliberately spread-only. No bid open/high/low/close is
    # loaded, so executable entry fills and post-entry paths remain unopened.
    spread_bars = pd.read_parquet(m1_path, columns=["time", "spread"])
    spread_bars["time"] = _utc_ns(spread_bars["time"])
    start = pd.Timestamp(policy["research_window"][0])
    end = pd.Timestamp(policy["research_window"][1])
    spread_bars = spread_bars[(spread_bars["time"] >= start) & (spread_bars["time"] < end)].copy()
    if (spread_bars["time"] >= end).any():
        raise RuntimeError("2026+ spread data leaked into calibration")

    try:
        import MetaTrader5 as mt5  # type: ignore
    except ImportError as exc:
        raise RuntimeError("MetaTrader5 package is required for NAS execution calibration") from exc
    if not mt5.initialize():
        raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
    try:
        broker_symbol = str(policy["broker_symbol"])
        try:
            mt5.symbol_select(broker_symbol, True)
        except Exception:
            pass
        info = mt5.symbol_info(broker_symbol)
        if info is None:
            raise RuntimeError(f"MT5 symbol_info unavailable for {broker_symbol}")
        account = mt5.account_info()
        point = float(getattr(info, "point", 0.0) or 0.0)
        digits = int(getattr(info, "digits", 0) or 0)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or point)
        tick_values = [
            float(getattr(info, "trade_tick_value", 0.0) or 0.0),
            float(getattr(info, "trade_tick_value_profit", 0.0) or 0.0),
            float(getattr(info, "trade_tick_value_loss", 0.0) or 0.0),
        ]
        tick_value = max([abs(v) for v in tick_values] + [0.0])
        contract_size = float(getattr(info, "trade_contract_size", 0.0) or 0.0)
        volume_min = float(getattr(info, "volume_min", 0.0) or 0.0)
        volume_step = float(getattr(info, "volume_step", 0.0) or 0.0)
        account_currency = str(getattr(account, "currency", "")) if account is not None else None
        account_company = str(getattr(account, "company", "")) if account is not None else None
        account_server = str(getattr(account, "server", "")) if account is not None else None

        cwin = policy["commission"]["mt5_deal_history"]["window"]
        deals_all = mt5.history_deals_get(pd.Timestamp(cwin[0]).to_pydatetime(), pd.Timestamp(cwin[1]).to_pydatetime())
        if deals_all is None:
            deals_all = ()
        deals = [
            d for d in deals_all
            if str(getattr(d, "symbol", "")).upper() == broker_symbol.upper()
        ]
        commission = resolve_commission(
            deals,
            tick_size=tick_size,
            tick_value=tick_value,
            policy=policy,
            broker_symbol=broker_symbol,
            account_company=account_company,
            account_server=account_server,
        )
    finally:
        mt5.shutdown()

    if point <= 0 or not np.isfinite(point):
        raise RuntimeError(f"invalid MT5 symbol point for {policy['broker_symbol']}: {point}")
    spreads = merge_entry_spreads(events, spread_bars, point=point)
    report = build_report(
        project_root=project_root,
        policy=policy,
        spreads=spreads,
        broker_symbol=str(policy["broker_symbol"]),
        point=point,
        digits=digits,
        tick_size=tick_size,
        tick_value=tick_value,
        contract_size=contract_size,
        volume_min=volume_min,
        volume_step=volume_step,
        account_currency=account_currency,
        account_company=account_company,
        account_server=account_server,
        commission=commission,
    )

    out_dir = (project_root / REPORT_REL).parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = project_root / REPORT_REL
    spread_path = project_root / SPREAD_AUDIT_REL
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    spreads.to_json(spread_path, orient="records", lines=True, date_format="iso")
    return report, report_path, spread_path


def _validate_report_for_freeze(project_root: Path, report: dict[str, Any]) -> None:
    if report.get("analysis_version") != ANALYSIS_VERSION or report.get("hypothesis") != HYPOTHESIS_KEY:
        raise RuntimeError("unexpected NAS execution calibration report identity")
    if report.get("decision") != "PASS_TO_2019_2025_TRADE_RUNNER_FREEZE":
        raise RuntimeError("NAS execution calibration did not pass")
    if report.get("ready_to_freeze_trade_runner") is not True:
        raise RuntimeError("NAS execution calibration is not ready to freeze")
    if float(report.get("entry_spread_coverage", 0.0)) < float(report.get("minimum_entry_spread_coverage", 1.0)):
        raise RuntimeError("NAS entry spread coverage gate failed")
    if not bool((report.get("commission") or {}).get("resolved")):
        raise RuntimeError("NAS commission remains unresolved")
    for key in (
        "entry_bid_open_read",
        "post_entry_OHLC_read",
        "trade_stop_target_result_read",
        "trade_R_PF_PnL_read",
        "final_2026_holdout_accessed",
        "parameter_search_performed",
        "OR15_OR30_fallback_used",
    ):
        if bool(report.get(key)):
            raise RuntimeError(f"forbidden calibration flag is true: {key}")
    if report.get("policy_sha256") != _sha256(project_root / CONFIG_REL):
        raise RuntimeError("execution-cost policy changed after calibration")
    if report.get("calibration_source_sha256") != _sha256(project_root / SOURCE_REL):
        raise RuntimeError("execution calibration source changed after calibration")
    if report.get("trade_hypothesis_manifest_sha256") != _sha256(project_root / TRADE_MANIFEST_REL):
        raise RuntimeError("frozen executable trade hypothesis changed after calibration")
    if report.get("census_events_sha256") != _sha256(project_root / CENSUS_EVENTS_REL):
        raise RuntimeError("frozen NAS census event artifact changed after calibration")


def freeze_execution_cost_calibration(project_root: Path) -> tuple[Path, dict[str, Any]]:
    verify_frozen_trade_hypothesis(project_root)
    load_execution_cost_policy(project_root)
    report_path = project_root / REPORT_REL
    spread_path = project_root / SPREAD_AUDIT_REL
    if not report_path.exists() or not spread_path.exists():
        raise RuntimeError("run NAS execution-cost calibration before freezing it")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _validate_report_for_freeze(project_root, report)

    manifest = {
        "phase": PHASE,
        "analysis_version": ANALYSIS_VERSION,
        "hypothesis": HYPOTHESIS_KEY,
        "trade_hypothesis_manifest_sha256": _sha256(project_root / TRADE_MANIFEST_REL),
        "policy_sha256": _sha256(project_root / CONFIG_REL),
        "calibration_source_sha256": _sha256(project_root / SOURCE_REL),
        "calibration_report_sha256": _sha256(report_path),
        "entry_spread_audit_sha256": _sha256(spread_path),
        "broker_symbol": report["broker_symbol"],
        "symbol_point": report["symbol"]["point"],
        "commission_source": report["commission"]["source_type"],
        "commission_price_per_side": report["commission"]["median_price_per_side"],
        "entry_spread_coverage": report["entry_spread_coverage"],
        "trade_outcomes_accessed_before_freeze": False,
        "final_2026_holdout_accessed_before_freeze": False,
        "parameter_search_before_freeze": False,
        "next_step": "FREEZE_2019_2025_EXECUTABLE_TRADE_RUNNER_WITH_2026_STILL_LOCKED",
    }
    target = project_root / MANIFEST_REL
    if target.exists():
        frozen = json.loads(target.read_text(encoding="utf-8"))
        if frozen != manifest:
            raise RuntimeError("NAS execution-cost calibration manifest exists but current frozen inputs differ")
        return target, frozen
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return target, manifest


def verify_frozen_execution_cost_calibration(project_root: Path) -> str:
    target = project_root / MANIFEST_REL
    if not target.exists():
        raise RuntimeError("NAS-H001 execution-cost calibration is not frozen")
    frozen = json.loads(target.read_text(encoding="utf-8"))
    report_path = project_root / REPORT_REL
    spread_path = project_root / SPREAD_AUDIT_REL
    if not report_path.exists() or not spread_path.exists():
        raise RuntimeError("frozen NAS execution-cost artifacts are missing")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    _validate_report_for_freeze(project_root, report)
    checks = {
        "trade_hypothesis_manifest_sha256": _sha256(project_root / TRADE_MANIFEST_REL),
        "policy_sha256": _sha256(project_root / CONFIG_REL),
        "calibration_source_sha256": _sha256(project_root / SOURCE_REL),
        "calibration_report_sha256": _sha256(report_path),
        "entry_spread_audit_sha256": _sha256(spread_path),
    }
    for key, value in checks.items():
        if frozen.get(key) != value:
            raise RuntimeError(f"NAS execution-cost frozen artifact changed after freeze: {key}")
    token = "\n".join(f"{k}:{checks[k]}" for k in sorted(checks))
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
