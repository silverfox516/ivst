"""Per-stock timing verdict engine.

Pure aggregation: takes per-block sub-signals (each -1/0/+1), averages each
block into a score in [-1, +1], then combines blocks with mode-specific
weights. The final score maps to a 5-level signal. In WATCH mode, buy
signals are downgraded by one tier and a mode-mismatch flag is set.

See plan §3-B (blocks) and §3-D (weights).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from ivst.analysis.market import Mode, WeightedContribution


class Signal5(str, Enum):
    """Five-level signal, aligned with the legacy `Signal` enum in
    `ivst.analysis.signal` but kept local so we don't couple to the
    indicator-weight layout that is being phased out."""

    STRONG_BUY  = "STRONG BUY"
    BUY         = "BUY"
    HOLD        = "HOLD"
    SELL        = "SELL"
    STRONG_SELL = "STRONG SELL"


@dataclass(frozen=True)
class StockSubSignal:
    name: str
    value: float
    unit: str
    raw_signal: int
    detail: str
    rule: str = ""


@dataclass(frozen=True)
class StockBlock:
    """One of the four plan §3-B blocks.

    `sub_signals` is the authoritative input; `block_score` is the mean of
    clamped raw signals (or 0.0 when empty).
    """

    code: str
    name: str
    sub_signals: tuple[StockSubSignal, ...]
    block_score: float


@dataclass(frozen=True)
class StockVerdict:
    ticker: str
    name: str
    mode: Mode
    blocks: tuple[StockBlock, ...]
    contributions: tuple[WeightedContribution, ...]
    total_score: float
    signal: Signal5
    mode_mismatch_warning: bool


# Plan §3-D: mode-specific block weights.
MODE_WEIGHTS: dict[Mode, dict[str, float]] = {
    Mode.LONG_TERM: {
        "VALUE":  0.45,
        "EVENT":  0.30,
        "TREND":  0.15,
        "SECTOR": 0.10,
    },
    Mode.SWING: {
        "TREND":  0.45,
        "EVENT":  0.25,
        "SECTOR": 0.15,
        "VALUE":  0.15,
    },
    # In WATCH mode we still compute a score so the user sees the mechanics,
    # but we downgrade buy signals and surface a mode-mismatch warning.
    Mode.WATCH: {
        "VALUE":  0.25,
        "EVENT":  0.25,
        "TREND":  0.25,
        "SECTOR": 0.25,
    },
}


STRONG_BUY_THRESHOLD  = 0.6
BUY_THRESHOLD         = 0.2
SELL_THRESHOLD        = -0.2
STRONG_SELL_THRESHOLD = -0.6


def _clamp(v: int) -> int:
    if v > 0:
        return 1
    if v < 0:
        return -1
    return 0


def _block_score(sub_signals: Sequence[StockSubSignal]) -> float:
    """Mean of clamped raw signals — always within [-1.0, +1.0]."""
    if not sub_signals:
        return 0.0
    clamped = [_clamp(s.raw_signal) for s in sub_signals]
    return sum(clamped) / len(clamped)


def make_block(code: str, name: str, sub_signals: Sequence[StockSubSignal]) -> StockBlock:
    """Helper: build a StockBlock by averaging sub-signals into block_score."""
    subs = tuple(sub_signals)
    return StockBlock(
        code=code,
        name=name,
        sub_signals=subs,
        block_score=_block_score(subs),
    )


def _signal_for_score(score: float) -> Signal5:
    if score >= STRONG_BUY_THRESHOLD:
        return Signal5.STRONG_BUY
    if score >= BUY_THRESHOLD:
        return Signal5.BUY
    if score <= STRONG_SELL_THRESHOLD:
        return Signal5.STRONG_SELL
    if score <= SELL_THRESHOLD:
        return Signal5.SELL
    return Signal5.HOLD


def _downgrade_signal(s: Signal5) -> Signal5:
    """WATCH-mode safety bias: buy signals get pulled down one tier.
    Sell signals are left alone (we do not want to soften risk)."""
    if s == Signal5.STRONG_BUY:
        return Signal5.BUY
    if s == Signal5.BUY:
        return Signal5.HOLD
    return s


def aggregate_stock(
    ticker: str,
    name: str,
    mode: Mode,
    blocks: Sequence[StockBlock],
) -> StockVerdict:
    """Combine block scores under the current market mode into a StockVerdict.

    Missing blocks (no entry for a weight slot) are handled by normalizing
    against the supplied weight sum — partial data gives a best-effort read
    rather than a false HOLD.
    """
    profile = MODE_WEIGHTS.get(mode)
    if profile is None:
        raise ValueError(f"No weight profile for mode: {mode}")

    contributions: list[WeightedContribution] = []
    supplied_weight = 0.0
    raw_sum = 0.0
    seen: set[str] = set()

    for block in blocks:
        if block.code not in profile:
            continue
        if block.code in seen:
            continue
        seen.add(block.code)

        bscore = max(-1.0, min(1.0, block.block_score))
        weight = profile[block.code]
        contribution = bscore * weight
        raw_sum += contribution
        supplied_weight += weight
        contributions.append(
            WeightedContribution(
                code=block.code,
                raw_signal=_clamp(round(bscore)) if bscore != 0 else 0,
                weight=weight,
                contribution=contribution,
            )
        )

    total = raw_sum / supplied_weight if supplied_weight > 0 else 0.0
    total = round(total, 4)

    signal = _signal_for_score(total)
    mode_mismatch = mode == Mode.WATCH
    if mode_mismatch:
        signal = _downgrade_signal(signal)

    return StockVerdict(
        ticker=ticker,
        name=name,
        mode=mode,
        blocks=tuple(blocks),
        contributions=tuple(contributions),
        total_score=total,
        signal=signal,
        mode_mismatch_warning=mode_mismatch,
    )


# ---------------------------------------------------------------------------
# Earnings revision helper (plan §3-B: the edge add).
# ---------------------------------------------------------------------------


def calc_earnings_revision_signal(
    estimates_4w_ago: float | None,
    estimates_12w_ago: float | None,
    current_estimate: float | None,
) -> tuple[int, str]:
    """Turn analyst EPS-estimate trajectory into a -1/0/+1 signal.

    Returns (signal, human-readable detail). If inputs are insufficient, the
    signal is 0 and the detail reads "─" so callers can render a dash.

    Rules:
    - 4w change >= +2% AND 12w change >= +3%  ->  +1 (clear upward revision)
    - 4w change <= -2% AND 12w change <= -3%  ->  -1 (clear downward revision)
    - Otherwise                                   0
    """
    if current_estimate is None or current_estimate == 0:
        return 0, "─"

    def _pct(prev: float | None) -> float | None:
        if prev is None or prev == 0:
            return None
        return (current_estimate - prev) / prev * 100.0  # type: ignore[operator]

    d4 = _pct(estimates_4w_ago)
    d12 = _pct(estimates_12w_ago)

    if d4 is None or d12 is None:
        return 0, "─"

    if d4 >= 2 and d12 >= 3:
        return +1, f"4w {d4:+.1f}%, 12w {d12:+.1f}% (상향)"
    if d4 <= -2 and d12 <= -3:
        return -1, f"4w {d4:+.1f}%, 12w {d12:+.1f}% (하향)"
    return 0, f"4w {d4:+.1f}%, 12w {d12:+.1f}%"
