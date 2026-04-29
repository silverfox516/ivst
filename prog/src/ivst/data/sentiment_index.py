"""CNN Fear & Greed Index — broad market sentiment composite.

CNN publishes the current F&G reading through a public JSON endpoint used
by their own charts:

    https://production.dataviz.cnn.io/index/fearandgreed/graphdata

The endpoint is keyless but rejects requests without a browser-like
User-Agent. This module wraps the call defensively so any failure (network,
schema drift) degrades to None — the caller is expected to just omit the
indicator from the panel.

The F&G score is a 0-100 composite built from seven sub-signals including
VIX (volatility), put/call ratio, market momentum (S&P500 vs 125DMA),
junk bond demand, stock price strength/breadth, and safe haven demand.
It therefore supersedes a plain VIX reading for an at-a-glance sentiment
gauge.
"""

from __future__ import annotations

from dataclasses import dataclass


_FG_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class FearGreedReading:
    score: float  # 0-100
    rating: str   # "extreme fear" | "fear" | "neutral" | "greed" | "extreme greed"


def fetch_fear_greed() -> FearGreedReading | None:
    """Return the latest CNN Fear & Greed score + rating, or None on failure."""
    try:
        import httpx
    except Exception:
        return None

    try:
        resp = httpx.get(
            _FG_URL,
            headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
            timeout=15.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    fg = data.get("fear_and_greed")
    if not isinstance(fg, dict):
        return None

    try:
        score = float(fg["score"])
    except (KeyError, TypeError, ValueError):
        return None

    rating = str(fg.get("rating", "")).strip().lower()
    return FearGreedReading(score=score, rating=rating)
