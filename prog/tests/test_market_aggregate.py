"""Unit tests for ivst.analysis.market aggregation.

Synthetic-only: no network, no DB.
"""

from __future__ import annotations

import pytest

from ivst.analysis.market import (
    BEARISH_THRESHOLD,
    BULLISH_THRESHOLD,
    AssetClass,
    CoreIndicator,
    Mode,
    Verdict,
    WEIGHT_PROFILES,
    aggregate,
)


def _ci(code: str, raw: int, *, value: float = 0.0, detail: str = "") -> CoreIndicator:
    return CoreIndicator(
        code=code,
        name=code,
        value=value,
        unit="",
        raw_signal=raw,
        detail=detail,
        resolution="일일",
    )


def _c1(sig: int) -> list[CoreIndicator]:
    """Helper: all three C1 slots at the given raw signal (total weight 0.30)."""
    return [_ci("C1_BS", sig), _ci("C1_TGA", sig), _ci("C1_RRP", sig)]


class TestUSAsset:
    def test_all_bullish_yields_bullish_long_term(self) -> None:
        indicators = _c1(+1) + [_ci("C2", +1), _ci("C3", +1), _ci("C4", +1)]
        v = aggregate(AssetClass.US, indicators)
        assert v.total_score == pytest.approx(1.0)
        assert v.verdict == Verdict.BULLISH
        assert v.mode == Mode.LONG_TERM

    def test_all_bearish_yields_bearish_watch(self) -> None:
        indicators = _c1(-1) + [_ci("C2", -1), _ci("C3", -1), _ci("C4", -1)]
        v = aggregate(AssetClass.US, indicators)
        assert v.total_score == pytest.approx(-1.0)
        assert v.verdict == Verdict.BEARISH
        assert v.mode == Mode.WATCH

    def test_mixed_around_zero_yields_mixed_swing(self) -> None:
        indicators = _c1(+1) + [_ci("C2", -1), _ci("C3", +1), _ci("C4", -1)]
        v = aggregate(AssetClass.US, indicators)
        # 0.30 - 0.30 + 0.25 - 0.15 = 0.10
        assert v.total_score == pytest.approx(0.10)
        assert v.verdict == Verdict.MIXED
        assert v.mode == Mode.SWING

    def test_threshold_boundary_bullish(self) -> None:
        v = aggregate(AssetClass.US, _c1(+1) + [_ci("C2", +1), _ci("C3", 0), _ci("C4", 0)])
        assert v.total_score >= BULLISH_THRESHOLD
        assert v.verdict == Verdict.BULLISH

    def test_threshold_boundary_bearish(self) -> None:
        v = aggregate(AssetClass.US, _c1(-1) + [_ci("C2", -1), _ci("C3", 0), _ci("C4", 0)])
        assert v.total_score <= BEARISH_THRESHOLD
        assert v.verdict == Verdict.BEARISH

    def test_unknown_code_ignored(self) -> None:
        indicators = [_ci("C1_BS", +1), _ci("FX", +1), _ci("C2", +1)]
        v = aggregate(AssetClass.US, indicators)
        codes = {c.code for c in v.contributions}
        assert codes == {"C1_BS", "C2"}

    def test_duplicate_codes_first_wins(self) -> None:
        indicators = [_ci("C1_TGA", +1), _ci("C1_TGA", -1)]
        v = aggregate(AssetClass.US, indicators)
        c = next(c for c in v.contributions if c.code == "C1_TGA")
        assert c.raw_signal == +1

    def test_raw_signal_clamped(self) -> None:
        v = aggregate(AssetClass.US, [_ci("C1_BS", +5), _ci("C2", -9), _ci("C3", 0), _ci("C4", 0)])
        bs = next(c for c in v.contributions if c.code == "C1_BS")
        c2 = next(c for c in v.contributions if c.code == "C2")
        assert bs.raw_signal == 1
        assert c2.raw_signal == -1


class TestNoIndicators:
    def test_empty_us_is_mixed(self) -> None:
        v = aggregate(AssetClass.US, [])
        assert v.total_score == 0.0
        assert v.verdict == Verdict.MIXED


class TestContextAlertOverride:
    def test_bullish_downgraded_to_mixed(self) -> None:
        indicators = _c1(+1) + [_ci("C2", +1), _ci("C3", +1), _ci("C4", +1)]
        v = aggregate(AssetClass.US, indicators, context_alert=True)
        assert v.total_score == pytest.approx(1.0)
        assert v.verdict == Verdict.MIXED
        assert v.mode == Mode.SWING
        assert v.context_alert is True

    def test_mixed_downgraded_to_bearish(self) -> None:
        v = aggregate(AssetClass.US, [_ci("C1_BS", +1), _ci("C2", -1)], context_alert=True)
        assert v.verdict == Verdict.BEARISH
        assert v.mode == Mode.WATCH

    def test_bearish_stays_bearish(self) -> None:
        indicators = _c1(-1) + [_ci("C2", -1), _ci("C3", -1), _ci("C4", -1)]
        v = aggregate(AssetClass.US, indicators, context_alert=True)
        assert v.verdict == Verdict.BEARISH

    def test_context_alert_never_upgrades(self) -> None:
        indicators = _c1(+1) + [_ci("C2", +1), _ci("C3", +1), _ci("C4", +1)]
        v = aggregate(AssetClass.US, indicators, context_alert=True)
        assert v.verdict != Verdict.BULLISH


class TestWeightProfilesInvariants:
    @pytest.mark.parametrize("asset", list(AssetClass))
    def test_weights_sum_to_one(self, asset: AssetClass) -> None:
        profile = WEIGHT_PROFILES[asset]
        assert sum(profile.values()) == pytest.approx(1.0), (
            f"{asset} weights should sum to 1.0, got {sum(profile.values())}"
        )

    @pytest.mark.parametrize("asset", list(AssetClass))
    def test_all_weights_positive(self, asset: AssetClass) -> None:
        profile = WEIGHT_PROFILES[asset]
        assert all(w > 0 for w in profile.values()), f"{asset} has non-positive weight"


class TestUnknownAsset:
    def test_rejects_invalid_asset(self) -> None:
        class _Fake:
            pass
        with pytest.raises(ValueError):
            aggregate(_Fake(), [])  # type: ignore[arg-type]
