from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from .models import Fill
from .risk import RiskPolicy

LIVE_ACK_VALUE = "I_UNDERSTAND_LIVE_TRADING_RISK"


@dataclass
class PaperBroker:
    cash: float
    policy: RiskPolicy
    positions: dict[str, float] = field(default_factory=dict)

    def submit_market_order(self, symbol: str, side: str, quantity: float, price: float) -> Fill:
        symbol = symbol.upper()
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price <= 0:
            raise ValueError("price must be positive")

        current = self.positions.get(symbol, 0.0)
        if side == "buy":
            cost = quantity * price
            if cost > self.cash - self.policy.min_cash_buffer(self.cash):
                raise ValueError("paper order rejected: insufficient cash after buffer")
            self.cash -= cost
            self.positions[symbol] = current + quantity
            realized_pnl = 0.0
        elif side == "sell":
            if quantity > current:
                raise ValueError("paper order rejected: cannot sell more than current position")
            self.cash += quantity * price
            self.positions[symbol] = current - quantity
            realized_pnl = 0.0
        else:
            raise ValueError("side must be 'buy' or 'sell'")

        return Fill(
            timestamp=datetime.utcnow(),
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            cash_after=self.cash,
            realized_pnl=realized_pnl,
            strategy="manual",
            mode="paper",
            notes="paper broker fill",
        )


def assert_live_mode_allowed() -> None:
    if os.getenv("TRADING_LIVE_ACK") != LIVE_ACK_VALUE:
        raise RuntimeError(
            "Live trading is locked. Set "
            f"TRADING_LIVE_ACK={LIVE_ACK_VALUE} only after broker and risk checks are verified."
        )

