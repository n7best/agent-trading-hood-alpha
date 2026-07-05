from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RiskPolicy:
    initial_cash: float = 500.0
    monthly_profit_target: float = 100.0
    max_risk_per_trade_pct: float = 0.01
    max_position_value_pct: float = 0.25
    max_daily_loss_pct: float = 0.03
    max_monthly_loss_pct: float = 0.08
    stop_loss_pct: float = 0.05
    min_cash_buffer_pct: float = 0.05
    allow_fractional: bool = True

    @property
    def monthly_target_return_pct(self) -> float:
        if self.initial_cash <= 0:
            return 0.0
        return (self.monthly_profit_target / self.initial_cash) * 100

    def warnings(self) -> list[str]:
        warnings: list[str] = []
        if self.monthly_target_return_pct >= 10:
            warnings.append(
                "Monthly target is aggressive: "
                f"${self.monthly_profit_target:.2f} on ${self.initial_cash:.2f} "
                f"is {self.monthly_target_return_pct:.1f}% before fees and taxes."
            )
        if self.max_risk_per_trade_pct > 0.02:
            warnings.append("Max risk per trade is above 2%; small accounts can draw down quickly.")
        if self.max_position_value_pct > 0.5:
            warnings.append("Position value cap is above 50%; concentration risk is high.")
        if self.stop_loss_pct <= 0:
            warnings.append("Stop loss percent must be positive to size risk-based trades.")
        return warnings

    def risk_budget(self, equity: float) -> float:
        return max(0.0, equity * self.max_risk_per_trade_pct)

    def max_position_value(self, equity: float) -> float:
        return max(0.0, equity * self.max_position_value_pct)

    def min_cash_buffer(self, equity: float) -> float:
        return max(0.0, equity * self.min_cash_buffer_pct)

    def daily_stop_amount(self, equity: float) -> float:
        return max(0.0, equity * self.max_daily_loss_pct)

    def monthly_stop_amount(self, equity: float) -> float:
        return max(0.0, equity * self.max_monthly_loss_pct)

    def position_quantity(self, equity: float, price: float, stop_price: float | None = None) -> float:
        if equity <= 0 or price <= 0:
            return 0.0

        if stop_price is None:
            stop_price = price * (1 - self.stop_loss_pct)

        loss_per_share = abs(price - stop_price)
        if loss_per_share <= 0:
            return 0.0

        risk_sized_quantity = self.risk_budget(equity) / loss_per_share
        value_sized_quantity = self.max_position_value(equity) / price
        quantity = max(0.0, min(risk_sized_quantity, value_sized_quantity))
        if not self.allow_fractional:
            quantity = math.floor(quantity)
        return round(quantity, 6)

