"""News command: show sentiment-tagged news for watchlist stocks."""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.analysis.sentiment import Sentiment, classify_sentiment
from ivst.data.news import fetch_all_news, match_news_to_watchlist
from ivst.db import repo
from ivst.ui import colors

console = Console()
news_app = typer.Typer(help="뉴스 및 감성 분석")


def _sentiment_style(s: Sentiment) -> str:
    return {
        Sentiment.BULLISH: colors.BULLISH,
        Sentiment.BEARISH: colors.BEARISH,
        Sentiment.NEUTRAL: colors.NEUTRAL,
    }[s]


def build_news_panel(
    news_with_sentiment: list[tuple], title: str = "Latest News"
) -> Panel:
    """Build news panel with sentiment tags."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("감성", width=8, justify="center")
    table.add_column("종목", width=12)
    table.add_column("제목", width=50)
    table.add_column("출처", width=12)

    for item, matched_ticker, sentiment_result in news_with_sentiment:
        style = _sentiment_style(sentiment_result.sentiment)
        tag = f"[{style}][{sentiment_result.sentiment.value}][/]"
        ticker_str = matched_ticker or ""

        title_str = item.title[:60]
        if len(item.title) > 60:
            title_str += "..."

        table.add_row(tag, ticker_str, title_str, item.source)

    if not news_with_sentiment:
        table.add_row("", "", "[dim]뉴스가 없습니다[/dim]", "")

    return Panel(table, title=title, border_style="blue")


@news_app.callback(invoke_without_command=True)
def news_main(
    ctx: typer.Context,
    all_news: Annotated[bool, typer.Option("--all", help="전체 시장 뉴스 표시")] = False,
) -> None:
    """관심종목 관련 뉴스를 호재/악재로 분류하여 보여줍니다."""
    with console.status("[cyan]뉴스 수집 중...[/cyan]"):
        items = repo.watchlist_list()
        names = [i.name for i in items]
        tickers = [i.ticker for i in items]

        raw_news = fetch_all_news(limit=40)
        matched = match_news_to_watchlist(raw_news, names, tickers)

    results = []
    for news_item, matched_ticker in matched:
        text = news_item.title + " " + news_item.summary
        sentiment = classify_sentiment(text)
        results.append((news_item, matched_ticker, sentiment))

    if not all_news:
        watchlist_news = [(n, t, s) for n, t, s in results if t is not None]
        other_news = [(n, t, s) for n, t, s in results if t is None]

        if watchlist_news:
            console.print()
            console.print(build_news_panel(watchlist_news, "관심종목 뉴스"))

        if not watchlist_news:
            console.print("\n[dim]관심종목 관련 뉴스가 없습니다. --all 옵션으로 전체 뉴스를 확인하세요.[/dim]")
            console.print()
            console.print(build_news_panel(results[:15], "전체 시장 뉴스"))
    else:
        console.print()
        console.print(build_news_panel(results[:20], "전체 시장 뉴스"))

    console.print()
