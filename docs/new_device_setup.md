# New Device Setup

Use this guide to initialize an always-running Mac for the Codex SOXL/SOXS workflow.

## Source Of Truth

`origin/main` is the instruction source of truth for this repo. Before every manual run or scheduled automation run:

```bash
git pull --ff-only origin main
```

If the pull fails because local files changed, stop before any market or broker action. Resolve the local state first. Future edits to workflow instructions, schedules, authorization notes, or setup docs must be committed and pushed to `origin/main` before any run relies on them.

After pulling, read the active instructions in this order:

1. `README.md`
2. `docs/new_device_setup.md`
3. `docs/live_automation.md`
4. `scripts/daily_routine.md`
5. `scripts/robinhood_mcp_workflow.md`
6. `docs/soxl_soxs_rules.md`
7. `config/trading.toml`

Do not commit `.env`, `data/live_quotes/*.json`, generated report markdown, Python caches, or `.DS_Store` files.

## Bootstrap

Clone and prepare the project:

```bash
git clone https://github.com/n7best/agent-trading-hood-alpha.git
cd agent-trading-hood-alpha
git pull --ff-only origin main
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[market-data,dev]'
python -m unittest discover -s tests
```

Create local environment settings only on the device:

```bash
cp .env.example .env
```

Keep `TRADING_MODE=paper` unless a live path is explicitly requested and verified. Fill `TRADING_ACCOUNT_NUMBER` only in `.env`; never commit it.

## Codex And Robinhood MCP

Install or sign in to Codex on the always-running Mac, then configure the Robinhood Trading MCP server:

```bash
codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading
codex -c service_tier="fast" mcp login robinhood-trading
codex -c service_tier="fast" mcp list
```

The `service_tier="fast"` override is a known workaround when a local Codex config rejects `service_tier = "priority"`.

## Available Tools

Repo CLI tools:

- `python -m tradebot check`
- `python -m tradebot plan`
- `python -m tradebot backtest`
- `python -m tradebot quote`
- `python -m tradebot live-plan`
- `python -m tradebot authorization`
- `python -m tradebot authorize-intent`
- `python -m tradebot save-mcp-quotes`
- `python -m tradebot journal-summary`
- `python -m tradebot download-data`
- `python -m tradebot import-nasdaq-history`
- `python -m tradebot backtest-pair`
- `python -m tradebot backtest-daytrade`
- `python -m tradebot daily-review`
- `python -m tradebot premarket-plan`
- `python -m tradebot tune-daytrade`

Robinhood MCP read-only tools available to Codex include account discovery, portfolio, positions, orders, tradability, quotes, fundamentals, realized P/L, earnings, instrument search, market indexes, option chains, option contracts, option quotes, option positions, watchlists, scans, and scan execution.

Robinhood MCP review or write tools available to Codex include equity order review/place/cancel, option order review/place/cancel, watchlist edits, option watchlist edits, and scan creation or updates. This repo's standing automation scope is narrower: SOXL/SOXS equity trading only, no options, no short selling, no watchlist or scan writes unless the user explicitly expands scope.

Codex app tools used by this workflow include recurring automations and thread management. Git/GitHub are used to pull current instructions before runs and push instruction updates after they are made.

## Scheduled Setup

Create or update these Codex automations on the always-running Mac:

- `SOXL/SOXS premarket plan`: 8:45 AM ET on market weekdays. Local cron automation in the repo. It must pull `origin/main`, read the active instructions, fetch the configured Robinhood quote basket, write `data/live_quotes/latest.json`, run `python -m tradebot premarket-plan --quote-input data/live_quotes/latest.json --write-report`, and summarize the plan without placing, reviewing, or cancelling orders.
- `SOXL/SOXS market monitor`: starts at 9:30 AM ET on market weekdays, then adapts to 5, 10, or 15 minutes from exposure and risk mode. It must pull `origin/main` before each run, use the current Eastern trading date, rebuild broker state from live MCP data, enforce `config/trading.toml`, and keep a 5-minute cadence whenever a SOXL/SOXS position or open order exists.
- `SOXL/SOXS trading rules check`: 9:35 AM ET on market weekdays. It must pull `origin/main`, read the current instructions, refresh quote/account/order/tradability context, evaluate the configured rules, and trade only if every standing authorization and exit-management gate passes.
- `SOXL/SOXS daily review`: 4:30 PM ET on market weekdays. It must pull `origin/main`, read the current instructions, refresh SOXL/SOXS context when available, run the daily review and tuning commands, and avoid all live broker review/place/cancel actions.

All schedules use `America/New_York` as the market-date authority. If UTC and Eastern dates differ, use the Eastern date for market-session labels, same-day order checks, daily notional, and authorization expiration.

## First-Run Verification

Run these before trusting the new device:

```bash
git status --short --branch
python -m unittest discover -s tests
python -m tradebot check
python -m tradebot authorization
python -m tradebot premarket-plan --symbols
```

Then verify the Robinhood MCP connection in Codex with read-only account and quote checks before any trade-capable automation is enabled.
