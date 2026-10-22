from __future__ import annotations

import argparse
import json

from .engine import AccountRiskEngine
from .models import AccountRiskSnapshot, RiskPolicy


def main() -> None:
    p = argparse.ArgumentParser(description="ATLAS Account Risk Engine")
    p.add_argument("--balance", type=float, required=True)
    p.add_argument("--equity", type=float, required=True)
    p.add_argument("--peak-equity", type=float, required=True)
    p.add_argument("--day-start-equity", type=float, required=True)
    p.add_argument("--daily-realized-pnl", type=float, default=0.0)
    p.add_argument("--open-positions", type=int, default=0)
    p.add_argument("--kill-switch", action="store_true")
    p.add_argument("--risk-per-trade", type=float, default=0.005)
    p.add_argument("--max-daily-loss", type=float, default=0.03)
    p.add_argument("--max-drawdown", type=float, default=0.08)
    p.add_argument("--max-open-positions", type=int, default=3)
    args = p.parse_args()

    policy = RiskPolicy(
        max_risk_per_trade_pct=args.risk_per_trade,
        max_daily_loss_pct=args.max_daily_loss,
        max_equity_drawdown_pct=args.max_drawdown,
        max_open_positions=args.max_open_positions,
    )
    snapshot = AccountRiskSnapshot(
        balance=args.balance,
        equity=args.equity,
        peak_equity=args.peak_equity,
        day_start_equity=args.day_start_equity,
        daily_realized_pnl=args.daily_realized_pnl,
        open_positions=args.open_positions,
        kill_switch_active=args.kill_switch,
    )
    print(json.dumps(AccountRiskEngine(policy).evaluate(snapshot).to_dict(), indent=2))


if __name__ == "__main__":
    main()
