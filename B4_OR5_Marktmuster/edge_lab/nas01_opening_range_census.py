from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from .history import SafeHistoryWindow
from .nas01_opening_range import HYPOTHESIS_KEY, MARKET_ID, NASOpeningRangePolicy, detect_nas_opening_range_break_events
from .registry import fingerprint_payload

PHASE = "0.7G.4"
CONFIG_REL = Path("config/edge_lab/detectors/NAS-H001-V1.json")
CALENDAR_REL = Path("config/edge_lab/calendars/XNYS_2019_2025_sessions.json")
SOURCE_REL = Path("atlas/edge_lab/nas01_opening_range.py")


@dataclass(frozen=True)
class NASOpeningRangeCensusResult:
    report: dict[str, Any]
    report_path: Path
    events_path: Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_nas_h001_policy(project_root: Path) -> dict[str, Any]:
    payload = json.loads((project_root / CONFIG_REL).read_text(encoding="utf-8"))
    required = {
        "hypothesis": HYPOTHESIS_KEY,
        "market_id": MARKET_ID,
        "opening_range_variants_minutes": [5, 15, 30],
        "break_definition": "FIRST_COMPLETE_M1_CLOSE_STRICTLY_OUTSIDE_FROZEN_OPENING_RANGE",
        "wick_only_break_counts": False,
        "break_search_minutes_after_range_end": 60,
        "require_complete_range_window": True,
        "require_complete_break_search_window": True,
        "events_per_session_per_variant": 1,
        "pool_variants_for_sample_gate": False,
        "final_holdout_start": "2026-01-01T00:00:00Z",
        "future_path_after_first_break_inspected": False,
        "trade_outcomes_inspected": False,
        "pnl_inspected": False,
    }
    for k, v in required.items():
        if payload.get(k) != v:
            raise RuntimeError(f"NAS-H001 detector policy changed: {k}={payload.get(k)!r}, expected {v!r}")
    return payload


def operational_fingerprint(project_root: Path) -> str:
    return fingerprint_payload(
        {
            "policy": load_nas_h001_policy(project_root),
            "detector_source_sha256": _sha256(project_root / SOURCE_REL),
            "calendar_sha256": _sha256(project_root / CALENDAR_REL),
        }
    )


def _manifest_path(project_root: Path) -> Path:
    return project_root / "artifacts/research/atlas07_edge_lab/NAS-H001-V1/nas_h001_event_census_manifest.json"


def freeze_nas_h001_event_census(project_root: Path) -> Path:
    policy = load_nas_h001_policy(project_root)
    target = _manifest_path(project_root)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "phase": PHASE,
        "hypothesis": HYPOTHESIS_KEY,
        "operational_fingerprint": operational_fingerprint(project_root),
        "detector_source_sha256": _sha256(project_root / SOURCE_REL),
        "calendar_sha256": _sha256(project_root / CALENDAR_REL),
        "policy_fingerprint": fingerprint_payload(policy),
        "future_path_after_first_break_inspected_before_freeze": False,
        "trade_outcomes_inspected_before_freeze": False,
        "pnl_inspected_before_freeze": False,
        "validation_2023_2024_outcomes_accessed_before_freeze": False,
        "confirmation_2025_outcomes_accessed_before_freeze": False,
        "2026_holdout_accessed_before_freeze": False,
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def verify_frozen_nas_h001_event_census(project_root: Path) -> str:
    path = _manifest_path(project_root)
    if not path.exists():
        raise RuntimeError("NAS-H001 event census is not frozen. Run: python scripts/atlas07_freeze_nas_h001.py")
    frozen = json.loads(path.read_text(encoding="utf-8"))
    current = operational_fingerprint(project_root)
    if frozen.get("operational_fingerprint") != current:
        raise RuntimeError("NAS-H001 event detector/calendar/policy changed after freeze; create a new analysis version")
    return current


def _safe_rate(num: int, den: int) -> float | None:
    return float(num / den) if den else None


def run_nas_h001_census(
    project_root: Path,
    *,
    cutoff: str = "2026-01-01T00:00:00Z",
    show_progress: bool = True,
) -> NASOpeningRangeCensusResult:
    fp = verify_frozen_nas_h001_event_census(project_root)
    cfg = load_nas_h001_policy(project_root)
    if pd.Timestamp(cutoff) > pd.Timestamp("2026-01-01T00:00:00Z"):
        raise RuntimeError("NAS-H001 census may not read the 2026+ final holdout")

    reader = SafeHistoryWindow(project_root=project_root, market_id=MARKET_ID)
    m1 = reader.read_before("M1", cutoff)
    detection = detect_nas_opening_range_break_events(
        m1, project_root=project_root, policy=NASOpeningRangePolicy(), show_progress=show_progress
    )
    records = [e.to_dict() for e in detection.events]
    ev = pd.DataFrame(records)
    if not ev.empty:
        ev["available_at"] = pd.to_datetime(ev["available_at"], utc=True)
        ev["variant"] = ev["context"].map(lambda x: str(x.get("variant")))
        ev["session_date"] = ev["context"].map(lambda x: str(x.get("session_date")))
        ev["year"] = ev["session_date"].str.slice(0, 4)
        ev["break_delay"] = ev["context"].map(lambda x: int(x.get("break_delay_minutes_after_range_end")))
    else:
        ev = pd.DataFrame(columns=["available_at", "variant", "session_date", "year", "direction", "break_delay"])

    development_start = pd.Timestamp(cfg["development_window"][0])
    development_end = pd.Timestamp(cfg["development_window"][1])
    if development_start.tzinfo is None:
        development_start = development_start.tz_localize("UTC")
    if development_end.tzinfo is None:
        development_end = development_end.tz_localize("UTC")

    variant_reports: dict[str, Any] = {}
    for minutes in cfg["opening_range_variants_minutes"]:
        key = f"OR{minutes}"
        sub = ev[ev["variant"] == key].copy()
        dev = sub[(sub["available_at"] >= development_start) & (sub["available_at"] < development_end)]
        stats = detection.variant_stats[key]
        total_n = int(len(sub))
        dev_n = int(len(dev))
        minimum_total = int(cfg["minimum_total_events_per_variant"])
        preferred_total = int(cfg["preferred_total_events_per_variant"])
        minimum_dev = int(cfg["minimum_development_events_per_variant"])
        sample_pass = total_n >= minimum_total and dev_n >= minimum_dev
        dirs = Counter(str(x) for x in sub.get("direction", pd.Series(dtype=str)))
        years = Counter(str(x) for x in sub.get("year", pd.Series(dtype=str)))
        delays = [int(x) for x in sub.get("break_delay", pd.Series(dtype=int)).tolist()]
        variant_reports[key] = {
            **stats,
            "event_rate_among_fully_observable_sessions": _safe_rate(total_n, int(stats["fully_observable_sessions"])),
            "development_events_2019_2022": dev_n,
            "minimum_total_events_gate": minimum_total,
            "preferred_total_events": preferred_total,
            "minimum_development_events_gate": minimum_dev,
            "sample_gate": "PASS" if sample_pass else "INSUFFICIENT_EVIDENCE",
            "events_by_direction": dict(sorted(dirs.items())),
            "events_by_year": dict(sorted(years.items())),
            "median_break_delay_minutes": float(median(delays)) if delays else None,
            "p90_break_delay_minutes": float(pd.Series(delays).quantile(0.90)) if delays else None,
        }

    passed = [k for k, v in variant_reports.items() if v["sample_gate"] == "PASS"]
    report = {
        "phase": PHASE,
        "budget_id": "NAS100-BUDGET-1",
        "hypothesis": HYPOTHESIS_KEY,
        "operational_fingerprint": fp,
        "research_cutoff_exclusive": cutoff,
        "m1_rows_read_pre2026": int(len(m1)),
        "frozen_calendar": "XNYS_2019_2025_FROZEN_V1",
        "calendar_session_count_2019_2025": 1760,
        "opening_range_variants": ["OR5", "OR15", "OR30"],
        "variants_are_not_independent_and_not_pooled": True,
        "event_definition": "first complete M1 close strictly beyond the frozen OR high/low within 60 minutes after range end",
        "wick_only_breaks_count": False,
        "future_path_after_first_break_inspected": False,
        "trade_outcomes_inspected": False,
        "stop_target_results_inspected": False,
        "r_inspected": False,
        "pnl_inspected": False,
        "validation_2023_2024_outcomes_accessed": False,
        "confirmation_2025_outcomes_accessed": False,
        "final_2026_holdout_accessed": False,
        "frozen_chronology_for_future_path_research": {
            "development": "2019-2022",
            "validation": "2023-2024",
            "confirmation": "2025",
            "final_holdout": "2026+",
        },
        "variants": variant_reports,
        "variants_passing_sample_gate": passed,
        "scientific_gate": "PASS_TO_DEVELOPMENT_PATH_PLAN" if passed else "INSUFFICIENT_EVIDENCE",
        "interpretation": (
            "Event census only. OR5/OR15/OR30 are preregistered research variants. A record ends at the first close-outside break event. "
            "No bar after the event is inspected for continuation/failure, MFE/MAE, stop/target, R, PF or PnL."
        ),
    }

    out_dir = project_root / "artifacts/research/atlas07_edge_lab/NAS-H001-V1"
    out_dir.mkdir(parents=True, exist_ok=True)
    events_path = out_dir / "nas_h001_opening_range_break_events_pre2026.jsonl"
    report_path = out_dir / "nas_h001_event_census.json"
    with events_path.open("w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec, sort_keys=True) + "\n")
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return NASOpeningRangeCensusResult(report=report, report_path=report_path, events_path=events_path)
