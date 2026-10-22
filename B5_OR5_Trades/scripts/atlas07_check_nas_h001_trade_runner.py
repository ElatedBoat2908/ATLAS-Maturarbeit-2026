from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.edge_lab.nas01_execution_calibration import verify_frozen_execution_cost_calibration
from atlas.edge_lab.nas01_trade_hypothesis_freeze import verify_frozen_trade_hypothesis
from atlas.edge_lab.nas01_trade_outcome import load_trade_runner_contract, validate_trade_runner_contract


def main() -> None:
    verify_frozen_trade_hypothesis(ROOT)
    verify_frozen_execution_cost_calibration(ROOT)
    contract = load_trade_runner_contract(ROOT)
    validate_trade_runner_contract(contract)
    print("ATLAS 0.7G.13 NAS-H001 2019-2025 EXECUTABLE TRADE RUNNER CONTRACT: OK")
    print("selected_variant=OR5 selected_mechanism=CONTINUATION")
    print("candidate_source=FROZEN_PRE2026_OR5_CENSUS_EVENTS_ONLY")
    print("entry=next M1 open at event available_at with frozen historical spread + baseline slippage")
    print("target=broken OR boundary +/- 0.5 OR width; stop=OR midpoint")
    print("trigger_basis=M1 BID high/low; same-bar stop+target=STOP_FIRST_CONSERVATIVE")
    print("holding=60 consecutive M1 bars; normalized cost-adjusted R only")
    print("hard_gates=n>=1000, meanR>=+0.05, lower95>0, PF_R>=1.10, >=5/7 positive years, early>=0, late>=0, stress>=0")
    print("2026+ final holdout: LOCKED")
    print("parameter search: FORBIDDEN")
    print("OR15/OR30 fallback: FORBIDDEN")
    print("Trade outcomes inspected by this check: NO")


if __name__ == "__main__":
    main()
