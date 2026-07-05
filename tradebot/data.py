from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .models import Bar


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unsupported timestamp format: {value!r}")


class CSVDataSource:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_bars(self, symbol: str) -> list[Bar]:
        if not self.path.exists():
            raise FileNotFoundError(f"CSV data file not found: {self.path}")

        wanted = symbol.upper()
        bars: list[Bar] = []
        with self.path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_symbol = row.get("symbol", wanted).upper()
                if row_symbol != wanted:
                    continue

                timestamp = parse_timestamp(row.get("timestamp") or row.get("date") or "")
                close = float(row["close"])
                bars.append(
                    Bar(
                        timestamp=timestamp,
                        symbol=row_symbol,
                        open=float(row.get("open") or close),
                        high=float(row.get("high") or close),
                        low=float(row.get("low") or close),
                        close=close,
                        volume=float(row.get("volume") or 0.0),
                    )
                )

        bars.sort(key=lambda bar: bar.timestamp)
        if not bars:
            raise ValueError(f"No bars found for {wanted} in {self.path}")
        return bars


def write_bars_csv(path: str | Path, bars: Iterable[Bar]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["timestamp", "symbol", "open", "high", "low", "close", "volume"],
        )
        writer.writeheader()
        for bar in bars:
            writer.writerow(
                {
                    "timestamp": bar.timestamp.strftime("%Y-%m-%d"),
                    "symbol": bar.symbol,
                    "open": f"{bar.open:.4f}",
                    "high": f"{bar.high:.4f}",
                    "low": f"{bar.low:.4f}",
                    "close": f"{bar.close:.4f}",
                    "volume": f"{bar.volume:.0f}",
                }
            )


def _nasdaq_float(value: Any) -> float:
    if value in (None, "", "N/A"):
        return 0.0
    return float(str(value).replace("$", "").replace(",", ""))


def load_nasdaq_history_json(path: str | Path, symbol: str) -> list[Bar]:
    input_path = Path(path)
    with input_path.open() as handle:
        payload = json.load(handle)

    rows = (
        payload.get("data", {})
        .get("tradesTable", {})
        .get("rows", [])
    )
    if not rows:
        raise ValueError(f"No Nasdaq historical rows found in {input_path}")

    bars: list[Bar] = []
    for row in rows:
        timestamp = datetime.strptime(row["date"], "%m/%d/%Y")
        bars.append(
            Bar(
                timestamp=timestamp,
                symbol=symbol.upper(),
                open=_nasdaq_float(row.get("open")),
                high=_nasdaq_float(row.get("high")),
                low=_nasdaq_float(row.get("low")),
                close=_nasdaq_float(row.get("close")),
                volume=_nasdaq_float(row.get("volume")),
            )
        )
    bars.sort(key=lambda bar: bar.timestamp)
    return bars


def combine_bars_csv(path: str | Path, groups: Iterable[Iterable[Bar]]) -> None:
    bars: list[Bar] = []
    for group in groups:
        bars.extend(group)
    bars.sort(key=lambda bar: (bar.timestamp, bar.symbol))
    write_bars_csv(path, bars)


def download_yfinance(symbol: str, period: str, output_path: str | Path) -> Path:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError(
            "Install optional market data dependencies first: "
            "python -m pip install -e '.[market-data]'"
        ) from exc

    frame = yf.download(symbol, period=period, auto_adjust=False, progress=False)
    if frame.empty:
        raise RuntimeError(f"yfinance returned no rows for {symbol} period={period}")

    bars: list[Bar] = []
    for timestamp, row in frame.iterrows():
        bars.append(
            Bar(
                timestamp=timestamp.to_pydatetime().replace(tzinfo=None),
                symbol=symbol.upper(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row.get("Volume", 0.0)),
            )
        )

    output = Path(output_path)
    write_bars_csv(output, bars)
    return output
