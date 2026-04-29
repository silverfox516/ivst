"""Repository layer for database CRUD operations."""

from ivst.db.engine import get_conn
from ivst.db.models import WatchItem


def watchlist_add(ticker: str, name: str, market: str) -> WatchItem:
    """Add a stock to the watchlist. Raises if duplicate."""
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO watchlist (ticker, name, market) VALUES (?, ?, ?)",
            (ticker, name, market),
        )
        row = conn.execute(
            "SELECT * FROM watchlist WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return WatchItem(**dict(row))


def watchlist_list() -> list[WatchItem]:
    """Return all watchlist items."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
        return [WatchItem(**dict(r)) for r in rows]


def watchlist_remove(ticker: str) -> bool:
    """Remove a stock from the watchlist by ticker. Returns True if removed."""
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist WHERE ticker = ?", (ticker,)
        )
        return cursor.rowcount > 0


def watchlist_find(ticker: str) -> WatchItem | None:
    """Find a watchlist item by ticker."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM watchlist WHERE ticker = ?", (ticker,)
        ).fetchone()
        return WatchItem(**dict(row)) if row else None


def ticker_cache_get(name_or_code: str) -> tuple[str, str, str] | None:
    """Lookup ticker cache by name or code. Returns (ticker, name, market) or None."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT ticker, name, market FROM ticker_cache WHERE ticker = ? OR name = ?",
            (name_or_code, name_or_code),
        ).fetchone()
        return (row["ticker"], row["name"], row["market"]) if row else None


def ticker_cache_upsert(ticker: str, name: str, market: str) -> None:
    """Insert or update ticker cache."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ticker_cache (ticker, name, market, updated_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (ticker, name, market),
        )


def ticker_cache_search(query: str) -> list[tuple[str, str, str]]:
    """Fuzzy search ticker cache by name substring. Returns list of (ticker, name, market)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT ticker, name, market FROM ticker_cache WHERE name LIKE ?",
            (f"%{query}%",),
        ).fetchall()
        return [(r["ticker"], r["name"], r["market"]) for r in rows]


def ticker_cache_count(market: str) -> int:
    """Count cached tickers for a given market."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM ticker_cache WHERE market = ?", (market,)
        ).fetchone()
        return row["cnt"]
