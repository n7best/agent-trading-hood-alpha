# Daily Trading Routine

1. Start a new Codex trading session for the current Eastern trading date.
2. Reconstruct state only from Robinhood live data, `config/trading.toml`, current-date reports, same-day orders, same-month realized SOXL/SOXS order history, and journal files.
3. Check economic calendar and major market-moving events.
4. Run `python -m tradebot plan`.
5. Run the latest strategy backtest before market open.
6. Generate a current-date premarket plan and verify `reports/premarket/latest.md` is for today.
7. Define the maximum number of trades for the day.
8. Write the planned setup, invalidation level, and position size before entry.
9. Stop for the day if the daily stop amount is hit.
10. Export or record fills into the journal.
11. Review mistakes, missed rules, and emotional deviations after market close.
12. End the day's live-monitor session after flat/open-order checks and daily review; do not carry the same chat session into the next trading day.
