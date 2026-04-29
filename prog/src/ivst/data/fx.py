"""Index, FX, and macro-rate quotes (yfinance backed)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    name: str
    price: float
    change_pct: float
    currency: str = ""


_SYMBOL_MAP: dict[str, tuple[str, str]] = {
    # display name -> (yahoo symbol, currency prefix)
    # VIX omitted — replaced by CNN Fear & Greed (data/sentiment_index.py).
    "KOSPI":   ("^KS11", ""),
    "KOSDAQ":  ("^KQ11", ""),
    "S&P 500": ("^GSPC", ""),
    "NASDAQ":  ("^IXIC", ""),
    "USD/KRW": ("KRW=X", ""),
    "10Y UST": ("^TNX", ""),
}


def _fetch_one(name: str, symbol: str, currency: str) -> Quote | None:
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except Exception:
        return None

    try:
        hist = yf.Ticker(symbol).history(period="5d", auto_adjust=False)
    except Exception:
        return None

    if hist is None or hist.empty or len(hist) < 1:
        return None

    closes = hist["Close"].dropna()
    if closes.empty:
        return None

    latest = float(closes.iloc[-1])
    if len(closes) >= 2:
        prev = float(closes.iloc[-2])
        change_pct = ((latest - prev) / prev * 100.0) if prev else 0.0
    else:
        change_pct = 0.0

    return Quote(name=name, price=latest, change_pct=change_pct, currency=currency)


def fetch_all_market_quotes() -> list[Quote]:
    """Fetch display-ready quotes for major indices, FX, and macro rates.

    Returns an empty list if yfinance is unavailable. Individual failures are
    silently dropped so the rest of the dashboard keeps rendering.
    """
    results: list[Quote] = []

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [
            (name, pool.submit(_fetch_one, name, sym, cur))
            for name, (sym, cur) in _SYMBOL_MAP.items()
        ]
        for _name, fut in futures:
            try:
                q = fut.result(timeout=15)
            except Exception:
                q = None
            if q is not None:
                results.append(q)

    order = {name: i for i, name in enumerate(_SYMBOL_MAP)}
    results.sort(key=lambda q: order.get(q.name, 99))
    return results
