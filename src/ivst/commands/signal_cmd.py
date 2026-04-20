"""Signal command: show buy/sell signals for watchlist stocks."""

from typing import Annotated

import numpy as np
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ivst.analysis.signal import CompositeSignal, Signal, generate_signal
from ivst.data.resolver import resolve_ticker
from ivst.db import repo
from ivst.ui import colors
from ivst.ui.formatters import fmt_pct, fmt_price

console = Console()
signal_app = typer.Typer(help="매수/매도 시그널 분석")


def _fetch_ohlcv(ticker: str, market: str) -> tuple[np.ndarray, np.ndarray]:
    """Fetch OHLCV and return (closes, volumes) as numpy arrays."""
    if market == "KR":
        from ivst.data.kr_stock import fetch_kr_ohlcv
        records = fetch_kr_ohlcv(ticker, days=300)
    else:
        from ivst.data.us_stock import fetch_us_ohlcv
        records = fetch_us_ohlcv(ticker, period="1y")

    if not records:
        return np.array([]), np.array([])

    closes = np.array([r["close"] for r in records])
    volumes = np.array([r["volume"] for r in records])
    return closes, volumes


def _signal_style(signal: Signal) -> str:
    """Return Rich style string for a signal."""
    return {
        Signal.STRONG_BUY: colors.STRONG_BUY,
        Signal.BUY: colors.BUY,
        Signal.HOLD: colors.HOLD,
        Signal.SELL: colors.SELL,
        Signal.STRONG_SELL: colors.STRONG_SELL,
    }[signal]


def _build_signal_table(signals: list[CompositeSignal]) -> Panel:
    """Build a Rich table showing signals for all watchlist stocks."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("종목", width=16)
    table.add_column("현재가", justify="right", width=14)
    table.add_column("등락", justify="right", width=10)
    table.add_column("시그널", justify="center", width=14)
    table.add_column("신뢰도", justify="right", width=10)

    for sig in signals:
        price_style = colors.PRICE_UP if sig.price_change_pct >= 0 else colors.PRICE_DOWN
        sig_style = _signal_style(sig.signal)

        table.add_row(
            f"{sig.name}",
            f"[{price_style}]{fmt_price(sig.current_price, sig.market)}[/]",
            f"[{price_style}]{fmt_pct(sig.price_change_pct)}[/]",
            f"[{sig_style}]{sig.signal.value}[/]",
            f"{sig.confidence:.0f}%",
        )

    return Panel(table, title="Watchlist Signals", border_style="blue")


def _build_detail_panel(sig: CompositeSignal) -> Panel:
    """Build a detail panel for one stock showing all indicators."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("지표", width=14)
    table.add_column("신호", justify="center", width=10)
    table.add_column("강도", justify="right", width=10)
    table.add_column("상세", width=40)

    for ind in sig.indicators:
        dir_text = {1: "[green]BUY[/]", -1: "[red]SELL[/]", 0: "[yellow]HOLD[/]"}[
            ind.direction.value
        ]
        table.add_row(
            ind.name,
            dir_text,
            f"{ind.strength:.0%}",
            ind.detail,
        )

    sig_style = _signal_style(sig.signal)
    price_style = colors.PRICE_UP if sig.price_change_pct >= 0 else colors.PRICE_DOWN

    header = (
        f"[bold]{sig.name}[/bold] ({sig.ticker}) | "
        f"[{price_style}]{fmt_price(sig.current_price, sig.market)} "
        f"({fmt_pct(sig.price_change_pct)})[/] | "
        f"[{sig_style}]{sig.signal.value}[/] (신뢰도 {sig.confidence:.0f}%)"
    )

    return Panel(table, title=header, border_style="blue")


def generate_all_signals() -> list[CompositeSignal]:
    """Generate signals for all watchlist stocks."""
    items = repo.watchlist_list()
    signals = []

    for item in items:
        try:
            closes, volumes = _fetch_ohlcv(item.ticker, item.market)
            if len(closes) == 0:
                continue
            sig = generate_signal(
                item.ticker, item.name, item.market, closes, volumes
            )
            signals.append(sig)
        except Exception as e:
            console.print(f"[dim]{item.name}: 데이터 수집 실패 ({e})[/dim]")

    return signals


@signal_app.callback(invoke_without_command=True)
def signal_main(
    ctx: typer.Context,
    ticker: Annotated[str | None, typer.Argument(help="종목코드 (없으면 전체 관심종목)")] = None,
) -> None:
    """관심종목의 매수/매도 시그널을 분석합니다."""
    if ticker:
        matches = resolve_ticker(ticker)
        if not matches:
            console.print(f"[red]'{ticker}' 종목을 찾을 수 없습니다.[/red]")
            raise typer.Exit(1)

        info = matches[0]
        with console.status(f"[cyan]{info.name} 분석 중...[/cyan]"):
            closes, volumes = _fetch_ohlcv(info.ticker, info.market)
            if len(closes) == 0:
                console.print(f"[red]{info.name}: 가격 데이터 없음[/red]")
                raise typer.Exit(1)

            sig = generate_signal(
                info.ticker, info.name, info.market, closes, volumes
            )

        console.print()
        console.print(_build_detail_panel(sig))
        console.print()
    else:
        items = repo.watchlist_list()
        if not items:
            console.print("[dim]관심종목이 없습니다. ivst watch add <종목> 으로 추가하세요.[/dim]")
            raise typer.Exit()

        with console.status("[cyan]관심종목 분석 중...[/cyan]"):
            signals = generate_all_signals()

        if signals:
            console.print()
            console.print(_build_signal_table(signals))
            console.print()
