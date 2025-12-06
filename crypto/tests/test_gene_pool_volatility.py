"""Tests for volatility primitives."""
import pytest
import pandas as pd

from shared.engine.gene_pool.volatility import atr_regime, atr_percentile


def candles_to_df(candles):
    """Convert Candle objects to DataFrame."""
    data = {
        "timestamp": [c.timestamp for c in candles],
        "open": [c.open for c in candles],
        "high": [c.high for c in candles],
        "low": [c.low for c in candles],
        "close": [c.close for c in candles],
        "volume": [c.volume for c in candles],
    }
    return pd.DataFrame(data)


class TestATRRegime:
    """Tests for atr_regime function."""

    def test_returns_valid_values(self, sample_candles):
        """Should return one of [-1.0, 0.0, +1.0]."""
        df = candles_to_df(sample_candles)
        result = atr_regime(df, period=14, lookback=50)

        assert result in [-1.0, 0.0, 1.0], f"Expected -1.0, 0.0, or 1.0, got {result}"

    def test_insufficient_data_returns_zero(self, sample_candles):
        """Should return 0.0 when insufficient data."""
        df = candles_to_df(sample_candles[:50])  # Only 50 candles
        result = atr_regime(df, period=14, lookback=100)  # Need 114 total

        assert result == 0.0, "Should return 0.0 for insufficient data"

    def test_classifies_volatility_regimes(self, multi_regime):
        """Should correctly classify high/normal/low volatility."""
        df = candles_to_df(multi_regime)

        # Test at different points in the dataset
        # Early period (first 200 candles) - should have some volatility
        early_df = df.iloc[:200].copy()
        early_result = atr_regime(early_df, period=14, lookback=100)
        assert early_result in [-1.0, 0.0, 1.0]

        # Middle period
        mid_df = df.iloc[:1000].copy()
        mid_result = atr_regime(mid_df, period=14, lookback=100)
        assert mid_result in [-1.0, 0.0, 1.0]

        # Full dataset
        full_result = atr_regime(df, period=14, lookback=100)
        assert full_result in [-1.0, 0.0, 1.0]

    def test_different_parameters(self, sample_candles):
        """Should work with different period and lookback values."""
        df = candles_to_df(sample_candles)

        # Short period, short lookback
        result1 = atr_regime(df, period=7, lookback=30)
        assert result1 in [-1.0, 0.0, 1.0]

        # Longer period, longer lookback (but still fits in 100 candles)
        result2 = atr_regime(df, period=20, lookback=50)
        assert result2 in [-1.0, 0.0, 1.0]

    def test_extreme_volatility_detection(self):
        """Should detect extreme volatility changes."""
        # Create synthetic data with varying volatility
        # Low volatility period
        low_vol_data = {
            "timestamp": list(range(200)),
            "open": [100.0] * 200,
            "high": [100.1] * 200,
            "low": [99.9] * 200,
            "close": [100.0] * 200,
            "volume": [1000.0] * 200,
        }
        low_vol_df = pd.DataFrame(low_vol_data)

        # Add high volatility spike at the end
        for i in range(180, 200):
            low_vol_df.loc[i, "high"] = 105.0
            low_vol_df.loc[i, "low"] = 95.0

        result = atr_regime(low_vol_df, period=14, lookback=100)
        assert result == 1.0, "Should detect high volatility spike"


class TestATRPercentile:
    """Tests for atr_percentile function."""

    def test_returns_valid_range(self, sample_candles):
        """Should return value in [0.0, 1.0]."""
        df = candles_to_df(sample_candles)
        result = atr_percentile(df, period=14, lookback=50)

        assert 0.0 <= result <= 1.0, f"Expected value in [0.0, 1.0], got {result}"

    def test_insufficient_data_returns_half(self, sample_candles):
        """Should return 0.5 when insufficient data."""
        df = candles_to_df(sample_candles[:50])  # Only 50 candles
        result = atr_percentile(df, period=14, lookback=100)  # Need 114 total

        assert result == 0.5, "Should return 0.5 for insufficient data"

    def test_percentile_calculation(self, multi_regime):
        """Should calculate percentile correctly."""
        df = candles_to_df(multi_regime)

        # Test at different points
        result = atr_percentile(df, period=14, lookback=100)

        # Should be a valid percentile
        assert 0.0 <= result <= 1.0
        assert isinstance(result, float)

    def test_different_parameters(self, sample_candles):
        """Should work with different period and lookback values."""
        df = candles_to_df(sample_candles)

        # Short period, short lookback
        result1 = atr_percentile(df, period=7, lookback=30)
        assert 0.0 <= result1 <= 1.0

        # Longer period, longer lookback
        result2 = atr_percentile(df, period=20, lookback=50)
        assert 0.0 <= result2 <= 1.0

    def test_extreme_percentiles(self):
        """Should return extreme percentiles for extreme volatility."""
        # Create synthetic data with consistent low volatility
        # then a spike at the end
        data = {
            "timestamp": list(range(200)),
            "open": [100.0] * 200,
            "high": [100.1] * 200,
            "low": [99.9] * 200,
            "close": [100.0] * 200,
            "volume": [1000.0] * 200,
        }
        df = pd.DataFrame(data)

        # Add high volatility spike at the very end
        for i in range(195, 200):
            df.loc[i, "high"] = 110.0
            df.loc[i, "low"] = 90.0

        result = atr_percentile(df, period=14, lookback=100)

        # Should be very high percentile (close to 1.0)
        assert result > 0.9, f"Expected high percentile for volatility spike, got {result}"

    def test_varying_volatility_regimes(self, multi_regime):
        """Should show varying volatility across different market regimes."""
        df = candles_to_df(multi_regime)

        # Collect percentiles at different points in time
        percentiles = []
        for i in range(150, len(df), 500):
            slice_df = df.iloc[:i].copy()
            if len(slice_df) >= 114:  # Minimum required
                p = atr_percentile(slice_df, period=14, lookback=100)
                percentiles.append(p)

        # Should have valid percentiles
        assert all(0.0 <= p <= 1.0 for p in percentiles)
        # Should have some variation (not all the same)
        assert len(set(percentiles)) > 1, "Percentiles should vary across regimes"


class TestIntegration:
    """Integration tests for volatility primitives."""

    def test_regime_and_percentile_consistency(self, sample_candles):
        """atr_regime and atr_percentile should be consistent."""
        df = candles_to_df(sample_candles)

        regime = atr_regime(df, period=14, lookback=50)
        percentile = atr_percentile(df, period=14, lookback=50)

        # High regime should correspond to high percentile
        if regime == 1.0:
            assert percentile > 0.75, f"High regime should have percentile > 0.75, got {percentile}"

        # Low regime should correspond to low percentile
        if regime == -1.0:
            assert percentile < 0.25, f"Low regime should have percentile < 0.25, got {percentile}"

        # Normal regime should be in middle
        if regime == 0.0:
            # Either insufficient data or in middle range
            if percentile != 0.5:  # Not the insufficient data case
                assert 0.25 <= percentile <= 0.75

    def test_both_handle_insufficient_data(self, sample_candles):
        """Both functions should handle insufficient data gracefully."""
        df = candles_to_df(sample_candles[:10])  # Very few candles

        regime = atr_regime(df, period=14, lookback=100)
        percentile = atr_percentile(df, period=14, lookback=100)

        assert regime == 0.0, "atr_regime should return 0.0 for insufficient data"
        assert percentile == 0.5, "atr_percentile should return 0.5 for insufficient data"
