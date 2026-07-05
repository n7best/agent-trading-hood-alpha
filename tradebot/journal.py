from __future__ import annotations

import csv
from pathlib import Path

from .models import Fill


FIELDNAMES = [
    "timestamp",
    "symbol",
    "side",
    "quantity",
    "price",
    "cash_after",
    "realized_pnl",
    "strategy",
    "mode",
    "notes",
]


class TradeJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append_fills(self, fills: list[Fill]) -> None:
        if not fills:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        should_write_header = not self.path.exists()
        with self.path.open("a", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            if should_write_header:
                writer.writeheader()
            for fill in fills:
                writer.writerow(
                    {
                        "timestamp": fill.timestamp.isoformat(),
                        "symbol": fill.symbol,
                        "side": fill.side,
                        "quantity": f"{fill.quantity:.6f}",
                        "price": f"{fill.price:.4f}",
                        "cash_after": f"{fill.cash_after:.2f}",
                        "realized_pnl": f"{fill.realized_pnl:.2f}",
                        "strategy": fill.strategy,
                        "mode": fill.mode,
                        "notes": fill.notes,
                    }
                )

    def load_rows(self) -> list[dict[str, str]]:
        if not self.path.exists():
            return []
        with self.path.open(newline="") as handle:
            return list(csv.DictReader(handle))

    def summary(self) -> dict[str, float | int]:
        rows = self.load_rows()
        sells = [row for row in rows if row.get("side") == "sell"]
        realized_pnl = sum(float(row.get("realized_pnl") or 0.0) for row in sells)
        wins = [row for row in sells if float(row.get("realized_pnl") or 0.0) > 0]
        losses = [row for row in sells if float(row.get("realized_pnl") or 0.0) < 0]
        win_rate_pct = 0.0 if not sells else (len(wins) / len(sells)) * 100
        return {
            "rows": len(rows),
            "closed_trades": len(sells),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate_pct": win_rate_pct,
            "realized_pnl": realized_pnl,
        }

