"""Unit tests for market_adapters threshold functions."""

from __future__ import annotations

import pytest

from ivst.analysis.market_adapters import (
    FED_BS_TREND_THRESHOLD_MN,
    HY_SPREAD_SAFE_BP,
    HY_SPREAD_WARN_BP,
    INDEX_VS_200DMA_MARGIN,
    RRP_FLOW_THRESHOLD_BN,
    RRP_HIGH_BN,
    RRP_LOW_BN,
    SECTOR_ROTATION_MARGIN_PCT,
    TGA_FLOW_THRESHOLD_MN,
    TGA_HIGH_MN,
    TGA_LOW_MN,
    fed_bs_trend_signal,
    hy_credit_spread_signal,
    index_vs_200dma_signal,
    rrp_potential_signal,
    sector_rotation_signal,
    tga_potential_signal,
)


class TestFedBSTrend:
    def test_qe_signal(self) -> None:
        # 4-week change +$80B in millions
        assert fed_bs_trend_signal(80_000.0) == +1

    def test_qt_signal(self) -> None:
        assert fed_bs_trend_signal(-80_000.0) == -1

    def test_flat_neutral(self) -> None:
        assert fed_bs_trend_signal(10_000.0) == 0

    def test_exact_threshold(self) -> None:
        assert fed_bs_trend_signal(FED_BS_TREND_THRESHOLD_MN) == +1

    def test_just_below_threshold_neutral(self) -> None:
        assert fed_bs_trend_signal(FED_BS_TREND_THRESHOLD_MN - 1.0) == 0


class TestTGAPotential:
    def test_high_and_draining(self) -> None:
        # $800B (high) + 4w decrease $150B → bullish
        assert tga_potential_signal(800_000.0, -150_000.0) == +1

    def test_low_and_filling(self) -> None:
        # $150B (low) + 4w increase $150B → bearish
        assert tga_potential_signal(150_000.0, 150_000.0) == -1

    def test_high_and_filling_cancel(self) -> None:
        # level +1, direction -1 → 0
        assert tga_potential_signal(800_000.0, 150_000.0) == 0

    def test_low_and_draining_cancel(self) -> None:
        assert tga_potential_signal(150_000.0, -150_000.0) == 0

    def test_middle_and_flat_neutral(self) -> None:
        assert tga_potential_signal(400_000.0, 10_000.0) == 0

    def test_middle_high_draining_is_direction_only(self) -> None:
        # level 0, direction +1 → +1
        assert tga_potential_signal(400_000.0, -150_000.0) == +1

    def test_exact_level_thresholds(self) -> None:
        assert tga_potential_signal(TGA_HIGH_MN, 0.0) == +1
        assert tga_potential_signal(TGA_LOW_MN, 0.0) == -1

    def test_exact_flow_threshold(self) -> None:
        assert tga_potential_signal(400_000.0, -TGA_FLOW_THRESHOLD_MN) == +1


class TestRRPPotential:
    def test_high_and_draining(self) -> None:
        # $600B (high) + 4w decrease $100B → bullish
        assert rrp_potential_signal(600.0, -100.0) == +1

    def test_low_and_filling(self) -> None:
        assert rrp_potential_signal(30.0, 100.0) == -1

    def test_high_and_filling_cancel(self) -> None:
        assert rrp_potential_signal(600.0, 100.0) == 0

    def test_low_and_draining_is_bearish_level_wins(self) -> None:
        # level -1, direction +1 → 0 (no more fuel to extract)
        assert rrp_potential_signal(30.0, -100.0) == 0

    def test_middle_and_flat_neutral(self) -> None:
        assert rrp_potential_signal(200.0, 10.0) == 0

    def test_exact_level_thresholds(self) -> None:
        assert rrp_potential_signal(RRP_HIGH_BN, 0.0) == +1
        assert rrp_potential_signal(RRP_LOW_BN, 0.0) == -1

    def test_exact_flow_threshold(self) -> None:
        assert rrp_potential_signal(200.0, -RRP_FLOW_THRESHOLD_BN) == +1


class TestIndexVs200dma:
    def test_above(self) -> None:
        assert index_vs_200dma_signal(price=105.0, sma200=100.0) == +1

    def test_below(self) -> None:
        assert index_vs_200dma_signal(price=95.0, sma200=100.0) == -1

    def test_dead_zone(self) -> None:
        assert index_vs_200dma_signal(price=100.2, sma200=100.0) == 0

    def test_zero_sma_safe(self) -> None:
        assert index_vs_200dma_signal(price=100.0, sma200=0.0) == 0

    def test_just_above_margin_triggers_signal(self) -> None:
        price = 100.0 * (1.0 + INDEX_VS_200DMA_MARGIN + 1e-6)
        assert index_vs_200dma_signal(price=price, sma200=100.0) == +1

    def test_just_below_margin_is_neutral(self) -> None:
        price = 100.0 * (1.0 + INDEX_VS_200DMA_MARGIN - 1e-6)
        assert index_vs_200dma_signal(price=price, sma200=100.0) == 0


class TestHYCreditSpread:
    def test_safe(self) -> None:
        assert hy_credit_spread_signal(300.0) == +1

    def test_warn(self) -> None:
        assert hy_credit_spread_signal(700.0) == -1

    def test_middle_is_neutral(self) -> None:
        assert hy_credit_spread_signal(500.0) == 0

    def test_exact_safe_boundary_is_neutral(self) -> None:
        assert hy_credit_spread_signal(HY_SPREAD_SAFE_BP) == 0

    def test_exact_warn_boundary_is_neutral(self) -> None:
        assert hy_credit_spread_signal(HY_SPREAD_WARN_BP) == 0


class TestSectorRotation:
    def test_offensive_leading(self) -> None:
        assert sector_rotation_signal(4.0, 1.0) == +1

    def test_defensive_leading(self) -> None:
        assert sector_rotation_signal(0.5, 2.0) == -1

    def test_tight_spread_neutral(self) -> None:
        assert sector_rotation_signal(2.0, 1.5) == 0

    def test_exact_margin(self) -> None:
        assert sector_rotation_signal(SECTOR_ROTATION_MARGIN_PCT, 0.0) == +1


class TestAdapterReturnDomain:
    """All adapters must produce only {-1, 0, +1}."""

    @pytest.mark.parametrize(
        "fn, args",
        [
            (fed_bs_trend_signal, (80_000.0,)),
            (tga_potential_signal, (800_000.0, -150_000.0)),
            (rrp_potential_signal, (600.0, -100.0)),
            (index_vs_200dma_signal, (100.0, 110.0)),
            (hy_credit_spread_signal, (999.0,)),
            (sector_rotation_signal, (1.0, 3.0)),
        ],
    )
    def test_clamps(self, fn, args) -> None:  # type: ignore[no-untyped-def]
        result = fn(*args)
        assert result in {-1, 0, +1}
