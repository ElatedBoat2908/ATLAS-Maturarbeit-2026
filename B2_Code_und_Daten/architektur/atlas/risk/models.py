from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RiskPolicy:
    max_risk_per_trade_pct: float = 0.005
    max_daily_loss_pct: float = 0.03
    max_equity_drawdown_pct: float = 0.08
    max_open_positions: int = 3
    minimum_equity: float = 100.0
    block_when_kill_switch_active: bool = True

    def validate(self) -> None:
        percentage_fields = {
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_equity_drawdown_pct": self.max_equity_drawdown_pct,
        }
        for name, value in percentage_fields.items():
            if not 0 < float(value) < 1:
                raise ValueError(f"{name} must be between 0 and 1.")
        if int(self.max_open_positions) < 1:
            raise ValueError("max_open_positions must be at least 1.")
        if float(self.minimum_equity) <= 0:
            raise ValueError("minimum_equity must be positive.")


@dataclass(frozen=True)
class AccountRiskSnapshot:
    balance: float
    equity: float
    peak_equity: float
    day_start_equity: float
    daily_realized_pnl: float
    open_positions: int
    kill_switch_active: bool = False
    account_login: int | None = None
    currency: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskDecision:
    decision: str
    allow_new_risk: bool
    max_cash_risk: float
    risk_per_trade_pct: float
    current_drawdown_pct: float
    current_daily_loss_pct: float
    reasons: tuple[str, ...]
    live_trading_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["live_trading_allowed"] = False
        return payload
