# Trades

Paper-first trading toolkit for a small account starting at `$500`.

The stated monthly survival target is `$100`, which is a `20%` monthly return on `$500`. That is an aggressive target with a high probability of drawdowns or total loss if pursued with oversized positions. This repo is set up to measure, constrain, and journal trading decisions before any live execution.

## What Is Included

- Configurable account, target, risk, data, and strategy settings in `config/trading.toml`.
- Robinhood trading MCP quote parser for live equity market data snapshots.
- CSV historical-data loader plus an optional `yfinance` downloader for backtests.
- Moving-average crossover strategy for baseline testing.
- Risk policy with position sizing, cash buffer, per-trade risk, daily loss, and monthly loss limits.
- Backtest engine with fills, equity curve, drawdown, win rate, and profit factor.
- Trade journal helpers.
- CLI commands for checking the account plan, reading MCP quotes, sizing live plans, backtesting, downloading historical data, and summarizing the journal.
- Unit tests that run without external services.

## Quick Start

Run the account and risk plan:

```bash
python -m tradebot plan
```

Read the latest Robinhood MCP quote snapshot:

```bash
python -m tradebot quote --symbol SPY
```

Size a paper/live-plan candidate from that quote:

```bash
python -m tradebot live-plan --symbol SPY
```

Run the historical sample backtest:

```bash
python -m tradebot backtest --symbol SPY
```

Write backtest fills into the journal:

```bash
python -m tradebot backtest --symbol SPY --write-journal
python -m tradebot journal-summary
```

Run tests:

```bash
python -m unittest discover -s tests
```

## Optional Setup

Create a virtual environment if you want installed scripts and optional historical-data packages:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[market-data,dev]'
```

Download recent historical CSV data after installing `yfinance`:

```bash
python -m tradebot download-data --symbol SPY --period 1y --output data/spy.csv
python -m tradebot backtest --symbol SPY --data data/spy.csv
```

## Robinhood MCP Market Data

The configured current-data source is `robinhood_mcp`, with raw quote snapshots expected at `data/live_quotes/latest.json`.

Operational workflow:

1. Use the Robinhood trading MCP tool `get_equity_quotes` for the configured symbol list.
2. Save the raw MCP JSON response to `data/live_quotes/latest.json`.
3. Run `python -m tradebot quote --symbol SPY`.
4. Run `python -m tradebot live-plan --symbol SPY` to size the position from the live quote and configured risk policy.
5. Before any real order, use Robinhood MCP `review_equity_order`; only call `place_equity_order` after explicit confirmation.

The quote command warns when the snapshot is stale, when the instrument state is not active, or when the instrument has not traded.

## Standing Authorization

The current standing authorization is encoded in `config/trading.toml` under `[authorization]`.

It allows only:

- Agentic account ending `6375`.
- `SOXL` and `SOXS`.
- Regular-hours or extended-hours equity orders.
- `GFD` orders.
- Buy orders up to `$300` each.
- Sells only to close existing `SOXL` or `SOXS` positions.
- Up to `100` new buy entries per day, still capped by `$300` total daily notional.
- `$100` maximum monthly realized loss.
- No options and no short selling.
- No configured expiration date; if `expires_on` is added later, it is enforced.

Validate the policy:

```bash
python -m tradebot authorization
```

Validate a proposed order:

```bash
python -m tradebot authorize-intent \
  --account-number "$TRADING_ACCOUNT_NUMBER" \
  --symbol SOXL \
  --side buy \
  --dollar-amount 25 \
  --market-hours regular_hours
```

Important Robinhood constraint: dollar-based orders are valid only in `regular_hours`. Extended-hours orders need share quantity plus an estimated price so the notional can be checked.

## SOXL/SOXS Rules Backtest

The trading rules are documented in `docs/soxl_soxs_rules.md` and configured under `[pair_strategy]`.

Convert Nasdaq historical JSON:

```bash
python -m tradebot import-nasdaq-history --symbol SOXL --input data/raw/soxl_nasdaq_1y.json --output data/history/soxl.csv
python -m tradebot import-nasdaq-history --symbol SOXS --input data/raw/soxs_nasdaq_1y.json --output data/history/soxs.csv
```

Run the rules backtest:

```bash
python -m tradebot backtest-pair --soxl-data data/history/soxl.csv --soxs-data data/history/soxs.csv
```

Run the aggressive day-trade proxy backtest:

```bash
python -m tradebot backtest-daytrade --soxl-data data/history/soxl.csv --soxs-data data/history/soxs.csv
```

The live day-trade monitor checks on an adaptive 5, 10, or 15 minute cadence during regular hours and is not limited to the market open. Live entries use fresh Robinhood SOXL/SOXS quotes plus the current-date premarket plan; with `require_fresh_history_for_live_entries = false`, stale daily CSV history does not block quote-confirmed live momentum entries. With `allow_stale_plan_live_fallback = true`, a stale premarket plan may fall back to fresh quote-only momentum only when the stricter fallback move threshold is met and all broker/account/order/authorization/monthly-loss/tradability/exit checks pass. The current aggressive day-trade profile uses a `3%` protective stop, an `8%` full-position fallback take-profit, and runner mode: sell half at `+3%`, protect the remaining runner at breakeven, target `+8%`, and trail by `2%`. The daily-history backtest still uses daily OHLC as a coarse same-day proxy until intraday bars are available.

Generate the premarket session plan after refreshing the Robinhood MCP quote basket:

```bash
python -m tradebot premarket-plan --symbols
python -m tradebot premarket-plan --write-report
```

The premarket plan writes `reports/premarket/latest.md`. The adaptive monitor uses that plan to apply the session bias, risk mode, and cadence guidance without loosening the hard authorization caps.

Start a fresh Codex trading session for each Eastern trading date, named `YYYY-MM-DD SOXL/SOXS trading session` using the America/New_York market date. The monitor must rebuild state from Robinhood live data and repo artifacts instead of relying on prior chat context; this keeps daily notional, order state, risk mode, and authorization checks from being polluted by a long-running conversation.

## Operating Rules

Use this as the minimum checklist before any live trade path:

1. Paper trade the strategy for at least 20 market sessions.
2. Backtest across multiple symbols and market regimes.
3. Keep max risk per trade at or below the configured `1%` of equity.
4. Stop trading for the day after the configured daily loss limit.
5. Stop trading for the month after the configured monthly loss limit.
6. Record every entry, exit, reason, and deviation in the journal.
7. Do not enable live mode unless the MCP quote, order-review payload, order size, and stop have been separately verified.

## Live Trading Guard

The code defaults to `paper`. Any future live order path should require `TRADING_LIVE_ACK=I_UNDERSTAND_LIVE_TRADING_RISK`. This is intentional friction so a config typo does not place real orders. The repository does not call `place_equity_order` itself.
