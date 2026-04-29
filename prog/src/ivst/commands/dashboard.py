"""Main dashboard: unified view of signals, news, and market data."""

from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.analysis.sentiment import classify_sentiment
from ivst.commands.market import build_market_panel
from ivst.commands.signal_cmd import (
    _build_signal_table,
    _signal_style,
    generate_all_signals,
)
from ivst.data.fx import fetch_all_market_quotes
from ivst.data.news import fetch_all_news, match_news_to_watchlist
from ivst.db import repo
from ivst.ui import colors

console = Console()


def _build_news_summary(
    news_with_sentiment: list[tuple], limit: int = 5
) -> Panel:
    """Build a compact news panel for the dashboard."""
    table = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    table.add_column("tag", width=6)
    table.add_column("title", ratio=1)
    table.add_column("source", width=10, style="dim")

    for item, _matched, sentiment_result in news_with_sentiment[:limit]:
        style = {
            "호재": colors.BULLISH,
            "악재": colors.BEARISH,
            "중립": colors.NEUTRAL,
        }.get(sentiment_result.sentiment.value, colors.NEUTRAL)

        tag = f"[{style}][{sentiment_result.sentiment.value}][/]"
        title_str = item.title[:55]
        if len(item.title) > 55:
            title_str += "..."

        table.add_row(tag, title_str, item.source)

    if not news_with_sentiment:
        table.add_row("", "[dim]뉴스가 없습니다[/dim]", "")

    return Panel(table, title="Latest News", border_style="blue")


def show_dashboard() -> None:
    """Display the full dashboard."""
    items = repo.watchlist_list()

    if not items:
        console.print(
            "\n[dim]관심종목이 없습니다. 먼저 종목을 추가하세요:[/dim]"
        )
        console.print("  [cyan]ivst watch add 삼성전자[/cyan]")
        console.print("  [cyan]ivst watch add AAPL[/cyan]\n")
        return

    today = datetime.now()
    weekday = ["월", "화", "수", "목", "금", "토", "일"][today.weekday()]
    date_str = f"{today.strftime('%Y-%m-%d')} ({weekday})"

    console.print()
    console.print(f"[bold cyan]  IVST Dashboard[/bold cyan]  [dim]{date_str}[/dim]")
    console.print()

    # Signals
    with console.status("[cyan]관심종목 분석 중...[/cyan]"):
        signals = generate_all_signals()

    if signals:
        console.print(_build_signal_table(signals))

    # News
    with console.status("[cyan]뉴스 수집 중...[/cyan]"):
        names = [i.name for i in items]
        tickers = [i.ticker for i in items]
        raw_news = fetch_all_news(limit=20)
        matched = match_news_to_watchlist(raw_news, names, tickers)

        news_results = []
        for news_item, matched_ticker in matched:
            text = news_item.title + " " + getattr(news_item, "summary", "")
            sentiment = classify_sentiment(text)
            news_results.append((news_item, matched_ticker, sentiment))

        watchlist_news = [(n, t, s) for n, t, s in news_results if t is not None]
        display_news = watchlist_news if watchlist_news else news_results

    console.print(_build_news_summary(display_news, limit=5))

    # Market
    with console.status("[cyan]시장 데이터 수집 중...[/cyan]"):
        quotes = fetch_all_market_quotes()

    if quotes:
        console.print(build_market_panel(quotes))

    console.print()
