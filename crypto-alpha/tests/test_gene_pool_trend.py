"""Tests for trend primitives."""
import pandas as pd
import pytest

from engine.gene_pool.trend import ema_trend, price_position


def candles_to_df(candles: list) -> pd.DataFrame:
    """Convert list of Candle objects to DataFrame."""
    data = {
        'timestamp': [c.timestamp for c in candles],
        'open': [c.open for c in candles],
        'high': [c.high for c in candles],
        'low': [c.low for c in candles],
        'close': [c.close for c in candles],
        'volume': [c.volume for c in candles],
    }
    return pd.DataFrame(data)


def test_ema_trend_bull_market(bull_market):
    """ema_trend returns valid output (+1.0 or -1.0) with sufficient data."""
    df = candles_to_df(bull_market)

    # Test that function returns valid values
    result = ema_trend(df, fast=9, slow=21)
    assert result in [1.0, -1.0], f"Expected +1.0 or -1.0, got {result}"

    result = ema_trend(df, fast=12, slow=26)
    assert result in [1.0, -1.0], f"Expected +1.0 or -1.0, got {result}"


def test_ema_trend_bear_market(bear_market):
    """ema_trend returns valid output (+1.0 or -1.0) with sufficient data."""
    df = candles_to_df(bear_market)

    # Test that function returns valid values
    result = ema_trend(df, fast=9, slow=21)
    assert result in [1.0, -1.0], f"Expected +1.0 or -1.0, got {result}"

    result = ema_trend(df, fast=50, slow=100)
    assert result in [1.0, -1.0], f"Expected +1.0 or -1.0, got {result}"


def test_ema_trend_deterministic_uptrend():
    """ema_trend returns +1.0 on deterministic uptrending data."""
    # Create simple uptrending data
    data = {
        'timestamp': list(range(1000, 1200)),
        'open': [100 + i * 0.5 for i in range(200)],
        'high': [100.5 + i * 0.5 for i in range(200)],
        'low': [99.5 + i * 0.5 for i in range(200)],
        'close': [100 + i * 0.5 for i in range(200)],
        'volume': [1000000.0] * 200,
    }
    df = pd.DataFrame(data)

    # In a clear uptrend, fast EMA should be > slow EMA
    assert ema_trend(df, fast=9, slow=21) == 1.0
    assert ema_trend(df, fast=12, slow=26) == 1.0


def test_ema_trend_deterministic_downtrend():
    """ema_trend returns -1.0 on deterministic downtrending data."""
    # Create simple downtrending data
    data = {
        'timestamp': list(range(1000, 1200)),
        'open': [200 - i * 0.5 for i in range(200)],
        'high': [200.5 - i * 0.5 for i in range(200)],
        'low': [199.5 - i * 0.5 for i in range(200)],
        'close': [200 - i * 0.5 for i in range(200)],
        'volume': [1000000.0] * 200,
    }
    df = pd.DataFrame(data)

    # In a clear downtrend, fast EMA should be < slow EMA
    assert ema_trend(df, fast=9, slow=21) == -1.0
    assert ema_trend(df, fast=12, slow=26) == -1.0


def test_ema_trend_insufficient_data(bull_market):
    """ema_trend returns 0.0 with insufficient data."""
    df = candles_to_df(bull_market)

    # Slow period larger than data
    assert ema_trend(df.head(50), fast=9, slow=100) == 0.0

    # Very small dataset
    assert ema_trend(df.head(10), fast=9, slow=21) == 0.0


def test_ema_trend_boundary_conditions(bull_market):
    """ema_trend handles edge cases."""
    df = candles_to_df(bull_market)

    # Exact slow period size (should work)
    result = ema_trend(df.head(100), fast=20, slow=100)
    assert result in [1.0, -1.0]  # Valid output

    # Slow period = data length - 1 (should work)
    result = ema_trend(df.head(100), fast=20, slow=99)
    assert result in [1.0, -1.0]


def test_ema_trend_empty_dataframe():
    """ema_trend handles empty DataFrame."""
    df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    assert ema_trend(df, fast=9, slow=21) == 0.0


def test_ema_trend_single_candle(bull_market):
    """ema_trend handles single candle."""
    df = candles_to_df(bull_market[:1])
    assert ema_trend(df, fast=9, slow=21) == 0.0


def test_price_position_range_capping(bull_market):
    """price_position caps output at ±3.0."""
    df = candles_to_df(bull_market)

    # Test with various periods
    for period in [10, 20, 50, 100]:
        result = price_position(df, period)
        assert -3.0 <= result <= 3.0, f"Result {result} outside [-3.0, 3.0] for period {period}"


def test_price_position_bull_market(bull_market):
    """price_position returns value within valid range."""
    df = candles_to_df(bull_market)

    # Test that function returns value in valid range
    result = price_position(df, period=20)
    assert -3.0 <= result <= 3.0


def test_price_position_bear_market(bear_market):
    """price_position returns value within valid range."""
    df = candles_to_df(bear_market)

    # Test that function returns value in valid range
    result = price_position(df, period=100)
    assert -3.0 <= result <= 3.0


def test_price_position_deterministic_uptrend():
    """price_position returns positive value on deterministic uptrending data."""
    # Create simple uptrending data
    data = {
        'timestamp': list(range(1000, 1200)),
        'open': [100 + i * 0.5 for i in range(200)],
        'high': [100.5 + i * 0.5 for i in range(200)],
        'low': [99.5 + i * 0.5 for i in range(200)],
        'close': [100 + i * 0.5 for i in range(200)],
        'volume': [1000000.0] * 200,
    }
    df = pd.DataFrame(data)

    # In a clear uptrend, price should be above EMA
    result = price_position(df, period=20)
    assert result > 0.0


def test_price_position_deterministic_downtrend():
    """price_position returns negative value on deterministic downtrending data."""
    # Create simple downtrending data
    data = {
        'timestamp': list(range(1000, 1200)),
        'open': [200 - i * 0.5 for i in range(200)],
        'high': [200.5 - i * 0.5 for i in range(200)],
        'low': [199.5 - i * 0.5 for i in range(200)],
        'close': [200 - i * 0.5 for i in range(200)],
        'volume': [1000000.0] * 200,
    }
    df = pd.DataFrame(data)

    # In a clear downtrend, price should be below EMA
    result = price_position(df, period=20)
    assert result < 0.0


def test_price_position_insufficient_data(bull_market):
    """price_position returns 0.0 with insufficient data."""
    df = candles_to_df(bull_market)

    # Period larger than data
    assert price_position(df.head(50), period=100) == 0.0

    # Very small dataset
    assert price_position(df.head(5), period=20) == 0.0


def test_price_position_zero_atr():
    """price_position handles zero ATR edge case."""
    # Create a DataFrame with identical OHLC (zero ATR)
    data = {
        'timestamp': [1000 + i for i in range(100)],
        'open': [100.0] * 100,
        'high': [100.0] * 100,
        'low': [100.0] * 100,
        'close': [100.0] * 100,
        'volume': [1000.0] * 100,
    }
    df = pd.DataFrame(data)

    # Should return 0.0 when ATR is zero
    assert price_position(df, period=20) == 0.0


def test_price_position_boundary_conditions(bull_market):
    """price_position handles edge cases."""
    df = candles_to_df(bull_market)

    # Exact period size (should work)
    result = price_position(df.head(100), period=100)
    assert -3.0 <= result <= 3.0

    # Period = data length - 1 (should work)
    result = price_position(df.head(100), period=99)
    assert -3.0 <= result <= 3.0


def test_price_position_empty_dataframe():
    """price_position handles empty DataFrame."""
    df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    assert price_position(df, period=20) == 0.0


def test_price_position_single_candle(bull_market):
    """price_position handles single candle."""
    df = candles_to_df(bull_market[:1])
    assert price_position(df, period=20) == 0.0


def test_price_position_sideways_market(sideways_market):
    """price_position returns value within valid range in sideways market."""
    df = candles_to_df(sideways_market)

    # In sideways market, price should oscillate around EMA
    result = price_position(df, period=50)
    # Should be within valid range (capped at ±3.0)
    assert -3.0 <= result <= 3.0
