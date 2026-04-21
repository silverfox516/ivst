"""News aggregation from public RSS feeds.

Best-effort: any single feed failure is silently dropped so the rest of the
pipeline (sentiment, recommendations, dashboard) keeps rendering.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass


@dataclass(frozen=True)
class NewsItem:
    title: str
    summary: str
    source: str
    url: str
    published_at: str


_FEEDS: list[tuple[str, str]] = [
    ("Yahoo",   "https://finance.yahoo.com/news/rssindex"),
    ("MKT",     "https://www.marketwatch.com/rss/topstories"),
    ("GoogleK", "https://news.google.com/rss/search?q=%EC%A3%BC%EC%8B%9D+%EC%8B%9C%EC%9E%A5&hl=ko&gl=KR&ceid=KR:ko"),
    ("GoogleU", "https://news.google.com/rss/search?q=stock+market&hl=en-US&gl=US&ceid=US:en"),
]


def _parse_feed(source: str, url: str, timeout: float = 8.0) -> list[NewsItem]:
    """Fetch and parse one feed into NewsItems."""
    try:
        import feedparser  # type: ignore[import-untyped]
        import httpx
    except Exception:
        return []

    try:
        resp = httpx.get(url, timeout=timeout, follow_redirects=True)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception:
        return []

    items: list[NewsItem] = []
    for entry in parsed.entries[:50]:
        title = (entry.get("title") or "").strip()
        if not title:
            continue

        summary = (entry.get("summary") or entry.get("description") or "").strip()
        if len(summary) > 500:
            summary = summary[:500]

        published_at = ""
        pp = entry.get("published_parsed") or entry.get("updated_parsed")
        if pp:
            try:
                published_at = time.strftime("%Y-%m-%dT%H:%M:%S", pp)
            except Exception:
                published_at = ""

        items.append(
            NewsItem(
                title=title,
                summary=summary,
                source=source,
                url=(entry.get("link") or "").strip(),
                published_at=published_at,
            )
        )

    return items


def fetch_all_news(limit: int = 40) -> list[NewsItem]:
    """Fetch and merge headlines from all configured feeds.

    Returns up to `limit` most recent items, newest first when timestamps
    are available.
    """
    collected: list[NewsItem] = []

    with ThreadPoolExecutor(max_workers=len(_FEEDS)) as pool:
        futures = [pool.submit(_parse_feed, src, url) for src, url in _FEEDS]
        for fut in futures:
            try:
                collected.extend(fut.result(timeout=20))
            except Exception:
                continue

    collected.sort(
        key=lambda n: n.published_at or "0000-00-00T00:00:00",
        reverse=True,
    )
    return collected[:limit]


def match_news_to_watchlist(
    items: list[NewsItem],
    names: list[str],
    tickers: list[str],
) -> list[tuple[NewsItem, str | None]]:
    """Associate each news item with a watchlist ticker if its title or
    summary mentions the stock name or ticker (case-insensitive)."""
    haystack = list(zip(names, tickers))
    matched: list[tuple[NewsItem, str | None]] = []

    for item in items:
        text = f"{item.title} {item.summary}".lower()
        hit: str | None = None
        for name, ticker in haystack:
            name_l = (name or "").lower().strip()
            ticker_l = (ticker or "").lower().strip()
            if name_l and name_l in text:
                hit = ticker
                break
            if ticker_l and ticker_l in text:
                hit = ticker
                break
        matched.append((item, hit))

    return matched
