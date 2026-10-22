from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HYPOTHESIS_KEY = "NAS-H001-V1"
ANALYSIS_VERSION = "NAS-H001-V1-SELECTED-OR5-CONTINUATION-V1"
CONFIG_REL = Path("config/edge_lab/analysis/NAS-H001-V1-selected-variant.json")
DEV_REPORT_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_analysis.json")
DEV_EVENT_PATHS_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_event_paths.jsonl")
PATH_PLAN_MANIFEST_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_plan_manifest.json")
DEV_RUNNER_MANIFEST_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_runner_manifest.json")
MANIFEST_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_selected_variant_manifest.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_selected_variant_contract(project_root: Path) -> dict[str, Any]:
    path = project_root / CONFIG_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 selected-variant contract missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_development_report(project_root: Path) -> dict[str, Any]:
    path = project_root / DEV_REPORT_REL
    if not path.exists():
        raise RuntimeError(f"NAS-H001 development path report missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_selected_variant_contract(contract: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if contract.get("analysis_version") != ANALYSIS_VERSION:
        errors.append("unexpected selected-variant analysis_version")
    if contract.get("hypothesis") != HYPOTHESIS_KEY:
        errors.append("unexpected hypothesis")

    source = contract.get("selection_source", {})
    selected = source.get("selected_variant")
    mechanism = source.get("selected_mechanism")
    if selected != "OR5":
        errors.append("selected variant must be OR5")
    if mechanism != "ROBUST_CONTINUATION_CANDIDATE":
        errors.append("selected mechanism must be ROBUST_CONTINUATION_CANDIDATE")
    if source.get("fallback_to_OR15_or_OR30_if_OR5_fails_validation") is not False:
        errors.append("fallback to OR15/OR30 must be forbidden")

    if report.get("scientific_gate") != "PASS_TO_VARIANT_FREEZE_BEFORE_VALIDATION":
        errors.append("development scientific gate did not pass to variant freeze")
    if report.get("selected_variant") != selected:
        errors.append("development-selected variant does not match contract")
    if report.get("selected_mechanism") != mechanism:
        errors.append("development-selected mechanism does not match contract")
    if selected not in report.get("variants_passing_all_development_gates", []):
        errors.append("selected variant did not pass every development gate")

    selected_report = report.get("variants", {}).get(str(selected), {})
    if selected_report.get("gate_status") != "PASS":
        errors.append("selected development variant gate_status is not PASS")
    if float(selected_report.get("primary_effect", 0.0)) <= 0.0:
        errors.append("selected development effect is not positive continuation")
    for check in selected_report.get("gate_checks", []):
        if not bool(check.get("pass")):
            errors.append(f"development gate unexpectedly failed: {check.get('name')}")

    for key in (
        "validation_2023_2024_paths_accessed",
        "confirmation_2025_paths_accessed",
        "final_2026_holdout_accessed",
        "trade_entry_stop_target_r_pf_pnl_inspected",
    ):
        if bool(report.get(key)):
            errors.append(f"forbidden development-report access flag is true: {key}")

    chrono = contract.get("chronology", {})
    if chrono.get("validation") != ["2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"]:
        errors.append("validation window must be 2023-2024 only")
    if chrono.get("confirmation") != ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"]:
        errors.append("confirmation window must be 2025 only")
    if chrono.get("final_holdout_start") != "2026-01-01T00:00:00Z":
        errors.append("2026+ final holdout boundary changed")

    if errors:
        raise RuntimeError("NAS-H001 selected-variant contract invalid: " + "; ".join(errors))
    return selected_report


def operational_fingerprint(project_root: Path) -> str:
    required = [
        CONFIG_REL,
        DEV_REPORT_REL,
        DEV_EVENT_PATHS_REL,
        PATH_PLAN_MANIFEST_REL,
        DEV_RUNNER_MANIFEST_REL,
    ]
    parts = []
    for rel in required:
        path = project_root / rel
        if not path.exists():
            raise RuntimeError(f"required NAS-H001 freeze input missing: {path}")
        parts.append(f"{rel.as_posix()}:{_sha256(path)}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def freeze_selected_variant(project_root: Path) -> tuple[Path, dict[str, Any]]:
    contract = load_selected_variant_contract(project_root)
    report = load_development_report(project_root)
    selected_report = validate_selected_variant_contract(contract, report)
    fp = operational_fingerprint(project_root)

    manifest_path = project_root / MANIFEST_REL
    manifest = {
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "operational_fingerprint": fp,
        "selected_variant": "OR5",
        "selected_mechanism": "ROBUST_CONTINUATION_CANDIDATE",
        "development_observed_effect": float(selected_report["primary_effect"]),
        "development_bootstrap_lower95": float(selected_report["bootstrap_lower95"]),
        "development_bootstrap_upper95": float(selected_report["bootstrap_upper95"]),
        "development_eligible_events": int(selected_report["eligible_events"]),
        "development_year_effects": selected_report["year_effects"],
        "validation_window": ["2023-01-01T00:00:00Z", "2025-01-01T00:00:00Z"],
        "confirmation_window": ["2025-01-01T00:00:00Z", "2026-01-01T00:00:00Z"],
        "final_holdout_start": "2026-01-01T00:00:00Z",
        "validation_paths_accessed_before_freeze": False,
        "confirmation_paths_accessed_before_freeze": False,
        "2026_holdout_accessed_before_freeze": False,
        "trade_outcomes_accessed_before_freeze": False,
        "fallback_to_nonselected_variant": False,
        "config_sha256": _sha256(project_root / CONFIG_REL),
        "development_report_sha256": _sha256(project_root / DEV_REPORT_REL),
        "development_event_paths_sha256": _sha256(project_root / DEV_EVENT_PATHS_REL),
        "path_plan_manifest_sha256": _sha256(project_root / PATH_PLAN_MANIFEST_REL),
        "development_runner_manifest_sha256": _sha256(project_root / DEV_RUNNER_MANIFEST_REL),
    }
    if manifest_path.exists():
        frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
        if frozen != manifest:
            raise RuntimeError("NAS-H001 selected-variant manifest already exists but does not match current frozen inputs")
        return manifest_path, frozen

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest_path, manifest


def verify_frozen_selected_variant(project_root: Path) -> str:
    manifest_path = project_root / MANIFEST_REL
    if not manifest_path.exists():
        raise RuntimeError("NAS-H001 selected variant is not frozen")
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    contract = load_selected_variant_contract(project_root)
    report = load_development_report(project_root)
    validate_selected_variant_contract(contract, report)
    fp = operational_fingerprint(project_root)
    if frozen.get("operational_fingerprint") != fp:
        raise RuntimeError("NAS-H001 selected-variant frozen inputs changed after freeze")
    return str(fp)
