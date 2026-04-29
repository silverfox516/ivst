"""Signal command — Plan §4 `목적 2 수행`.

`ivst signal [TICKER]` builds a per-stock StockVerdict and renders it. No
argument means: analyse the whole watchlist as a summary table.

Market mode (`중장기/스윙/관망`) is derived from `build_us_verdict()` /
`build_kr_verdict()` depending on whether the watchlist is US-heavy or
KR-heavy. Each stock verdict then uses mode-specific block weights.

Exports preserved for `commands/dashboard.py`:
- `signal_app`           — Typer app
- `generate_all_signals` — now returns list[StockVerdict]
- `_build_signal_table`  — summary table for a list of StockVerdicts
- `_signal_style`        — Rich style string for a Signal5 value
"""

from __future__ import annotations

from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ivst.analysis.market import Mode
from ivst.analysis.market_service import build_us_verdict
from ivst.analysis.stock import Signal5, StockVerdict
from ivst.analysis.stock_service import build_stock_verdict
from ivst.data.resolver import resolve_ticker
from ivst.db import repo
from ivst.db.models import WatchItem
from ivst.ui.panels import build_stock_verdict_panel

console = Console()
signal_app = typer.Typer(help="종목 타이밍 판정 (목적 2)")


# ---------------------------------------------------------------------------
# Rich styling helpers (preserved names for dashboard.py)
# ---------------------------------------------------------------------------


_SIGNAL5_RICH_STYLE: dict[Signal5, str] = {
    Signal5.STRONG_BUY:  "bold bright_green",
    Signal5.BUY:         "green",
    Signal5.HOLD:        "yellow",
    Signal5.SELL:        "red",
    Signal5.STRONG_SELL: "bold bright_red",
}


def _signal_style(signal: Signal5) -> str:
    """Rich style string for a Signal5 value (dashboard compat)."""
    return _SIGNAL5_RICH_STYLE[signal]


# ---------------------------------------------------------------------------
# Market-mode resolution
# ---------------------------------------------------------------------------


def _resolve_market_mode(items: list[WatchItem]) -> Mode:
    """Always use the US market verdict's mode — KR market verdict was
    removed due to unreliable data. KR *stocks* still analyze locally via
    stock_service, they just don't drive a separate market-level mode.
    """
    return build_us_verdict().mode


# ---------------------------------------------------------------------------
# Summary table (dashboard-compatible)
# ---------------------------------------------------------------------------


def _build_signal_table(verdicts: list[StockVerdict]) -> Panel:
    """Compact summary table for a list of StockVerdicts."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("종목", width=24)
    table.add_column("모드", width=8)
    table.add_column("신호", justify="center", width=14)
    table.add_column("총점", justify="right", width=8)
    table.add_column("블록 점수 (V/E/T/S)", width=26)

    for v in verdicts:
        style = _signal_style(v.signal)
        scores = {b.code: b.block_score for b in v.blocks}
        per_block = (
            f"V {scores.get('VALUE',  0.0):+.1f} "
            f"E {scores.get('EVENT',  0.0):+.1f} "
            f"T {scores.get('TREND',  0.0):+.1f} "
            f"S {scores.get('SECTOR', 0.0):+.1f}"
        )
        warn = "⚠ " if v.mode_mismatch_warning else ""
        table.add_row(
            f"{v.name} ({v.ticker})",
            v.mode.value,
            f"[{style}]{warn}{v.signal.value}[/]",
            f"{v.total_score:+.2f}",
            per_block,
        )

    return Panel(table, title="Watchlist Signals", border_style="blue")


# ---------------------------------------------------------------------------
# Public worker
# ---------------------------------------------------------------------------


def generate_all_signals() -> list[StockVerdict]:
    """Build a StockVerdict for every watchlist item.

    Individual failures are logged at dim severity and skipped so the rest
    of the list still renders.
    """
    items = repo.watchlist_list()
    if not items:
        return []

    mode = _resolve_market_mode(items)
    verdicts: list[StockVerdict] = []

    for item in items:
        try:
            verdicts.append(
                build_stock_verdict(item.ticker, item.name, item.market, mode)
            )
        except Exception as e:
            console.print(f"[dim]{item.name}: 판정 실패 ({e})[/dim]")
    return verdicts


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@signal_app.callback(invoke_without_command=True)
def signal_main(
    ctx: typer.Context,
    ticker: Annotated[str | None, typer.Argument(help="종목코드 (비우면 전체 관심종목)")] = None,
) -> None:
    """종목 매수/매도 판정."""
    if ticker:
        matches = resolve_ticker(ticker)
        if not matches:
            console.print(f"[red]'{ticker}' 종목을 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)

        info = matches[0]
        watchlist = repo.watchlist_list()
        mode = _resolve_market_mode(watchlist)

        with console.status(f"[cyan]{info.name} 분석 중 (모드: {mode.value})...[/cyan]"):
            verdict = build_stock_verdict(info.ticker, info.name, info.market, mode)

        console.print()
        console.print(build_stock_verdict_panel(verdict))
        console.print()
        return

    items = repo.watchlist_list()
    if not items:
        console.print(
            "[dim]관심종목이 없습니다. ivst watch add <종목> 으로 추가하세요.[/dim]"
        )
        raise typer.Exit()

    with console.status("[cyan]관심종목 분석 중...[/cyan]"):
        verdicts = generate_all_signals()

    if not verdicts:
        console.print("[red]분석 가능한 종목이 없습니다.[/red]")
        raise typer.Exit(1)

    console.print()
    console.print(_build_signal_table(verdicts))
    console.print()
