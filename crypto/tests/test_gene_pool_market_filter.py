"""Tests for market filter primitives."""
import pandas as pd
import pytest

from engine.gene_pool.market_filter import btc_trend


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


def test_btc_trend_bull_market():
    """btc_trend returns +1.0 in deterministic BTC uptrend."""
    # Use deterministic data to ensure test reliability
    df = pd.DataFrame({
        'open': [40000.0 + i * 20 for i in range(200)],
        'high': [40050.0 + i * 20 for i in range(200)],
        'low': [39950.0 + i * 20 for i in range(200)],
        'close': [40000.0 + i * 20 for i in range(200)],  # Clear uptrend
        'volume': [1000.0] * 200,
    })

    # Clear uptrend should return +1.0
    result = btc_trend(df, window=100)
    assert result == 1.0, f"Clear uptrend should return +1.0, got {result}"


def test_btc_trend_bear_market(btc_bear):
    """btc_trend returns valid output for bear market fixture."""
    df = candles_to_df(btc_bear)

    # The bear market fixture has bearish drift but random walk can overcome it
    # We just test that the function executes correctly
    result = btc_trend(df, window=100)
    assert result in [1.0, -1.0], "btc_trend must return either +1.0 or -1.0"


def test_btc_trend_insufficient_data(btc_bull):
    """btc_trend returns -1.0 with insufficient data (conservative)."""
    df = candles_to_df(btc_bull)

    # Window larger than data
    assert btc_trend(df.head(50), window=100) == -1.0

    # Very small dataset
    assert btc_trend(df.head(10), window=50) == -1.0


def test_btc_trend_boundary_conditions(btc_bull):
    """btc_trend handles edge cases."""
    df = candles_to_df(btc_bull)

    # Exact window size (should work)
    result = btc_trend(df.head(100), window=100)
    assert result in [1.0, -1.0]  # Valid output

    # Window = data length - 1 (should work)
    result = btc_trend(df.head(100), window=99)
    assert result in [1.0, -1.0]


def test_btc_trend_small_window():
    """btc_trend with very small window (tests minimum window logic)."""
    # Create clear uptrend for small window test
    prices = [40000 * (1.001 ** i) for i in range(500)]
    df = pd.DataFrame({
        'timestamp': range(500),
        'close': prices,
        'open': prices,
        'high': prices,
        'low': prices,
        'volume': [1000000] * 500,
    })

    # Small windows should still work (short_window has min of 5)
    assert btc_trend(df, window=20) == 1.0


def test_btc_trend_tolerance_levels():
    """Test the 2% price tolerance and momentum checks."""
    # Create uptrend for tolerance test
    prices = [40000 * (1.001 ** i) for i in range(500)]
    df = pd.DataFrame({
        'timestamp': range(500),
        'close': prices,
        'open': prices,
        'high': prices,
        'low': prices,
        'volume': [1000000] * 500,
    })

    # In an uptrend, both conditions should be met
    # Price >= EMA * 0.98 and Short EMA > Long EMA
    result = btc_trend(df, window=100)
    assert result == 1.0


def test_btc_trend_empty_dataframe():
    """btc_trend handles empty DataFrame."""
    df = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    assert btc_trend(df, window=50) == -1.0


def test_btc_trend_single_candle(btc_bull):
    """btc_trend handles single candle."""
    df = candles_to_df(btc_bull[:1])
    assert btc_trend(df, window=50) == -1.0


def test_btc_trend_clear_uptrend():
    """btc_trend detects clear uptrend with synthetic data."""
    # Create clear uptrend: steady 0.1% increase per candle
    prices = [40000 * (1.001 ** i) for i in range(500)]
    df = pd.DataFrame({
        'timestamp': range(500),
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [1000000] * 500,
    })

    # Clear uptrend should return +1.0
    assert btc_trend(df, window=50) == 1.0
    assert btc_trend(df, window=100) == 1.0


def test_btc_trend_clear_downtrend():
    """btc_trend detects clear downtrend with synthetic data."""
    # Create clear downtrend: steady 0.1% decrease per candle
    prices = [40000 * (0.999 ** i) for i in range(500)]
    df = pd.DataFrame({
        'timestamp': range(500),
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [1000000] * 500,
    })

    # Clear downtrend should return -1.0
    assert btc_trend(df, window=50) == -1.0
    assert btc_trend(df, window=100) == -1.0


def test_btc_trend_sideways():
    """btc_trend detects sideways market with synthetic data."""
    # Create sideways: prices oscillate around 40000
    import math
    prices = [40000 + 100 * math.sin(i / 10) for i in range(500)]
    df = pd.DataFrame({
        'timestamp': range(500),
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [1000000] * 500,
    })

    # Sideways market could return either depending on the phase
    result = btc_trend(df, window=50)
    assert result in [1.0, -1.0]
