from __future__ import annotations


def simple_moving_average(values: list[float], window: int) -> list[float | None]:
    if window <= 0:
        raise ValueError("window must be positive")
    averages: list[float | None] = []
    running_total = 0.0
    for index, value in enumerate(values):
        running_total += value
        if index >= window:
            running_total -= values[index - window]
        if index + 1 < window:
            averages.append(None)
        else:
            averages.append(running_total / window)
    return averages


def max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak <= 0:
            continue
        drawdown = (peak - equity) / peak
        max_drawdown = max(max_drawdown, drawdown)
    return max_drawdown * 100

