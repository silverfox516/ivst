"""Rich panel and table builders for CLI output."""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ivst.analysis.market import MarketVerdict, Verdict
from ivst.analysis.stock import Signal5, StockVerdict
from ivst.db.models import WatchItem


_FRED_SOURCED_CODES = {
    "C1", "C3", "REALRATE_INV", "PMI",
}


def build_watchlist_table(items: list[WatchItem]) -> Panel:
    """Build a Rich table panel for the watchlist."""
    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("종목코드", width=10)
    table.add_column("종목명", width=20)
    table.add_column("시장", width=8)
    table.add_column("등록일", width=12)

    for i, item in enumerate(items, 1):
        table.add_row(
            str(i),
            item.ticker,
            item.name,
            item.market,
            item.added_at[:10],
        )

    if not items:
        table.add_row("", "", "[dim]관심종목이 없습니다[/dim]", "", "")

    return Panel(table, title="관심종목", border_style="blue")


# ---------------------------------------------------------------------------
# Market verdict rendering
# ---------------------------------------------------------------------------


_VERDICT_ICON = {
    Verdict.BULLISH: "🟢",
    Verdict.MIXED:   "🟡",
    Verdict.BEARISH: "🔴",
}


def _signal_icon(raw: int) -> str:
    if raw > 0:
        return "🟢"
    if raw < 0:
        return "🔴"
    return "🟡"


def _verdict_border(verdict: Verdict) -> str:
    return {
        Verdict.BULLISH: "green",
        Verdict.MIXED:   "yellow",
        Verdict.BEARISH: "red",
    }[verdict]


def _sig_color(raw: int) -> str:
    if raw > 0:
        return "green"
    if raw < 0:
        return "red"
    return "yellow"


def _contrib_color(contrib: float) -> str:
    if contrib > 0:
        return "green"
    if contrib < 0:
        return "red"
    return "dim"


def _setup_hint_for(missing: tuple[str, ...]) -> Text | None:
    """Produce a one-line hint when FRED-sourced indicators fail.

    FRED CSV endpoint is keyless — the usual cause of these missing values
    is a network failure or temporary FRED outage, not misconfiguration.
    """
    fred_missing = [m for m in missing if m in _FRED_SOURCED_CODES]
    if not fred_missing:
        return None
    hint = Text()
    hint.append("💡 ", style="yellow")
    hint.append(
        f"{', '.join(fred_missing)} 은 FRED(무료·키 불필요)에서 자동 수집. "
        "네트워크 또는 FRED 일시 오류일 가능성 — 다시 실행해 보세요.",
        style="dim",
    )
    return hint


def _trunc(s: str, width: int) -> str:
    if len(s) <= width:
        return s
    return s[: max(0, width - 1)] + "…"


def build_verdict_panel(verdict: MarketVerdict, title: str) -> Panel:
    """Render a MarketVerdict as a [코어] panel. 2 lines per indicator keeps
    every value readable on an 80-wide terminal with no truncation."""
    border_style = _verdict_border(verdict.verdict)

    # Header
    header = Text()
    header.append(title, style="bold")
    header.append("\n")
    header.append(f"{_VERDICT_ICON[verdict.verdict]} ", style="")
    header.append(verdict.verdict.value, style=f"bold {border_style}")
    header.append(f"   총점 {verdict.total_score:+.2f}", style="bold")
    header.append(f"   모드 {verdict.mode.value}", style="bold")
    if verdict.context_alert:
        header.append("   ⚠ 맥락 경고로 1단계 하향", style="yellow")

    body: list = [header]

    if not verdict.indicators:
        body.append(Text(""))
        body.append(Text("  데이터 없음 — 아래 설정 안내 참고", style="dim"))
    else:
        contrib_by_code = {c.code: c for c in verdict.contributions}
        for ind in verdict.indicators:
            c = contrib_by_code.get(ind.code)
            contrib_val = c.contribution if c else 0.0
            body.append(Text(""))

            # Line 1: icon · name · current value
            value_str = f"{ind.value:,.2f}{ind.unit}" if ind.unit else f"{ind.value:,.2f}"
            l1 = Text()
            l1.append(f"{_signal_icon(ind.raw_signal)} ", style="")
            l1.append(ind.name, style="bold")
            l1.append("    ")
            l1.append(value_str, style="bold")
            body.append(l1)

            # Line 2: observation (+ resolution tag) → verdict + contribution
            l2 = Text()
            l2.append("   ")
            l2.append(ind.detail, style="")
            l2.append(f"  [{ind.resolution}]", style="dim")
            l2.append("   →  ", style="dim")
            l2.append(_sig_label(ind.raw_signal), style=f"bold {_sig_color(ind.raw_signal)}")
            l2.append(f"  기여 {contrib_val:+.2f}", style=_contrib_color(contrib_val))
            body.append(l2)

            # Line 3: rule
            l3 = Text()
            l3.append("   기준: ", style="dim")
            l3.append(ind.rule or "—", style="dim")
            body.append(l3)

    # Missing + setup hint
    if verdict.missing_codes:
        body.append(Text(""))
        miss = Text()
        miss.append("누락: ", style="dim")
        miss.append(", ".join(verdict.missing_codes), style="yellow")
        miss.append("  (분모 자동 정규화)", style="dim")
        body.append(miss)
        hint = _setup_hint_for(verdict.missing_codes)
        if hint is not None:
            body.append(hint)

    return Panel(
        Group(*body),
        title=None,
        border_style=border_style,
        padding=(1, 1),
    )


def _sig_label(raw: int) -> str:
    if raw > 0:
        return "우호"
    if raw < 0:
        return "비우호"
    return "중립"


_SIGNAL5_STYLE = {
    Signal5.STRONG_BUY:  ("bold bright_green", "🟢🟢"),
    Signal5.BUY:         ("green",             "🟢"),
    Signal5.HOLD:        ("yellow",            "🟡"),
    Signal5.SELL:        ("red",               "🔴"),
    Signal5.STRONG_SELL: ("bold bright_red",   "🔴🔴"),
}


def build_stock_verdict_panel(verdict: StockVerdict) -> Panel:
    """Render a per-stock StockVerdict with one aligned text row per sub-signal,
    grouped by block, with explicit `기준` column."""
    style, icon = _SIGNAL5_STYLE[verdict.signal]
    border = {
        Signal5.STRONG_BUY:  "bright_green",
        Signal5.BUY:         "green",
        Signal5.HOLD:        "yellow",
        Signal5.SELL:        "red",
        Signal5.STRONG_SELL: "bright_red",
    }[verdict.signal]

    lines: list = []

    # Header.
    header = Text()
    header.append(f"{verdict.name} ({verdict.ticker})", style="bold")
    header.append("\n")
    header.append(f"{icon} ", style="")
    header.append(verdict.signal.value, style=f"bold {border}")
    header.append(f"   총점 {verdict.total_score:+.2f}", style="bold")
    header.append(f"   모드 {verdict.mode.value}", style="bold")
    if verdict.mode_mismatch_warning:
        header.append("   ⚠ 관망 모드: 매수 신호 하향", style="yellow")
    lines.append(header)

    contrib_by_code = {c.code: c for c in verdict.contributions}
    for block in verdict.blocks:
        c = contrib_by_code.get(block.code)
        contrib_val = c.contribution if c else 0.0

        # Block heading.
        lines.append(Text(""))
        block_hdr = Text()
        block_hdr.append(f"▎{block.code} · {block.name}  ", style="bold cyan")
        block_hdr.append(f"블록 점수 {block.block_score:+.2f}", style="cyan")
        block_hdr.append(f"   기여 {contrib_val:+.2f}", style=_contrib_color(contrib_val))
        lines.append(block_hdr)

        if not block.sub_signals:
            lines.append(Text("  데이터 없음", style="dim"))
            continue

        for s in block.sub_signals:
            l1 = Text()
            l1.append(f"  {_signal_icon(s.raw_signal)} ", style="")
            l1.append(s.name, style="bold")
            l1.append(f"  {s.detail}", style="")
            lines.append(l1)
            l2 = Text()
            l2.append("     기준: ", style="dim")
            l2.append(s.rule or "—", style="dim")
            lines.append(l2)

    return Panel(
        Group(*lines),
        title=None,
        border_style=border,
        padding=(1, 1),
    )


def build_context_panel(rows: list[tuple[str, float, str]]) -> Panel | None:
    """Render the [맥락] supplementary panel (FRED indicators, VIX, etc.).

    Returns None when there's nothing to show so the caller can skip it.
    """
    if not rows:
        return None

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("지표", width=20)
    table.add_column("값", justify="right", width=12)

    for name, value, unit in rows:
        table.add_row(name, f"{value:.2f}{unit}")

    return Panel(table, title="[맥락] 참고 지표 (FRED)", border_style="blue")
