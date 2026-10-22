from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from atlas.edge_lab.history_extension_audit import (
    REQUIRED,
    _prepare,
    _utc,
    reconcile_m1_to_m15,
    session_total_variation,
    stream_audit,
)


MARKET_ID = 'NAS100'
NY_TZ = 'America/New_York'


@dataclass(frozen=True)
class NASHistoryAuditResult:
    report: dict[str, Any]
    report_path: Path


def _read_canonical(project_root: Path, timeframe: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    path = project_root / 'data' / 'raw' / 'atlas05_history' / MARKET_ID / f'{timeframe}.parquet'
    if not path.exists():
        raise FileNotFoundError(f"canonical NAS100 stream not found: {path}")
    try:
        import pyarrow  # noqa: F401
    except Exception as exc:
        raise RuntimeError('pyarrow is required for strict NAS100 history audit filtering') from exc
    frame = pd.read_parquet(
        path,
        engine='pyarrow',
        filters=[('time', '>=', start.to_pydatetime()), ('time', '<', end.to_pydatetime())],
    )
    if not frame.empty:
        frame = _prepare(frame)
        if not bool(((frame['time'] >= start) & (frame['time'] < end)).all()):
            raise RuntimeError('NAS100 parquet filter returned rows outside requested window')
    return frame


def _fetch_mt5(project_root: Path, start: pd.Timestamp, end: pd.Timestamp, chunk_days: int) -> tuple[str, dict[str, pd.DataFrame]]:
    from atlas.core.settings import load_atlas05_settings
    from atlas.intelligence.memory.mt5_history_source import MT5HistorySource

    settings = load_atlas05_settings(project_root)
    frames: dict[str, pd.DataFrame] = {}
    with MT5HistorySource(settings) as source:
        broker_symbol = source.resolve_symbol(MARKET_ID)
        for timeframe in ('M1', 'M15'):
            parts: list[pd.DataFrame] = []
            for chunk in source.iter_chunks(
                market_id=MARKET_ID,
                timeframe=timeframe,
                start=start.to_pydatetime(),
                end=end.to_pydatetime(),
                chunk_days=chunk_days,
            ):
                if not chunk.bars.empty:
                    parts.append(chunk.bars.copy())
            frames[timeframe] = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=list(REQUIRED))
    return broker_symbol, frames


def _spread_stats(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty or 'spread' not in frame.columns:
        return {'median_points': None, 'p90_points': None, 'p95_points': None, 'max_points': None}
    s = pd.to_numeric(frame['spread'], errors='coerce').dropna().astype(float)
    if s.empty:
        return {'median_points': None, 'p90_points': None, 'p95_points': None, 'max_points': None}
    return {
        'median_points': float(s.median()),
        'p90_points': float(s.quantile(0.90)),
        'p95_points': float(s.quantile(0.95)),
        'max_points': float(s.max()),
    }


def cash_open_window_audit(
    m1: pd.DataFrame,
    *,
    window_start_local: str = '09:30',
    window_end_local: str = '10:30',
    candidate_session_start_local: str = '08:00',
    candidate_session_end_local: str = '16:30',
    minimum_rows_for_complete_window: int = 55,
) -> dict[str, Any]:
    if m1.empty:
        return {
            'candidate_cash_session_days': 0,
            'complete_cash_open_days': 0,
            'complete_cash_open_fraction': None,
            'missing_or_incomplete_dates': [],
            'median_rows_in_open_window': None,
            'p05_rows_in_open_window': None,
            'cash_open_utc_hour_counts': {},
            'cash_open_utc_minute_counts': {},
        }

    f = _prepare(m1)
    local = f['time'].dt.tz_convert(NY_TZ)
    local_minutes = local.dt.hour * 60 + local.dt.minute
    weekday = local.dt.weekday < 5
    local_date = local.dt.strftime('%Y-%m-%d')

    def minute_of(text: str) -> int:
        hh, mm = (int(x) for x in text.split(':'))
        return hh * 60 + mm

    session_start = minute_of(candidate_session_start_local)
    session_end = minute_of(candidate_session_end_local)
    open_start = minute_of(window_start_local)
    open_end = minute_of(window_end_local)

    candidate_mask = weekday & (local_minutes >= session_start) & (local_minutes < session_end)
    candidate_dates = sorted(set(local_date[candidate_mask]))
    open_mask = weekday & (local_minutes >= open_start) & (local_minutes < open_end)
    open_counts = local_date[open_mask].value_counts()
    counts = np.array([int(open_counts.get(d, 0)) for d in candidate_dates], dtype=int)
    complete = counts >= int(minimum_rows_for_complete_window)
    incomplete_dates = [d for d, ok in zip(candidate_dates, complete, strict=False) if not bool(ok)]

    exact_open = weekday & (local_minutes == open_start)
    open_utc_hours = f.loc[exact_open, 'time'].dt.hour.value_counts().sort_index()
    open_utc_minutes = f.loc[exact_open, 'time'].dt.minute.value_counts().sort_index()

    return {
        'timezone': NY_TZ,
        'window_local': f'{window_start_local}-{window_end_local}',
        'candidate_cash_session_local': f'{candidate_session_start_local}-{candidate_session_end_local}',
        'minimum_rows_for_complete_window': int(minimum_rows_for_complete_window),
        'candidate_cash_session_days': int(len(candidate_dates)),
        'complete_cash_open_days': int(complete.sum()) if len(counts) else 0,
        'complete_cash_open_fraction': float(complete.mean()) if len(counts) else None,
        'missing_or_incomplete_dates': incomplete_dates,
        'median_rows_in_open_window': float(np.median(counts)) if len(counts) else None,
        'p05_rows_in_open_window': float(np.quantile(counts, 0.05)) if len(counts) else None,
        'cash_open_utc_hour_counts': {str(int(k)): int(v) for k, v in open_utc_hours.items()},
        'cash_open_utc_minute_counts': {str(int(k)): int(v) for k, v in open_utc_minutes.items()},
    }


def _gate(name: str, passed: bool, observed: Any, required: str) -> dict[str, Any]:
    return {'name': name, 'status': 'PASS' if passed else 'FAIL', 'observed': observed, 'required': required}


def run_nas100_history_audit(
    project_root: Path,
    *,
    old_start: str = '2016-01-01T00:00:00Z',
    old_end_exclusive: str = '2020-01-01T00:00:00Z',
    chunk_days: int = 31,
) -> NASHistoryAuditResult:
    cfg_path = project_root / 'config' / 'edge_lab' / 'audits' / 'NAS-H001-history-audit.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8'))
    thresholds = cfg['thresholds']

    old_start_ts = _utc(old_start)
    old_end_ts = _utc(old_end_exclusive)
    baseline_start = _utc(cfg['baseline_start'])
    baseline_end = _utc(cfg['baseline_end_exclusive'])
    if old_end_ts > baseline_start:
        raise ValueError('NAS old-history audit must end on or before baseline start')
    if baseline_end > _utc('2026-01-01T00:00:00Z'):
        raise ValueError('2026 final holdout access is forbidden')

    broker_symbol, old = _fetch_mt5(project_root, old_start_ts, old_end_ts, chunk_days)
    baseline = {tf: _read_canonical(project_root, tf, baseline_start, baseline_end) for tf in ('M1', 'M15')}

    old_audits = {
        tf: stream_audit(old[tf], timeframe=tf, requested_start=old_start_ts, requested_end_exclusive=old_end_ts)
        for tf in ('M1', 'M15')
    }
    baseline_audits = {
        tf: stream_audit(baseline[tf], timeframe=tf, requested_start=baseline_start, requested_end_exclusive=baseline_end)
        for tf in ('M1', 'M15')
    }
    reconciliation = reconcile_m1_to_m15(old['M1'], old['M15'])
    session_tv = {tf: session_total_variation(old_audits[tf], baseline_audits[tf]) for tf in ('M1', 'M15')}
    old_cash = cash_open_window_audit(old['M1'])
    base_cash = cash_open_window_audit(baseline['M1'])

    old_last_close = float(_prepare(old['M15'])['close'].iloc[-1]) if not old['M15'].empty else None
    baseline_first_close = float(_prepare(baseline['M15'])['close'].iloc[0]) if not baseline['M15'].empty else None
    boundary_ratio = (baseline_first_close / old_last_close) if old_last_close not in (None, 0) and baseline_first_close is not None else None

    gates: list[dict[str, Any]] = []
    for tf in ('M1', 'M15'):
        a = old_audits[tf]
        gates.extend([
            _gate(f'{tf}_rows_present', int(a['rows']) > 0, int(a['rows']), '> 0'),
            _gate(f'{tf}_start_coverage', a['start_lag_days'] is not None and a['start_lag_days'] <= float(thresholds['maximum_start_lag_days']), a['start_lag_days'], f"<= {thresholds['maximum_start_lag_days']} days"),
            _gate(f'{tf}_end_coverage', a['end_lag_days'] is not None and a['end_lag_days'] <= float(thresholds['maximum_end_lag_days']), a['end_lag_days'], f"<= {thresholds['maximum_end_lag_days']} days"),
            _gate(f'{tf}_calendar_months', len(a['missing_calendar_months']) <= int(thresholds['maximum_missing_calendar_months']), a['missing_calendar_months'], f"<= {thresholds['maximum_missing_calendar_months']} missing months"),
            _gate(f'{tf}_duplicates', int(a['duplicate_timestamps']) == 0, int(a['duplicate_timestamps']), '0'),
            _gate(f'{tf}_ohlc_integrity', int(a['ohlc_integrity_errors'] or 0) == 0, a['ohlc_integrity_errors'], '0'),
            _gate(f'{tf}_required_values', int(a['missing_required_values'] or 0) == 0, a['missing_required_values'], '0'),
            _gate(f'{tf}_non_grid', a['non_grid_fraction'] is not None and a['non_grid_fraction'] <= float(thresholds['maximum_non_grid_fraction']), a['non_grid_fraction'], f"<= {thresholds['maximum_non_grid_fraction']}"),
            _gate(f'{tf}_session_structure', session_tv[tf] is not None and session_tv[tf] <= float(thresholds['maximum_session_total_variation']), session_tv[tf], f"TV <= {thresholds['maximum_session_total_variation']} vs 2020-2025"),
        ])

    gates.extend([
        _gate('m1_m15_comparable_bars', int(reconciliation['comparable_bars']) >= int(thresholds['minimum_m1_m15_comparable_bars']), reconciliation['comparable_bars'], f">= {thresholds['minimum_m1_m15_comparable_bars']}"),
        _gate('m1_m15_ohlc_reconciliation', reconciliation['ohlc_match_rate'] is not None and reconciliation['ohlc_match_rate'] >= float(thresholds['minimum_m1_m15_ohlc_match_rate']), reconciliation['ohlc_match_rate'], f">= {thresholds['minimum_m1_m15_ohlc_match_rate']}"),
        _gate('2019_2020_price_scale_boundary', boundary_ratio is not None and float(thresholds['minimum_boundary_price_ratio']) <= boundary_ratio <= float(thresholds['maximum_boundary_price_ratio']), boundary_ratio, f"between {thresholds['minimum_boundary_price_ratio']} and {thresholds['maximum_boundary_price_ratio']}"),
        _gate('old_cash_open_window_coverage', old_cash['complete_cash_open_fraction'] is not None and old_cash['complete_cash_open_fraction'] >= float(thresholds['minimum_cash_open_complete_fraction']), old_cash['complete_cash_open_fraction'], f">= {thresholds['minimum_cash_open_complete_fraction']}"),
        _gate('baseline_cash_open_window_coverage', base_cash['complete_cash_open_fraction'] is not None and base_cash['complete_cash_open_fraction'] >= float(thresholds['minimum_cash_open_complete_fraction']), base_cash['complete_cash_open_fraction'], f">= {thresholds['minimum_cash_open_complete_fraction']}"),
    ])

    # At 09:30 America/New_York, valid UTC hours are 13 (EDT) or 14 (EST), always minute 30.
    old_hours = set(old_cash['cash_open_utc_hour_counts'])
    base_hours = set(base_cash['cash_open_utc_hour_counts'])
    old_minutes = set(old_cash['cash_open_utc_minute_counts'])
    base_minutes = set(base_cash['cash_open_utc_minute_counts'])
    gates.extend([
        _gate('old_cash_open_dst_mapping', old_hours.issubset({'13', '14'}) and old_minutes.issubset({'30'}), {'utc_hours': sorted(old_hours), 'utc_minutes': sorted(old_minutes)}, '09:30 America/New_York -> 13:30/14:30 UTC only'),
        _gate('baseline_cash_open_dst_mapping', base_hours.issubset({'13', '14'}) and base_minutes.issubset({'30'}), {'utc_hours': sorted(base_hours), 'utc_minutes': sorted(base_minutes)}, '09:30 America/New_York -> 13:30/14:30 UTC only'),
    ])

    failed = [g for g in gates if g['status'] == 'FAIL']
    decision = 'PASS_TO_NAS_CANONICAL_EXTENSION' if not failed else 'REVIEW_BEFORE_NAS_RESEARCH'
    report = {
        'phase': '0.7G.1',
        'audit_id': cfg['audit_id'],
        'market_id': MARKET_ID,
        'broker_symbol_resolved': broker_symbol,
        'old_window': {'start': old_start_ts.isoformat(), 'end_exclusive': old_end_ts.isoformat()},
        'baseline_window': {'start': baseline_start.isoformat(), 'end_exclusive': baseline_end.isoformat()},
        'canonical_history_modified': False,
        'opening_range_detector_executed': False,
        'trade_outcomes_accessed': False,
        'final_2026_holdout_accessed': False,
        'old_streams': old_audits,
        'baseline_streams': baseline_audits,
        'session_total_variation_vs_2020_2025': session_tv,
        'spread_points': {'old': _spread_stats(old['M1']), 'baseline': _spread_stats(baseline['M1'])},
        'm1_to_m15_reconciliation': reconciliation,
        'cash_open_data_quality': {'old': old_cash, 'baseline': base_cash},
        'boundary': {
            'last_pre2020_m15_close': old_last_close,
            'first_2020_m15_close': baseline_first_close,
            'first2020_over_lastpre2020_ratio': boundary_ratio,
        },
        'gates': gates,
        'failed_gates': [g['name'] for g in failed],
        'decision': decision,
        'research_convention_verified': {
            'cash_open_timezone': NY_TZ,
            'cash_open_local_time': '09:30',
            'dst_handling': 'IANA America/New_York; no fixed UTC hour',
            'data_quality_window_checked': '09:30-10:30 America/New_York',
            'opening_range_length': 'NOT_YET_FROZEN',
        },
        'limitations': [
            'This is a read-only market-data audit, not an alpha test.',
            'The audit cannot prove historical broker contract metadata that MT5 no longer exposes, but it checks coverage, cadence, session shape, price scale and M1/M15 consistency.',
            'Cash-open coverage uses local America/New_York time so DST is handled causally and consistently.',
            'No NAS100 opening-range event, future path, win rate, stop, target, R, PF or PnL is inspected.',
        ],
    }
    out_dir = project_root / 'artifacts' / 'research' / 'atlas07_edge_lab' / 'NAS-BUDGET-1' / 'history_audit'
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / 'nas100_history_audit_2016_2025.json'
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    return NASHistoryAuditResult(report=report, report_path=report_path)
