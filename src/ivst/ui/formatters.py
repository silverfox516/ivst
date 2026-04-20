"""Number and display formatters."""


def fmt_krw(value: float) -> str:
    """Format as Korean Won: 72,300."""
    return f"{value:,.0f}"


def fmt_usd(value: float) -> str:
    """Format as USD: $198.42."""
    return f"${value:,.2f}"


def fmt_pct(value: float) -> str:
    """Format as percentage with arrow: +2.1% or -0.3%."""
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}%"


def fmt_price(value: float, market: str) -> str:
    """Format price based on market."""
    if market == "KR":
        return fmt_krw(value)
    return fmt_usd(value)
