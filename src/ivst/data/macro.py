"""FRED macro indicators — keyless CSV download.

FRED's public graph CSV endpoint (`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>`)
serves the full series as a two-column CSV with no API key or auth required.
This module uses that endpoint so the rest of the app works out-of-the-box.

If the network is down or a series ID is unknown, each helper gracefully
returns `None` / an empty list and the verdict engine normalizes the rest.
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class MacroIndicator:
    name: str
    value: float
    unit: str = ""


@dataclass(frozen=True)
class LiquiditySnapshot:
    """Raw liquidity-component readings plus their 4-week-ago values.

    Units preserved as FRED publishes them:
    - WALCL, WTREGEN: millions of USD
    - RRPONTSYD:      billions of USD
    """

    walcl_now_mn: float
    walcl_4w_ago_mn: float
    tga_now_mn: float
    tga_4w_ago_mn: float
    rrp_now_bn: float
    rrp_4w_ago_bn: float
    as_of_date: str
    reference_date: str


# (display name, FRED series id, unit suffix)
# VIX intentionally omitted — replaced by CNN Fear & Greed (see data/sentiment_index.py).
_SERIES: list[tuple[str, str, str]] = [
    ("10Y UST",          "DGS10",          "%"),
    ("10Y-2Y Spread",    "T10Y2Y",         "%"),
    ("HY OAS",           "BAMLH0A0HYM2",   "%"),
    ("Fed BS",           "WALCL",          "M$"),   # FRED units: Millions of Dollars
    ("RRP",              "RRPONTSYD",      "B$"),   # FRED units: Billions of Dollars
    ("TGA",              "WTREGEN",        "M$"),   # FRED units: Millions of Dollars
]


_FRED_CSV_BASE = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def _fetch_series(series_id: str, timeout: float = 15.0):  # type: ignore[no-untyped-def]
    """Download a FRED series as a pandas Series (DatetimeIndex → float).

    Returns None on network, parsing, or empty-data failure.
    """
    try:
        import httpx
        import pandas as pd
    except Exception:
        return None

    try:
        resp = httpx.get(
            _FRED_CSV_BASE,
            params={"id": series_id},
            timeout=timeout,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception:
        return None

    try:
        df = pd.read_csv(
            io.StringIO(resp.text),
            parse_dates=[0],
        )
    except Exception:
        return None

    if df.empty or df.shape[1] < 2:
        return None

    date_col = df.columns[0]
    value_col = df.columns[1]

    # FRED uses "." for missing values; force numeric coercion.
    series = pd.to_numeric(df[value_col], errors="coerce")
    series.index = df[date_col]
    series = series.dropna()

    return series if not series.empty else None


def fetch_latest_value(series_id: str) -> float | None:
    """Return the latest non-null value for a FRED series, or None."""
    series = _fetch_series(series_id)
    if series is None:
        return None
    try:
        return float(series.iloc[-1])
    except Exception:
        return None


def fetch_series_mean(series_id: str, days: int = 60) -> tuple[float, float] | None:
    """Return (latest_value, trailing_window_mean) for a FRED series.

    The mean is computed over the last `days` calendar days of observations.
    Returns None if data is insufficient.
    """
    series = _fetch_series(series_id)
    if series is None:
        return None
    try:
        latest_date = series.index.max()
        window_start = latest_date - timedelta(days=days)
        window = series.loc[window_start:latest_date]
        if window.empty:
            return None
        return float(series.iloc[-1]), float(window.mean())
    except Exception:
        return None


def fetch_fred_indicators() -> list[MacroIndicator]:
    """Return the latest values for the tracked FRED series.

    Fetches each series in parallel to keep the CLI responsive. Individual
    series failures are dropped so the rest of the panel still renders.
    """
    results: list[MacroIndicator] = []

    with ThreadPoolExecutor(max_workers=min(len(_SERIES), 6)) as pool:
        futures = {
            pool.submit(_fetch_series, sid): (name, unit)
            for name, sid, unit in _SERIES
        }
        for fut, (name, unit) in futures.items():
            try:
                series = fut.result(timeout=30)
            except Exception:
                continue
            if series is None:
                continue
            try:
                latest = float(series.iloc[-1])
            except Exception:
                continue
            results.append(MacroIndicator(name=name, value=latest, unit=unit))

    # Preserve declared order for deterministic layout.
    order = {name: i for i, (name, _, _) in enumerate(_SERIES)}
    results.sort(key=lambda r: order.get(r.name, 99))
    return results


def fetch_liquidity_snapshot() -> LiquiditySnapshot | None:
    """Return current and 4-week-ago readings for WALCL, WTREGEN, RRPONTSYD.

    The market_service layer turns these into direction + level signals
    (see `tga_potential_signal`, `rrp_potential_signal`, `fed_bs_trend_signal`).
    Returns None when any required series is unavailable.
    """
    walcl = _fetch_series("WALCL")
    tga = _fetch_series("WTREGEN")
    rrp = _fetch_series("RRPONTSYD")

    if walcl is None or tga is None or rrp is None:
        return None

    latest_date = min(walcl.index.max(), tga.index.max(), rrp.index.max())
    ref_date = latest_date - timedelta(days=28)

    def _at_or_before(series, target):  # type: ignore[no-untyped-def]
        sub = series.loc[:target]
        return None if sub.empty else sub.iloc[-1]

    try:
        walcl_now = float(_at_or_before(walcl, latest_date))
        tga_now = float(_at_or_before(tga, latest_date))
        rrp_now = float(_at_or_before(rrp, latest_date))
        walcl_ref = float(_at_or_before(walcl, ref_date))
        tga_ref = float(_at_or_before(tga, ref_date))
        rrp_ref = float(_at_or_before(rrp, ref_date))
    except Exception:
        return None

    return LiquiditySnapshot(
        walcl_now_mn=walcl_now,
        walcl_4w_ago_mn=walcl_ref,
        tga_now_mn=tga_now,
        tga_4w_ago_mn=tga_ref,
        rrp_now_bn=rrp_now,
        rrp_4w_ago_bn=rrp_ref,
        as_of_date=str(latest_date)[:10],
        reference_date=str(ref_date)[:10],
    )
