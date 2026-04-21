"""Market timing verdict engine.

Pure aggregation logic: given per-indicator raw signals (-1/0/+1), combine
with asset-class-specific weights into a total score, then map to a verdict
and trading mode. No network or I/O — all inputs are in-memory dataclasses so
this module is trivially unit-testable with synthetic scenarios.

See plan §3-D for the weighting rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class AssetClass(str, Enum):
    US = "US"


class Verdict(str, Enum):
    BULLISH = "매수 우위"
    MIXED = "혼조"
    BEARISH = "하락장"


class Mode(str, Enum):
    LONG_TERM = "중장기"
    SWING = "스윙"
    WATCH = "관망"


@dataclass(frozen=True)
class CoreIndicator:
    """A single core signal contributing to a market verdict.

    `detail` is a factual observation (e.g. "주간 +80B").
    `rule` is the threshold that produced `raw_signal`
    (e.g. "주간 ≥+$20B 확장 / ≤-$20B 긴축"). Shown beside the verdict so
    the reader can see *why* the indicator ended up 🟢/🟡/🔴.
    """

    code: str
    name: str
    value: float
    unit: str
    raw_signal: int
    detail: str
    resolution: str  # e.g. "일일", "주간", "월간"
    rule: str = ""


@dataclass(frozen=True)
class WeightedContribution:
    code: str
    raw_signal: int
    weight: float
    contribution: float  # raw_signal * weight


@dataclass(frozen=True)
class MarketVerdict:
    asset: AssetClass
    indicators: tuple[CoreIndicator, ...]
    contributions: tuple[WeightedContribution, ...]
    total_score: float
    verdict: Verdict
    mode: Mode
    context_alert: bool = False
    missing_codes: tuple[str, ...] = field(default_factory=tuple)


# See plan §3-D. Keys correspond to CoreIndicator.code values.
WEIGHT_PROFILES: dict[AssetClass, dict[str, float]] = {
    AssetClass.US: {
        # Liquidity potential + direction, split by source.
        "C1_BS":  0.10,   # Fed 대차대조표 4주 방향 (QE/QT)
        "C1_TGA": 0.10,   # TGA 잔량 + 방향 (앞으로 풀릴 연료)
        "C1_RRP": 0.10,   # RRP 잔량 + 방향 (유입 파이프)
        "C2":     0.30,   # S&P500 vs 200일선
        "C3":     0.25,   # HY 크레딧 스프레드
        "C4":     0.15,   # 섹터 로테이션
    },
}


BULLISH_THRESHOLD = 0.4
BEARISH_THRESHOLD = -0.4


def _clamp_signal(raw: int) -> int:
    if raw > 0:
        return 1
    if raw < 0:
        return -1
    return 0


def _verdict_for_score(score: float) -> Verdict:
    if score >= BULLISH_THRESHOLD:
        return Verdict.BULLISH
    if score <= BEARISH_THRESHOLD:
        return Verdict.BEARISH
    return Verdict.MIXED


def _mode_for_verdict(verdict: Verdict) -> Mode:
    return {
        Verdict.BULLISH: Mode.LONG_TERM,
        Verdict.MIXED:   Mode.SWING,
        Verdict.BEARISH: Mode.WATCH,
    }[verdict]


def _downgrade_verdict(v: Verdict) -> Verdict:
    """Context-alert downgrade. Never upgrades — safety bias."""
    if v == Verdict.BULLISH:
        return Verdict.MIXED
    if v == Verdict.MIXED:
        return Verdict.BEARISH
    return Verdict.BEARISH


def aggregate(
    asset: AssetClass,
    indicators: Sequence[CoreIndicator],
    context_alert: bool = False,
) -> MarketVerdict:
    """Combine core indicators into a weighted verdict.

    `context_alert=True` (from the LLM context layer) downgrades the verdict
    by exactly one tier. The raw numeric score is left untouched so callers
    can still show the numeric evidence.

    Missing indicators (weight slots with no input) are reported but not
    penalized: the denominator is the sum of weights for codes actually
    supplied, so partial data gives a best-effort reading rather than a
    false bearish.
    """
    profile = WEIGHT_PROFILES.get(asset)
    if profile is None:
        raise ValueError(f"No weight profile for asset class: {asset}")

    contributions: list[WeightedContribution] = []
    supplied_weight = 0.0
    raw_sum = 0.0
    seen_codes: set[str] = set()

    for ind in indicators:
        if ind.code not in profile:
            continue  # ignore unknown codes; caller may pass extras
        if ind.code in seen_codes:
            continue  # first wins; caller should not pass duplicates
        seen_codes.add(ind.code)

        clamped = _clamp_signal(ind.raw_signal)
        weight = profile[ind.code]
        contribution = clamped * weight
        raw_sum += contribution
        supplied_weight += weight
        contributions.append(
            WeightedContribution(
                code=ind.code,
                raw_signal=clamped,
                weight=weight,
                contribution=contribution,
            )
        )

    if supplied_weight > 0:
        total = raw_sum / supplied_weight
    else:
        total = 0.0

    verdict = _verdict_for_score(total)
    if context_alert:
        verdict = _downgrade_verdict(verdict)
    mode = _mode_for_verdict(verdict)

    missing = tuple(sorted(set(profile.keys()) - seen_codes))

    return MarketVerdict(
        asset=asset,
        indicators=tuple(indicators),
        contributions=tuple(contributions),
        total_score=round(total, 4),
        verdict=verdict,
        mode=mode,
        context_alert=context_alert,
        missing_codes=missing,
    )
