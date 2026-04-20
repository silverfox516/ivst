"""Market dashboard command."""

from typing import Annotated

import typer
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.data.fx import Quote, fetch_all_market_quotes
from ivst.data.macro import MacroIndicator, fetch_fred_indicators
from ivst.ui import colors
from ivst.ui.formatters import fmt_pct

console = Console()
market_app = typer.Typer(help="시장 지표 대시보드")


def _fmt_quote(q: Quote) -> str:
    """Format a quote for display."""
    color = colors.PRICE_UP if q.change_pct >= 0 else colors.PRICE_DOWN

    if q.name in ("VIX", "10Y UST"):
        price_str = f"{q.price:.2f}"
        if q.name == "10Y UST":
            price_str += "%"
    elif q.name == "USD/KRW":
        price_str = f"{q.price:,.1f}"
    elif q.name in ("KOSPI", "KOSDAQ"):
        price_str = f"{q.price:,.2f}"
    elif q.currency:
        price_str = f"{q.currency}{q.price:,.2f}"
    else:
        price_str = f"{q.price:,.2f}"

    return f"[bold]{q.name}[/bold]  [{color}]{price_str} ({fmt_pct(q.change_pct)})[/]"


def build_market_panel(quotes: list[Quote]) -> Panel:
    """Build the market summary panel."""
    indices = [q for q in quotes if q.name in ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ")]
    others = [q for q in quotes if q.name not in ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ")]

    left_table = Table(show_header=False, box=None, padding=(0, 2))
    left_table.add_column("항목", width=40)

    for q in indices:
        left_table.add_row(_fmt_quote(q))

    right_table = Table(show_header=False, box=None, padding=(0, 2))
    right_table.add_column("항목", width=40)

    for q in others:
        right_table.add_row(_fmt_quote(q))

    return Panel(
        Columns([left_table, right_table], expand=True),
        title="Market Summary",
        border_style="blue",
    )


def build_macro_panel(indicators: list[MacroIndicator]) -> Panel | None:
    """Build the macro indicators panel."""
    if not indicators:
        return None

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("지표", width=20)
    table.add_column("값", justify="right", width=12)

    for ind in indicators:
        table.add_row(ind.name, f"{ind.value:.2f}{ind.unit}")

    return Panel(table, title="경제 지표 (FRED)", border_style="blue")


@market_app.callback(invoke_without_command=True)
def market_main(
    ctx: typer.Context,
    detail: Annotated[str | None, typer.Argument(help="상세 보기 (liquidity)")] = None,
) -> None:
    """시장 지표를 한눈에 보여줍니다."""
    with console.status("[cyan]시장 데이터 수집 중...[/cyan]"):
        quotes = fetch_all_market_quotes()
        macro = fetch_fred_indicators()

    if not quotes:
        console.print("[red]시장 데이터를 가져올 수 없습니다.[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(build_market_panel(quotes))

    macro_panel = build_macro_panel(macro)
    if macro_panel:
        console.print(macro_panel)

    if not macro:
        console.print(
            "\n[dim]FRED 경제 지표를 보려면 API 키를 설정하세요: "
            "~/.config/ivst/fred_api_key[/dim]"
        )
    console.print()
