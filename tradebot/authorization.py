from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(frozen=True)
class TradeIntent:
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    market_hours: str
    dollar_amount: float | None = None
    quantity: float | None = None
    estimated_price: float | None = None
    asset_class: str = "equity"
    opens_position: bool = True

    @property
    def normalized_symbol(self) -> str:
        return self.symbol.upper()

    @property
    def normalized_side(self) -> str:
        return self.side.lower()

    @property
    def estimated_notional(self) -> float | None:
        if self.dollar_amount is not None:
            return self.dollar_amount
        if self.quantity is not None and self.estimated_price is not None:
            return self.quantity * self.estimated_price
        return None


@dataclass(frozen=True)
class AuthorizationContext:
    account_number: str
    trade_date: date = field(default_factory=date.today)
    current_position_quantity: float = 0.0
    opening_trades_today: int = 0
    daily_notional_so_far: float = 0.0
    monthly_realized_loss: float = 0.0


@dataclass(frozen=True)
class AuthorizationPolicy:
    enabled: bool
    account_nickname: str
    allowed_account_last4: str
    allowed_symbols: frozenset[str]
    allowed_market_hours: frozenset[str]
    time_in_force: str
    skip_review: bool
    max_buy_order_usd: float
    sell_to_close_symbols: frozenset[str]
    max_opening_trades_per_day: int
    max_daily_notional_usd: float
    max_monthly_realized_loss_usd: float
    allow_options: bool
    allow_short_selling: bool
    expires_on: date | None

    @classmethod
    def disabled(cls) -> "AuthorizationPolicy":
        return cls(
            enabled=False,
            account_nickname="",
            allowed_account_last4="",
            allowed_symbols=frozenset(),
            allowed_market_hours=frozenset(),
            time_in_force="gfd",
            skip_review=False,
            max_buy_order_usd=0.0,
            sell_to_close_symbols=frozenset(),
            max_opening_trades_per_day=0,
            max_daily_notional_usd=0.0,
            max_monthly_realized_loss_usd=0.0,
            allow_options=False,
            allow_short_selling=False,
            expires_on=None,
        )

    def validate(self, intent: TradeIntent, context: AuthorizationContext) -> list[str]:
        errors: list[str] = []
        if not self.enabled:
            errors.append("authorization policy is disabled")
            return errors

        if self.expires_on is not None and context.trade_date > self.expires_on:
            errors.append(f"authorization expired on {self.expires_on.isoformat()}")

        if not context.account_number.endswith(self.allowed_account_last4):
            errors.append(f"account must end in {self.allowed_account_last4}")

        symbol = intent.normalized_symbol
        side = intent.normalized_side
        if symbol not in self.allowed_symbols:
            errors.append(f"symbol {symbol} is not allowed")

        if intent.asset_class != "equity":
            errors.append("only equity orders are allowed")
        if intent.asset_class == "option" or not self.allow_options and intent.asset_class != "equity":
            errors.append("options are not allowed")

        if intent.market_hours not in self.allowed_market_hours:
            errors.append(f"market_hours must be one of {sorted(self.allowed_market_hours)}")

        if intent.time_in_force.lower() != self.time_in_force:
            errors.append(f"time_in_force must be {self.time_in_force}")

        notional = intent.estimated_notional
        if notional is None:
            errors.append("order notional could not be estimated")
        else:
            if context.daily_notional_so_far + notional > self.max_daily_notional_usd:
                errors.append(
                    "daily notional limit exceeded: "
                    f"{context.daily_notional_so_far + notional:.2f} > {self.max_daily_notional_usd:.2f}"
                )

        if side == "buy":
            if notional is not None and notional > self.max_buy_order_usd:
                errors.append(f"buy order exceeds max ${self.max_buy_order_usd:.2f}")
            if intent.opens_position and context.opening_trades_today >= self.max_opening_trades_per_day:
                errors.append("new-position trade count limit reached")
        elif side == "sell":
            if symbol not in self.sell_to_close_symbols:
                errors.append(f"sell orders are allowed only to close: {sorted(self.sell_to_close_symbols)}")
            if intent.opens_position:
                errors.append("sell orders may not open positions")
            if intent.quantity is None:
                errors.append("sell-to-close validation requires quantity")
            elif intent.quantity > context.current_position_quantity:
                errors.append("sell quantity exceeds current position")
        else:
            errors.append("side must be buy or sell")

        if not self.allow_short_selling and side == "sell" and intent.opens_position:
            errors.append("short selling is not allowed")

        if context.monthly_realized_loss >= self.max_monthly_realized_loss_usd:
            errors.append("monthly realized loss limit reached")

        if intent.market_hours != "regular_hours" and intent.dollar_amount is not None:
            errors.append("dollar-based orders are allowed only in regular_hours")

        return errors

    def summary_lines(self) -> list[str]:
        return [
            f"Authorization enabled: {self.enabled}",
            f"Account: {self.account_nickname} ending {self.allowed_account_last4}",
            f"Symbols: {', '.join(sorted(self.allowed_symbols))}",
            f"Market hours: {', '.join(sorted(self.allowed_market_hours))}",
            f"Time in force: {self.time_in_force}",
            f"Skip review: {self.skip_review}",
            f"Max buy order: ${self.max_buy_order_usd:.2f}",
            f"Sell to close symbols: {', '.join(sorted(self.sell_to_close_symbols)) or 'none'}",
            f"Max new-position trades/day: {self.max_opening_trades_per_day}",
            f"Max daily notional: ${self.max_daily_notional_usd:.2f}",
            f"Max monthly realized loss: ${self.max_monthly_realized_loss_usd:.2f}",
            f"Options allowed: {self.allow_options}",
            f"Short selling allowed: {self.allow_short_selling}",
            f"Expires on: {self.expires_on.isoformat() if self.expires_on is not None else 'none'}",
        ]


def parse_policy_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
