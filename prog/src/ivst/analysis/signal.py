"""Composite signal scorer combining multiple technical indicators."""

from dataclasses import dataclass
from enum import Enum

import numpy as np

from ivst.analysis.indicators import (
    Direction,
    IndicatorResult,
    calc_bollinger,
    calc_macd,
    calc_rsi,
    calc_sma_crossover,
    calc_volume_surge,
)


class Signal(Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"


@dataclass(frozen=True)
class CompositeSignal:
    ticker: str
    name: str
    market: str
    signal: Signal
    score: float  # -1.0 to 1.0
    confidence: float  # 0-100%
    current_price: float
    price_change_pct: float
    indicators: tuple[IndicatorResult, ...]


WEIGHTS = {
    "RSI": 0.20,
    "MACD": 0.25,
    "볼린저": 0.20,
    "SMA크로스": 0.25,
    "거래량": 0.10,
}


def generate_signal(
    ticker: str,
    name: str,
    market: str,
    closes: np.ndarray,
    volumes: np.ndarray,
) -> CompositeSignal:
    """Generate a composite buy/sell signal from OHLCV data."""
    rsi = calc_rsi(closes)
    macd = calc_macd(closes)
    bollinger = calc_bollinger(closes)
    sma_cross = calc_sma_crossover(closes)
    volume = calc_volume_surge(volumes)

    indicators = (rsi, macd, bollinger, sma_cross, volume)

    raw_score = 0.0
    for ind in indicators:
        weight = WEIGHTS.get(ind.name, 0.0)
        if ind.name == "거래량":
            continue
        raw_score += weight * ind.strength * ind.direction.value

    if volume.strength > 0:
        raw_score *= 1.0 + 0.5 * volume.strength

    score = max(-1.0, min(1.0, raw_score))

    if score >= 0.6:
        signal = Signal.STRONG_BUY
    elif score >= 0.2:
        signal = Signal.BUY
    elif score > -0.2:
        signal = Signal.HOLD
    elif score > -0.6:
        signal = Signal.SELL
    else:
        signal = Signal.STRONG_SELL

    confidence = abs(score) * 100.0

    current_price = float(closes[-1]) if len(closes) > 0 else 0.0
    prev_price = float(closes[-2]) if len(closes) > 1 else current_price
    price_change_pct = (
        ((current_price - prev_price) / prev_price * 100.0)
        if prev_price != 0
        else 0.0
    )

    return CompositeSignal(
        ticker=ticker,
        name=name,
        market=market,
        signal=signal,
        score=score,
        confidence=confidence,
        current_price=current_price,
        price_change_pct=price_change_pct,
        indicators=indicators,
    )
