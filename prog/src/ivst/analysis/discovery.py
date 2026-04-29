"""KRX whole-market stock screening (data-driven candidate discovery).

Replaces the hardcoded `KR_SECTOR_STOCKS` lookup in `recommend.py` with a
pykrx-backed screen across every listed KOSPI/KOSDAQ name. Three scoring
modes are supported:

- **momentum**: pure 1M/3M momentum (chases winners — high overheating risk).
- **value**: low PER/PBR with non-deteriorating recent action (mean-reversion).
- **balanced** (default): momentum minus overheating and rich-valuation
  penalties, so already-spiked names get demoted.

Raw candidates (after liquidity/cap filtering) are cached in SQLite
(`screening_cache`) per trading day. Mode-specific scoring runs on top of
the cached pool, so switching `--mode` does not re-pull KRX.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Literal

from ivst.db.engine import get_conn

DEFAULT_MIN_MARKET_CAP_WON = 200_000_000_000   # 2,000억원
DEFAULT_MIN_TRADING_VALUE_WON = 1_000_000_000  # 일 거래대금 10억원
CACHE_TTL_HOURS = 12

ScreenMode = Literal["momentum", "value", "balanced"]


@dataclass(frozen=True)
class KRStockCandidate:
    """Raw, mode-independent KR market candidate (cacheable)."""
    ticker: str
    name: str
    sector: str
    market: str           # "KOSPI" / "KOSDAQ"
    market_cap: int       # 원
    return_1m: float      # %
    return_3m: float      # %
    per: float
    pbr: float
    trading_value: int    # 원 (최근일 거래대금)


@dataclass(frozen=True)
class ScoredKRCandidate:
    """Candidate with mode-specific score and human-readable warning tags."""
    base: KRStockCandidate
    score: float
    warnings: tuple[str, ...]


# ---------------------------------------------------------------------------
# Trading-day helpers
# ---------------------------------------------------------------------------


def _last_trading_day() -> str:
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except Exception:
        return datetime.now().strftime("%Y%m%d")

    today = datetime.now().strftime("%Y%m%d")
    try:
        return stock.get_nearest_business_day_in_a_week(today, prev=True)
    except Exception:
        return today


def _date_back(yyyymmdd: str, days: int) -> str:
    d = datetime.strptime(yyyymmdd, "%Y%m%d") - timedelta(days=days)
    return d.strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# Cache layer (raw pool, mode-independent)
# ---------------------------------------------------------------------------


def _pool_cache_key(min_cap: int, min_tv: int) -> str:
    return f"kr_pool:{_last_trading_day()}:{min_cap}:{min_tv}"


def _load_pool(key: str) -> list[KRStockCandidate] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT payload, cached_at FROM screening_cache WHERE key = ?",
            (key,),
        ).fetchone()
    if not row:
        return None

    try:
        cached_at = datetime.fromisoformat(row["cached_at"].replace("Z", ""))
    except Exception:
        return None
    if datetime.utcnow() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
        return None

    try:
        items = json.loads(row["payload"])
        return [KRStockCandidate(**item) for item in items]
    except Exception:
        return None


def _save_pool(key: str, pool: list[KRStockCandidate]) -> None:
    payload = json.dumps([asdict(c) for c in pool], ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO screening_cache(key, payload, cached_at) "
            "VALUES (?, ?, datetime('now'))",
            (key, payload),
        )


# ---------------------------------------------------------------------------
# Whole-market fetch
# ---------------------------------------------------------------------------


def _fetch_market(market: str, end_date: str, start_1m: str, start_3m: str) -> list[KRStockCandidate]:
    try:
        from pykrx import stock  # type: ignore[import-untyped]
    except Exception:
        return []

    try:
        chg_1m = stock.get_market_price_change_by_ticker(start_1m, end_date, market=market)
        chg_3m = stock.get_market_price_change_by_ticker(start_3m, end_date, market=market)
        cap = stock.get_market_cap_by_ticker(end_date, market=market)
        fund = stock.get_market_fundamental_by_ticker(end_date, market=market)
        sec = stock.get_market_sector_classifications(end_date, market=market)
    except Exception:
        return []

    out: list[KRStockCandidate] = []
    for ticker in chg_1m.index:
        try:
            r1m = float(chg_1m.loc[ticker, "등락률"])
            r3m_val = chg_3m.loc[ticker, "등락률"] if ticker in chg_3m.index else 0.0
            r3m = float(r3m_val)
            mc = int(cap.loc[ticker, "시가총액"]) if ticker in cap.index else 0
            tv = int(cap.loc[ticker, "거래대금"]) if ticker in cap.index else 0
            per = float(fund.loc[ticker, "PER"]) if ticker in fund.index else 0.0
            pbr = float(fund.loc[ticker, "PBR"]) if ticker in fund.index else 0.0
            name = str(chg_1m.loc[ticker, "종목명"])
            sector = str(sec.loc[ticker, "업종명"]) if ticker in sec.index else "-"
        except Exception:
            continue

        out.append(KRStockCandidate(
            ticker=str(ticker),
            name=name,
            sector=sector,
            market=market,
            market_cap=mc,
            return_1m=r1m,
            return_3m=r3m,
            per=per,
            pbr=pbr,
            trading_value=tv,
        ))
    return out


def _build_pool(min_cap: int, min_tv: int) -> list[KRStockCandidate]:
    end = _last_trading_day()
    start_1m = _date_back(end, 30)
    start_3m = _date_back(end, 90)

    raw: list[KRStockCandidate] = []
    for board in ("KOSPI", "KOSDAQ"):
        raw.extend(_fetch_market(board, end, start_1m, start_3m))

    return [c for c in raw if c.market_cap >= min_cap and c.trading_value >= min_tv]


# ---------------------------------------------------------------------------
# Mode-specific scoring + warnings
# ---------------------------------------------------------------------------


def _warnings_for(c: KRStockCandidate) -> tuple[str, ...]:
    """Risk tags surfaced to the user regardless of mode."""
    tags: list[str] = []
    if c.return_1m > 100:
        tags.append("⚠1M+100%")
    elif c.return_1m > 50:
        tags.append("⚠1M+50%")
    if c.per <= 0:
        tags.append("⚠적자")
    elif c.per > 50:
        tags.append("⚠고PER")
    if c.pbr > 5:
        tags.append("⚠고PBR")
    if c.market_cap > 0 and (c.trading_value / c.market_cap) > 0.15:
        tags.append("⚠회전율↑")
    return tuple(tags)


def _score_momentum(c: KRStockCandidate) -> float:
    return 0.6 * c.return_1m + 0.4 * c.return_3m


def _score_balanced(c: KRStockCandidate) -> float:
    """Momentum, then demote overheated and richly-valued names."""
    score = _score_momentum(c)
    if score <= 0:
        return score

    # Overheating penalty (reduce on already-spiked 1M)
    if c.return_1m > 100:
        score *= 0.20
    elif c.return_1m > 50:
        score *= 0.50
    elif c.return_1m > 30:
        score *= 0.80

    # Valuation penalty
    if c.per <= 0 or c.per > 50:
        score *= 0.50
    elif c.per > 30:
        score *= 0.80
    if c.pbr > 5:
        score *= 0.70
    elif c.pbr > 3:
        score *= 0.90

    # Pump signal: extreme intraday turnover
    if c.market_cap > 0 and (c.trading_value / c.market_cap) > 0.20:
        score *= 0.50

    return score


def _passes_value(c: KRStockCandidate) -> bool:
    """Hard filter for the value mode universe."""
    return (
        3.0 <= c.per <= 25.0
        and 0.0 < c.pbr <= 2.0
        and c.return_1m >= -15.0
    )


def _score_value(c: KRStockCandidate) -> float:
    """Reward low PER/PBR, mild positive 1M, and turnaround setups."""
    if not _passes_value(c):
        return float("-inf")

    per_pts = (25.0 - c.per) / 25.0 * 40.0   # 0~40
    pbr_pts = max(0.0, (2.0 - c.pbr) / 2.0) * 30.0  # 0~30
    r1m_pts = max(0.0, c.return_1m)
    turnaround = 15.0 if c.return_3m < 0 < c.return_1m else 0.0
    return per_pts + pbr_pts + r1m_pts + turnaround


_SCORERS = {
    "momentum": _score_momentum,
    "balanced": _score_balanced,
    "value": _score_value,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def screen_kr_market(
    top_n: int = 20,
    mode: ScreenMode = "balanced",
    min_market_cap_won: int = DEFAULT_MIN_MARKET_CAP_WON,
    min_trading_value_won: int = DEFAULT_MIN_TRADING_VALUE_WON,
    use_cache: bool = True,
) -> list[ScoredKRCandidate]:
    """Return top-N KR candidates ranked under the requested mode.

    Pool fetching/caching is mode-independent; switching `mode` between
    calls only re-runs scoring on the cached pool.

    Returns an empty list when pykrx is unavailable, KRX is unreachable,
    or no candidate clears the mode-specific filter.
    """
    scorer = _SCORERS.get(mode, _score_balanced)

    key = _pool_cache_key(min_market_cap_won, min_trading_value_won)
    pool: list[KRStockCandidate] | None = _load_pool(key) if use_cache else None
    if pool is None:
        pool = _build_pool(min_market_cap_won, min_trading_value_won)
        if pool:
            _save_pool(key, pool)

    scored = [
        ScoredKRCandidate(base=c, score=scorer(c), warnings=_warnings_for(c))
        for c in pool
    ]
    scored = [s for s in scored if s.score > float("-inf")]
    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:top_n]
