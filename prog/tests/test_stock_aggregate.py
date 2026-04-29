"""Unit tests for ivst.analysis.stock aggregation."""

from __future__ import annotations

import pytest

from ivst.analysis.market import Mode
from ivst.analysis.stock import (
    BUY_THRESHOLD,
    MODE_WEIGHTS,
    SELL_THRESHOLD,
    STRONG_BUY_THRESHOLD,
    STRONG_SELL_THRESHOLD,
    Signal5,
    StockBlock,
    StockSubSignal,
    _block_score,
    aggregate_stock,
    calc_earnings_revision_signal,
    make_block,
)


def _sub(name: str, raw: int) -> StockSubSignal:
    return StockSubSignal(name=name, value=0.0, unit="", raw_signal=raw, detail="")


def _block(code: str, score: float, subs: tuple = ()) -> StockBlock:
    return StockBlock(code=code, name=code, sub_signals=subs, block_score=score)


class TestLongTermMode:
    def test_all_bullish_strong_buy(self) -> None:
        blocks = [_block("VALUE", 1.0), _block("EVENT", 1.0), _block("TREND", 1.0), _block("SECTOR", 1.0)]
        v = aggregate_stock("AAPL", "Apple", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(1.0)
        assert v.signal == Signal5.STRONG_BUY
        assert v.mode_mismatch_warning is False

    def test_only_value_bullish(self) -> None:
        # VALUE=+1 (0.45), others 0 -> total = 0.45 -> BUY (>=0.2, <0.6)
        blocks = [_block("VALUE", 1.0), _block("EVENT", 0.0), _block("TREND", 0.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("AAPL", "Apple", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(0.45)
        assert v.signal == Signal5.BUY

    def test_all_bearish_strong_sell(self) -> None:
        blocks = [_block("VALUE", -1.0), _block("EVENT", -1.0), _block("TREND", -1.0), _block("SECTOR", -1.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(-1.0)
        assert v.signal == Signal5.STRONG_SELL

    def test_value_weight_dominates_over_trend(self) -> None:
        # VALUE=-1 (0.45) vs TREND=+1 (0.15) -> net = -0.30 -> SELL
        blocks = [_block("VALUE", -1.0), _block("EVENT", 0.0), _block("TREND", 1.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(-0.30)
        assert v.signal == Signal5.SELL


class TestSwingMode:
    def test_swing_trend_dominates(self) -> None:
        # In SWING, TREND=+1 (0.45) vs VALUE=-1 (0.15) -> net = +0.30 -> BUY
        blocks = [_block("VALUE", -1.0), _block("EVENT", 0.0), _block("TREND", 1.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("X", "X", Mode.SWING, blocks)
        assert v.total_score == pytest.approx(0.30)
        assert v.signal == Signal5.BUY

    def test_same_blocks_different_mode_different_verdict(self) -> None:
        blocks = [_block("VALUE", -1.0), _block("EVENT", 0.0), _block("TREND", 1.0), _block("SECTOR", 0.0)]
        long_term = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        swing = aggregate_stock("X", "X", Mode.SWING, blocks)
        assert long_term.signal == Signal5.SELL
        assert swing.signal == Signal5.BUY


class TestWatchMode:
    def test_watch_equal_weights(self) -> None:
        blocks = [_block("VALUE", 1.0), _block("EVENT", 1.0), _block("TREND", 1.0), _block("SECTOR", 1.0)]
        v = aggregate_stock("X", "X", Mode.WATCH, blocks)
        # raw score = 1.0 -> STRONG_BUY -> downgraded to BUY
        assert v.total_score == pytest.approx(1.0)
        assert v.signal == Signal5.BUY
        assert v.mode_mismatch_warning is True

    def test_watch_downgrades_buy_to_hold(self) -> None:
        # score = 0.25 (uniform) -> BUY -> downgrade to HOLD
        blocks = [_block("VALUE", 0.25), _block("EVENT", 0.25), _block("TREND", 0.25), _block("SECTOR", 0.25)]
        v = aggregate_stock("X", "X", Mode.WATCH, blocks)
        assert v.total_score == pytest.approx(0.25)
        assert v.signal == Signal5.HOLD

    def test_watch_leaves_sell_alone(self) -> None:
        blocks = [_block("VALUE", -1.0), _block("EVENT", -1.0), _block("TREND", -1.0), _block("SECTOR", -1.0)]
        v = aggregate_stock("X", "X", Mode.WATCH, blocks)
        assert v.signal == Signal5.STRONG_SELL
        assert v.mode_mismatch_warning is True

    def test_watch_hold_stays_hold(self) -> None:
        blocks = [_block("VALUE", 0.0), _block("EVENT", 0.0), _block("TREND", 0.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("X", "X", Mode.WATCH, blocks)
        assert v.signal == Signal5.HOLD


class TestThresholds:
    def test_exact_buy_threshold(self) -> None:
        # EVENT=+1 (0.30) + SECTOR=-1 (0.10): 0.30 - 0.10 = 0.20 -> BUY (>= 0.2)
        blocks = [_block("VALUE", 0.0), _block("EVENT", 1.0), _block("TREND", 0.0), _block("SECTOR", -1.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(BUY_THRESHOLD)
        assert v.signal == Signal5.BUY

    def test_exact_strong_buy_threshold(self) -> None:
        # VALUE=+1 (0.45) + EVENT=+1 (0.30) - TREND=-1 (0.15) = 0.60 -> STRONG_BUY
        blocks = [_block("VALUE", 1.0), _block("EVENT", 1.0), _block("TREND", -1.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(STRONG_BUY_THRESHOLD)
        assert v.signal == Signal5.STRONG_BUY

    def test_exact_sell_threshold(self) -> None:
        blocks = [_block("VALUE", 0.0), _block("EVENT", -1.0), _block("TREND", 0.0), _block("SECTOR", +1.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(SELL_THRESHOLD)
        assert v.signal == Signal5.SELL

    def test_exact_strong_sell_threshold(self) -> None:
        blocks = [_block("VALUE", -1.0), _block("EVENT", -1.0), _block("TREND", +1.0), _block("SECTOR", 0.0)]
        v = aggregate_stock("X", "X", Mode.LONG_TERM, blocks)
        assert v.total_score == pytest.approx(STRONG_SELL_THRESHOLD)
        assert v.signal == Signal5.STRONG_SELL


class TestBlockScoreAveraging:
    def test_empty_sub_signals_is_zero(self) -> None:
        assert _block_score(()) == 0.0

    def test_balanced_sub_signals(self) -> None:
        subs = [_sub("a", +1), _sub("b", 0), _sub("c", -1)]
        assert _block_score(subs) == pytest.approx(0.0)

    def test_two_bullish_two_neutral(self) -> None:
        subs = [_sub("a", +1), _sub("b", +1), _sub("c", 0), _sub("d", 0)]
        assert _block_score(subs) == pytest.approx(0.5)

    def test_make_block_averages(self) -> None:
        subs = [_sub("RSI", +1), _sub("MACD", +1), _sub("Volume", -1)]
        block = make_block("TREND", "추세", subs)
        assert block.block_score == pytest.approx(1 / 3)
        assert block.sub_signals == tuple(subs)

    def test_make_block_clamps_wild_raw_values(self) -> None:
        subs = [_sub("a", +99), _sub("b", -99)]
        block = make_block("VALUE", "가치", subs)
        assert block.block_score == pytest.approx(0.0)


class TestPartialDataNormalization:
    def test_only_one_block_is_full_weight(self) -> None:
        v = aggregate_stock("X", "X", Mode.LONG_TERM, [_block("VALUE", 1.0)])
        assert v.total_score == pytest.approx(1.0)
        assert v.signal == Signal5.STRONG_BUY

    def test_no_blocks_is_hold(self) -> None:
        v = aggregate_stock("X", "X", Mode.LONG_TERM, [])
        assert v.total_score == 0.0
        assert v.signal == Signal5.HOLD

    def test_unknown_block_code_ignored(self) -> None:
        v = aggregate_stock("X", "X", Mode.LONG_TERM, [_block("BOGUS", 1.0), _block("VALUE", 1.0)])
        assert {c.code for c in v.contributions} == {"VALUE"}

    def test_duplicate_block_code_first_wins(self) -> None:
        v = aggregate_stock("X", "X", Mode.LONG_TERM, [_block("VALUE", 1.0), _block("VALUE", -1.0)])
        value_c = next(c for c in v.contributions if c.code == "VALUE")
        assert value_c.contribution > 0


class TestModeWeightInvariants:
    @pytest.mark.parametrize("mode", list(Mode))
    def test_weights_sum_to_one(self, mode: Mode) -> None:
        assert sum(MODE_WEIGHTS[mode].values()) == pytest.approx(1.0)

    @pytest.mark.parametrize("mode", list(Mode))
    def test_covers_all_blocks(self, mode: Mode) -> None:
        assert set(MODE_WEIGHTS[mode].keys()) == {"VALUE", "EVENT", "TREND", "SECTOR"}


class TestEarningsRevision:
    def test_clear_upward(self) -> None:
        sig, detail = calc_earnings_revision_signal(
            estimates_4w_ago=10.0, estimates_12w_ago=9.5, current_estimate=10.5
        )
        assert sig == +1
        assert "상향" in detail

    def test_clear_downward(self) -> None:
        sig, _ = calc_earnings_revision_signal(
            estimates_4w_ago=10.0, estimates_12w_ago=10.5, current_estimate=9.5
        )
        assert sig == -1

    def test_mixed_signals_are_neutral(self) -> None:
        sig, _ = calc_earnings_revision_signal(
            estimates_4w_ago=10.0, estimates_12w_ago=10.5, current_estimate=10.3
        )
        assert sig == 0

    def test_missing_inputs_returns_zero_dash(self) -> None:
        sig, detail = calc_earnings_revision_signal(None, 9.0, 10.0)
        assert sig == 0
        assert detail == "─"

    def test_current_estimate_missing_returns_zero(self) -> None:
        sig, detail = calc_earnings_revision_signal(9.0, 8.0, None)
        assert sig == 0
        assert detail == "─"


class TestInvalidMode:
    def test_unknown_mode_raises(self) -> None:
        class _Fake:
            pass

        with pytest.raises(ValueError):
            aggregate_stock("X", "X", _Fake(), [])  # type: ignore[arg-type]
