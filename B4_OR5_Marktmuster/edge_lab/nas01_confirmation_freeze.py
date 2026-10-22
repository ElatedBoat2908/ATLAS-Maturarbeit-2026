from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .nas01_variant_freeze import (
    ANALYSIS_VERSION as SELECTED_ANALYSIS_VERSION,
    CONFIG_REL as SELECTED_CONFIG_REL,
    HYPOTHESIS_KEY,
    MANIFEST_REL as SELECTED_MANIFEST_REL,
    load_selected_variant_contract,
    verify_frozen_selected_variant,
)
from .nas01_validation import (
    EVENT_PATHS_REL as VALIDATION_EVENT_PATHS_REL,
    REPORT_REL as VALIDATION_REPORT_REL,
    RUNNER_MANIFEST_REL as VALIDATION_RUNNER_MANIFEST_REL,
)

PHASE = "0.7G.9"
ANALYSIS_VERSION = "NAS-H001-V1-CONFIRMATION-OR5-CONTINUATION-V1"
CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-confirmation.json")
MANIFEST_REL = Path(
    "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_confirmation_contract_manifest.json"
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_confirmation_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 confirmation contract missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_validation_report(project_root: Path) -> dict[str, Any]:
    path = project_root / VALIDATION_REPORT_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 validation report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_confirmation_contract(
    contract: dict[str, Any],
    validation_report: dict[str, Any],
    selected_contract: dict[str, Any],
) -> dict[str, Any]:
    errors: list[str] = []

    if contract.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("unexpected confirmation analysis_version")
    if contract.get("hypothesis") != HYPOTHESIS_KEY:
        errors.append("unexpected hypothesis")

    source = contract.get("source", {})
    if source.get("selected_variant") != "OR5":
        errors.append("confirmation selected variant must be OR5")
    if source.get("selected_mechanism") != "ROBUST_CONTINUATION_CANDIDATE":
        errors.append("confirmation mechanism must remain robust continuation")
    if source.get("validation_scientific_gate_required") != "PASS_TO_CONFIRMATION_FREEZE":
        errors.append("confirmation must require passed validation")
    if source.get("fallback_to_OR15_or_OR30") is not False:
        errors.append("fallback to OR15/OR30 must remain forbidden")

    if validation_report.get("scientific_gate") != "PASS_TO_CONFIRMATION_FREEZE":
        errors.append("validation did not pass to confirmation freeze")
    if validation_report.get("selected_variant") != "OR5":
        errors.append("validation report is not OR5")
    if validation_report.get("selected_mechanism") != "ROBUST_CONTINUATION_CANDIDATE":
        errors.append("validation report mechanism changed")
    if float(validation_report.get("primary_effect", 0.0)) <= 0.0:
        errors.append("validation continuation effect is not positive")
    if float(validation_report.get("bootstrap_lower95", 0.0)) <= 0.0:
        errors.append("validation lower 95% bound is not positive")
    for check in validation_report.get("gate_checks", []):
        if not bool(check.get("pass")):
            errors.append(f"validation gate unexpectedly failed: {check.get('name')}")

    expected_validation_window = [
        "2023-01-01T00:00:00+00:00",
        "2025-01-01T00:00:00+00:00",
    ]
    if validation_report.get("validation_window") != expected_validation_window:
        errors.append("validation report window changed")

    for key in (
        "confirmation_2025_paths_accessed",
        "final_2026_holdout_accessed",
        "trade_entry_stop_target_r_pf_pnl_inspected",
        "OR15_OR30_validation_accessed",
        "fallback_to_nonselected_variant",
    ):
        if bool(validation_report.get(key)):
            errors.append(f"forbidden validation-report flag is true: {key}")

    if selected_contract.get("analysis_version") != SELECTED_ANALYSIS_VERSION:
        errors.append("selected-variant analysis version changed")
    selection = selected_contract.get("selection_source", {})
    if selection.get("selected_variant") != "OR5":
        errors.append("selected-variant contract is not OR5")
    if selection.get("selected_mechanism") != "ROBUST_CONTINUATION_CANDIDATE":
        errors.append("selected-variant mechanism changed")

    mechanism = contract.get("mechanism_locked", {})
    selected_mechanism = selected_contract.get("mechanism_locked_from_development", {})
    locked_pairs = {
        "opening_range_minutes": 5,
        "cash_open": "09:30 America/New_York",
        "break_rule": "FIRST_COMPLETE_M1_CLOSE_STRICTLY_OUTSIDE_FROZEN_OPENING_RANGE",
        "break_search_minutes_after_range_end": 60,
        "path_start": "NEXT_COMPLETE_M1_BAR_AFTER_BREAK_EVENT_AVAILABLE_AT",
        "path_price_basis": "COMPLETE_M1_CLOSE_ONLY",
        "path_horizon_minutes": 60,
        "normalizer": "OPENING_RANGE_WIDTH",
        "barrier_multiple": 0.5,
    }
    for key, value in locked_pairs.items():
        if mechanism.get(key) != value:
            errors.append(f"confirmation mechanism changed: {key}")
        if selected_mechanism.get(key) != value:
            errors.append(f"selected mechanism no longer matches frozen value: {key}")

    chrono = contract.get("chronology", {})
    if chrono.get("confirmation") != ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]:
        errors.append("confirmation window must be 2025 only")
    if chrono.get("final_holdout_start") != "2026-01-01T00:00:00Z":
        errors.append("2026+ final holdout boundary changed")

    selected_gates = selected_contract.get("confirmation_gates", {})
    gates = contract.get("confirmation_gates", {})
    required_gates = {
        "minimum_eligible_events": 200,
        "minimum_resolved_fraction": 0.6,
        "minimum_continuation_effect": 0.05,
        "bootstrap_lower95_must_be_positive": True,
        "two_sided_block_p_value_max": 0.05,
    }
    for key, value in required_gates.items():
        if gates.get(key) != value:
            errors.append(f"confirmation gate changed: {key}")
        if selected_gates.get(key) != value:
            errors.append(f"selected contract confirmation gate changed: {key}")

    if errors:
        raise RuntimeError("NAS-H001 confirmation contract invalid: " + "; ".join(errors))
    return validation_report


def operational_fingerprint(project_root: Path) -> str:
    required = [
        CONFIG_REL,
        SELECTED_CONFIG_REL,
        SELECTED_MANIFEST_REL,
        VALIDATION_REPORT_REL,
        VALIDATION_EVENT_PATHS_REL,
        VALIDATION_RUNNER_MANIFEST_REL,
    ]
    parts: list[str] = []
    for rel in required:
        path = project_root / rel
        if not path.exists():
            raise RuntimeError(f"required NAS-H001 confirmation freeze input missing: {path}")
        parts.append(f"{rel.as_posix()}:{_sha256(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def freeze_confirmation_contract(project_root: Path) -> tuple[Path, dict[str, Any]]:
    selected_fp = verify_frozen_selected_variant(project_root)
    selected_contract = load_selected_variant_contract(project_root)
    contract = load_confirmation_contract(project_root)
    validation_report = load_validation_report(project_root)
    validate_confirmation_contract(contract, validation_report, selected_contract)
    fp = operational_fingerprint(project_root)

    manifest_path = project_root / MANIFEST_REL
    manifest = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "operational_fingerprint": fp,
        "selected_variant_operational_fingerprint": selected_fp,
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "validation_observed_effect": float(validation_report["primary_effect"]),
        "validation_bootstrap_lower95": float(validation_report["bootstrap_lower95"]),
        "validation_bootstrap_upper95": float(validation_report["bootstrap_upper95"]),
        "validation_eligible_events": int(validation_report["eligible_complete_60m_paths"]),
        "validation_year_effects": validation_report["year_effects"],
        "confirmation_window": ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
        "final_holdout_start": "2026-01-01T00:00:00Z",
        "confirmation_paths_accessed_before_freeze": False,
        "2026_holdout_accessed_before_freeze": False,
        "trade_outcomes_accessed_before_freeze": False,
        "fallback_to_nonselected_variant": False,
        "config_sha256": _sha256(project_root / CONFIG_REL),
        "selected_variant_config_sha256": _sha256(project_root / SELECTED_CONFIG_REL),
        "selected_variant_manifest_sha256": _sha256(project_root / SELECTED_MANIFEST_REL),
        "validation_report_sha256": _sha256(project_root / VALIDATION_REPORT_REL),
        "validation_event_paths_sha256": _sha256(project_root / VALIDATION_EVENT_PATHS_REL),
        "validation_runner_manifest_sha256": _sha256(project_root / VALIDATION_RUNNER_MANIFEST_REL),
    }

    if manifest_path.exists():
        frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
        if frozen != manifest:
            raise RuntimeError(
                "NAS-H001 confirmation manifest already exists but does not match current frozen inputs"
            )
        return manifest_path, frozen

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path, manifest


def verify_frozen_confirmation_contract(project_root: Path) -> str:
    manifest_path = project_root / MANIFEST_REL
    if not manifest_path.exists():
        raise RuntimeError("NAS-H001 confirmation contract is not frozen")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    selected_contract = load_selected_variant_contract(project_root)
    contract = load_confirmation_contract(project_root)
    validation_report = load_validation_report(project_root)
    validate_confirmation_contract(contract, validation_report, selected_contract)
    fp = operational_fingerprint(project_root)
    if frozen.get("operational_fingerprint") != fp:
        raise RuntimeError("NAS-H001 confirmation frozen inputs changed after freeze")
    return str(fp)
