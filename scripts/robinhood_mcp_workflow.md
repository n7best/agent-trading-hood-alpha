# Robinhood MCP Workflow

Use this workflow for current market data and any future live trading path.

## Session Boundary

Use a new Codex trading session for each Eastern trading date. The session must not rely on prior chat context for broker state, daily notional, monthly realized-loss usage, authorization, premarket risk mode, or open-order status.

At the start of each session, rebuild state from Robinhood MCP tools and repo artifacts:

1. Live account, portfolio, positions, orders, quotes, and tradability.
2. `config/trading.toml`.
3. Current-date `reports/premarket/latest.md`.
4. Same-day SOXL/SOXS orders.
5. Same-month realized SOXL/SOXS order history.

## Market Data

1. Fetch current quotes with `mcp__robinhood_trading.get_equity_quotes`.
2. Save the raw JSON response to `data/live_quotes/latest.json`.
3. Run:

```bash
python -m tradebot quote --symbol SPY
python -m tradebot live-plan --symbol SPY
```

## Execution Gate

The repo should not place orders directly.

Before any real equity order:

1. Resolve the brokerage account with `get_accounts` only when the user asks to trade.
2. Check tradability with `get_equity_tradability`.
3. Review the exact proposed order with `review_equity_order`.
4. Present alerts, estimated cost, and order details.
5. Call `place_equity_order` only after explicit confirmation.
