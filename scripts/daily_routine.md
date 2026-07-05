# Daily Trading Routine

1. Run `git pull --ff-only origin main` before any market or broker action. If it fails, stop and resolve the repo state first.
2. Read the current instructions: `README.md`, `docs/new_device_setup.md`, `docs/live_automation.md`, this file, `scripts/robinhood_mcp_workflow.md`, `docs/soxl_soxs_rules.md`, and `config/trading.toml`.
3. Start a new Codex trading session for the current Eastern trading date.
4. Reconstruct state only from Robinhood live data, `config/trading.toml`, current-date reports, same-day orders, same-month realized SOXL/SOXS order history, and journal files.
5. Check economic calendar and major market-moving events.
6. Run `python -m tradebot plan`.
7. Run the latest strategy backtest before market open.
8. Generate a current-date premarket plan and verify `reports/premarket/latest.md` is for today.
9. Define the maximum number of trades for the day.
10. Write the planned setup, invalidation level, and position size before entry.
11. Stop for the day if the daily stop amount is hit.
12. Export or record fills into the journal.
13. Review mistakes, missed rules, and emotional deviations after market close.
14. Commit and push any instruction, schedule, setup, or authorization-guidance changes to `origin/main` before relying on them in future runs.
15. End the day's live-monitor session after flat/open-order checks and daily review; do not carry the same chat session into the next trading day.
