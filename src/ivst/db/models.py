"""Domain models as frozen dataclasses."""

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchItem:
    id: int
    ticker: str
    name: str
    market: str  # "KR" or "US"
    added_at: str


@dataclass(frozen=True)
class TickerInfo:
    ticker: str
    name: str
    market: str  # "KR" or "US"
