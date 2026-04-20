"""Watchlist management commands."""

import sqlite3
from typing import Annotated

import typer
from rich.console import Console
from rich.prompt import Prompt

from ivst.data.resolver import resolve_ticker
from ivst.db import repo
from ivst.db.models import TickerInfo
from ivst.ui.panels import build_watchlist_table

console = Console()
watch_app = typer.Typer(help="관심종목 관리")


def _pick_one(matches: list[TickerInfo], query: str) -> TickerInfo | None:
    """If multiple matches, prompt user to pick one."""
    if len(matches) == 1:
        return matches[0]

    console.print(f"\n[yellow]'{query}'에 대한 검색 결과:[/yellow]")
    for i, m in enumerate(matches[:10], 1):
        console.print(f"  {i}. {m.ticker} - {m.name} ({m.market})")

    choice = Prompt.ask("번호를 선택하세요", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(matches):
            return matches[idx]
    except ValueError:
        pass

    console.print("[red]잘못된 선택입니다.[/red]")
    return None


@watch_app.command("add")
def add(
    tickers: Annotated[list[str], typer.Argument(help="종목명 또는 코드 (여러 개 가능)")],
) -> None:
    """관심종목을 추가합니다."""
    for query in tickers:
        matches = resolve_ticker(query)
        if not matches:
            console.print(f"[red]'{query}' 종목을 찾을 수 없습니다.[/red]")
            continue

        picked = _pick_one(matches, query)
        if not picked:
            continue

        try:
            item = repo.watchlist_add(picked.ticker, picked.name, picked.market)
            console.print(
                f"[green]+ {item.name} ({item.ticker}) 추가됨[/green]"
            )
        except sqlite3.IntegrityError:
            console.print(
                f"[yellow]{picked.name} ({picked.ticker})은(는) 이미 관심종목에 있습니다.[/yellow]"
            )


@watch_app.command("list")
def list_watchlist() -> None:
    """관심종목 목록을 표시합니다."""
    items = repo.watchlist_list()
    console.print(build_watchlist_table(items))


@watch_app.command("remove")
def remove(
    ticker: Annotated[str, typer.Argument(help="제거할 종목코드 또는 종목명")],
) -> None:
    """관심종목에서 제거합니다."""
    if repo.watchlist_remove(ticker):
        console.print(f"[green]- {ticker} 제거됨[/green]")
        return

    matches = resolve_ticker(ticker)
    for m in matches:
        if repo.watchlist_remove(m.ticker):
            console.print(f"[green]- {m.name} ({m.ticker}) 제거됨[/green]")
            return

    console.print(f"[red]'{ticker}'을(를) 관심종목에서 찾을 수 없습니다.[/red]")
