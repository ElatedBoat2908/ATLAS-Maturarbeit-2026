from __future__ import annotations

from .models import AccountRiskSnapshot, RiskDecision, RiskPolicy


class AccountRiskEngine:
    """Account-level risk gate. No sizing and no execution."""

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy()
        self.policy.validate()

    def evaluate(self, snapshot: AccountRiskSnapshot) -> RiskDecision:
        self._validate_snapshot(snapshot)
        reasons: list[str] = []

        drawdown_pct = self._drawdown_pct(snapshot.equity, snapshot.peak_equity)
        daily_loss_pct = self._daily_loss_pct(
            snapshot.equity,
            snapshot.day_start_equity,
            snapshot.daily_realized_pnl,
        )

        if self.policy.block_when_kill_switch_active and snapshot.kill_switch_active:
            reasons.append("KILL_SWITCH_ACTIVE")
        if snapshot.equity < self.policy.minimum_equity:
            reasons.append("EQUITY_BELOW_MINIMUM")
        if drawdown_pct >= self.policy.max_equity_drawdown_pct:
            reasons.append("MAX_EQUITY_DRAWDOWN_REACHED")
        if daily_loss_pct >= self.policy.max_daily_loss_pct:
            reasons.append("MAX_DAILY_LOSS_REACHED")
        if snapshot.open_positions >= self.policy.max_open_positions:
            reasons.append("MAX_OPEN_POSITIONS_REACHED")

        allow = not reasons
        max_cash_risk = (
            round(snapshot.equity * self.policy.max_risk_per_trade_pct, 2)
            if allow
            else 0.0
        )

        return RiskDecision(
            decision="ALLOW_NEW_RISK" if allow else "BLOCK_NEW_RISK",
            allow_new_risk=allow,
            max_cash_risk=max_cash_risk,
            risk_per_trade_pct=self.policy.max_risk_per_trade_pct,
            current_drawdown_pct=round(drawdown_pct, 8),
            current_daily_loss_pct=round(daily_loss_pct, 8),
            reasons=tuple(reasons) if reasons else ("RISK_LIMITS_OK",),
            live_trading_allowed=False,
        )

    @staticmethod
    def _validate_snapshot(snapshot: AccountRiskSnapshot) -> None:
        for name, value in {
            "balance": snapshot.balance,
            "equity": snapshot.equity,
            "peak_equity": snapshot.peak_equity,
            "day_start_equity": snapshot.day_start_equity,
        }.items():
            if float(value) <= 0:
                raise ValueError(f"{name} must be positive.")
        if snapshot.peak_equity < snapshot.equity:
            raise ValueError("peak_equity may not be below current equity.")
        if int(snapshot.open_positions) < 0:
            raise ValueError("open_positions may not be negative.")

    @staticmethod
    def _drawdown_pct(current: float, peak: float) -> float:
        return max(0.0, (peak - current) / peak) if peak > 0 else 0.0

    @staticmethod
    def _daily_loss_pct(current: float, day_start: float, realized_pnl: float) -> float:
        if day_start <= 0:
            return 0.0
        equity_loss = max(0.0, day_start - current)
        realized_loss = max(0.0, -float(realized_pnl))
        return max(equity_loss, realized_loss) / day_start
