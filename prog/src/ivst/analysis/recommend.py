"""Rule-based stock recommendation engine: sector momentum + policy beneficiary + fundamentals."""

from dataclasses import dataclass

import yfinance as yf

from ivst.analysis.discovery import ScoredKRCandidate, ScreenMode, screen_kr_market


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
    warnings: tuple[str, ...] = ()


# Sector ETF mappings
KR_SECTOR_ETFS = {
    "반도체": "091160.KS",       # KODEX 반도체
    "2차전지": "305720.KS",      # KODEX 2차전지
    "자동차": "091180.KS",       # KODEX 자동차
    "바이오": "244580.KS",       # KODEX 바이오
    "은행": "091170.KS",         # KODEX 은행
    "철강": "117680.KS",         # KODEX 철강
    "건설": "117700.KS",         # KODEX 건설
    "IT": "139260.KS",           # TIGER 200 IT (KODEX IT 098560 상폐 대체)
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


# Policy-sector vocabulary (`POLICY_SECTOR_MAP` values) → KRX 업종명 substrings.
# KRX classifies semiconductors under "전기·전자", banks under "기타금융", etc.,
# so substring match against the raw policy token alone misses most cases.
_POLICY_TO_KRX_SECTOR = {
    "반도체": ("전기·전자", "전기전자"),
    "IT": ("서비스", "통신", "전기·전자"),
    "2차전지": ("화학", "전기·전자"),
    "자동차": ("운수장비", "자동차"),
    "건설": ("건설",),
    "은행": ("금융", "은행"),
    "바이오": ("의약품", "바이오"),
    "방산": ("운수장비", "기계"),
}


def _policy_boost_kr(sc: ScoredKRCandidate, policy_sectors: set[str]) -> tuple[float, bool]:
    """Apply 1.3x boost when KRX 업종명 or 종목명 maps to a policy sector token."""
    if not policy_sectors:
        return sc.score, False
    haystack = f"{sc.base.sector} {sc.base.name}".lower()
    for token in policy_sectors:
        token_lc = token.lower()
        if token_lc in haystack:
            return sc.score * 1.3, True
        for krx_term in _POLICY_TO_KRX_SECTOR.get(token, ()):
            if krx_term.lower() in haystack:
                return sc.score * 1.3, True
    return sc.score, False


def _kr_recommendations_dynamic(
    policy_sectors: set[str],
    top_n: int,
    mode: ScreenMode,
) -> list[Recommendation]:
    """Build KR recommendations from a live whole-market screen."""
    candidates = screen_kr_market(top_n=max(top_n * 3, 20), mode=mode)
    if not candidates:
        return []

    boosted: list[tuple[ScoredKRCandidate, float, bool]] = [
        (sc, *_policy_boost_kr(sc, policy_sectors)) for sc in candidates
    ]
    boosted.sort(key=lambda x: x[1], reverse=True)

    recs: list[Recommendation] = []
    for sc, score, policy in boosted[:top_n]:
        c = sc.base
        policy_text = ", 정책 수혜" if policy else ""
        reason = (
            f"{c.sector} | 1M {c.return_1m:+.1f}% / 3M {c.return_3m:+.1f}% "
            f"| PER {c.per:.1f} PBR {c.pbr:.1f}{policy_text}"
        )
        recs.append(Recommendation(
            ticker=c.ticker,
            name=c.name,
            sector=c.sector,
            momentum_score=score,
            policy_match=policy,
            reason=reason,
            warnings=sc.warnings,
        ))
    return recs


def _us_recommendations_static(
    policy_sectors: set[str],
    top_n: int,
) -> list[Recommendation]:
    """Existing static US path: sector ETF momentum + hardcoded representatives."""
    sectors = score_sectors("US")
    if not sectors:
        return []

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

    recs: list[Recommendation] = []
    for sector in top_sectors:
        for ticker, name in US_SECTOR_STOCKS.get(sector.name, [])[:2]:
            policy_text = ", 정책 수혜" if sector.policy_boost else ""
            reason = (
                f"{sector.name} 섹터 1개월 {sector.return_1m:+.1f}%, "
                f"3개월 {sector.return_3m:+.1f}% (모멘텀 상위){policy_text}"
            )
            recs.append(Recommendation(
                ticker=ticker,
                name=name,
                sector=sector.name,
                momentum_score=sector.momentum_score,
                policy_match=sector.policy_boost,
                reason=reason,
            ))
    return recs[:top_n]


def generate_recommendations(
    news_texts: list[str] | None = None,
    market: str = "ALL",
    top_n: int = 8,
    mode: ScreenMode = "balanced",
) -> list[Recommendation]:
    """Generate stock recommendations.

    KR side uses live KRX whole-market screening with the requested mode
    (`momentum` / `value` / `balanced`). US side keeps the sector-ETF +
    representatives approach until a US screener is added; `mode` does
    not affect the US slate.
    """
    policy_sectors = detect_policy_sectors(news_texts or [])
    market_u = market.upper()

    if market_u == "KR":
        return _kr_recommendations_dynamic(policy_sectors, top_n, mode)
    if market_u == "US":
        return _us_recommendations_static(policy_sectors, top_n)

    # ALL: split slots so KR per-stock momentum doesn't crowd out US ETF picks,
    # which sit on a much smaller numeric scale.
    kr_slots = top_n // 2
    us_slots = top_n - kr_slots
    kr = _kr_recommendations_dynamic(policy_sectors, kr_slots, mode)
    us = _us_recommendations_static(policy_sectors, us_slots)
    return kr + us
