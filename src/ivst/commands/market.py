"""Market timing command — Plan §4 `목적 1 수행`.

`ivst market` builds the US-equity MarketVerdict via
`analysis/market_service.py` and renders the `[코어]` + `[맥락]` panels.
The legacy price-quote panel (`build_market_panel`) is preserved as a
supplementary block and is still exported for `commands/dashboard.py`.
"""

from __future__ import annotations

import typer
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.analysis.market_service import (
    build_us_verdict,
    fetch_context_indicators,
)
from ivst.data.fx import Quote, fetch_all_market_quotes
from ivst.ui import colors
from ivst.ui.formatters import fmt_pct
from ivst.ui.panels import build_context_panel, build_verdict_panel

console = Console()
market_app = typer.Typer(help="시장 타이밍 판정 (목적 1)")


# ---------------------------------------------------------------------------
# Legacy price-quote panel — preserved for commands/dashboard.py.
# ---------------------------------------------------------------------------


def _fmt_quote(q: Quote) -> str:
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
    """Price-quote side panel. Kept for dashboard.py compatibility."""
    indices = [q for q in quotes if q.name in ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ")]
    others = [q for q in quotes if q.name not in ("KOSPI", "KOSDAQ", "S&P 500", "NASDAQ")]

    left = Table(show_header=False, box=None, padding=(0, 2))
    left.add_column("항목", width=40)
    for q in indices:
        left.add_row(_fmt_quote(q))

    right = Table(show_header=False, box=None, padding=(0, 2))
    right.add_column("항목", width=40)
    for q in others:
        right.add_row(_fmt_quote(q))

    return Panel(
        Columns([left, right], expand=True),
        title="Market Summary",
        border_style="blue",
    )


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------


@market_app.callback(invoke_without_command=True)
def market_main(ctx: typer.Context) -> None:
    """시장 타이밍 판정 (현재 지원: 미국 주식)."""
    console.print()
    with console.status("[cyan]시장 데이터 수집 중...[/cyan]"):
        verdict = build_us_verdict()
        console.print(build_verdict_panel(verdict, "[코어] 미국 주식 시장"))

    ctx_panel = build_context_panel(fetch_context_indicators())
    if ctx_panel is not None:
        console.print(ctx_panel)

    try:
        quotes = fetch_all_market_quotes()
    except Exception:
        quotes = []
    if quotes:
        console.print(build_market_panel(quotes))

    console.print()
