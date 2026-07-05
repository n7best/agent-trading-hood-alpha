# Data

`sample_prices.csv` is synthetic SPY-like daily data for local backtest smoke tests only.

Current trading quote snapshots should come from the Robinhood trading MCP and be written to `data/live_quotes/latest.json`. Files in `data/live_quotes/*.json` are ignored because they become stale quickly.
