"""Resolve user queries (ticker code or name) to TickerInfo candidates.

Strategy:
1. Normalize query.
2. Probe cache (exact match on ticker or name, then substring on name).
3. If nothing found and the query looks like a raw symbol, probe pykrx/yfinance
   to validate and enrich.
4. Upsert any discovery into the ticker cache.
"""

from __future__ import annotations

import re
from typing import Iterable

from ivst.db import repo
from ivst.db.models import TickerInfo

_KR_CODE_RE = re.compile(r"^\d{6}$")
_US_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


def _dedup(candidates: Iterable[TickerInfo]) -> list[TickerInfo]:
    seen: set[str] = set()
    out: list[TickerInfo] = []
    for c in candidates:
        if c.ticker in seen:
            continue
        seen.add(c.ticker)
        out.append(c)
    return out


def _from_cache(query: str) -> list[TickerInfo]:
    """Cache-first lookup: exact match, then substring."""
    results: list[TickerInfo] = []

    exact = repo.ticker_cache_get(query)
    if exact:
        ticker, name, market = exact
        results.append(TickerInfo(ticker=ticker, name=name, market=market))

    for ticker, name, market in repo.ticker_cache_search(query):
        results.append(TickerInfo(ticker=ticker, name=name, market=market))

    return _dedup(results)


def _probe_kr(code: str) -> TickerInfo | None:
    """Validate a 6-digit Korean stock code via pykrx."""
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except Exception:
        return None

    try:
        name = stock.get_market_ticker_name(code)
    except Exception:
        return None

    if not name or not isinstance(name, str):
        return None
    return TickerInfo(ticker=code, name=name, market="KR")


def _probe_us(symbol: str) -> TickerInfo | None:
    """Validate a US symbol via yfinance."""
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except Exception:
        return None

    try:
        t = yf.Ticker(symbol)
        info = t.info or {}
    except Exception:
        return None

    name = info.get("longName") or info.get("shortName")
    if not name:
        return None
    return TickerInfo(ticker=symbol, name=str(name), market="US")


def _probe_network(query: str) -> list[TickerInfo]:
    """Try KR first if query looks like a KR code, else try US symbol."""
    out: list[TickerInfo] = []

    if _KR_CODE_RE.match(query):
        kr = _probe_kr(query)
        if kr:
            out.append(kr)
        return out

    upper = query.upper()
    if _US_SYMBOL_RE.match(upper):
        us = _probe_us(upper)
        if us:
            out.append(us)

    return out


def resolve_ticker(query: str) -> list[TickerInfo]:
    """Resolve a user query to one or more TickerInfo candidates.

    Returns an empty list when nothing matches.
    """
    query = query.strip()
    if not query:
        return []

    cached = _from_cache(query)
    if cached:
        return cached

    probed = _probe_network(query)
    for info in probed:
        repo.ticker_cache_upsert(info.ticker, info.name, info.market)
    return probed
