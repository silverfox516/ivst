"""Recommendation command: AI-recommended stocks based on sector momentum and policy."""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.analysis.recommend import Recommendation, generate_recommendations
from ivst.data.news import fetch_all_news
from ivst.ui import colors

console = Console()
recommend_app = typer.Typer(help="유망 종목 추천")


def build_recommend_panel(
    recs: list[Recommendation], show_reason: bool = False
) -> Panel:
    """Build recommendation table panel."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", width=4, style="dim")
    table.add_column("종목", width=20)
    table.add_column("섹터", width=16)
    table.add_column("모멘텀", justify="right", width=10)
    table.add_column("정책", justify="center", width=8)

    if show_reason:
        table.add_column("추천 근거", width=50)

    for i, rec in enumerate(recs, 1):
        policy_str = f"[{colors.BULLISH}]O[/]" if rec.policy_match else ""
        score_str = f"{rec.momentum_score:+.1f}"

        row = [str(i), f"{rec.name} ({rec.ticker})", rec.sector, score_str, policy_str]
        if show_reason:
            row.append(rec.reason)

        table.add_row(*row)

    return Panel(table, title="추천 종목", border_style="green")


@recommend_app.callback(invoke_without_command=True)
def recommend_main(
    ctx: typer.Context,
    reason: Annotated[bool, typer.Option("--reason", help="추천 근거 표시")] = False,
    market: Annotated[str, typer.Option("--market", help="시장 (KR/US/ALL)")] = "ALL",
) -> None:
    """섹터 모멘텀과 정책 수혜를 분석하여 유망 종목을 추천합니다."""
    with console.status("[cyan]섹터 분석 및 종목 추천 중...[/cyan]"):
        news = fetch_all_news(limit=30)
        news_texts = [n.title + " " + n.summary for n in news]
        recs = generate_recommendations(
            news_texts=news_texts, market=market.upper(), top_n=8
        )

    if not recs:
        console.print("[dim]추천할 종목이 없습니다.[/dim]")
        raise typer.Exit()

    console.print()
    console.print(build_recommend_panel(recs, show_reason=reason))
    console.print()
