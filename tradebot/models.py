from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class TradeSignal:
    timestamp: datetime
    symbol: str
    side: str
    price: float
    reason: str


@dataclass(frozen=True)
class PairSignal:
    timestamp: datetime
    target_symbol: str | None
    price: float | None
    reason: str


@dataclass(frozen=True)
class LiveQuote:
    symbol: str
    price: float
    as_of: datetime
    source: str
    bid: float | None = None
    ask: float | None = None
    previous_close: float | None = None
    state: str = "unknown"
    has_traded: bool = False

    @property
    def spread(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return self.ask - self.bid

    @property
    def daily_change_pct(self) -> float | None:
        if self.previous_close in (None, 0):
            return None
        return ((self.price / self.previous_close) - 1) * 100

    def age_seconds(self, now: datetime | None = None) -> float:
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        quote_time = self.as_of
        if quote_time.tzinfo is None:
            quote_time = quote_time.replace(tzinfo=timezone.utc)
        return max(0.0, (reference - quote_time).total_seconds())


@dataclass
class Fill:
    timestamp: datetime
    symbol: str
    side: str
    quantity: float
    price: float
    cash_after: float
    realized_pnl: float = 0.0
    strategy: str = ""
    mode: str = "paper"
    notes: str = ""


@dataclass
class BacktestResult:
    symbol: str
    initial_equity: float
    final_equity: float
    realized_pnl: float
    fills: list[Fill] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    metrics: dict[str, float | int | None] = field(default_factory=dict)

    def text_report(self) -> str:
        lines = [
            f"Symbol: {self.symbol}",
            f"Initial equity: ${self.initial_equity:,.2f}",
            f"Final equity:   ${self.final_equity:,.2f}",
            f"Realized PnL:   ${self.realized_pnl:,.2f}",
        ]
        for key, value in self.metrics.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                if key.endswith("_pct"):
                    lines.append(f"{label}: {value:.2f}%")
                else:
                    lines.append(f"{label}: {value:.4f}")
            else:
                lines.append(f"{label}: {value}")
        return "\n".join(lines)
