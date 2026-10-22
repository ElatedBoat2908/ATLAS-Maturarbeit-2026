from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import Direction, EventRecord
from .progress import TerminalProgress

HYPOTHESIS_KEY = "NAS-H001-V1"
MARKET_ID = "NAS100"
NY_TZ = "America/New_York"
_NS_PER_MINUTE = 60_000_000_000


@dataclass(frozen=True)
class NASOpeningRangePolicy:
    variants_minutes: tuple[int, ...] = (5, 15, 30)
    search_minutes_after_range: int = 60
    m1_atr_period: int = 14
    require_complete_range_window: bool = True
    require_complete_search_window: bool = True

    def validate(self) -> None:
        if self.variants_minutes != (5, 15, 30):
            raise ValueError("NAS-H001-V1 freezes opening-range variants to exactly 5/15/30 minutes")
        if self.search_minutes_after_range != 60:
            raise ValueError("NAS-H001-V1 freezes a 60-minute first-break search after each range ends")
        if self.m1_atr_period != 14:
            raise ValueError("NAS-H001-V1 census freezes M1 ATR14 as descriptive event scale")
        if not self.require_complete_range_window or not self.require_complete_search_window:
            raise ValueError("NAS-H001-V1 requires complete M1 range and search windows")


@dataclass(frozen=True)
class NASOpeningRangeDetectionResult:
    events: tuple[EventRecord, ...]
    variant_stats: dict[str, dict[str, Any]]


def _utc_ns_index(values: pd.Series | pd.Index) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(values, utc=True, errors="raise"))
    # Normalize explicitly because Windows/Pandas may retain datetime64[us, UTC].
    try:
        idx = idx.as_unit("ns")
    except AttributeError:  # pragma: no cover - compatibility with older pandas
        idx = pd.DatetimeIndex(idx.tz_convert("UTC").tz_localize(None).to_numpy(dtype="datetime64[ns]"), tz="UTC")
    return idx


def _prepare_m1(frame: pd.DataFrame, *, atr_period: int) -> pd.DataFrame:
    required = {"time", "open", "high", "low", "close"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"NAS100 M1 missing required columns: {sorted(missing)}")
    out = frame.copy()
    out["time"] = _utc_ns_index(out["time"])
    out = out.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="raise")
    if bool((out["low"] > out[["open", "close"]].min(axis=1)).any()):
        raise ValueError("OHLC integrity failure: low above open/close")
    if bool((out["high"] < out[["open", "close"]].max(axis=1)).any()):
        raise ValueError("OHLC integrity failure: high below open/close")
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr14"] = tr.rolling(atr_period, min_periods=atr_period).mean()
    out["available_at"] = out["time"] + pd.Timedelta(minutes=1)
    return out


def _load_frozen_sessions(project_root: Path) -> list[dict[str, Any]]:
    path = project_root / "config" / "edge_lab" / "calendars" / "XNYS_2019_2025_sessions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("calendar_id") != "XNYS_2019_2025_FROZEN_V1":
        raise RuntimeError("unexpected NAS cash-session calendar id")
    if int(payload.get("session_count", 0)) <= 0:
        raise RuntimeError("frozen XNYS calendar contains no sessions")
    return list(payload["sessions"])


def _event_id(session_date: str, variant: int, direction: Direction, available_at: pd.Timestamp) -> str:
    token = f"{HYPOTHESIS_KEY}|OR{variant}|{session_date}|{direction.value}|{available_at.isoformat()}"
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]
    return f"NAS-H001-V1-OR{variant}-{direction.value}-{available_at.strftime('%Y%m%dT%H%M%SZ')}-{digest}"


def _complete_contiguous_window(time_ns: np.ndarray, start_ns: int, minutes: int) -> tuple[bool, int]:
    """O(log n + minutes) exact minute-grid completeness check.

    The original EL20 implementation repeatedly called DatetimeIndex.isin()
    against the complete ~2.7M-row history for every session/variant.  This
    function preserves the exact completeness semantics but uses one binary
    search plus a tiny contiguous slice.
    """
    pos = int(np.searchsorted(time_ns, start_ns, side="left"))
    end = pos + int(minutes)
    if pos >= len(time_ns) or end > len(time_ns):
        return False, pos
    expected = start_ns + np.arange(minutes, dtype=np.int64) * _NS_PER_MINUTE
    return bool(np.array_equal(time_ns[pos:end], expected)), pos


def detect_nas_opening_range_break_events(
    m1: pd.DataFrame,
    *,
    project_root: Path,
    policy: NASOpeningRangePolicy | None = None,
    show_progress: bool = False,
) -> NASOpeningRangeDetectionResult:
    """Detect first close-outside opening-range events without post-break paths.

    EL20.1 performance hotfix: identical NAS-H001-V1 event semantics, but the
    session scan uses binary-search/NumPy slices instead of repeated Pandas
    membership scans over the entire M1 index.
    """
    p = policy or NASOpeningRangePolicy()
    p.validate()
    bars = _prepare_m1(m1, atr_period=p.m1_atr_period)
    if bars.empty:
        return NASOpeningRangeDetectionResult(events=(), variant_stats={})

    times = _utc_ns_index(bars["time"])
    time_ns = times.asi8
    high = bars["high"].to_numpy(dtype=float, copy=False)
    low = bars["low"].to_numpy(dtype=float, copy=False)
    close = bars["close"].to_numpy(dtype=float, copy=False)
    atr14 = bars["atr14"].to_numpy(dtype=float, copy=False)

    sessions_all = _load_frozen_sessions(project_root)
    first_ns = int(time_ns[0])
    last_ns = int(time_ns[-1])
    sessions: list[tuple[dict[str, Any], pd.Timestamp, int]] = []
    for session in sessions_all:
        open_utc = pd.Timestamp(session["open_utc"])
        if open_utc.tzinfo is None:
            open_utc = open_utc.tz_localize("UTC")
        else:
            open_utc = open_utc.tz_convert("UTC")
        # Normalize before integer conversion (Windows/Pandas us-vs-ns safe).
        open_utc = pd.Timestamp(open_utc.to_datetime64().astype("datetime64[ns]"), tz="UTC")
        open_ns = int(open_utc.value)
        if first_ns <= open_ns <= last_ns:
            sessions.append((session, open_utc, open_ns))

    events: list[EventRecord] = []
    stats: dict[str, dict[str, Any]] = {
        f"OR{v}": {
            "calendar_sessions": 0,
            "fully_observable_sessions": 0,
            "incomplete_sessions": 0,
            "break_events": 0,
            "no_close_break_within_search": 0,
            "up_break_events": 0,
            "down_break_events": 0,
        }
        for v in p.variants_minutes
    }

    progress = TerminalProgress(total=len(sessions), label="NAS-H001 census") if show_progress else None
    for session_i, (session, open_utc, open_ns) in enumerate(sessions, start=1):
        session_date = str(session["session_date"])

        for variant in p.variants_minutes:
            key = f"OR{variant}"
            stats[key]["calendar_sessions"] += 1
            total_minutes = int(variant + p.search_minutes_after_range)
            complete, range_pos = _complete_contiguous_window(time_ns, open_ns, total_minutes)
            if not complete:
                stats[key]["incomplete_sessions"] += 1
                continue
            stats[key]["fully_observable_sessions"] += 1

            range_end_pos = range_pos + variant
            search_start_pos = range_end_pos
            search_end_pos = search_start_pos + p.search_minutes_after_range

            or_high = float(np.max(high[range_pos:range_end_pos]))
            or_low = float(np.min(low[range_pos:range_end_pos]))
            if not np.isfinite(or_high) or not np.isfinite(or_low) or or_high <= or_low:
                stats[key]["incomplete_sessions"] += 1
                stats[key]["fully_observable_sessions"] -= 1
                continue

            search_close = close[search_start_pos:search_end_pos]
            above = search_close > or_high
            below = search_close < or_low
            crossed = above | below
            hits = np.flatnonzero(crossed)
            if hits.size == 0:
                stats[key]["no_close_break_within_search"] += 1
                continue

            rel = int(hits[0])
            row_pos = search_start_pos + rel
            break_direction = Direction.LONG if bool(above[rel]) else Direction.SHORT
            atr = float(atr14[row_pos])
            if not np.isfinite(atr) or atr <= 0:
                stats[key]["incomplete_sessions"] += 1
                stats[key]["fully_observable_sessions"] -= 1
                continue

            observed_at = pd.Timestamp(times[row_pos])
            available_at = observed_at + pd.Timedelta(minutes=1)
            range_end = open_utc + pd.Timedelta(minutes=variant)
            search_end = range_end + pd.Timedelta(minutes=p.search_minutes_after_range)
            break_close = float(close[row_pos])
            overshoot = break_close - or_high if break_direction == Direction.LONG else or_low - break_close
            delay = rel
            context = {
                "implementation": "NAS-H001-OPENING-RANGE-CENSUS-V1",
                "variant": key,
                "session_date": session_date,
                "xnys_open_utc": open_utc.isoformat(),
                "range_start_utc": open_utc.isoformat(),
                "range_end_exclusive_utc": range_end.isoformat(),
                "break_search_end_exclusive_utc": search_end.isoformat(),
                "opening_range_high": or_high,
                "opening_range_low": or_low,
                "opening_range_width": or_high - or_low,
                "break_bar_open_time": observed_at.isoformat(),
                "break_delay_minutes_after_range_end": delay,
                "break_close": break_close,
                "close_overshoot_points": float(overshoot),
                "m1_atr14_at_break": atr,
                "future_path_after_break_inspected": False,
                "trade_outcomes_inspected": False,
            }
            events.append(
                EventRecord(
                    event_id=_event_id(session_date, variant, break_direction, available_at),
                    hypothesis_id="NAS-H001",
                    hypothesis_version=1,
                    symbol="NAS100",
                    timeframe="M1",
                    event_type=f"OPENING_RANGE_FIRST_CLOSE_BREAK_{key}",
                    observed_at=observed_at.to_pydatetime(),
                    available_at=available_at.to_pydatetime(),
                    reference_price=break_close,
                    atr=atr,
                    direction=break_direction,
                    cluster_key=f"{HYPOTHESIS_KEY}|{key}|{session_date}",
                    context=context,
                    source_refs=("canonical NAS100 M1", "frozen XNYS session calendar"),
                )
            )
            stats[key]["break_events"] += 1
            if break_direction == Direction.LONG:
                stats[key]["up_break_events"] += 1
            else:
                stats[key]["down_break_events"] += 1

        if progress and (session_i == 1 or session_i == len(sessions) or session_i % 10 == 0):
            progress.update(session_i)

    if progress:
        progress.finish()
    events.sort(key=lambda e: (e.available_at, str(e.context.get("variant"))))
    return NASOpeningRangeDetectionResult(events=tuple(events), variant_stats=stats)
