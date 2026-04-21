"""Unit tests for stock_adapters threshold functions."""

from __future__ import annotations

import pytest

from ivst.analysis.stock_adapters import (
    DEBT_HIGH_PCT,
    DEBT_SAFE_PCT,
    EARNINGS_GROWTH_FLAT_PCT,
    EARNINGS_GROWTH_GOOD_PCT,
    PER_CHEAP_RATIO,
    PER_EXPENSIVE_RATIO,
    PRICE_VS_200DMA_MARGIN,
    ROE_GOOD_PCT,
    ROE_WARN_PCT,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    VOLUME_DRY_RATIO,
    VOLUME_SURGE_RATIO,
    debt_ratio_signal,
    earnings_growth_signal,
    macd_cross_signal,
    per_signal,
    price_vs_200dma_signal,
    roe_signal,
    rsi_signal,
    volume_surge_signal,
)


class TestPriceVs200dma:
    def test_above_margin(self) -> None:
        assert price_vs_200dma_signal(price=105.0, sma200=100.0) == +1

    def test_below_margin(self) -> None:
        assert price_vs_200dma_signal(price=95.0, sma200=100.0) == -1

    def test_dead_zone(self) -> None:
        assert price_vs_200dma_signal(price=101.0, sma200=100.0) == 0

    def test_exact_margin(self) -> None:
        price = 100.0 * (1.0 + PRICE_VS_200DMA_MARGIN)
        assert price_vs_200dma_signal(price=price, sma200=100.0) == +1

    def test_invalid_sma(self) -> None:
        assert price_vs_200dma_signal(price=100.0, sma200=0.0) == 0


class TestRSI:
    def test_oversold_rebound(self) -> None:
        assert rsi_signal(25.0) == +1

    def test_overbought(self) -> None:
        assert rsi_signal(75.0) == -1

    def test_mid_range_neutral(self) -> None:
        assert rsi_signal(50.0) == 0

    def test_exact_oversold_boundary(self) -> None:
        assert rsi_signal(RSI_OVERSOLD) == +1

    def test_exact_overbought_boundary(self) -> None:
        assert rsi_signal(RSI_OVERBOUGHT) == -1


class TestMACDCross:
    def test_golden_cross(self) -> None:
        assert macd_cross_signal(macd=1.5, signal=1.0, prev_macd=0.8, prev_signal=1.0) == +1

    def test_dead_cross(self) -> None:
        assert macd_cross_signal(macd=0.8, signal=1.0, prev_macd=1.5, prev_signal=1.0) == -1

    def test_held_bullish(self) -> None:
        assert macd_cross_signal(macd=1.3, signal=1.0, prev_macd=1.2, prev_signal=1.0) == +1

    def test_held_bearish(self) -> None:
        assert macd_cross_signal(macd=0.5, signal=1.0, prev_macd=0.6, prev_signal=1.0) == -1

    def test_equal_is_neutral(self) -> None:
        assert macd_cross_signal(macd=1.0, signal=1.0, prev_macd=1.0, prev_signal=1.0) == 0


class TestVolumeSurge:
    def test_surge(self) -> None:
        assert volume_surge_signal(avg5=1_500_000, avg20=1_000_000) == +1

    def test_dry(self) -> None:
        assert volume_surge_signal(avg5=500_000, avg20=1_000_000) == -1

    def test_normal(self) -> None:
        assert volume_surge_signal(avg5=1_050_000, avg20=1_000_000) == 0

    def test_invalid_avg20(self) -> None:
        assert volume_surge_signal(avg5=1_000_000, avg20=0) == 0

    def test_exact_surge_ratio(self) -> None:
        assert volume_surge_signal(avg5=VOLUME_SURGE_RATIO, avg20=1.0) == +1

    def test_exact_dry_ratio(self) -> None:
        assert volume_surge_signal(avg5=VOLUME_DRY_RATIO, avg20=1.0) == -1


class TestPER:
    def test_cheap_vs_sector(self) -> None:
        assert per_signal(per=16.0, sector_median_per=22.0) == +1

    def test_expensive_vs_sector(self) -> None:
        assert per_signal(per=30.0, sector_median_per=20.0) == -1

    def test_in_range_is_neutral(self) -> None:
        assert per_signal(per=22.0, sector_median_per=22.0) == 0

    def test_negative_per_neutral(self) -> None:
        assert per_signal(per=-5.0, sector_median_per=20.0) == 0

    def test_invalid_sector_median(self) -> None:
        assert per_signal(per=15.0, sector_median_per=0.0) == 0

    def test_exact_cheap_ratio(self) -> None:
        median = 20.0
        per = median * PER_CHEAP_RATIO
        assert per_signal(per=per, sector_median_per=median) == +1

    def test_exact_expensive_ratio(self) -> None:
        median = 20.0
        per = median * PER_EXPENSIVE_RATIO
        assert per_signal(per=per, sector_median_per=median) == -1


class TestROE:
    def test_good(self) -> None:
        assert roe_signal(20.0) == +1

    def test_warn(self) -> None:
        assert roe_signal(5.0) == -1

    def test_mid_neutral(self) -> None:
        assert roe_signal(12.0) == 0

    def test_exact_good(self) -> None:
        assert roe_signal(ROE_GOOD_PCT) == +1

    def test_exact_warn(self) -> None:
        assert roe_signal(ROE_WARN_PCT) == -1


class TestDebtRatio:
    def test_safe(self) -> None:
        assert debt_ratio_signal(35.0) == +1

    def test_high(self) -> None:
        assert debt_ratio_signal(150.0) == -1

    def test_moderate_is_neutral(self) -> None:
        assert debt_ratio_signal(75.0) == 0

    def test_exact_safe_boundary_is_neutral(self) -> None:
        assert debt_ratio_signal(DEBT_SAFE_PCT) == 0

    def test_exact_high_boundary_is_neutral(self) -> None:
        assert debt_ratio_signal(DEBT_HIGH_PCT) == 0


class TestEarningsGrowth:
    def test_growing(self) -> None:
        assert earnings_growth_signal(15.0) == +1

    def test_declining(self) -> None:
        assert earnings_growth_signal(-5.0) == -1

    def test_mild_growth_neutral(self) -> None:
        assert earnings_growth_signal(5.0) == 0

    def test_exact_good(self) -> None:
        assert earnings_growth_signal(EARNINGS_GROWTH_GOOD_PCT) == +1

    def test_exact_flat_is_decline(self) -> None:
        assert earnings_growth_signal(EARNINGS_GROWTH_FLAT_PCT) == -1


class TestAdapterReturnDomain:
    """Every adapter must return -1, 0, or +1."""

    @pytest.mark.parametrize(
        "fn, args",
        [
            (price_vs_200dma_signal, (200.0, 150.0)),
            (rsi_signal, (50.0,)),
            (macd_cross_signal, (1.0, 0.9, 1.0, 1.1)),
            (volume_surge_signal, (1_000_000, 900_000)),
            (per_signal, (25.0, 20.0)),
            (roe_signal, (10.0,)),
            (debt_ratio_signal, (75.0,)),
            (earnings_growth_signal, (5.0,)),
        ],
    )
    def test_clamps(self, fn, args) -> None:  # type: ignore[no-untyped-def]
        result = fn(*args)
        assert result in {-1, 0, +1}
