"""Keyword-based news sentiment classifier."""

from dataclasses import dataclass
from enum import Enum


class Sentiment(Enum):
    BULLISH = "호재"
    BEARISH = "악재"
    NEUTRAL = "중립"


BULLISH_KEYWORDS: dict[str, int] = {
    "실적 개선": 2, "실적 호조": 2, "매출 증가": 2, "영업이익 증가": 2,
    "순이익 증가": 2, "신규 수주": 2, "배당 확대": 1, "배당 인상": 1,
    "목표가 상향": 2, "투자의견 상향": 2, "흑자 전환": 3, "사상 최대": 2,
    "수주 잔고": 1, "신사업": 1, "합작": 1, "인수": 1, "성장": 1,
    "호실적": 2, "어닝서프라이즈": 3, "컨센서스 상회": 2, "상한가": 3,
    "급등": 2, "반등": 1, "매수": 1, "추천": 1,
    "beat": 2, "upgrade": 2, "record revenue": 2, "record profit": 2,
    "growth": 1, "bullish": 2, "outperform": 2, "buy rating": 2,
    "acquisition": 1, "partnership": 1, "dividend increase": 1,
    "all-time high": 2, "rally": 1, "surge": 2,
}

BEARISH_KEYWORDS: dict[str, int] = {
    "실적 부진": -2, "실적 악화": -2, "매출 감소": -2, "영업이익 감소": -2,
    "적자": -3, "적자 전환": -3, "목표가 하향": -2, "투자의견 하향": -2,
    "하향": -1, "리콜": -2, "소송": -1, "제재": -2, "벌금": -2,
    "감산": -1, "구조조정": -2, "감원": -1, "해고": -1,
    "어닝쇼크": -3, "컨센서스 하회": -2, "하한가": -3,
    "급락": -2, "폭락": -3, "매도": -1, "공매도": -1,
    "miss": -2, "downgrade": -2, "layoffs": -1, "recall": -2,
    "investigation": -1, "lawsuit": -1, "fine": -2, "bearish": -2,
    "underperform": -2, "sell rating": -2, "warning": -1,
    "crash": -3, "plunge": -2, "decline": -1,
}


@dataclass(frozen=True)
class SentimentResult:
    sentiment: Sentiment
    score: int
    matched_keywords: tuple[str, ...]


def classify_sentiment(text: str) -> SentimentResult:
    """Classify text as bullish/bearish/neutral using keyword matching."""
    text_lower = text.lower()
    score = 0
    matched = []

    for keyword, weight in BULLISH_KEYWORDS.items():
        if keyword.lower() in text_lower:
            score += weight
            matched.append(keyword)

    for keyword, weight in BEARISH_KEYWORDS.items():
        if keyword.lower() in text_lower:
            score += weight  # weight is already negative
            matched.append(keyword)

    if score > 0:
        sentiment = Sentiment.BULLISH
    elif score < 0:
        sentiment = Sentiment.BEARISH
    else:
        sentiment = Sentiment.NEUTRAL

    return SentimentResult(
        sentiment=sentiment, score=score, matched_keywords=tuple(matched)
    )
