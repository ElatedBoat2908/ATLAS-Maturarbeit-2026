from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .nas01_confirmation import (
    EVENT_PATHS_REL as CONFIRMATION_EVENT_PATHS_REL,
    REPORT_REL as CONFIRMATION_REPORT_REL,
    RUNNER_MANIFEST_REL as CONFIRMATION_RUNNER_MANIFEST_REL,
)
from .nas01_confirmation_freeze import (
    MANIFEST_REL as CONFIRMATION_CONTRACT_MANIFEST_REL,
    verify_frozen_confirmation_contract,
)
from .nas01_variant_freeze import HYPOTHESIS_KEY

PHASE = "0.7G.11"
ANALYSIS_VERSION = "NAS-H001-V1-EXECUTABLE-TRADE-HYPOTHESIS-V1"
CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-executable-trade.json")
MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_executable_trade_hypothesis_manifest.json"
)
CONFIRMED_STATUS = (
    "CONFIRMED_MARKET_MECHANISM_ONLY__NEXT_FREEZE_EXECUTABLE_TRADE_HYPOTHESIS"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_trade_hypothesis_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 executable trade contract missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_confirmation_report(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIRMATION_REPORT_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 confirmation report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_trade_hypothesis_contract(
    contract: dict[str, Any], confirmation_report: dict[str, Any]
) -> dict[str, Any]:
    errors: list[str] = []

    if contract.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("unexpected executable-trade analysis_version")
    if contract.get("hypothesis") != HYPOTHESIS_KEY:
        errors.append("unexpected hypothesis")

    source = contract.get("source_mechanism") or {}
    required_source = {
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "confirmation_status_required": CONFIRMED_STATUS,
        "opening_range_minutes": 5,
        "cash_open": "09:30 America/New_York",
        "break_rule": "FIRST_COMPLETE_M1_CLOSE_STRICTLY_OUTSIDE_FROZEN_OPENING_RANGE",
        "break_search_minutes_after_range_end": 60,
        "path_barrier_multiple": 0.5,
        "fallback_to_OR15_or_OR30": False,
    }
    for key, value in required_source.items():
        if source.get(key) != value:
            errors.append(f"source mechanism changed: {key}")

    if confirmation_report.get("scientific_gate") != CONFIRMED_STATUS:
        errors.append("2025 market mechanism was not confirmed")
    if confirmation_report.get("selected_variant") != "OR5":
        errors.append("confirmation report is not OR5")
    if confirmation_report.get("selected_mechanism") != "ROBUST_CONTINUATION_CANDIDATE":
        errors.append("confirmation mechanism changed")
    if float(confirmation_report.get("primary_effect", 0.0)) <= 0.0:
        errors.append("confirmation effect is not positive continuation")
    if float(confirmation_report.get("bootstrap_lower95", 0.0)) <= 0.0:
        errors.append("confirmation lower 95% bound is not positive")
    for check in confirmation_report.get("gate_checks", []):
        if not bool(check.get("pass")):
            errors.append(f"confirmation gate unexpectedly failed: {check.get('name')}")
    for key in (
        "final_2026_holdout_accessed",
        "trade_entry_stop_target_r_pf_pnl_inspected",
        "OR15_OR30_confirmation_accessed",
        "fallback_to_nonselected_variant",
    ):
        if bool(confirmation_report.get(key)):
            errors.append(f"forbidden confirmation-report flag is true: {key}")

    mapping = contract.get("trade_mapping") or {}
    required_mapping = {
        "candidate_frequency": "MAX_ONE_OR5_FIRST_BREAK_CANDIDATE_PER_XNYS_SESSION",
        "signal_available_at": "OPEN_OF_THE_FIRST_M1_BAR_AFTER_THE_BREAK_BAR_CLOSE",
        "entry_timing": "AT_SIGNAL_AVAILABLE_AT_M1_OPEN",
        "entry_reference_price": "CANONICAL_NAS100_M1_BID_OPEN_AT_AVAILABLE_AT",
        "long_entry_fill": "BID_OPEN + HISTORICAL_SPREAD_PRICE + BASELINE_SLIPPAGE",
        "short_entry_fill": "BID_OPEN - BASELINE_SLIPPAGE",
        "long_target_reference": "OR_HIGH + 0.5 * OR_WIDTH",
        "long_stop_reference": "OR_HIGH - 0.5 * OR_WIDTH",
        "short_target_reference": "OR_LOW - 0.5 * OR_WIDTH",
        "short_stop_reference": "OR_LOW + 0.5 * OR_WIDTH",
        "geometry_feasibility": "TRADE_ONLY_IF_TARGET_IS_STRICTLY_FAVORABLE_TO_EXECUTABLE_ENTRY_AND_STOP_IS_STRICTLY_ADVERSE; OTHERWISE NO_TRADE_INEXECUTABLE_GEOMETRY",
        "overshoot_filter": "NONE_BEYOND_MECHANICAL_GEOMETRY_FEASIBILITY",
        "spread_filter": "NONE",
        "regime_filter": "NONE",
        "direction_filter": "NONE",
        "barrier_trigger_price_basis": "CANONICAL_M1_BID_OHLC_SOFTWARE_TRIGGER_FOR_BOTH_DIRECTIONS",
        "same_bar_stop_and_target": "STOP_FIRST_CONSERVATIVE",
        "holding_horizon_minutes": 60,
        "time_exit": "END_OF_60TH_M1_BAR_AFTER_ENTRY_IF_NEITHER_BARRIER_TRIGGERED",
        "max_concurrent_positions": 1,
        "reentry_same_session": False,
        "pyramiding": False,
        "trailing_stop": False,
        "break_even_move": False,
        "partial_exit": False,
        "position_sizing": "NOT_PART_OF_EDGE_TEST; REPORT_NORMALIZED_R_ONLY",
    }
    for key, value in required_mapping.items():
        if mapping.get(key) != value:
            errors.append(f"trade mapping changed: {key}")

    costs = contract.get("execution_cost_policy") or {}
    if costs.get("calibration_required_before_trade_outcomes") is not True:
        errors.append("NAS execution calibration must be required before outcomes")
    if costs.get("broker_symbol") != "USTEC.c":
        errors.append("broker symbol must remain USTEC.c")
    if costs.get("historical_spread_source") != "M1_SPREAD_COLUMN_AT_ENTRY_AND_EXIT_TIMESTAMPS":
        errors.append("historical spread source changed")
    if costs.get("baseline_slippage_price_per_side") != "max(1 * symbol_point, 0.25 * contemporaneous_spread_price)":
        errors.append("baseline slippage rule changed")
    if costs.get("stress_slippage_price_per_side") != "max(1 * symbol_point, 0.50 * contemporaneous_spread_price)":
        errors.append("stress slippage rule changed")

    test = contract.get("research_trade_test") or {}
    if test.get("window") != ["2019-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]:
        errors.append("research trade window must be 2019-2025 only")
    gates = test.get("hard_gates") or {}
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
            errors.append(f"research trade gate changed: {key}")

    chrono = contract.get("chronology") or {}
    if chrono.get("final_holdout_start") != "2026-01-01T00:00:00Z":
        errors.append("2026+ final holdout boundary changed")
    if chrono.get("final_holdout_access_before_separate_freeze") != "FORBIDDEN":
        errors.append("2026 must remain locked before separate final-holdout freeze")

    forbidden = contract.get("forbidden_before_this_freeze") or {}
    for key in (
        "trade_entry_fill_results",
        "trade_stop_target_results",
        "trade_R_PF_PnL",
        "2026_plus_market_data_access",
        "parameter_search",
        "OR15_OR30_fallback",
    ):
        if forbidden.get(key) is not True:
            errors.append(f"pre-freeze prohibition changed: {key}")

    if errors:
        raise RuntimeError("NAS-H001 executable trade contract invalid: " + "; ".join(errors))
    return confirmation_report


def operational_fingerprint(project_root: Path) -> str:
    required = [
        CONFIG_REL,
        CONFIRMATION_REPORT_REL,
        CONFIRMATION_EVENT_PATHS_REL,
        CONFIRMATION_RUNNER_MANIFEST_REL,
        CONFIRMATION_CONTRACT_MANIFEST_REL,
    ]
    parts: list[str] = []
    for rel in required:
        path = project_root / rel
        if not path.exists():
            raise RuntimeError(f"required NAS-H001 executable-trade freeze input missing: {path}")
        parts.append(f"{rel.as_posix()}:{_sha256(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def freeze_trade_hypothesis(project_root: Path) -> tuple[Path, dict[str, Any]]:
    confirmation_fp = verify_frozen_confirmation_contract(project_root)
    contract = load_trade_hypothesis_contract(project_root)
    report = load_confirmation_report(project_root)
    validate_trade_hypothesis_contract(contract, report)
    fp = operational_fingerprint(project_root)

    manifest_path = project_root / MANIFEST_REL
    manifest = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "operational_fingerprint": fp,
        "confirmation_contract_operational_fingerprint": confirmation_fp,
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "confirmation_observed_effect": float(report["primary_effect"]),
        "confirmation_bootstrap_lower95": float(report["bootstrap_lower95"]),
        "confirmation_bootstrap_upper95": float(report["bootstrap_upper95"]),
        "confirmation_eligible_events": int(report["eligible_complete_60m_paths"]),
        "trade_outcomes_accessed_before_freeze": False,
        "2026_holdout_accessed_before_freeze": False,
        "parameter_search_before_freeze": False,
        "fallback_to_nonselected_variant": False,
        "execution_calibration_required_next": True,
        "config_sha256": _sha256(project_root / CONFIG_REL),
        "confirmation_report_sha256": _sha256(project_root / CONFIRMATION_REPORT_REL),
        "confirmation_event_paths_sha256": _sha256(project_root / CONFIRMATION_EVENT_PATHS_REL),
        "confirmation_runner_manifest_sha256": _sha256(project_root / CONFIRMATION_RUNNER_MANIFEST_REL),
        "confirmation_contract_manifest_sha256": _sha256(project_root / CONFIRMATION_CONTRACT_MANIFEST_REL),
    }

    if manifest_path.exists():
        frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
        if frozen != manifest:
            raise RuntimeError(
                "NAS-H001 executable trade manifest already exists but does not match current frozen inputs"
            )
        return manifest_path, frozen

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path, manifest


def verify_frozen_trade_hypothesis(project_root: Path) -> str:
    manifest_path = project_root / MANIFEST_REL
    if not manifest_path.exists():
        raise RuntimeError(
            "NAS-H001 executable trade hypothesis is not frozen. Run: python scripts/atlas07_freeze_nas_h001_trade_hypothesis.py"
        )
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = load_trade_hypothesis_contract(project_root)
    report = load_confirmation_report(project_root)
    validate_trade_hypothesis_contract(contract, report)
    fp = operational_fingerprint(project_root)
    if frozen.get("operational_fingerprint") != fp:
        raise RuntimeError("NAS-H001 executable trade frozen inputs changed after freeze")
    return str(fp)
