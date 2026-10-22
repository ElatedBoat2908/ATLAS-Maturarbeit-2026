from __future__ import annotations

from typing import Any

from .models import AccountRiskSnapshot


def account_snapshot_from_connector(
    account: Any,
    *,
    peak_equity: float,
    day_start_equity: float,
    daily_realized_pnl: float,
    open_positions: int,
    kill_switch_active: bool = False,
) -> AccountRiskSnapshot:
    return AccountRiskSnapshot(
        balance=float(account.balance),
        equity=float(account.equity),
        peak_equity=float(peak_equity),
        day_start_equity=float(day_start_equity),
        daily_realized_pnl=float(daily_realized_pnl),
        open_positions=int(open_positions),
        kill_switch_active=bool(kill_switch_active),
        account_login=getattr(account, "login", None),
        currency=getattr(account, "currency", None),
    )
