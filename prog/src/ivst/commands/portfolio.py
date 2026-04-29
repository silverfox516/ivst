"""Portfolio management commands."""

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.data.resolver import resolve_ticker
from ivst.db.engine import get_conn
from ivst.ui import colors
from ivst.ui.formatters import fmt_krw, fmt_pct, fmt_price, fmt_usd

console = Console()
portfolio_app = typer.Typer(help="포트폴리오 관리")


def _get_current_price(ticker: str, market: str) -> float | None:
    """Fetch current price for a stock."""
    try:
        if market == "KR":
            from ivst.data.kr_stock import fetch_kr_ohlcv
            records = fetch_kr_ohlcv(ticker, days=5)
        else:
            from ivst.data.us_stock import fetch_us_ohlcv
            records = fetch_us_ohlcv(ticker, period="5d")
        if records:
            return records[-1]["close"]
    except Exception:
        pass
    return None


@portfolio_app.command("add")
def add(
    ticker_query: Annotated[str, typer.Argument(help="종목코드 또는 종목명")],
    quantity: Annotated[int, typer.Argument(help="수량")],
    buy_price: Annotated[float, typer.Argument(help="매수 단가")],
    buy_date: Annotated[str, typer.Option("--date", help="매수일 (YYYY-MM-DD)")] = "",
    memo: Annotated[str, typer.Option("--memo", help="메모")] = "",
) -> None:
    """포트폴리오에 보유 종목을 추가합니다."""
    matches = resolve_ticker(ticker_query)
    if not matches:
        console.print(f"[red]'{ticker_query}' 종목을 찾을 수 없습니다.[/red]")
        raise typer.Exit(1)

    info = matches[0]
    if not buy_date:
        from datetime import datetime
        buy_date = datetime.now().strftime("%Y-%m-%d")

    with get_conn() as conn:
        conn.execute(
            "INSERT INTO portfolio (ticker, name, market, buy_price, quantity, buy_date, memo) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (info.ticker, info.name, info.market, buy_price, quantity, buy_date, memo),
        )

    console.print(
        f"[green]+ {info.name} ({info.ticker}) {quantity}주 @ "
        f"{fmt_price(buy_price, info.market)} 추가됨[/green]"
    )


@portfolio_app.command("list")
def list_portfolio() -> None:
    """포트폴리오 보유 종목을 표시합니다."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM portfolio ORDER BY buy_date DESC"
        ).fetchall()

    if not rows:
        console.print("[dim]포트폴리오가 비어있습니다.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("종목", width=16)
    table.add_column("수량", justify="right", width=8)
    table.add_column("매수가", justify="right", width=14)
    table.add_column("매수일", width=12)
    table.add_column("메모", width=20)

    for row in rows:
        table.add_row(
            f"{row['name']} ({row['ticker']})",
            str(row["quantity"]),
            fmt_price(row["buy_price"], row["market"]),
            row["buy_date"],
            row["memo"] or "",
        )

    console.print()
    console.print(Panel(table, title="포트폴리오", border_style="blue"))
    console.print()


@portfolio_app.command("perf")
def performance() -> None:
    """포트폴리오 수익률을 계산합니다."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM portfolio").fetchall()

    if not rows:
        console.print("[dim]포트폴리오가 비어있습니다.[/dim]")
        return

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("종목", width=16)
    table.add_column("수량", justify="right", width=8)
    table.add_column("매수가", justify="right", width=14)
    table.add_column("현재가", justify="right", width=14)
    table.add_column("수익률", justify="right", width=10)
    table.add_column("평가손익", justify="right", width=14)

    total_cost = 0.0
    total_value = 0.0

    with console.status("[cyan]현재가 조회 중...[/cyan]"):
        for row in rows:
            current = _get_current_price(row["ticker"], row["market"])
            cost = row["buy_price"] * row["quantity"]
            total_cost += cost

            if current:
                value = current * row["quantity"]
                total_value += value
                pnl = value - cost
                pnl_pct = (current - row["buy_price"]) / row["buy_price"] * 100

                pnl_color = colors.PRICE_UP if pnl >= 0 else colors.PRICE_DOWN
                table.add_row(
                    f"{row['name']}",
                    str(row["quantity"]),
                    fmt_price(row["buy_price"], row["market"]),
                    f"[{pnl_color}]{fmt_price(current, row['market'])}[/]",
                    f"[{pnl_color}]{fmt_pct(pnl_pct)}[/]",
                    f"[{pnl_color}]{fmt_price(pnl, row['market'])}[/]",
                )
            else:
                total_value += cost
                table.add_row(
                    f"{row['name']}",
                    str(row["quantity"]),
                    fmt_price(row["buy_price"], row["market"]),
                    "[dim]N/A[/dim]",
                    "[dim]N/A[/dim]",
                    "[dim]N/A[/dim]",
                )

    total_pnl = total_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    pnl_color = colors.PRICE_UP if total_pnl >= 0 else colors.PRICE_DOWN

    console.print()
    console.print(Panel(table, title="포트폴리오 수익률", border_style="blue"))
    console.print(
        f"  [bold]총 투자:[/bold] {total_cost:,.0f}  "
        f"[bold]총 평가:[/bold] [{pnl_color}]{total_value:,.0f}[/]  "
        f"[bold]손익:[/bold] [{pnl_color}]{total_pnl:,.0f} ({fmt_pct(total_pnl_pct)})[/]"
    )
    console.print()
