"""Korean stock OHLCV fetcher (pykrx backed)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict


class OHLCVRecord(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def fetch_kr_ohlcv(ticker: str, days: int = 300) -> list[OHLCVRecord]:
    """Fetch daily OHLCV for a Korean stock via pykrx.

    Returns an empty list on failure (missing dependency, bad code, network).
    Output is ordered ascending by date.
    """
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except Exception:
        return []

    # Ask for ~2× window so non-trading days don't drop below requested count.
    end = datetime.now()
    start = end - timedelta(days=max(days, 10) * 2)
    start_s = start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    try:
        df = stock.get_market_ohlcv(start_s, end_s, ticker)
    except Exception:
        return []

    if df is None or df.empty:
        return []

    records: list[OHLCVRecord] = []
    for idx, row in df.iterrows():
        try:
            date = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)
        except Exception:
            date = str(idx)

        records.append(
            OHLCVRecord(
                date=date,
                open=float(row.get("시가", 0.0)),
                high=float(row.get("고가", 0.0)),
                low=float(row.get("저가", 0.0)),
                close=float(row.get("종가", 0.0)),
                volume=int(row.get("거래량", 0)),
            )
        )

    return records[-days:] if len(records) > days else records
