"""Research notes commands."""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.db.engine import get_conn

console = Console()
note_app = typer.Typer(help="리서치 노트 관리")


@note_app.command("add")
def add(
    title: Annotated[str, typer.Argument(help="노트 제목")],
    content: Annotated[str, typer.Argument(help="노트 내용")],
    ticker: Annotated[str | None, typer.Option("--ticker", help="관련 종목코드")] = None,
) -> None:
    """리서치 노트를 추가합니다."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO notes (ticker, title, content) VALUES (?, ?, ?)",
            (ticker, title, content),
        )
    ticker_str = f" ({ticker})" if ticker else ""
    console.print(f"[green]+ 노트 추가됨: {title}{ticker_str}[/green]")


@note_app.command("list")
def list_notes(
    ticker: Annotated[str | None, typer.Argument(help="종목코드로 필터링")] = None,
) -> None:
    """리서치 노트를 표시합니다."""
    with get_conn() as conn:
        if ticker:
            rows = conn.execute(
                "SELECT * FROM notes WHERE ticker = ? ORDER BY created_at DESC",
                (ticker,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM notes ORDER BY created_at DESC"
            ).fetchall()

    if not rows:
        console.print("[dim]노트가 없습니다.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", width=4, style="dim")
    table.add_column("종목", width=10)
    table.add_column("제목", width=20)
    table.add_column("내용", width=40)
    table.add_column("작성일", width=12)

    for row in rows:
        content_preview = row["content"][:50]
        if len(row["content"]) > 50:
            content_preview += "..."

        table.add_row(
            str(row["id"]),
            row["ticker"] or "",
            row["title"],
            content_preview,
            row["created_at"][:10],
        )

    console.print()
    console.print(Panel(table, title="리서치 노트", border_style="blue"))
    console.print()


@note_app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="검색어")],
) -> None:
    """리서치 노트를 검색합니다."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE title LIKE ? OR content LIKE ? ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()

    if not rows:
        console.print(f"[dim]'{query}'에 대한 검색 결과가 없습니다.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", width=4, style="dim")
    table.add_column("종목", width=10)
    table.add_column("제목", width=20)
    table.add_column("내용", width=40)
    table.add_column("작성일", width=12)

    for row in rows:
        content_preview = row["content"][:50]
        if len(row["content"]) > 50:
            content_preview += "..."

        table.add_row(
            str(row["id"]),
            row["ticker"] or "",
            row["title"],
            content_preview,
            row["created_at"][:10],
        )

    console.print()
    console.print(Panel(table, title=f"검색: {query}", border_style="blue"))
    console.print()
