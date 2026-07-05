from __future__ import annotations

from .indicators import max_drawdown_pct
from .models import BacktestResult, Bar, Fill
from .risk import RiskPolicy
from .strategy import AggressiveSoxlSoxsDayTradeStrategy, MovingAverageCrossoverStrategy, SoxlSoxsRulesStrategy


class Backtester:
    def __init__(self, policy: RiskPolicy, commission_per_order: float = 0.0, mode: str = "paper"):
        self.policy = policy
        self.commission_per_order = commission_per_order
        self.mode = mode

    def run(self, bars: list[Bar], strategy: MovingAverageCrossoverStrategy) -> BacktestResult:
        if not bars:
            raise ValueError("bars cannot be empty")

        signals_by_timestamp = {signal.timestamp: signal for signal in strategy.generate_signals(bars)}
        symbol = bars[0].symbol
        cash = self.policy.initial_cash
        quantity = 0.0
        average_cost = 0.0
        stop_price: float | None = None
        realized_pnl = 0.0
        fills: list[Fill] = []
        equity_curve: list[tuple] = []

        for bar in bars:
            price = bar.close
            equity = cash + quantity * price

            if quantity > 0 and stop_price is not None and bar.low <= stop_price:
                cash, realized_pnl, fill = self._sell(
                    bar=bar,
                    price=stop_price,
                    cash=cash,
                    quantity=quantity,
                    average_cost=average_cost,
                    realized_pnl=realized_pnl,
                    strategy_name=strategy.name,
                    notes="protective stop",
                )
                fills.append(fill)
                quantity = 0.0
                average_cost = 0.0
                stop_price = None

            signal = signals_by_timestamp.get(bar.timestamp)
            if signal and signal.side == "buy" and quantity == 0:
                equity = cash
                planned_stop = price * (1 - self.policy.stop_loss_pct)
                quantity_to_buy = self.policy.position_quantity(equity, price, planned_stop)
                spendable_cash = max(0.0, cash - self.policy.min_cash_buffer(equity))
                if quantity_to_buy * price + self.commission_per_order > spendable_cash:
                    quantity_to_buy = max(0.0, (spendable_cash - self.commission_per_order) / price)
                if quantity_to_buy > 0:
                    cost = quantity_to_buy * price + self.commission_per_order
                    cash -= cost
                    quantity = quantity_to_buy
                    average_cost = price
                    stop_price = planned_stop
                    fills.append(
                        Fill(
                            timestamp=bar.timestamp,
                            symbol=bar.symbol,
                            side="buy",
                            quantity=quantity_to_buy,
                            price=price,
                            cash_after=cash,
                            strategy=strategy.name,
                            mode=self.mode,
                            notes=signal.reason,
                        )
                    )
            elif signal and signal.side == "sell" and quantity > 0:
                cash, realized_pnl, fill = self._sell(
                    bar=bar,
                    price=price,
                    cash=cash,
                    quantity=quantity,
                    average_cost=average_cost,
                    realized_pnl=realized_pnl,
                    strategy_name=strategy.name,
                    notes=signal.reason,
                )
                fills.append(fill)
                quantity = 0.0
                average_cost = 0.0
                stop_price = None

            equity_curve.append((bar.timestamp, cash + quantity * price))

        final_equity = cash + quantity * bars[-1].close
        metrics = self._metrics(
            initial_equity=self.policy.initial_cash,
            final_equity=final_equity,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_values=[equity for _, equity in equity_curve],
        )
        return BacktestResult(
            symbol=symbol,
            initial_equity=self.policy.initial_cash,
            final_equity=final_equity,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_curve=equity_curve,
            metrics=metrics,
        )

    def _sell(
        self,
        bar: Bar,
        price: float,
        cash: float,
        quantity: float,
        average_cost: float,
        realized_pnl: float,
        strategy_name: str,
        notes: str,
    ) -> tuple[float, float, Fill]:
        proceeds = quantity * price - self.commission_per_order
        trade_pnl = (price - average_cost) * quantity - self.commission_per_order
        cash += proceeds
        realized_pnl += trade_pnl
        fill = Fill(
            timestamp=bar.timestamp,
            symbol=bar.symbol,
            side="sell",
            quantity=quantity,
            price=price,
            cash_after=cash,
            realized_pnl=trade_pnl,
            strategy=strategy_name,
            mode=self.mode,
            notes=notes,
        )
        return cash, realized_pnl, fill

    @staticmethod
    def _metrics(
        initial_equity: float,
        final_equity: float,
        realized_pnl: float,
        fills: list[Fill],
        equity_values: list[float],
    ) -> dict[str, float | int | None]:
        sell_fills = [fill for fill in fills if fill.side == "sell"]
        wins = [fill for fill in sell_fills if fill.realized_pnl > 0]
        losses = [fill for fill in sell_fills if fill.realized_pnl < 0]
        gross_profit = sum(fill.realized_pnl for fill in wins)
        gross_loss = abs(sum(fill.realized_pnl for fill in losses))
        profit_factor = None if gross_loss == 0 else gross_profit / gross_loss
        total_return_pct = 0.0 if initial_equity == 0 else ((final_equity / initial_equity) - 1) * 100
        win_rate_pct = 0.0 if not sell_fills else (len(wins) / len(sell_fills)) * 100
        return {
            "total_return_pct": total_return_pct,
            "max_drawdown_pct": max_drawdown_pct(equity_values),
            "fills": len(fills),
            "closed_trades": len(sell_fills),
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
        }


class PairRulesBacktester:
    def __init__(
        self,
        policy: RiskPolicy,
        order_amount: float = 25.0,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.08,
        max_daily_notional: float = 100.0,
        max_monthly_realized_loss: float = 20.0,
        mode: str = "paper",
    ):
        self.policy = policy
        self.order_amount = order_amount
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_daily_notional = max_daily_notional
        self.max_monthly_realized_loss = max_monthly_realized_loss
        self.mode = mode

    def run(self, bars_by_symbol: dict[str, list[Bar]], strategy: SoxlSoxsRulesStrategy) -> BacktestResult:
        signals = strategy.generate_pair_signals(bars_by_symbol)
        bars_by_symbol_date = {
            symbol: {bar.timestamp.date(): bar for bar in bars}
            for symbol, bars in bars_by_symbol.items()
        }

        cash = self.policy.initial_cash
        position_symbol: str | None = None
        quantity = 0.0
        average_cost = 0.0
        realized_pnl = 0.0
        fills: list[Fill] = []
        equity_curve: list[tuple] = []
        daily_notional: dict = {}
        monthly_loss: dict = {}

        for signal in signals:
            trade_date = signal.timestamp.date()
            month_key = (trade_date.year, trade_date.month)
            daily_notional.setdefault(trade_date, 0.0)
            monthly_loss.setdefault(month_key, 0.0)

            current_bar = None
            if position_symbol is not None:
                current_bar = bars_by_symbol_date[position_symbol].get(trade_date)
            if position_symbol is not None and current_bar is not None:
                stop_price = average_cost * (1 - self.stop_loss_pct)
                take_profit_price = average_cost * (1 + self.take_profit_pct)
                exit_price: float | None = None
                exit_reason: str | None = None
                if current_bar.low <= stop_price:
                    exit_price = stop_price
                    exit_reason = "protective stop"
                elif current_bar.high >= take_profit_price:
                    exit_price = take_profit_price
                    exit_reason = "take profit"
                elif signal.target_symbol != position_symbol:
                    exit_price = current_bar.close
                    exit_reason = f"target changed to {signal.target_symbol or 'cash'}"

                if exit_price is not None and exit_reason is not None:
                    cash, realized_pnl, fill = self._sell(
                        bar=current_bar,
                        price=exit_price,
                        cash=cash,
                        quantity=quantity,
                        average_cost=average_cost,
                        realized_pnl=realized_pnl,
                        notes=exit_reason,
                    )
                    fills.append(fill)
                    if fill.realized_pnl < 0:
                        monthly_loss[month_key] += abs(fill.realized_pnl)
                    position_symbol = None
                    quantity = 0.0
                    average_cost = 0.0

            if position_symbol is None and signal.target_symbol is not None:
                if monthly_loss[month_key] >= self.max_monthly_realized_loss:
                    equity_curve.append((signal.timestamp, cash))
                    continue
                remaining_daily_notional = max(0.0, self.max_daily_notional - daily_notional[trade_date])
                order_amount = min(self.order_amount, remaining_daily_notional, cash - self.policy.min_cash_buffer(cash))
                if order_amount <= 0:
                    equity_curve.append((signal.timestamp, cash))
                    continue

                entry_bar = bars_by_symbol_date[signal.target_symbol].get(trade_date)
                if entry_bar is None or entry_bar.close <= 0:
                    equity_curve.append((signal.timestamp, cash))
                    continue
                quantity = order_amount / entry_bar.close
                cash -= order_amount
                average_cost = entry_bar.close
                position_symbol = signal.target_symbol
                daily_notional[trade_date] += order_amount
                fills.append(
                    Fill(
                        timestamp=signal.timestamp,
                        symbol=signal.target_symbol,
                        side="buy",
                        quantity=quantity,
                        price=entry_bar.close,
                        cash_after=cash,
                        strategy=strategy.name,
                        mode=self.mode,
                        notes=signal.reason,
                    )
                )

            equity = cash
            if position_symbol is not None:
                mark_bar = bars_by_symbol_date[position_symbol].get(trade_date)
                if mark_bar is not None:
                    equity += quantity * mark_bar.close
            equity_curve.append((signal.timestamp, equity))

        if position_symbol is not None and quantity > 0:
            last_bar = bars_by_symbol[position_symbol][-1]
            cash, realized_pnl, fill = self._sell(
                bar=last_bar,
                price=last_bar.close,
                cash=cash,
                quantity=quantity,
                average_cost=average_cost,
                realized_pnl=realized_pnl,
                notes="final close",
            )
            fills.append(fill)
            equity_curve.append((last_bar.timestamp, cash))

        final_equity = cash
        metrics = Backtester._metrics(
            initial_equity=self.policy.initial_cash,
            final_equity=final_equity,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_values=[equity for _, equity in equity_curve],
        )
        metrics["signal_days"] = len(signals)
        metrics["order_amount"] = self.order_amount
        metrics["stop_loss_pct"] = self.stop_loss_pct * 100
        metrics["take_profit_pct"] = self.take_profit_pct * 100
        return BacktestResult(
            symbol="SOXL/SOXS",
            initial_equity=self.policy.initial_cash,
            final_equity=final_equity,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_curve=equity_curve,
            metrics=metrics,
        )

    def _sell(
        self,
        bar: Bar,
        price: float,
        cash: float,
        quantity: float,
        average_cost: float,
        realized_pnl: float,
        notes: str,
    ) -> tuple[float, float, Fill]:
        proceeds = quantity * price
        trade_pnl = (price - average_cost) * quantity
        cash += proceeds
        realized_pnl += trade_pnl
        return (
            cash,
            realized_pnl,
            Fill(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                side="sell",
                quantity=quantity,
                price=price,
                cash_after=cash,
                realized_pnl=trade_pnl,
                strategy="soxl_soxs_rules",
                mode=self.mode,
                notes=notes,
            ),
        )


class AggressiveDayTradeBacktester:
    def __init__(
        self,
        policy: RiskPolicy,
        order_amount: float = 100.0,
        stop_loss_pct: float = 0.03,
        take_profit_pct: float = 0.06,
        max_daily_notional: float = 100.0,
        max_monthly_realized_loss: float = 20.0,
        mode: str = "paper",
    ):
        self.policy = policy
        self.order_amount = order_amount
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_daily_notional = max_daily_notional
        self.max_monthly_realized_loss = max_monthly_realized_loss
        self.mode = mode

    def run(
        self,
        bars_by_symbol: dict[str, list[Bar]],
        strategy: AggressiveSoxlSoxsDayTradeStrategy,
    ) -> BacktestResult:
        signals = strategy.generate_pair_signals(bars_by_symbol)
        bars_by_symbol_date = {
            symbol: {bar.timestamp.date(): bar for bar in bars}
            for symbol, bars in bars_by_symbol.items()
        }

        cash = self.policy.initial_cash
        realized_pnl = 0.0
        fills: list[Fill] = []
        equity_curve: list[tuple] = []
        daily_notional: dict = {}
        monthly_loss: dict = {}
        skipped_by_monthly_loss = 0

        for signal in signals:
            trade_date = signal.timestamp.date()
            month_key = (trade_date.year, trade_date.month)
            daily_notional.setdefault(trade_date, 0.0)
            monthly_loss.setdefault(month_key, 0.0)

            if signal.target_symbol is None:
                equity_curve.append((signal.timestamp, cash))
                continue
            if monthly_loss[month_key] >= self.max_monthly_realized_loss:
                skipped_by_monthly_loss += 1
                equity_curve.append((signal.timestamp, cash))
                continue

            bar = bars_by_symbol_date[signal.target_symbol].get(trade_date)
            if bar is None or bar.open <= 0:
                equity_curve.append((signal.timestamp, cash))
                continue

            spendable_cash = max(0.0, cash - self.policy.min_cash_buffer(cash))
            remaining_daily_notional = max(0.0, self.max_daily_notional - daily_notional[trade_date])
            order_amount = min(self.order_amount, spendable_cash, remaining_daily_notional)
            if order_amount <= 0:
                equity_curve.append((signal.timestamp, cash))
                continue

            quantity = order_amount / bar.open
            cash -= order_amount
            daily_notional[trade_date] += order_amount
            fills.append(
                Fill(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    side="buy",
                    quantity=quantity,
                    price=bar.open,
                    cash_after=cash,
                    strategy=strategy.name,
                    mode=self.mode,
                    notes=signal.reason,
                )
            )

            exit_price, exit_reason = self._same_day_exit(bar)
            proceeds = quantity * exit_price
            trade_pnl = (exit_price - bar.open) * quantity
            cash += proceeds
            realized_pnl += trade_pnl
            if trade_pnl < 0:
                monthly_loss[month_key] += abs(trade_pnl)
            fills.append(
                Fill(
                    timestamp=bar.timestamp,
                    symbol=bar.symbol,
                    side="sell",
                    quantity=quantity,
                    price=exit_price,
                    cash_after=cash,
                    realized_pnl=trade_pnl,
                    strategy=strategy.name,
                    mode=self.mode,
                    notes=exit_reason,
                )
            )
            equity_curve.append((signal.timestamp, cash))

        metrics = Backtester._metrics(
            initial_equity=self.policy.initial_cash,
            final_equity=cash,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_values=[equity for _, equity in equity_curve],
        )
        metrics["signal_days"] = len(signals)
        metrics["day_trades"] = len([fill for fill in fills if fill.side == "sell"])
        metrics["order_amount"] = self.order_amount
        metrics["stop_loss_pct"] = self.stop_loss_pct * 100
        metrics["take_profit_pct"] = self.take_profit_pct * 100
        metrics["skipped_by_monthly_loss"] = skipped_by_monthly_loss
        return BacktestResult(
            symbol="SOXL/SOXS DAY",
            initial_equity=self.policy.initial_cash,
            final_equity=cash,
            realized_pnl=realized_pnl,
            fills=fills,
            equity_curve=equity_curve,
            metrics=metrics,
        )

    def _same_day_exit(self, bar: Bar) -> tuple[float, str]:
        stop_price = bar.open * (1 - self.stop_loss_pct)
        take_profit_price = bar.open * (1 + self.take_profit_pct)
        hit_stop = bar.low <= stop_price
        hit_take_profit = bar.high >= take_profit_price
        if hit_stop:
            return stop_price, "same-day protective stop"
        if hit_take_profit:
            return take_profit_price, "same-day take profit"
        return bar.close, "same-day close"
