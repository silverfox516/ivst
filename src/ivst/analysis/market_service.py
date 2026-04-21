"""Assemble MarketVerdict for each asset class.

Currently only the US equity market verdict is wired. KR/Gold/Silver were
removed from scope due to unreliable or missing data sources; per-stock
analysis for Korean tickers still works via stock_service.py.
"""

from __future__ import annotations

import statistics

from ivst.analysis import market_adapters as adapt
from ivst.analysis.market import (
    AssetClass,
    CoreIndicator,
    MarketVerdict,
    aggregate,
)
from ivst.analysis.recommend import score_sectors
from ivst.data.macro import (
    fetch_fred_indicators,
    fetch_latest_value,
    fetch_liquidity_snapshot,
)
from ivst.data.sentiment_index import fetch_fear_greed
from ivst.data.us_stock import fetch_us_ohlcv


_SP500_SYMBOL = "^GSPC"


# Offensive vs defensive sector labels (US ETF sector map).
_OFFENSIVE_SECTORS = {"Technology", "Consumer Disc.", "Industrials"}
_DEFENSIVE_SECTORS = {"Utilities", "Consumer Staples", "Healthcare"}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / float(window)


def _sector_rotation_pct() -> tuple[float, float] | None:
    """Return (offensive_avg_1m_return, defensive_avg_1m_return) or None."""
    sectors = score_sectors("US")
    if not sectors:
        return None

    off = [s.return_1m for s in sectors if s.name in _OFFENSIVE_SECTORS]
    dfn = [s.return_1m for s in sectors if s.name in _DEFENSIVE_SECTORS]
    if not off or not dfn:
        return None
    return statistics.mean(off), statistics.mean(dfn)


# ---------------------------------------------------------------------------
# US verdict
# ---------------------------------------------------------------------------


def build_us_verdict() -> MarketVerdict:
    indicators: list[CoreIndicator] = []

    # C1 (liquidity potential + direction) — split into BS / TGA / RRP.
    snap = fetch_liquidity_snapshot()
    if snap is not None:
        # C1_BS — Fed balance sheet 4w trend (QE/QT direction).
        bs_delta_mn = snap.walcl_now_mn - snap.walcl_4w_ago_mn
        bs_sig = adapt.fed_bs_trend_signal(bs_delta_mn)
        bs_delta_b = bs_delta_mn / 1_000.0
        indicators.append(CoreIndicator(
            code="C1_BS",
            name="Fed 대차대조표",
            value=snap.walcl_now_mn / 1_000_000.0,
            unit="T$",
            raw_signal=bs_sig,
            detail=f"4주 Δ {bs_delta_b:+.0f}B",
            resolution="주간",
            rule=f"4주 ≥+{adapt.FED_BS_TREND_THRESHOLD_MN/1000:.0f}B QE / ≤-{adapt.FED_BS_TREND_THRESHOLD_MN/1000:.0f}B QT",
        ))

        # C1_TGA — 재무부 잔고(연료) + 4주 변화(흐름).
        tga_delta_mn = snap.tga_now_mn - snap.tga_4w_ago_mn
        tga_sig = adapt.tga_potential_signal(snap.tga_now_mn, tga_delta_mn)
        tga_t = snap.tga_now_mn / 1_000_000.0
        tga_delta_b = tga_delta_mn / 1_000.0
        indicators.append(CoreIndicator(
            code="C1_TGA",
            name="TGA 잠재+방향",
            value=tga_t,
            unit="T$",
            raw_signal=tga_sig,
            detail=f"{tga_t:.2f}T$ · 4주 Δ {tga_delta_b:+.0f}B",
            resolution="주간",
            rule=f"잔량 ≥{adapt.TGA_HIGH_MN/1000:.0f}B(+) · ≤{adapt.TGA_LOW_MN/1000:.0f}B(-) / 4주 감소(+) · 증가(-)",
        ))

        # C1_RRP — MMF 주차장 잔고 + 방향.
        rrp_delta_bn = snap.rrp_now_bn - snap.rrp_4w_ago_bn
        rrp_sig = adapt.rrp_potential_signal(snap.rrp_now_bn, rrp_delta_bn)
        indicators.append(CoreIndicator(
            code="C1_RRP",
            name="RRP 잠재+방향",
            value=snap.rrp_now_bn,
            unit="B$",
            raw_signal=rrp_sig,
            detail=f"{snap.rrp_now_bn:.1f}B$ · 4주 Δ {rrp_delta_bn:+.1f}B",
            resolution="주간",
            rule=f"잔량 ≥{adapt.RRP_HIGH_BN:.0f}B(+) · ≤{adapt.RRP_LOW_BN:.0f}B(-) / 4주 감소(+) · 증가(-)",
        ))

    # C2 — S&P 500 vs 200DMA
    ohlcv = fetch_us_ohlcv(_SP500_SYMBOL, period="1y")
    if ohlcv:
        closes = [float(r["close"]) for r in ohlcv if r["close"]]
        sma200 = _sma(closes, 200)
        if closes and sma200:
            price = closes[-1]
            sig = adapt.index_vs_200dma_signal(price, sma200)
            ratio_pct = (price / sma200 - 1.0) * 100.0
            margin_pct = adapt.INDEX_VS_200DMA_MARGIN * 100.0
            indicators.append(CoreIndicator(
                code="C2",
                name="S&P500 / 200일선",
                value=price,
                unit="",
                raw_signal=sig,
                detail=f"{ratio_pct:+.1f}% (200일선 {sma200:.0f})",
                resolution="일일",
                rule=f"±{margin_pct:.1f}% 데드존 (위/아래)",
            ))

    # C3 — HY credit spread (FRED BAMLH0A0HYM2 is in %, convert to bp)
    hy_pct = fetch_latest_value("BAMLH0A0HYM2")
    if hy_pct is not None:
        spread_bp = hy_pct * 100.0
        sig = adapt.hy_credit_spread_signal(spread_bp)
        indicators.append(CoreIndicator(
            code="C3",
            name="HY 크레딧 스프레드",
            value=spread_bp,
            unit="bp",
            raw_signal=sig,
            detail=f"{spread_bp:.0f}bp",
            resolution="일일",
            rule=f"<{adapt.HY_SPREAD_SAFE_BP:.0f}bp 안정 / >{adapt.HY_SPREAD_WARN_BP:.0f}bp 경계",
        ))

    # C4 — Sector rotation
    sector = _sector_rotation_pct()
    if sector is not None:
        off_avg, def_avg = sector
        sig = adapt.sector_rotation_signal(off_avg, def_avg)
        indicators.append(CoreIndicator(
            code="C4",
            name="섹터 로테이션",
            value=off_avg - def_avg,
            unit="%p",
            raw_signal=sig,
            detail=f"공격 {off_avg:+.1f}% vs 방어 {def_avg:+.1f}%",
            resolution="일일",
            rule=f"공격-방어 스프레드 ±{adapt.SECTOR_ROTATION_MARGIN_PCT:.1f}%p",
        ))

    return aggregate(AssetClass.US, indicators)


# ---------------------------------------------------------------------------
# Context panel data (맥락 레이어 참고)
# ---------------------------------------------------------------------------


def fetch_context_indicators() -> list[tuple[str, float, str]]:
    """Return (name, value, unit) triples for the [맥락] panel.

    Prepends the CNN Fear & Greed reading (sentiment composite, supersedes
    VIX) and then appends the FRED macro snapshot. No threshold judgement —
    purely informational rows for the secondary block.
    """
    rows: list[tuple[str, float, str]] = []

    fg = fetch_fear_greed()
    if fg is not None:
        rating_suffix = f"  ({fg.rating})" if fg.rating else ""
        rows.append(("Fear & Greed", fg.score, rating_suffix))

    rows.extend((ind.name, ind.value, ind.unit) for ind in fetch_fred_indicators())
    return rows
