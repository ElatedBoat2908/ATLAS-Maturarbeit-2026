from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.edge_lab.nas01_confirmation_freeze import (
    load_confirmation_contract,
    load_validation_report,
    validate_confirmation_contract,
)
from atlas.edge_lab.nas01_variant_freeze import load_selected_variant_contract


def main() -> int:
    contract = load_confirmation_contract(ROOT)
    validation = load_validation_report(ROOT)
    selected = load_selected_variant_contract(ROOT)
    validate_confirmation_contract(contract, validation, selected)

    print("ATLAS 0.7G.9 NAS-H001 OR5 CONFIRMATION CONTRACT: OK")
    print("selected_variant=OR5")
    print("selected_mechanism=ROBUST_CONTINUATION_CANDIDATE")
    print(f"validation_effect={100.0 * float(validation['primary_effect']):+.2f}%")
    print(
        "validation_95CI="
        f"[{100.0 * float(validation['bootstrap_lower95']):+.2f}%, "
        f"{100.0 * float(validation['bootstrap_upper95']):+.2f}%]"
    )
    print("confirmation=2025 ONLY")
    print("confirmation primary=+0.5 OR-width continuation-vs-failure close barrier, 60m, next-bar start")
    print("confirmation gates: n>=200, resolved>=60%, continuation effect>=+5pp, lower95>0, block p<0.05")
    print("OR15/OR30 fallback: FORBIDDEN")
    print("2026+ final holdout: LOCKED")
    print("trade entry/SL/TP/R/PF/PnL: DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
