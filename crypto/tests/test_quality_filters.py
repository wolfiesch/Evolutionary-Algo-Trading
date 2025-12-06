"""Tests for data quality filters."""
import pytest
from data.quality_filters import CandleValidator, ValidationResult
from data.storage.models import Candle


@pytest.fixture
def validator():
    """Create a fresh validator for each test."""
    return CandleValidator()


@pytest.fixture
def base_candle():
    """Create a base candle for testing."""
    return Candle(
        symbol="BTCUSDT",
        timestamp=1000000,
        open=50000.0,
        high=50500.0,
        low=49500.0,
        close=50000.0,
        volume=100.0,
        turnover=5000000.0
    )


class TestFlashCrashDetection:
    """Test flash crash detection (>50% move)."""

    def test_flash_crash_up_rejected(self, validator, base_candle):
        """Test that upward flash crash (>50%) is rejected."""
        # First candle - normal
        result = validator.validate(base_candle)
        assert result.valid

        # Second candle - 60% price increase (flash crash)
        crash_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=80000.0,
            low=50000.0,
            close=80000.0,  # 60% increase
            volume=100.0,
            turnover=8000000.0
        )

        result = validator.validate(crash_candle)
        assert not result.valid
        assert "Flash crash" in result.reason
        assert not result.requires_warmup

    def test_flash_crash_down_rejected(self, validator, base_candle):
        """Test that downward flash crash (>50%) is rejected."""
        # First candle
        result = validator.validate(base_candle)
        assert result.valid

        # Second candle - 55% price decrease (flash crash)
        crash_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=50000.0,
            low=22000.0,
            close=22500.0,  # 55% decrease
            volume=100.0,
            turnover=2250000.0
        )

        result = validator.validate(crash_candle)
        assert not result.valid
        assert "Flash crash" in result.reason

    def test_exactly_50_percent_move_accepted(self, validator, base_candle):
        """Test that exactly 50% move is accepted (threshold is >50%)."""
        # First candle
        validator.validate(base_candle)

        # Second candle - exactly 50% increase
        candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=75000.0,
            low=50000.0,
            close=75000.0,  # exactly 50% increase
            volume=100.0,
            turnover=7500000.0
        )

        result = validator.validate(candle)
        assert result.valid
        assert result.reason is None

    def test_just_over_50_percent_move_rejected(self, validator, base_candle):
        """Test that just over 50% move is rejected."""
        # First candle
        validator.validate(base_candle)

        # Second candle - 50.1% increase
        crash_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=75050.0,
            low=50000.0,
            close=75050.0,  # 50.1% increase
            volume=100.0,
            turnover=7505000.0
        )

        result = validator.validate(crash_candle)
        assert not result.valid
        assert "Flash crash" in result.reason

    def test_just_under_50_percent_move_accepted(self, validator, base_candle):
        """Test that <50% move is accepted."""
        # First candle
        validator.validate(base_candle)

        # Second candle - 49% increase (just under threshold)
        normal_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=74500.0,
            low=50000.0,
            close=74500.0,  # 49% increase
            volume=100.0,
            turnover=7450000.0
        )

        result = validator.validate(normal_candle)
        assert result.valid
        assert result.reason is None


class TestZeroVolumeRejection:
    """Test zero volume candle rejection."""

    def test_zero_volume_rejected(self, validator):
        """Test that zero volume candles are rejected."""
        candle = Candle(
            symbol="BTCUSDT",
            timestamp=1000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=0.0,  # Zero volume
            turnover=0.0
        )

        result = validator.validate(candle)
        assert not result.valid
        assert "Zero volume" in result.reason
        assert not result.requires_warmup

    def test_very_small_volume_accepted(self, validator):
        """Test that very small (but non-zero) volume is accepted."""
        candle = Candle(
            symbol="BTCUSDT",
            timestamp=1000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=0.0001,  # Very small but non-zero
            turnover=5.0
        )

        result = validator.validate(candle)
        assert result.valid


class TestDataGapDetection:
    """Test data gap detection (>5 minutes)."""

    def test_data_gap_requires_warmup(self, validator, base_candle):
        """Test that data gaps flag requires_warmup."""
        # First candle
        validator.validate(base_candle)

        # Second candle - 6 minutes later (gap > 5 minutes)
        gap_candle = Candle(
            symbol="BTCUSDT",
            timestamp=base_candle.timestamp + (6 * 60 * 1000),  # 6 minutes
            open=50100.0,
            high=50200.0,
            low=50000.0,
            close=50100.0,
            volume=100.0,
            turnover=5010000.0
        )

        result = validator.validate(gap_candle)
        assert result.valid
        assert result.requires_warmup
        assert "Data gap" in result.reason

    def test_exactly_5_minute_gap_no_warmup(self, validator, base_candle):
        """Test that exactly 5 minute gap does not require warmup."""
        # First candle
        validator.validate(base_candle)

        # Second candle - exactly 5 minutes later
        candle = Candle(
            symbol="BTCUSDT",
            timestamp=base_candle.timestamp + (5 * 60 * 1000),  # exactly 5 minutes
            open=50100.0,
            high=50200.0,
            low=50000.0,
            close=50100.0,
            volume=100.0,
            turnover=5010000.0
        )

        result = validator.validate(candle)
        assert result.valid
        assert not result.requires_warmup

    def test_large_gap_requires_warmup(self, validator, base_candle):
        """Test that large gaps (e.g., 1 hour) require warmup."""
        # First candle
        validator.validate(base_candle)

        # Second candle - 1 hour later
        gap_candle = Candle(
            symbol="BTCUSDT",
            timestamp=base_candle.timestamp + (60 * 60 * 1000),  # 1 hour
            open=50100.0,
            high=50200.0,
            low=50000.0,
            close=50100.0,
            volume=100.0,
            turnover=5010000.0
        )

        result = validator.validate(gap_candle)
        assert result.valid
        assert result.requires_warmup


class TestNormalCandleAcceptance:
    """Test normal candle acceptance."""

    def test_first_candle_accepted(self, validator, base_candle):
        """Test that first candle is always accepted."""
        result = validator.validate(base_candle)
        assert result.valid
        assert result.reason is None
        assert not result.requires_warmup

    def test_normal_sequence_accepted(self, validator):
        """Test that normal candle sequence is accepted."""
        candles = [
            Candle(
                symbol="BTCUSDT",
                timestamp=1000000 + i * 60000,  # 1 minute intervals
                open=50000.0 + i * 10,
                high=50010.0 + i * 10,
                low=49990.0 + i * 10,
                close=50005.0 + i * 10,
                volume=100.0,
                turnover=5000000.0
            )
            for i in range(5)
        ]

        for candle in candles:
            result = validator.validate(candle)
            assert result.valid
            assert not result.requires_warmup

    def test_normal_price_volatility_accepted(self, validator):
        """Test that normal price volatility (<50%) is accepted."""
        candle1 = Candle(
            symbol="BTCUSDT",
            timestamp=1000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=100.0,
            turnover=5000000.0
        )
        validator.validate(candle1)

        # 30% move - should be accepted
        candle2 = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=65000.0,
            low=50000.0,
            close=65000.0,
            volume=100.0,
            turnover=6500000.0
        )

        result = validator.validate(candle2)
        assert result.valid


class TestStateReset:
    """Test validator state reset."""

    def test_reset_single_symbol(self, validator, base_candle):
        """Test resetting a single symbol."""
        # Add a candle
        validator.validate(base_candle)
        assert "BTCUSDT" in validator._last_candles

        # Reset that symbol
        validator.reset("BTCUSDT")
        assert "BTCUSDT" not in validator._last_candles

    def test_reset_all_symbols(self, validator):
        """Test resetting all symbols."""
        # Add candles for multiple symbols
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        for symbol in symbols:
            candle = Candle(
                symbol=symbol,
                timestamp=1000000,
                open=100.0,
                high=100.0,
                low=100.0,
                close=100.0,
                volume=100.0,
                turnover=10000.0
            )
            validator.validate(candle)

        # Verify all are tracked
        assert len(validator._last_candles) == 3

        # Reset all
        validator.reset()
        assert len(validator._last_candles) == 0

    def test_reset_nonexistent_symbol(self, validator):
        """Test that resetting nonexistent symbol doesn't error."""
        # Should not raise an error
        validator.reset("NONEXISTENT")

    def test_reset_allows_revalidation(self, validator, base_candle):
        """Test that reset allows fresh validation."""
        # First candle
        validator.validate(base_candle)

        # Create a flash crash candle
        crash_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=80000.0,
            low=50000.0,
            close=80000.0,  # 60% increase
            volume=100.0,
            turnover=8000000.0
        )

        # Should be rejected (flash crash)
        result = validator.validate(crash_candle)
        assert not result.valid

        # Reset the symbol
        validator.reset("BTCUSDT")

        # Now the crash candle should be accepted (no previous candle to compare)
        result = validator.validate(crash_candle)
        assert result.valid


class TestMultipleSymbols:
    """Test that multiple symbols are tracked independently."""

    def test_independent_tracking(self, validator):
        """Test that different symbols don't interfere."""
        # Add BTCUSDT candle
        btc_candle = Candle(
            symbol="BTCUSDT",
            timestamp=1000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=100.0,
            turnover=5000000.0
        )
        validator.validate(btc_candle)

        # Add ETHUSDT candle
        eth_candle = Candle(
            symbol="ETHUSDT",
            timestamp=1000000,
            open=3000.0,
            high=3000.0,
            low=3000.0,
            close=3000.0,
            volume=100.0,
            turnover=300000.0
        )
        validator.validate(eth_candle)

        # Verify both are tracked
        assert len(validator._last_candles) == 2
        assert validator._last_candles["BTCUSDT"].close == 50000.0
        assert validator._last_candles["ETHUSDT"].close == 3000.0

    def test_flash_crash_only_affects_one_symbol(self, validator):
        """Test that flash crash in one symbol doesn't affect others."""
        # Setup two symbols
        btc_candle1 = Candle(
            symbol="BTCUSDT",
            timestamp=1000000,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=100.0,
            turnover=5000000.0
        )
        validator.validate(btc_candle1)

        eth_candle1 = Candle(
            symbol="ETHUSDT",
            timestamp=1000000,
            open=3000.0,
            high=3000.0,
            low=3000.0,
            close=3000.0,
            volume=100.0,
            turnover=300000.0
        )
        validator.validate(eth_candle1)

        # Flash crash in BTC
        btc_crash = Candle(
            symbol="BTCUSDT",
            timestamp=1060000,
            open=50000.0,
            high=80000.0,
            low=50000.0,
            close=80000.0,  # 60% increase
            volume=100.0,
            turnover=8000000.0
        )
        result = validator.validate(btc_crash)
        assert not result.valid

        # Normal ETH candle should still be accepted
        eth_candle2 = Candle(
            symbol="ETHUSDT",
            timestamp=1060000,
            open=3000.0,
            high=3100.0,
            low=3000.0,
            close=3050.0,  # Normal move
            volume=100.0,
            turnover=305000.0
        )
        result = validator.validate(eth_candle2)
        assert result.valid

    def test_data_gap_only_affects_one_symbol(self, validator):
        """Test that data gap in one symbol doesn't affect others."""
        # Setup two symbols with same timestamp
        timestamp = 1000000

        btc_candle = Candle(
            symbol="BTCUSDT",
            timestamp=timestamp,
            open=50000.0,
            high=50000.0,
            low=50000.0,
            close=50000.0,
            volume=100.0,
            turnover=5000000.0
        )
        validator.validate(btc_candle)

        eth_candle = Candle(
            symbol="ETHUSDT",
            timestamp=timestamp,
            open=3000.0,
            high=3000.0,
            low=3000.0,
            close=3000.0,
            volume=100.0,
            turnover=300000.0
        )
        validator.validate(eth_candle)

        # BTC with 6 minute gap (should require warmup)
        btc_gap = Candle(
            symbol="BTCUSDT",
            timestamp=timestamp + (6 * 60 * 1000),
            open=50100.0,
            high=50100.0,
            low=50100.0,
            close=50100.0,
            volume=100.0,
            turnover=5010000.0
        )
        result = validator.validate(btc_gap)
        assert result.valid
        assert result.requires_warmup

        # ETH with normal 1 minute gap (should not require warmup)
        eth_normal = Candle(
            symbol="ETHUSDT",
            timestamp=timestamp + (1 * 60 * 1000),
            open=3010.0,
            high=3010.0,
            low=3010.0,
            close=3010.0,
            volume=100.0,
            turnover=301000.0
        )
        result = validator.validate(eth_normal)
        assert result.valid
        assert not result.requires_warmup
