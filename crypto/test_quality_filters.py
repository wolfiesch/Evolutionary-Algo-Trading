"""Test Sprint 2 quality filters integration."""
import time
from data.storage.models import Candle
from data.quality_filters import CandleValidator


def test_clock_sync_validation():
    """Test T1.1: Clock sync validation."""
    validator = CandleValidator()
    current_time_ms = int(time.time() * 1000)

    # Test 1: Future timestamp (should reject)
    future_candle = Candle(
        symbol="BTCUSDT",
        timestamp=current_time_ms + 120000,  # 2 minutes in future
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=100.0,
        turnover=5000000.0,
    )
    result = validator.validate(future_candle)
    assert not result.valid, f"Expected future candle to be rejected, got: {result.reason}"
    assert "future" in result.reason.lower()
    print("✓ Future timestamp correctly rejected")

    # Test 2: Very old timestamp (should reject)
    old_candle = Candle(
        symbol="BTCUSDT",
        timestamp=current_time_ms - (400 * 24 * 60 * 60 * 1000),  # 400 days old
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=100.0,
        turnover=5000000.0,
    )
    result = validator.validate(old_candle)
    assert not result.valid, f"Expected old candle to be rejected, got: {result.reason}"
    assert "too old" in result.reason.lower()
    print("✓ Very old timestamp correctly rejected")

    # Test 3: Valid recent timestamp (should pass)
    valid_candle = Candle(
        symbol="BTCUSDT",
        timestamp=current_time_ms - 10000,  # 10 seconds ago
        open=50000.0,
        high=50100.0,
        low=49900.0,
        close=50050.0,
        volume=100.0,
        turnover=5000000.0,
    )
    result = validator.validate(valid_candle)
    assert result.valid, f"Expected valid candle to pass, got: {result.reason}"
    print("✓ Valid timestamp correctly accepted")


def test_volume_anomaly_filters():
    """Test T1.2: Volume anomaly filters."""
    validator = CandleValidator()
    current_time_ms = int(time.time() * 1000)

    # Test 1: Zero volume (should reject)
    zero_vol_candle = Candle(
        symbol="ETHUSDT",
        timestamp=current_time_ms - 60000,
        open=3000.0,
        high=3010.0,
        low=2990.0,
        close=3005.0,
        volume=0.0,
        turnover=0.0,
    )
    result = validator.validate(zero_vol_candle)
    assert not result.valid
    assert "zero volume" in result.reason.lower()
    print("✓ Zero volume correctly rejected")

    # Test 2: Normal volume candles
    validator.reset("ETHUSDT")  # Reset for fresh test
    for i in range(10):
        candle = Candle(
            symbol="ETHUSDT",
            timestamp=current_time_ms - 60000 * (10 - i),
            open=3000.0,
            high=3010.0,
            low=2990.0,
            close=3005.0,
            volume=100.0,  # Normal volume
            turnover=300000.0,
        )
        result = validator.validate(candle)
        assert result.valid
    print("✓ Normal volume candles accepted")

    # Test 3: Volume spike (should reject after baseline established)
    spike_candle = Candle(
        symbol="ETHUSDT",
        timestamp=current_time_ms - 50000,
        open=3000.0,
        high=3010.0,
        low=2990.0,
        close=3005.0,
        volume=1500.0,  # 15x normal volume
        turnover=4500000.0,
    )
    result = validator.validate(spike_candle)
    assert not result.valid
    assert "volume spike" in result.reason.lower()
    print("✓ Volume spike correctly rejected")


def test_price_spike_detection():
    """Test T1.3: Price spike detection."""
    validator = CandleValidator()
    current_time_ms = int(time.time() * 1000)

    # Establish baseline with normal candles
    for i in range(10):
        candle = Candle(
            symbol="SOLUSDT",
            timestamp=current_time_ms - 60000 * (10 - i),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1000.0,
            turnover=100000.0,
        )
        result = validator.validate(candle)
        assert result.valid
    print("✓ Baseline candles accepted")

    # Test 1: Wick anomaly (abnormally large range)
    wick_candle = Candle(
        symbol="SOLUSDT",
        timestamp=current_time_ms - 50000,
        open=100.0,
        high=150.0,  # 50 point wick (vs normal 2 point range)
        low=50.0,
        close=100.0,
        volume=1000.0,
        turnover=100000.0,
    )
    result = validator.validate(wick_candle)
    assert not result.valid
    assert "wick anomaly" in result.reason.lower()
    print("✓ Wick anomaly correctly rejected")

    # Test 2: Flash crash (>50% price move)
    validator.reset("SOLUSDT")
    first_candle = Candle(
        symbol="SOLUSDT",
        timestamp=current_time_ms - 120000,
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1000.0,
        turnover=100000.0,
    )
    validator.validate(first_candle)

    crash_candle = Candle(
        symbol="SOLUSDT",
        timestamp=current_time_ms - 60000,
        open=40.0,
        high=45.0,
        low=39.0,
        close=40.0,  # 60% drop
        volume=5000.0,
        turnover=200000.0,
    )
    result = validator.validate(crash_candle)
    assert not result.valid
    assert "flash crash" in result.reason.lower()
    print("✓ Flash crash correctly rejected")


def test_gap_detection():
    """Test T1.4: Gap detection improvements."""
    validator = CandleValidator()
    current_time_ms = int(time.time() * 1000)

    # First candle
    candle1 = Candle(
        symbol="XRPUSDT",
        timestamp=current_time_ms - 3600000,  # 1 hour ago
        open=0.5,
        high=0.51,
        low=0.49,
        close=0.50,
        volume=10000.0,
        turnover=5000.0,
    )
    result = validator.validate(candle1)
    assert result.valid

    # Test 1: Small gap (< 5 min) - should pass
    candle2 = Candle(
        symbol="XRPUSDT",
        timestamp=current_time_ms - 3540000,  # 1 minute later
        open=0.50,
        high=0.51,
        low=0.49,
        close=0.50,
        volume=10000.0,
        turnover=5000.0,
    )
    result = validator.validate(candle2)
    assert result.valid
    assert not result.requires_warmup
    print("✓ Small gap correctly handled")

    # Test 2: Medium gap (> 5 min but < 1 hour) - should trigger warmup
    candle3 = Candle(
        symbol="XRPUSDT",
        timestamp=current_time_ms - 3000000,  # 10 minutes later
        open=0.50,
        high=0.51,
        low=0.49,
        close=0.50,
        volume=10000.0,
        turnover=5000.0,
    )
    result = validator.validate(candle3)
    assert result.valid
    assert result.requires_warmup
    assert "gap" in result.reason.lower()
    print("✓ Medium gap correctly triggers warmup")

    # Test 3: Extreme gap (> 1 hour) - should force reset
    validator.reset("XRPUSDT")
    validator.validate(candle1)  # Re-establish baseline

    extreme_gap_candle = Candle(
        symbol="XRPUSDT",
        timestamp=current_time_ms + 1000,  # 1 hour + 1 second later from candle1
        open=0.50,
        high=0.51,
        low=0.49,
        close=0.50,
        volume=10000.0,
        turnover=5000.0,
    )
    result = validator.validate(extreme_gap_candle)
    assert result.valid
    assert result.requires_warmup
    assert "extreme" in result.reason.lower() or "gap" in result.reason.lower()
    print("✓ Extreme gap correctly forces reset")


def main():
    """Run all Sprint 2 integration tests."""
    print("\n=== Sprint 2 Quality Filters Integration Test ===\n")

    print("T1.1: Clock Sync Validation")
    test_clock_sync_validation()
    print()

    print("T1.2: Volume Anomaly Filters")
    test_volume_anomaly_filters()
    print()

    print("T1.3: Price Spike Detection")
    test_price_spike_detection()
    print()

    print("T1.4: Gap Detection Improvements")
    test_gap_detection()
    print()

    print("=== All Sprint 2 Tests Passed! ✓ ===\n")


if __name__ == "__main__":
    main()
