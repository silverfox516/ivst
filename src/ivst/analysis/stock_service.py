"""Assemble a StockVerdict for a single ticker.

Glue between raw data (yfinance / pykrx / existing indicators) and the pure
per-stock aggregator in `analysis/stock.py`. Missing data simply produces
fewer sub-signals — block_score averages only what's there.
"""

from __future__ import annotations

import numpy as np

from ivst.analysis import stock_adapters as adapt
from ivst.analysis.indicators import (
    Direction,
    calc_macd,
    calc_rsi,
    calc_sma_crossover,
    calc_volume_surge,
)
from ivst.analysis.market import Mode
from ivst.analysis.recommend import score_sectors
from ivst.analysis.stock import (
    StockBlock,
    StockSubSignal,
    StockVerdict,
    aggregate_stock,
    make_block,
)
from ivst.data.kr_stock import fetch_kr_ohlcv
from ivst.data.us_stock import fetch_us_ohlcv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dir_to_signal(d: Direction) -> int:
    return {Direction.BUY: 1, Direction.SELL: -1, Direction.HOLD: 0}[d]


def _fetch_info_us(ticker: str) -> dict:
    try:
        import yfinance as yf  # type: ignore[import-untyped]
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Block builders
# ---------------------------------------------------------------------------


def _trend_block(closes: np.ndarray, volumes: np.ndarray) -> StockBlock:
    subs: list[StockSubSignal] = []

    if len(closes) >= 200:
        price = float(closes[-1])
        sma200 = float(closes[-200:].mean())
        sig = adapt.price_vs_200dma_signal(price, sma200)
        ratio_pct = (price / sma200 - 1.0) * 100.0
        margin_pct = adapt.PRICE_VS_200DMA_MARGIN * 100.0
        subs.append(StockSubSignal(
            name="주가/200일선",
            value=price,
            unit="",
            raw_signal=sig,
            detail=f"{ratio_pct:+.1f}% (200일선 {sma200:.2f})",
            rule=f"±{margin_pct:.0f}% 데드존",
        ))

    rsi_res = calc_rsi(closes, period=14)
    if rsi_res.detail != "데이터 부족":
        subs.append(StockSubSignal(
            name="RSI(14)",
            value=0.0,
            unit="",
            raw_signal=_dir_to_signal(rsi_res.direction),
            detail=rsi_res.detail,
            rule=f"≤{adapt.RSI_OVERSOLD:.0f} 과매도 +1 / ≥{adapt.RSI_OVERBOUGHT:.0f} 과매수 -1",
        ))

    macd_res = calc_macd(closes)
    if macd_res.detail != "데이터 부족":
        subs.append(StockSubSignal(
            name="MACD",
            value=0.0,
            unit="",
            raw_signal=_dir_to_signal(macd_res.direction),
            detail=macd_res.detail,
            rule="히스토그램 0 상향/하향 돌파",
        ))

    sma_res = calc_sma_crossover(closes)
    if sma_res.detail != "데이터 부족":
        subs.append(StockSubSignal(
            name="SMA 크로스",
            value=0.0,
            unit="",
            raw_signal=_dir_to_signal(sma_res.direction),
            detail=sma_res.detail,
            rule="50일선 vs 200일선",
        ))

    if len(volumes) >= 20:
        vol_res = calc_volume_surge(volumes.astype(float))
        if vol_res.detail != "데이터 부족":
            subs.append(StockSubSignal(
                name="거래량",
                value=0.0,
                unit="",
                raw_signal=_dir_to_signal(vol_res.direction),
                detail=vol_res.detail,
                rule="5일/20일 평균 비율",
            ))

    return make_block("TREND", "추세·가격", subs)


def _value_block(info: dict) -> StockBlock:
    subs: list[StockSubSignal] = []

    per = info.get("trailingPE")
    if per is not None and per > 0:
        anchor = info.get("forwardPE") or 18.0
        try:
            anchor_f = float(anchor) if anchor and anchor > 0 else 18.0
        except (TypeError, ValueError):
            anchor_f = 18.0
        per_f = float(per)
        sig = adapt.per_signal(per_f, anchor_f)
        subs.append(StockSubSignal(
            name="PER",
            value=per_f,
            unit="",
            raw_signal=sig,
            detail=f"{per_f:.1f} (기준 {anchor_f:.1f})",
            rule=f"기준 ×{adapt.PER_CHEAP_RATIO:.2f} 이하 저평가 / ×{adapt.PER_EXPENSIVE_RATIO:.2f} 이상 고평가",
        ))

    roe = info.get("returnOnEquity")
    if roe is not None:
        try:
            roe_pct = float(roe) * 100.0
            sig = adapt.roe_signal(roe_pct)
            subs.append(StockSubSignal(
                name="ROE",
                value=roe_pct,
                unit="%",
                raw_signal=sig,
                detail=f"{roe_pct:.1f}%",
                rule=f"≥{adapt.ROE_GOOD_PCT:.0f}% 우수 / ≤{adapt.ROE_WARN_PCT:.0f}% 경계",
            ))
        except (TypeError, ValueError):
            pass

    debt = info.get("debtToEquity")
    if debt is not None:
        try:
            debt_pct = float(debt)
            sig = adapt.debt_ratio_signal(debt_pct)
            subs.append(StockSubSignal(
                name="부채비율",
                value=debt_pct,
                unit="%",
                raw_signal=sig,
                detail=f"{debt_pct:.0f}%",
                rule=f"<{adapt.DEBT_SAFE_PCT:.0f}% 안전 / >{adapt.DEBT_HIGH_PCT:.0f}% 경계",
            ))
        except (TypeError, ValueError):
            pass

    growth = info.get("revenueGrowth")
    if growth is not None:
        try:
            g_pct = float(growth) * 100.0
            sig = adapt.earnings_growth_signal(g_pct)
            subs.append(StockSubSignal(
                name="매출 성장(YoY)",
                value=g_pct,
                unit="%",
                raw_signal=sig,
                detail=f"{g_pct:+.1f}%",
                rule=f"≥{adapt.EARNINGS_GROWTH_GOOD_PCT:.0f}% 양호 / ≤{adapt.EARNINGS_GROWTH_FLAT_PCT:.0f}% 역성장",
            ))
        except (TypeError, ValueError):
            pass

    return make_block("VALUE", "밸류·퀄리티", subs)


def _event_block() -> StockBlock:
    """Phase E: 실적·공시·어닝 리비전·내부자 거래. 현재는 graceful missing."""
    return make_block("EVENT", "이벤트·엣지", [])


def _sector_block(market: str) -> StockBlock:
    """Proxy for per-stock sector: use overall market sector momentum avg.

    Better per-ticker mapping (e.g. yfinance sector -> ETF) is Phase E+.
    """
    sectors = score_sectors(market)
    if not sectors:
        return make_block("SECTOR", "섹터 맥락", [])

    avg_score = sum(s.momentum_score for s in sectors) / len(sectors)
    if avg_score > 2:
        sig = +1
    elif avg_score < -2:
        sig = -1
    else:
        sig = 0

    return make_block("SECTOR", "섹터 맥락", [
        StockSubSignal(
            name="섹터 모멘텀(평균)",
            value=avg_score,
            unit="%",
            raw_signal=sig,
            detail=f"전체 섹터 1개월 평균 {avg_score:+.1f}%",
        )
    ])


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_stock_verdict(
    ticker: str,
    name: str,
    market: str,  # "US" or "KR"
    mode: Mode,
) -> StockVerdict:
    """Fetch data, build all four blocks, return a StockVerdict.

    Empty or partial data yields an empty/degraded verdict — the aggregator
    handles the normalization (see `ivst.analysis.stock.aggregate_stock`).
    """
    if market == "KR":
        records = fetch_kr_ohlcv(ticker, days=300)
    else:
        records = fetch_us_ohlcv(ticker, period="1y")

    if not records:
        return aggregate_stock(ticker, name, mode, [])

    closes = np.array([float(r["close"]) for r in records], dtype=float)
    volumes = np.array([float(r["volume"]) for r in records], dtype=float)

    trend = _trend_block(closes, volumes)

    if market == "US":
        info = _fetch_info_us(ticker)
        value = _value_block(info)
    else:
        value = make_block("VALUE", "밸류·퀄리티", [])

    event = _event_block()
    sector = _sector_block(market)

    return aggregate_stock(ticker, name, mode, [trend, value, event, sector])
