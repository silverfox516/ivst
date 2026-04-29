"""Technical indicators using pure numpy. All functions are pure: arrays in, result out."""

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Direction(Enum):
    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass(frozen=True)
class IndicatorResult:
    name: str
    direction: Direction
    strength: float  # 0.0 - 1.0
    detail: str


def calc_rsi(closes: np.ndarray, period: int = 14) -> IndicatorResult:
    """Calculate RSI and return a signal.

    RSI < 30 -> BUY (oversold), RSI > 70 -> SELL (overbought).
    """
    if len(closes) < period + 1:
        return IndicatorResult("RSI", Direction.HOLD, 0.0, "데이터 부족")

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        rsi = 100.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))

    if rsi < 30:
        strength = (30.0 - rsi) / 30.0
        return IndicatorResult("RSI", Direction.BUY, strength, f"RSI {rsi:.1f} (과매도)")
    elif rsi > 70:
        strength = (rsi - 70.0) / 30.0
        return IndicatorResult("RSI", Direction.SELL, strength, f"RSI {rsi:.1f} (과매수)")
    else:
        return IndicatorResult("RSI", Direction.HOLD, 0.0, f"RSI {rsi:.1f}")


def calc_macd(
    closes: np.ndarray, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> IndicatorResult:
    """Calculate MACD crossover signal."""
    if len(closes) < slow + signal_period:
        return IndicatorResult("MACD", Direction.HOLD, 0.0, "데이터 부족")

    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    macd_line = ema_fast - ema_slow
    signal_line = _ema(macd_line, signal_period)
    histogram = macd_line - signal_line

    current_hist = histogram[-1]
    prev_hist = histogram[-2] if len(histogram) > 1 else 0

    if prev_hist <= 0 < current_hist:
        strength = min(abs(current_hist) / (abs(closes[-1]) * 0.01 + 1e-10), 1.0)
        return IndicatorResult(
            "MACD", Direction.BUY, strength,
            f"MACD 상향돌파 (히스토그램: {current_hist:.2f})"
        )
    elif prev_hist >= 0 > current_hist:
        strength = min(abs(current_hist) / (abs(closes[-1]) * 0.01 + 1e-10), 1.0)
        return IndicatorResult(
            "MACD", Direction.SELL, strength,
            f"MACD 하향돌파 (히스토그램: {current_hist:.2f})"
        )
    else:
        return IndicatorResult(
            "MACD", Direction.HOLD, 0.0,
            f"MACD 히스토그램: {current_hist:.2f}"
        )


def calc_bollinger(
    closes: np.ndarray, period: int = 20, num_std: float = 2.0
) -> IndicatorResult:
    """Calculate Bollinger Band signal."""
    if len(closes) < period:
        return IndicatorResult("볼린저", Direction.HOLD, 0.0, "데이터 부족")

    window = closes[-period:]
    middle = np.mean(window)
    std = np.std(window, ddof=1)
    upper = middle + num_std * std
    lower = middle - num_std * std
    current = closes[-1]

    band_width = upper - lower
    if band_width == 0:
        return IndicatorResult("볼린저", Direction.HOLD, 0.0, "밴드폭 없음")

    if current <= lower:
        strength = min((lower - current) / (band_width * 0.5 + 1e-10), 1.0)
        return IndicatorResult(
            "볼린저", Direction.BUY, strength,
            f"하단밴드 터치 ({current:,.0f} <= {lower:,.0f})"
        )
    elif current >= upper:
        strength = min((current - upper) / (band_width * 0.5 + 1e-10), 1.0)
        return IndicatorResult(
            "볼린저", Direction.SELL, strength,
            f"상단밴드 터치 ({current:,.0f} >= {upper:,.0f})"
        )
    else:
        return IndicatorResult(
            "볼린저", Direction.HOLD, 0.0,
            f"밴드 내 ({lower:,.0f} < {current:,.0f} < {upper:,.0f})"
        )


def calc_sma_crossover(
    closes: np.ndarray, short: int = 50, long: int = 200, lookback: int = 5
) -> IndicatorResult:
    """Detect golden cross / death cross within recent lookback days."""
    if len(closes) < long + lookback:
        return IndicatorResult("SMA크로스", Direction.HOLD, 0.0, "데이터 부족")

    sma_short = _sma(closes, short)
    sma_long = _sma(closes, long)

    for i in range(-lookback, 0):
        prev_diff = sma_short[i - 1] - sma_long[i - 1]
        curr_diff = sma_short[i] - sma_long[i]

        if prev_diff <= 0 < curr_diff:
            return IndicatorResult(
                "SMA크로스", Direction.BUY, 1.0,
                f"골든크로스 (SMA{short} > SMA{long})"
            )
        elif prev_diff >= 0 > curr_diff:
            return IndicatorResult(
                "SMA크로스", Direction.SELL, 1.0,
                f"데드크로스 (SMA{short} < SMA{long})"
            )

    diff = sma_short[-1] - sma_long[-1]
    if diff > 0:
        detail = f"SMA{short} > SMA{long} (상승 추세)"
    else:
        detail = f"SMA{short} < SMA{long} (하락 추세)"

    return IndicatorResult("SMA크로스", Direction.HOLD, 0.0, detail)


def calc_volume_surge(
    volumes: np.ndarray, period: int = 20, threshold: float = 2.0
) -> IndicatorResult:
    """Detect unusual volume (amplifier signal, not directional)."""
    if len(volumes) < period + 1:
        return IndicatorResult("거래량", Direction.HOLD, 0.0, "데이터 부족")

    avg_vol = np.mean(volumes[-period - 1 : -1])
    current_vol = volumes[-1]

    if avg_vol == 0:
        return IndicatorResult("거래량", Direction.HOLD, 0.0, "거래량 없음")

    ratio = current_vol / avg_vol

    if ratio >= threshold:
        strength = min((ratio - 1.0) / threshold, 1.0)
        return IndicatorResult(
            "거래량", Direction.HOLD, strength,
            f"거래량 급증 ({ratio:.1f}x 평균)"
        )
    else:
        return IndicatorResult(
            "거래량", Direction.HOLD, 0.0,
            f"거래량 정상 ({ratio:.1f}x 평균)"
        )


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Calculate Exponential Moving Average."""
    multiplier = 2.0 / (period + 1)
    ema = np.zeros_like(data, dtype=float)
    ema[0] = data[0]
    for i in range(1, len(data)):
        ema[i] = data[i] * multiplier + ema[i - 1] * (1 - multiplier)
    return ema


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    """Calculate Simple Moving Average."""
    sma = np.full_like(data, np.nan, dtype=float)
    cumsum = np.cumsum(data, dtype=float)
    sma[period - 1 :] = (cumsum[period - 1 :] - np.concatenate(([0], cumsum[:-period]))) / period
    return sma
