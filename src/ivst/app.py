"""Root Typer application."""

import typer
from rich.console import Console

from ivst.commands.market import market_app
from ivst.commands.news_cmd import news_app
from ivst.commands.note import note_app
from ivst.commands.portfolio import portfolio_app
from ivst.commands.recommend_cmd import recommend_app
from ivst.commands.signal_cmd import signal_app
from ivst.commands.watch import watch_app
from ivst.db.engine import init_db

console = Console()

app = typer.Typer(
    name="ivst",
    help="IVST - 자동 투자 분석 어시스턴트",
    no_args_is_help=False,
    invoke_without_command=True,
)
app.add_typer(watch_app, name="watch")
app.add_typer(signal_app, name="signal")
app.add_typer(market_app, name="market")
app.add_typer(news_app, name="news")
app.add_typer(recommend_app, name="recommend")
app.add_typer(portfolio_app, name="portfolio")
app.add_typer(note_app, name="note")


@app.callback(invoke_without_command=True)
def main_callback(ctx: typer.Context) -> None:
    """IVST - 관심종목 등록 한 번이면 매수/매도 시그널, 뉴스, 시장 지표를 자동 분석합니다."""
    init_db()
    if ctx.invoked_subcommand is None:
        from ivst.commands.dashboard import show_dashboard
        show_dashboard()


def main() -> None:
    app()
