"""Threshold adapters: turn raw numeric readings into -1/0/+1 signals.

These live on the seam between data sources (FRED, yfinance, pykrx) and the
pure aggregator in `analysis/market.py`. Keeping them as pure functions makes
the threshold choices testable and trivial to tune later (e.g. move to a
YAML config).

All adapters clamp to {-1, 0, +1}. Ambiguous / missing inputs should be
handled by the *caller* (prefer neutral 0 when in doubt — the aggregator
handles partial data by renormalizing).
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Thresholds — single source of truth. Adjust here (or lift to YAML later).
# ---------------------------------------------------------------------------

# Liquidity potential + direction — see plan.md §3-A.
# Philosophy: look at "fuel available to flow into markets" (levels) and
# "which way it's moving right now" (4-week change).

# Fed BS — direction only (QE / QT).
FED_BS_TREND_THRESHOLD_MN = 50_000.0   # $50B over 4 weeks flags direction

# TGA — Treasury General Account. Higher balance = more potential fuel to
# spend into the economy; lower = government needs to refill (drains markets).
TGA_HIGH_MN = 700_000.0                # >= $700B = high potential (bullish)
TGA_LOW_MN = 200_000.0                 # <= $200B = low potential (bearish)
TGA_FLOW_THRESHOLD_MN = 100_000.0      # 4w change > ±$100B flags direction

# RRP — Overnight Reverse Repo. Money parked at Fed; draining = flowing back
# into markets (bullish). Filling = being pulled out of markets (bearish).
RRP_HIGH_BN = 500.0                    # >= $500B = high potential (bullish)
RRP_LOW_BN = 50.0                      # <= $50B  = largely depleted
RRP_FLOW_THRESHOLD_BN = 50.0           # 4w change > ±$50B flags direction

# Index vs 200-day moving average (S&P500, KOSPI). Dead-zone near the line.
INDEX_VS_200DMA_MARGIN = 0.005  # 0.5%

# HY OAS credit spread — wider = stress.
HY_SPREAD_SAFE_BP = 400.0
HY_SPREAD_WARN_BP = 600.0

# Sector rotation: offensive vs defensive average return spread.
SECTOR_ROTATION_MARGIN_PCT = 1.0  # percentage points

# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def _clamp(x: int) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def fed_bs_trend_signal(delta_4w_mn: float) -> int:
    """Fed 대차대조표 4주 변화 → +1 QE / -1 QT / 0 보합.

    유동성 공급의 절대 수준보다 *방향* 이 타이밍에 더 중요.
    """
    if delta_4w_mn >= FED_BS_TREND_THRESHOLD_MN:
        return +1
    if delta_4w_mn <= -FED_BS_TREND_THRESHOLD_MN:
        return -1
    return 0


def tga_potential_signal(current_mn: float, delta_4w_mn: float) -> int:
    """TGA 잠재 유동성(잔량) + 현재 흐름(4주 변화) 합성.

    - 잔량 많음 = 앞으로 풀릴 연료 있음 → 매수 편향 (+)
    - 잔량 적음 = 곧 채워야 함 (시장에서 흡수) → 매도 편향 (-)
    - 감소 중 = 지금 지출되는 중 → 매수 편향 (+)
    - 증가 중 = 지금 빨아들이는 중 → 매도 편향 (-)

    두 시그널 합을 {-1, 0, +1} 로 clamp. 같은 방향이면 강한 ±1,
    엇갈리면 0.
    """
    level = +1 if current_mn >= TGA_HIGH_MN else -1 if current_mn <= TGA_LOW_MN else 0
    direction = (
        +1 if delta_4w_mn <= -TGA_FLOW_THRESHOLD_MN else
        -1 if delta_4w_mn >= +TGA_FLOW_THRESHOLD_MN else 0
    )
    return _clamp(level + direction)


def rrp_potential_signal(current_bn: float, delta_4w_bn: float) -> int:
    """RRP 잠재 유동성 + 현재 흐름. 논리는 TGA 와 동일.

    - 잔량 많음 = 시장으로 유입될 여력 있음 → 매수 편향 (+)
    - 잔량 적음 = 더 나올 게 없음 → 매도 편향 (-)
    - 감소 = 지금 시장 유입 중 → 매수 편향 (+)
    - 증가 = 지금 Fed 로 빨려감 → 매도 편향 (-)
    """
    level = +1 if current_bn >= RRP_HIGH_BN else -1 if current_bn <= RRP_LOW_BN else 0
    direction = (
        +1 if delta_4w_bn <= -RRP_FLOW_THRESHOLD_BN else
        -1 if delta_4w_bn >= +RRP_FLOW_THRESHOLD_BN else 0
    )
    return _clamp(level + direction)


def index_vs_200dma_signal(price: float, sma200: float) -> int:
    """S&P500 / KOSPI vs 200일선 — 위/아래 with dead-zone."""
    if sma200 <= 0:
        return 0
    ratio = price / sma200 - 1.0
    if ratio >= INDEX_VS_200DMA_MARGIN:
        return +1
    if ratio <= -INDEX_VS_200DMA_MARGIN:
        return -1
    return 0


def hy_credit_spread_signal(spread_bp: float) -> int:
    """HY OAS (bp): <400 안정(+1), >600 경계(-1), 그 사이 중립."""
    if spread_bp < HY_SPREAD_SAFE_BP:
        return +1
    if spread_bp > HY_SPREAD_WARN_BP:
        return -1
    return 0


def sector_rotation_signal(
    offensive_avg_return_pct: float,
    defensive_avg_return_pct: float,
) -> int:
    """공격(기술·소비재·산업재) vs 방어(유틸·필수·헬스) 평균 수익률 비교."""
    diff = offensive_avg_return_pct - defensive_avg_return_pct
    if diff >= SECTOR_ROTATION_MARGIN_PCT:
        return +1
    if diff <= -SECTOR_ROTATION_MARGIN_PCT:
        return -1
    return 0


