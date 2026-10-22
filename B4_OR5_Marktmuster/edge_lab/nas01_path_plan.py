from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

PHASE = "0.7G.5"
HYPOTHESIS_KEY = "NAS-H001-V1"
ANALYSIS_VERSION = "NAS-H001-V1-DEVELOPMENT-PATH-V1"
PLAN_REL = Path("config/edge_lab/analysis/NAS-H001-V1-development-path.json")
DETECTOR_REL = Path("config/edge_lab/detectors/NAS-H001-V1.json")
DETECTOR_SOURCE_REL = Path("atlas/edge_lab/nas01_opening_range.py")
CALENDAR_REL = Path("config/edge_lab/calendars/XNYS_2019_2025_sessions.json")
CENSUS_MANIFEST_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_event_census_manifest.json")
CENSUS_REPORT_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_event_census.json")
CENSUS_EVENTS_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_opening_range_break_events_pre2026.jsonl")
PATH_MANIFEST_REL = Path("artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_development_path_plan_manifest.json")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_payload(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_nas_h001_path_plan(project_root: Path) -> dict[str, Any]:
    path = project_root / PLAN_REL
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_nas_h001_path_plan(payload)
    return payload


def validate_nas_h001_path_plan(p: dict[str, Any]) -> None:
    if p.get("analysis_version") != ANALYSIS_VERSION:
        raise ValueError("unexpected NAS-H001 path analysis version")
    if p.get("hypothesis") != HYPOTHESIS_KEY:
        raise ValueError("unexpected NAS-H001 hypothesis key")
    if p.get("variants") != ["OR5", "OR15", "OR30"]:
        raise ValueError("NAS-H001 path plan freezes OR5/OR15/OR30 separately")
    if p.get("pool_variants") is not False:
        raise ValueError("OR variants may not be pooled as independent events")
    if p.get("development_window") != ["2019-01-01T00:00:00Z", "2023-01-01T00:00:00Z"]:
        raise ValueError("NAS-H001 path development is frozen to 2019-2022")
    if p.get("market_data_cutoff_exclusive") != "2023-01-01T00:00:00Z":
        raise ValueError("development path runner must not read 2023+ market bars")
    primary = p.get("primary_mechanism_test", {})
    expected = {
        "path_start": "NEXT_COMPLETE_M1_BAR_AFTER_BREAK_EVENT_AVAILABLE_AT",
        "price_basis": "COMPLETE_M1_CLOSE_ONLY",
        "horizon_minutes": 60,
        "normalizer": "OPENING_RANGE_WIDTH",
        "barrier_multiple": 0.5,
        "score_continuation": 1,
        "score_failure": -1,
        "score_unresolved": 0,
    }
    for k, v in expected.items():
        if primary.get(k) != v:
            raise ValueError(f"NAS-H001 frozen primary setting changed: {k}")
    if primary.get("long_continuation") != "close >= OR_HIGH + 0.5*OR_WIDTH":
        raise ValueError("unexpected long continuation threshold")
    if primary.get("long_failure") != "close <= OR_HIGH - 0.5*OR_WIDTH":
        raise ValueError("unexpected long failure threshold")
    if primary.get("short_continuation") != "close <= OR_LOW - 0.5*OR_WIDTH":
        raise ValueError("unexpected short continuation threshold")
    if primary.get("short_failure") != "close >= OR_LOW + 0.5*OR_WIDTH":
        raise ValueError("unexpected short failure threshold")
    gates = p.get("development_gates_per_variant", {})
    frozen_gates = {
        "minimum_eligible_events": 400,
        "minimum_resolved_fraction": 0.60,
        "minimum_absolute_effect": 0.05,
        "bootstrap_interval_must_exclude_zero": True,
        "minimum_same_sign_calendar_years": 3,
        "holm_adjusted_alpha_across_three_variants": 0.05,
    }
    for k, v in frozen_gates.items():
        if gates.get(k) != v:
            raise ValueError(f"NAS-H001 frozen development gate changed: {k}")
    bootstrap = p.get("bootstrap", {})
    if bootstrap.get("simulations") != 5000 or bootstrap.get("block") != "ISO_CALENDAR_WEEK":
        raise ValueError("NAS-H001 bootstrap contract changed")
    if p.get("variant_selection_rule", {}).get("selection_metric") != "LARGEST_95CI_DISTANCE_FROM_ZERO":
        raise ValueError("NAS-H001 variant selection rule changed")
    forbidden = p.get("forbidden_before_development_path_freeze", {})
    if not all(forbidden.get(k) is True for k in [
        "validation_2023_2024_path_access",
        "confirmation_2025_path_access",
        "final_2026_holdout_access",
        "trade_entry_stop_target_r_pf_pnl",
    ]):
        raise ValueError("NAS-H001 path access locks must remain enabled")


def operational_fingerprint(project_root: Path) -> str:
    plan = load_nas_h001_path_plan(project_root)
    census_manifest = project_root / CENSUS_MANIFEST_REL
    census_report = project_root / CENSUS_REPORT_REL
    census_events = project_root / CENSUS_EVENTS_REL
    if not census_manifest.exists():
        raise RuntimeError("NAS-H001 event census must be frozen before the development path plan")
    if not census_report.exists() or not census_events.exists():
        raise RuntimeError("NAS-H001 census report/events missing; rerun frozen census before path-plan freeze")
    return fingerprint_payload({
        "plan": plan,
        "detector_config_sha256": _sha256(project_root / DETECTOR_REL),
        "detector_source_sha256": _sha256(project_root / DETECTOR_SOURCE_REL),
        "calendar_sha256": _sha256(project_root / CALENDAR_REL),
        "census_manifest_sha256": _sha256(census_manifest),
        "census_report_sha256": _sha256(census_report),
        "census_events_sha256": _sha256(census_events),
    })


def freeze_nas_h001_path_plan(project_root: Path) -> Path:
    fp = operational_fingerprint(project_root)
    plan = load_nas_h001_path_plan(project_root)
    target = project_root / PATH_MANIFEST_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "analysis_version": ANALYSIS_VERSION,
        "operational_fingerprint": fp,
        "plan_sha256": _sha256(project_root / PLAN_REL),
        "census_manifest_sha256": _sha256(project_root / CENSUS_MANIFEST_REL),
        "census_report_sha256": _sha256(project_root / CENSUS_REPORT_REL),
        "census_events_sha256": _sha256(project_root / CENSUS_EVENTS_REL),
        "post_break_development_paths_inspected_before_freeze": False,
        "validation_2023_2024_paths_accessed_before_freeze": False,
        "confirmation_2025_paths_accessed_before_freeze": False,
        "final_2026_holdout_accessed_before_freeze": False,
        "trade_outcomes_or_pnl_inspected_before_freeze": False,
        "frozen_primary_mechanism": plan["primary_mechanism_test"],
        "frozen_development_gates": plan["development_gates_per_variant"],
        "frozen_selection_rule": plan["variant_selection_rule"],
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def verify_frozen_nas_h001_path_plan(project_root: Path) -> str:
    path = project_root / PATH_MANIFEST_REL
    if not path.exists():
        raise RuntimeError("NAS-H001 development path plan is not frozen")
    frozen = json.loads(path.read_text(encoding="utf-8"))
    current = operational_fingerprint(project_root)
    if frozen.get("operational_fingerprint") != current:
        raise RuntimeError("NAS-H001 path plan inputs changed after freeze; create a new analysis version")
    return current
