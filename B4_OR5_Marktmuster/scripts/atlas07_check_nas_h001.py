from __future__ import annotations
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from atlas.edge_lab.nas01_opening_range_census import load_nas_h001_policy, operational_fingerprint

def main() -> None:
    p = load_nas_h001_policy(ROOT)
    print("ATLAS 0.7G.4 NAS-H001 OPENING-RANGE EVENT CENSUS CONTRACT: OK")
    print(f"market={p['market_id']} cash_open={p['cash_open_local_time']} {p['cash_open_timezone']}")
    print(f"variants={p['opening_range_variants_minutes']} minutes")
    print(f"break={p['break_definition']}")
    print(f"search_after_range={p['break_search_minutes_after_range_end']} minutes")
    print("wick-only breaks: NO")
    print("variant pooling: FORBIDDEN")
    print("future path after break: DISABLED")
    print("trade outcomes/PnL: DISABLED")
    print("chronology: development 2019-2022 -> validation 2023-2024 -> confirmation 2025 -> 2026+ holdout")
    print(f"operational_fingerprint={operational_fingerprint(ROOT)}")

if __name__ == '__main__':
    main()
