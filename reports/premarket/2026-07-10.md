# Premarket SOXL/SOXS Plan - 2026-07-10

## Snapshot

- Live execution: disabled inside this report
- Purpose: establish market/sector context before the adaptive monitor runs
- Bias: bearish-semiconductors
- Risk mode: normal
- Planned monitor cadence: 5 minutes
- Allowed opening symbols from plan: SOXS
- Rationale: SOXL is down materially and market or semiconductor confirmation is negative.

## Quote Basket

### Trading ETFs

- SOXL: $187.76 (-2.44% vs previous close, as of 2026-07-10T14:09:59.128646+00:00, state=active)
- SOXS: $4.16 (2.09% vs previous close, as of 2026-07-10T14:09:59.557295+00:00, state=active)

### Market ETFs

- SPY: $753.09 (0.18% vs previous close, as of 2026-07-10T14:10:01.559928+00:00, state=active)
- QQQ: $723.71 (0.06% vs previous close, as of 2026-07-10T14:10:00.910759+00:00, state=active)
- IWM: $295.94 (-0.44% vs previous close, as of 2026-07-10T14:10:00.493342+00:00, state=active)
- DIA: $524.53 (0.06% vs previous close, as of 2026-07-10T14:10:00.215017+00:00, state=active)

### Semiconductor Context

- SMH: $606.13 (-0.26% vs previous close, as of 2026-07-10T14:10:00.059605+00:00, state=active)
- SOXX: $577.50 (-0.72% vs previous close, as of 2026-07-10T14:10:01.076395+00:00, state=active)
- NVDA: $207.10 (2.13% vs previous close, as of 2026-07-10T14:10:00.712993+00:00, state=active)
- AMD: $552.42 (1.04% vs previous close, as of 2026-07-10T14:10:00.123501+00:00, state=active)
- AVGO: $400.22 (-0.22% vs previous close, as of 2026-07-10T14:10:01.301304+00:00, state=active)
- MU: $980.99 (-1.07% vs previous close, as of 2026-07-10T14:10:01.183246+00:00, state=active)
- TSM: $434.73 (-0.51% vs previous close, as of 2026-07-10T14:09:59.922960+00:00, state=active)

## Monitor Instructions

- The monitor must still enforce standing authorization, account state, buying power, order state, daily notional, and monthly realized-loss caps.
- Do not place orders outside regular hours.
- Do not open a new SOXL/SOXS position when a SOXL/SOXS position or open SOXL/SOXS order already exists.
- If risk mode is blocked, skip all new opening buys until a later plan or live risk check clears the block.
- If risk mode is defensive, skip opening buys unless regular-hours quotes meet the defensive live momentum threshold and all broker/account/order/exit checks are fresh.
- When daytrade_strategy.require_fresh_history_for_live_entries is false, stale daily CSV history must not block live entries that are confirmed by fresh Robinhood quotes and a current-date plan.
- If allowed opening symbols lists only one ETF, block opposite-direction opening buys for this session unless a later premarket or manual review updates the plan.
- If a SOXL/SOXS position is open, use 5-minute cadence for exit monitoring regardless of the premarket cadence.
