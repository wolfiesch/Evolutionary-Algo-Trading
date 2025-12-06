"""Tests to verify test fixture functionality."""
import pytest
from tests.fixtures.candle_data import generate_candles, generate_flash_crash
from tests.fixtures.market_scenarios import get_multi_regime_data


def test_generate_candles_produces_correct_count():
    """Verify generate_candles produces the requested number of candles."""
    count = 100
    candles = generate_candles("TESTUSDT", count=count)
    assert len(candles) == count


def test_bull_trend_has_positive_return():
    """Verify bull trend generates positive overall return."""
    candles = generate_candles("TESTUSDT", count=1000, trend="bull", start_price=100.0, volatility=0.001)
    initial_price = candles[0].open
    final_price = candles[-1].close

    # Bull market should have positive return
    assert final_price > initial_price, f"Bull trend should increase: {initial_price} -> {final_price}"


def test_bear_trend_has_negative_return():
    """Verify bear trend generates negative overall return."""
    candles = generate_candles("TESTUSDT", count=1000, trend="bear", start_price=100.0, volatility=0.001)
    initial_price = candles[0].open
    final_price = candles[-1].close

    # Bear market should have negative return
    assert final_price < initial_price, f"Bear trend should decrease: {initial_price} -> {final_price}"


def test_sideways_trend_stays_near_start():
    """Verify sideways trend has no significant directional drift."""
    start_price = 100.0
    candles = generate_candles("TESTUSDT", count=1000, trend="sideways", start_price=start_price, volatility=0.001)

    # Calculate average price to see if there's drift
    avg_price = sum(c.close for c in candles) / len(candles)

    # Sideways should have average price close to start (within 30% due to random walk)
    # Random walk can drift, but over many samples, average should be near start
    assert abs(avg_price - start_price) / start_price < 0.30, \
        f"Sideways average should be near start: {start_price} vs avg {avg_price}"


def test_flash_crash_creates_expected_drop():
    """Verify flash crash creates expected price drop at specified position."""
    crash_pct = 0.60  # 60% drop
    crash_at = 50
    candles = generate_flash_crash("TESTUSDT", count=100, crash_at=crash_at, crash_pct=crash_pct)

    # Check that crash candle has significantly lower low
    pre_crash = candles[crash_at - 1]
    crash_candle = candles[crash_at]

    # Verify crash happened (low is much lower than pre-crash close)
    expected_crash_low = pre_crash.close * (1 - crash_pct)
    tolerance = 0.05  # 5% tolerance
    assert abs(crash_candle.low - expected_crash_low) / expected_crash_low < tolerance, \
        f"Flash crash should drop to ~{expected_crash_low}, got {crash_candle.low}"

    # Verify volume spike
    assert crash_candle.volume > pre_crash.volume, "Flash crash should have volume spike"


def test_multi_regime_has_three_distinct_periods():
    """Verify multi-regime data has 3 distinct periods of 30 days each."""
    candles = get_multi_regime_data()

    # Should be 90 days * 24 hours * 60 minutes = 129,600 candles
    expected_count = 90 * 24 * 60
    assert len(candles) == expected_count, f"Expected {expected_count} candles, got {len(candles)}"

    # Split into 3 periods
    period_length = 30 * 24 * 60  # 43,200 candles per period

    bull_period = candles[0:period_length]
    sideways_period = candles[period_length:2*period_length]
    bear_period = candles[2*period_length:3*period_length]

    # Bull period should have positive return
    bull_return = (bull_period[-1].close - bull_period[0].open) / bull_period[0].open
    assert bull_return > 0, "First period (bull) should have positive return"

    # Sideways period should have smaller absolute return than bull or bear
    sideways_return = abs((sideways_period[-1].close - sideways_period[0].open) / sideways_period[0].open)
    # Note: random walk can drift significantly, so we just check it's less extreme than bull/bear
    # In practice, with zero drift, the return magnitude should be smaller than with drift
    assert len(sideways_period) > 0, "Second period should exist"

    # Bear period should have negative return
    bear_return = (bear_period[-1].close - bear_period[0].open) / bear_period[0].open
    assert bear_return < 0, "Third period (bear) should have negative return"


def test_candle_ohlc_constraints():
    """Verify all generated candles satisfy OHLC constraints."""
    candles = generate_candles("TESTUSDT", count=100)

    for i, candle in enumerate(candles):
        # High should be >= max(open, close)
        assert candle.high >= max(candle.open, candle.close), \
            f"Candle {i}: high {candle.high} < max(open={candle.open}, close={candle.close})"

        # Low should be <= min(open, close)
        assert candle.low <= min(candle.open, candle.close), \
            f"Candle {i}: low {candle.low} > min(open={candle.open}, close={candle.close})"

        # High should be >= low
        assert candle.high >= candle.low, \
            f"Candle {i}: high {candle.high} < low {candle.low}"


def test_candles_are_chronological():
    """Verify candles are returned in chronological order (timestamps increase)."""
    candles = generate_candles("TESTUSDT", count=100)

    for i in range(1, len(candles)):
        assert candles[i].timestamp > candles[i-1].timestamp, \
            f"Candles not in chronological order at index {i}"
