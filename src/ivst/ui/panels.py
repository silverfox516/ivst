"""Rich panel and table builders for CLI output."""

from rich.panel import Panel
from rich.table import Table

from ivst.db.models import WatchItem


def build_watchlist_table(items: list[WatchItem]) -> Panel:
    """Build a Rich table panel for the watchlist."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("종목코드", width=10)
    table.add_column("종목명", width=20)
    table.add_column("시장", width=8)
    table.add_column("등록일", width=12)

    for i, item in enumerate(items, 1):
        table.add_row(
            str(i),
            item.ticker,
            item.name,
            item.market,
            item.added_at[:10],
        )

    if not items:
        table.add_row("", "", "[dim]관심종목이 없습니다[/dim]", "", "")

    return Panel(table, title="관심종목", border_style="blue")
