# SOXL/SOXS Rules

These rules are for the Agentic account authorization in `config/trading.toml`.

## Universe

- Symbols: `SOXL`, `SOXS`.
- Order type: equities only.
- Time in force: `GFD`.
- Sessions: `regular_hours` and `extended_hours`.
- No options.
- No short selling.
- One open SOXL/SOXS position at a time.

## Entry Rules

Use SOXL as the trend reference.

- Buy `SOXL` when SOXL `SMA(5) > SMA(20)` and SOXL daily close-to-close return is at least `+0.5%`.
- Buy `SOXS` when SOXL `SMA(5) < SMA(20)` and SOXL daily close-to-close return is at most `-0.5%`.
- Skip new entries when `abs(SOXL daily return) > 8%`.
- Skip when the target is unchanged and a position is already open.

## Size Rules

- Default order size: `$25`.
- Max buy order size: `$300`.
- Max daily notional: `$300`.
- Max monthly realized loss: `$100`.
- Extended-hours dollar orders are blocked; extended-hours orders need share quantity and notional validation.

## Exit Rules

- Protective stop: `5%` below entry.
- Take profit: `8%` above entry.
- Exit at close when the target changes to the opposite ETF or to cash.
- Force-close any remaining backtest position on the final bar.

## Backtest Command

```bash
python -m tradebot backtest-pair \
  --soxl-data data/history/soxl.csv \
  --soxs-data data/history/soxs.csv
```

## Aggressive Day-Trade Rules

These rules are for the adaptive live monitor. The live monitor and daily-history backtest proxy intentionally use different data gates:

- Live monitor: uses fresh Robinhood SOXL/SOXS quotes, the current-date premarket plan, live account/order/position state, and the standing authorization.
- Daily backtest proxy: uses daily OHLC bars, prior SMA, and prior-return filters as a coarse same-day proxy until intraday bars are available.
- When `require_fresh_history_for_live_entries = false`, stale daily CSV history must not block a live entry that is confirmed by fresh Robinhood quotes and the current-date premarket plan.

- Evaluate entries during regular hours on each active monitor check.
- Exit the same day on stop, take-profit, or close.
- If the daily range touches both stop and take-profit, assume the stop happened first.
- In `normal` or `watch` risk mode, buy `SOXL` when the current-date plan allows `SOXL` and the live SOXL session move versus official prior close is at least `+0.25%`.
- In `normal` or `watch` risk mode, buy `SOXS` when the current-date plan allows `SOXS` and the live SOXL session move versus official prior close is at most `-0.25%`.
- In `defensive` risk mode, require the same directional plan permission plus a stronger live SOXL session move of at least `2.0%`.
- In `blocked` risk mode, skip opening buys.
- In stale-plan risk mode, skip opening buys unless `allow_stale_plan_live_fallback = true`, fresh Robinhood quotes show `abs(SOXL session move) >= 4.0%`, the move remains below the max-session-move cap, and all broker/account/order/authorization/monthly-loss/tradability/exit checks pass.
- Skip when `abs(SOXL session move) > 18%`.
- Order size: `$100`, allowing multiple attempts while staying under the daily cap.
- Protective stop: `3%`.
- Initial runner take profit: exit `50%` at `3%`.
- Runner stop: move remaining shares to breakeven after the initial take-profit fill.
- Final runner target: `8%`.
- Runner trailing stop: `2%`.
- Daily notional cap: `$300`, so the default sizing permits up to three opening attempts per day.
- Monthly realized loss cap: `$100`.

Run it:

```bash
python -m tradebot backtest-daytrade \
  --soxl-data data/history/soxl.csv \
  --soxs-data data/history/soxs.csv
```

## Live Authorization Note

The standing authorization allows sell-to-close for `SOXL` and `SOXS`. It still blocks short selling, so sells must not exceed currently sellable shares.
