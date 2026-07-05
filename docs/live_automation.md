# Live Automation

Current automations:

- `SOXL/SOXS premarket plan`: runs at 8:45 AM ET on market weekdays and writes the session setup.
- `SOXL/SOXS adaptive trade monitor`: starts at the 9:30 AM ET regular-session open on market weekdays, then runs every 5, 10, or 15 minutes during regular hours based on exposure and premarket risk mode.
- `SOXL/SOXS trading rules check`: paused detached local cron, scheduled for 9:35 AM ET on market weekdays.
- `SOXL/SOXS daily review`: runs at 4:30 PM ET on market weekdays in the current thread.

Automation schedules and trading-date checks use America/New_York market time. If UTC and Eastern dates differ, use the Eastern market date for same-day orders, daily notional, and authorization expiry.

## Instruction And Git Sync

Before every scheduled automation run, pull the latest repo instructions:

```bash
git pull --ff-only origin main
```

If the pull fails, the automation must stop before any market or broker action and report the local state that blocked synchronization. After a successful pull, read `README.md`, `docs/new_device_setup.md`, this file, `scripts/daily_routine.md`, `scripts/robinhood_mcp_workflow.md`, `docs/soxl_soxs_rules.md`, and `config/trading.toml`.

Any future edit to workflow instructions, schedules, setup docs, or authorization guidance must be committed and pushed to `origin/main` before a scheduled run relies on it. Generated reports and quote snapshots should remain local unless the user explicitly asks to publish them.

## Daily Session Boundary

Start a new Codex trading session for each Eastern trading date. Do not keep the same live-monitor conversation running across multiple trading days. Name the session with the Eastern market date and trading purpose:

```text
YYYY-MM-DD SOXL/SOXS trading session
```

For example, the June 29, 2026 regular-session monitor belongs in `2026-06-29 SOXL/SOXS trading session`. If the live monitor wakes up in a thread whose title or session date does not match the current Eastern trading date, it must not place live orders in that stale thread. It should create or retarget to the current date's trading-session thread before running broker checks.

The new session must reconstruct state from durable sources only:

- Robinhood live account, position, order, portfolio, quote, and tradability data.
- `config/trading.toml`.
- Current-date `reports/premarket/latest.md`.
- Same-month realized SOXL/SOXS order history.
- Same-day generated reports and journal files.

Prior chat context is not authoritative for daily notional, open orders, positions, realized-loss usage, premarket risk mode, or authorization. If the current-date premarket report is missing or stale in the new session, the monitor must notify during regular hours and either use the configured stale-plan live fallback or skip opening entries.

## Trading Capability

The adaptive monitor is trade-capable only inside the standing authorization in `config/trading.toml`.

It may place a live order only when all of these are true:

- The configured strategy produces a current eligible intent.
- The market session is regular hours.
- Robinhood quotes are fresh, active, and traded.
- The Agentic account is active and has enough buying power.
- Tradability checks pass for the target symbol.
- No conflicting SOXL/SOXS position exists.
- Daily notional, monthly loss, symbol, session, and expiration limits pass.
- A same-day exit path is executable for the exact shares to be traded.

## Adaptive Monitor

The monitor checks the live account, open orders, positions, tradability, and SOXL/SOXS quotes on each wake-up. It should use marketable limit orders for entries and sell-to-close exits.

The live entry rule is not restricted to the market open. During regular hours, the monitor may evaluate an entry whenever the current SOXL session move, current-date premarket direction, live broker/account checks, and authorization checks pass.

Daily CSV history is a backtest and daily-review input. With `daytrade_strategy.require_fresh_history_for_live_entries = false`, stale daily CSV history must not block a live entry that is confirmed by fresh Robinhood quotes and a current-date premarket plan. Stale or unavailable live broker/account/order/authorization/exit-management data still blocks trading.

The monitor should read `reports/premarket/latest.md` when available. That file may restrict opening symbols, set the session risk mode, and request a slower monitor cadence when there is no open SOXL/SOXS position or order. It must never loosen the hard authorization caps in `config/trading.toml`.

If `reports/premarket/latest.md` is stale and `daytrade_strategy.allow_stale_plan_live_fallback = true`, the monitor may use live quote-only fallback during regular hours instead of silently blocking all entries. This fallback is only allowed when fresh SOXL/SOXS quotes show `abs(SOXL session move)` at or above `daytrade_strategy.stale_plan_min_session_move_pct`, the move remains inside `max_session_move_pct`, and all live account, order, position, authorization, monthly-loss, tradability, and exit-management checks pass. A stale-plan fallback must be reported explicitly in the monitor summary.

Cadence rules:

- Use 5 minutes whenever a SOXL/SOXS position or open SOXL/SOXS order exists.
- Use 5 minutes for `normal` premarket risk mode.
- Use 10 minutes for `watch` or `defensive` premarket risk mode when there is no SOXL/SOXS position/order.
- Use 15 minutes for `blocked` premarket risk mode when there is no SOXL/SOXS position/order.

The exposed Robinhood MCP tools support limit and stop-style orders, but they do not expose a safe unattended bracket or OCO workflow. The cancel tool also requires current user confirmation. Because of that, the monitor must not place paired stop and take-profit orders that rely on automatic cancellation of the unused leg.

For live entries, the monitor must be able to manage exits with 5-minute checks whenever a SOXL/SOXS position or open SOXL/SOXS order exists. If a SOXL/SOXS position is open, it should compare the live quote against the strategy stop, take-profit, runner, reversal, risk cap, and end-of-day exit conditions, then place only an allowed sell-to-close order when an exit condition is met. If quotes, positions, orders, authorization, or exit management are unavailable, it should not trade.

When `daytrade_strategy.runner_enabled = true`, the monitor should manage exits in two stages instead of using a symmetric full-position take-profit. First, sell `initial_exit_fraction` of the current sellable position when the live quote reaches `initial_take_profit_pct` above the average entry price. After that scale-out is filled, manage the remaining runner with `runner_stop_loss_pct` relative to average entry price, `runner_take_profit_pct`, and `runner_trailing_stop_pct`. The configured `runner_stop_loss_pct = 0.0` means the runner stop is breakeven after the initial profit is taken. The monitor must rebuild partial-exit state from same-day filled SOXL/SOXS sell orders and current sellable shares before placing any runner order, so it never double-sells or treats a stale chat summary as position state.

## Current Constraint

SOXL is allowed up to the `$300` max buy order size, but the aggressive day-trade strategy now uses `$100` default entry tranches with a `3%` protective stop and an `8%` full-position fallback take-profit. Runner mode is enabled: sell `50%` of the sellable position at `+3%`, then manage the remaining runner with a breakeven stop, an `8%` target, and a `2%` trailing stop. The hard `$300` daily notional cap remains in force, so the default sizing permits up to three opening attempts per day.

Live entries use `premarket_confirmed_momentum`: the current-date premarket plan decides which ETF direction is allowed, and the live SOXL session move decides whether momentum is strong enough. `normal` and `watch` mode use the configured `0.25%` threshold; `defensive` mode requires the configured `2.0%` threshold. If the plan is stale and fallback is enabled, the fallback threshold is the stricter configured `4.0%` live SOXL session move.

The automation should prefer marketable limit entries when the tranche can be expressed as shares. For fractional SOXL tranches, it may use regular-hours market/dollar orders only when live quotes, buying power, exact sellable shares, and the same-day exit path are fresh and available. It must still enforce same-day exits and no short selling.

## Premarket Plan

The premarket run should refresh a broad quote basket before the open:

- Trading ETFs: `SOXL`, `SOXS`
- Market ETFs: `SPY`, `QQQ`, `IWM`, `DIA`
- Semiconductor context: `SMH`, `SOXX`, `NVDA`, `AMD`, `AVGO`, `MU`, `TSM`

It should run `python -m tradebot premarket-plan --write-report` after saving the quote snapshot. The command writes both a dated report and `reports/premarket/latest.md`.

The plan classifies the session into:

- `normal`: directional confirmation is strong enough to keep the active monitor at 5 minutes.
- `watch`: mixed conditions; use live momentum confirmation and a 10-minute cadence when no position/order exists.
- `defensive`: large or mixed movement; avoid opening buys unless the live SOXL session move clears the defensive threshold in the plan's allowed direction.
- `blocked`: missing required quotes or SOXL session move exceeds the configured max; skip all opening buys until a later plan or manual review clears it.
