"""Rule-based stock recommendation engine: sector momentum + policy beneficiary + fundamentals."""

from dataclasses import dataclass

import yfinance as yf


@dataclass(frozen=True)
class SectorScore:
    name: str
    etf_ticker: str
    return_1m: float
    return_3m: float
    momentum_score: float
    policy_boost: bool


@dataclass(frozen=True)
class Recommendation:
    ticker: str
    name: str
    sector: str
    momentum_score: float
    policy_match: bool
    reason: str


# Sector ETF mappings
KR_SECTOR_ETFS = {
    "반도체": "091160.KS",       # KODEX 반도체
    "2차전지": "305720.KS",      # KODEX 2차전지
    "자동차": "091180.KS",       # KODEX 자동차
    "바이오": "244580.KS",       # KODEX 바이오
    "은행": "091170.KS",         # KODEX 은행
    "철강": "117680.KS",         # KODEX 철강
    "건설": "117700.KS",         # KODEX 건설
    "IT": "098560.KS",           # KODEX IT
}

US_SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Energy": "XLE",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Disc.": "XLY",
    "Consumer Staples": "XLP",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Communication": "XLC",
}

# Sector-to-stock mapping (representative stocks per sector)
KR_SECTOR_STOCKS = {
    "반도체": [("005930", "삼성전자"), ("000660", "SK하이닉스"), ("042700", "한미반도체")],
    "2차전지": [("373220", "LG에너지솔루션"), ("006400", "삼성SDI"), ("051910", "LG화학")],
    "자동차": [("005380", "현대차"), ("000270", "기아"), ("012330", "현대모비스")],
    "바이오": [("207940", "삼성바이오로직스"), ("068270", "셀트리온"), ("326030", "SK바이오팜")],
    "은행": [("105560", "KB금융"), ("055550", "신한지주"), ("086790", "하나금융지주")],
    "IT": [("035720", "카카오"), ("035420", "NAVER"), ("263750", "펄어비스")],
}

US_SECTOR_STOCKS = {
    "Technology": [("AAPL", "Apple"), ("MSFT", "Microsoft"), ("NVDA", "NVIDIA"), ("GOOGL", "Alphabet")],
    "Financials": [("JPM", "JPMorgan"), ("BAC", "Bank of America"), ("GS", "Goldman Sachs")],
    "Energy": [("XOM", "Exxon Mobil"), ("CVX", "Chevron"), ("COP", "ConocoPhillips")],
    "Healthcare": [("UNH", "UnitedHealth"), ("JNJ", "Johnson & Johnson"), ("LLY", "Eli Lilly")],
    "Industrials": [("CAT", "Caterpillar"), ("HON", "Honeywell"), ("UPS", "UPS")],
}

# Policy keyword -> sector mapping
POLICY_SECTOR_MAP = {
    "반도체 지원": ["반도체"], "반도체 보조금": ["반도체"], "AI 투자": ["반도체", "IT"],
    "금리 인하": ["건설", "Real Estate"], "금리 인상": ["은행", "Financials"],
    "친환경": ["2차전지"], "탄소중립": ["2차전지"], "전기차": ["2차전지", "자동차"],
    "국방비": ["방산"], "방위산업": ["방산"],
    "바이오": ["바이오", "Healthcare"], "신약": ["바이오", "Healthcare"],
    "infrastructure": ["Industrials", "Materials"],
    "rate cut": ["Real Estate", "Technology"],
    "rate hike": ["Financials"],
    "clean energy": ["2차전지"],
    "chip": ["반도체", "Technology"], "semiconductor": ["반도체", "Technology"],
}


def _calc_return(ticker: str, period: str) -> float | None:
    """Calculate return for a given period."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 2:
            return None
        start_price = float(hist["Close"].iloc[0])
        end_price = float(hist["Close"].iloc[-1])
        if start_price == 0:
            return None
        return (end_price - start_price) / start_price * 100.0
    except Exception:
        return None


def score_sectors(market: str = "ALL") -> list[SectorScore]:
    """Score sectors by momentum (1M/3M weighted average)."""
    sectors = []

    etf_map = {}
    if market in ("KR", "ALL"):
        etf_map.update({k: (v, "KR") for k, v in KR_SECTOR_ETFS.items()})
    if market in ("US", "ALL"):
        etf_map.update({k: (v, "US") for k, v in US_SECTOR_ETFS.items()})

    for sector_name, (etf_ticker, _mkt) in etf_map.items():
        r1m = _calc_return(etf_ticker, "1mo")
        r3m = _calc_return(etf_ticker, "3mo")

        if r1m is None:
            r1m = 0.0
        if r3m is None:
            r3m = 0.0

        score = 0.6 * r1m + 0.4 * r3m

        sectors.append(SectorScore(
            name=sector_name,
            etf_ticker=etf_ticker,
            return_1m=r1m,
            return_3m=r3m,
            momentum_score=score,
            policy_boost=False,
        ))

    sectors.sort(key=lambda s: s.momentum_score, reverse=True)
    return sectors


def detect_policy_sectors(news_texts: list[str]) -> set[str]:
    """Detect sectors that benefit from recent policy news."""
    boosted = set()
    combined = " ".join(news_texts).lower()

    for keyword, mapped_sectors in POLICY_SECTOR_MAP.items():
        if keyword.lower() in combined:
            boosted.update(mapped_sectors)

    return boosted


def generate_recommendations(
    news_texts: list[str] | None = None,
    market: str = "ALL",
    top_n: int = 8,
) -> list[Recommendation]:
    """Generate stock recommendations based on sector momentum and policy."""
    sectors = score_sectors(market)
    policy_sectors = detect_policy_sectors(news_texts or [])

    for i, s in enumerate(sectors):
        if s.name in policy_sectors:
            sectors[i] = SectorScore(
                name=s.name,
                etf_ticker=s.etf_ticker,
                return_1m=s.return_1m,
                return_3m=s.return_3m,
                momentum_score=s.momentum_score * 1.3,
                policy_boost=True,
            )

    sectors.sort(key=lambda s: s.momentum_score, reverse=True)
    top_sectors = sectors[:5]

    stock_map = {**KR_SECTOR_STOCKS, **US_SECTOR_STOCKS}
    recommendations = []

    for sector in top_sectors:
        stocks = stock_map.get(sector.name, [])
        for ticker, name in stocks[:2]:
            policy_text = ", 정책 수혜" if sector.policy_boost else ""
            reason = (
                f"{sector.name} 섹터 1개월 {sector.return_1m:+.1f}%, "
                f"3개월 {sector.return_3m:+.1f}% (모멘텀 상위){policy_text}"
            )
            recommendations.append(Recommendation(
                ticker=ticker,
                name=name,
                sector=sector.name,
                momentum_score=sector.momentum_score,
                policy_match=sector.policy_boost,
                reason=reason,
            ))

    recommendations.sort(key=lambda r: r.momentum_score, reverse=True)
    return recommendations[:top_n]
