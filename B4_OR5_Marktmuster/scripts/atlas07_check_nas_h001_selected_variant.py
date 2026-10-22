from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.edge_lab.nas01_variant_freeze import (
    load_development_report,
    load_selected_variant_contract,
    validate_selected_variant_contract,
)


def main() -> int:
    contract = load_selected_variant_contract(ROOT)
    report = load_development_report(ROOT)
    selected = validate_selected_variant_contract(contract, report)
    print("ATLAS 0.7G.7 NAS-H001 SELECTED VARIANT / VALIDATION CONTRACT: OK")
    print("selected_variant=OR5")
    print("selected_mechanism=ROBUST_CONTINUATION_CANDIDATE")
    print(f"development_effect={100*float(selected['primary_effect']):+.2f}%")
    print(f"development_95CI=[{100*float(selected['bootstrap_lower95']):+.2f}%, {100*float(selected['bootstrap_upper95']):+.2f}%]")
    print("validation=2023-2024 ONLY")
    print("validation primary=+0.5 OR-width continuation-vs-failure close barrier, 60m, next-bar start")
    print("validation gates: n>=400, resolved>=60%, continuation effect>=+5pp, lower95>0, both years positive, block p<0.05")
    print("OR15/OR30 fallback if OR5 fails: FORBIDDEN")
    print("confirmation 2025: LOCKED")
    print("2026+ final holdout: LOCKED")
    print("trade entry/SL/TP/R/PF/PnL: DISABLED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
