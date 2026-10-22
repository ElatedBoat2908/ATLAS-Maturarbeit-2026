from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.edge_lab.nas01_trade_outcome import freeze_trade_runner


def main() -> None:
    path, manifest = freeze_trade_runner(ROOT)
    print("ATLAS 0.7G.13 NAS-H001 2019-2025 EXECUTABLE TRADE RUNNER FROZEN")
    print(f"manifest: {path}")
    print("selected_variant=OR5 selected_mechanism=ROBUST_CONTINUATION_CANDIDATE")
    print(f"bootstrap_seed={manifest['bootstrap_seed']}")
    print("Research window=2019-2025 ONLY")
    print("Trade outcomes inspected before runner freeze: NO")
    print("2026+ final holdout accessed before runner freeze: NO")
    print("Parameter search before runner freeze: NO")
    print("OR15/OR30 fallback before runner freeze: NO")
    print("NEXT: frozen runner may execute 2019-2025 trade research only. Do not open 2026.")


if __name__ == "__main__":
    main()
