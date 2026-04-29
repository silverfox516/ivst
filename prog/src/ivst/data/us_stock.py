"""US stock OHLCV fetcher (yfinance backed)."""

from __future__ import annotations

from typing import TypedDict


class OHLCVRecord(TypedDict):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


_VALID_PERIODS = {
    "1d", "5d", "1mo", "3mo", "6mo",
    "1y", "2y", "5y", "10y", "ytd", "max",
}


def fetch_us_ohlcv(ticker: str, period: str = "1y") -> list[OHLCVRecord]:
    """Fetch daily OHLCV for a US stock via yfinance.

    Returns an empty list on failure (missing dependency, bad symbol, network).
    Output is ordered ascending by date.
    """
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except Exception:
        return []

    if period not in _VALID_PERIODS:
        period = "1y"

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, auto_adjust=False)
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
                open=float(row.get("Open", 0.0) or 0.0),
                high=float(row.get("High", 0.0) or 0.0),
                low=float(row.get("Low", 0.0) or 0.0),
                close=float(row.get("Close", 0.0) or 0.0),
                volume=int(row.get("Volume", 0) or 0),
            )
        )

    return records
