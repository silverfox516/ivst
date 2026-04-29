"""Threshold adapters for per-stock sub-signals.

Pure functions: numeric reading → {-1, 0, +1}. These sit between
`analysis/indicators.py` / yfinance financials and the stock aggregator in
`analysis/stock.py`. Move to YAML config later if tuning friction grows.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# Price vs 200-day moving average. Margin avoids chop near the line.
PRICE_VS_200DMA_MARGIN = 0.03  # ±3%

# RSI(14): classic 30/70.
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0

# Volume: 5d vs 20d average.
VOLUME_SURGE_RATIO = 1.30
VOLUME_DRY_RATIO = 0.70

# PER vs sector median.
PER_CHEAP_RATIO = 0.80
PER_EXPENSIVE_RATIO = 1.30

# ROE.
ROE_GOOD_PCT = 15.0
ROE_WARN_PCT = 8.0

# Debt / equity (%).
DEBT_SAFE_PCT = 50.0
DEBT_HIGH_PCT = 100.0

# Earnings growth YoY (%).
EARNINGS_GROWTH_GOOD_PCT = 10.0
EARNINGS_GROWTH_FLAT_PCT = 0.0


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def price_vs_200dma_signal(price: float, sma200: float) -> int:
    """종목 주가 vs 200일선 (±3% dead-zone)."""
    if sma200 <= 0:
        return 0
    ratio = price / sma200 - 1.0
    if ratio >= PRICE_VS_200DMA_MARGIN:
        return +1
    if ratio <= -PRICE_VS_200DMA_MARGIN:
        return -1
    return 0


def rsi_signal(rsi14: float) -> int:
    """RSI(14): <=30 과매도 반등 후보(+1), >=70 과매수(-1), 그 사이 중립."""
    if rsi14 <= RSI_OVERSOLD:
        return +1
    if rsi14 >= RSI_OVERBOUGHT:
        return -1
    return 0


def macd_cross_signal(
    macd: float,
    signal: float,
    prev_macd: float,
    prev_signal: float,
) -> int:
    """MACD 골든크로스(+1) / 데드크로스(-1), 유지 방향은 ±1로 반영."""
    if prev_macd <= prev_signal and macd > signal:
        return +1
    if prev_macd >= prev_signal and macd < signal:
        return -1
    if macd > signal:
        return +1
    if macd < signal:
        return -1
    return 0


def volume_surge_signal(avg5: float, avg20: float) -> int:
    """거래량 5일 평균이 20일 평균 대비 +30% 이상 → 매집(+1), -30% 이하 → 건조(-1)."""
    if avg20 <= 0:
        return 0
    ratio = avg5 / avg20
    if ratio >= VOLUME_SURGE_RATIO:
        return +1
    if ratio <= VOLUME_DRY_RATIO:
        return -1
    return 0


def per_signal(per: float, sector_median_per: float) -> int:
    """PER: 업종 중앙값 대비 저평가(+1) / 고평가(-1). 적자(PER<=0)는 중립."""
    if per <= 0:
        return 0
    if sector_median_per <= 0:
        return 0
    ratio = per / sector_median_per
    if ratio <= PER_CHEAP_RATIO:
        return +1
    if ratio >= PER_EXPENSIVE_RATIO:
        return -1
    return 0


def roe_signal(roe_pct: float) -> int:
    """ROE ≥15% 우수(+1) / ≤8% 경계(-1)."""
    if roe_pct >= ROE_GOOD_PCT:
        return +1
    if roe_pct <= ROE_WARN_PCT:
        return -1
    return 0


def debt_ratio_signal(debt_to_equity_pct: float) -> int:
    """부채비율(자본 대비) <50% 안전(+1) / >100% 경계(-1)."""
    if debt_to_equity_pct < DEBT_SAFE_PCT:
        return +1
    if debt_to_equity_pct > DEBT_HIGH_PCT:
        return -1
    return 0


def earnings_growth_signal(yoy_growth_pct: float) -> int:
    """매출·이익 YoY 성장률 ≥10% 양호(+1) / ≤0% 역성장(-1)."""
    if yoy_growth_pct >= EARNINGS_GROWTH_GOOD_PCT:
        return +1
    if yoy_growth_pct <= EARNINGS_GROWTH_FLAT_PCT:
        return -1
    return 0
