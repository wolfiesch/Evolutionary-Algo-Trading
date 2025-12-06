"""Tests for volume primitives in gene pool."""
import pytest
import pandas as pd
import numpy as np

from shared.engine.gene_pool.volume import volume_intensity, vwap_distance
from data.storage.models import Candle


def candles_to_dataframe(candles: list[Candle]) -> pd.DataFrame:
    """Convert list of Candle objects to DataFrame."""
    data = {
        'symbol': [c.symbol for c in candles],
        'timestamp': [c.timestamp for c in candles],
        'open': [c.open for c in candles],
        'high': [c.high for c in candles],
        'low': [c.low for c in candles],
        'close': [c.close for c in candles],
        'volume': [c.volume for c in candles],
        'turnover': [c.turnover for c in candles],
    }
    return pd.DataFrame(data)


class TestVolumeIntensity:
    """Test suite for volume_intensity primitive."""

    def test_returns_one_when_volume_exceeds_threshold(self, sample_candles):
        """Test that volume_intensity returns 1.0 when volume > threshold * avg."""
        df = candles_to_dataframe(sample_candles)

        # Set up data: period=20, threshold=2.0
        period = 20
        threshold = 2.0

        # Calculate average volume for last 20 candles (excluding current)
        avg_volume = df['volume'].iloc[-(period + 1):-1].mean()

        # Set current volume to exceed threshold
        df.loc[df.index[-1], 'volume'] = avg_volume * threshold * 1.5  # 150% of threshold

        result = volume_intensity(df, period=period, threshold=threshold)
        assert result == 1.0

    def test_returns_zero_when_volume_below_threshold(self, sample_candles):
        """Test that volume_intensity returns 0.0 when volume <= threshold * avg."""
        df = candles_to_dataframe(sample_candles)

        period = 20
        threshold = 2.0

        # Calculate average volume
        avg_volume = df['volume'].iloc[-(period + 1):-1].mean()

        # Set current volume below threshold
        df.loc[df.index[-1], 'volume'] = avg_volume * threshold * 0.5  # 50% of threshold

        result = volume_intensity(df, period=period, threshold=threshold)
        assert result == 0.0

    def test_returns_zero_when_volume_exactly_at_threshold(self, sample_candles):
        """Test that volume_intensity returns 0.0 when volume == threshold * avg."""
        df = candles_to_dataframe(sample_candles)

        period = 20
        threshold = 2.0

        # Calculate average volume
        avg_volume = df['volume'].iloc[-(period + 1):-1].mean()

        # Set current volume exactly at threshold (not exceeding)
        df.loc[df.index[-1], 'volume'] = avg_volume * threshold

        result = volume_intensity(df, period=period, threshold=threshold)
        assert result == 0.0

    def test_handles_insufficient_data(self):
        """Test that volume_intensity returns 0.0 with insufficient data."""
        # Create DataFrame with only 10 candles
        small_df = pd.DataFrame({
            'volume': [1000] * 10,
            'close': [100] * 10,
        })

        # Request period of 20 (need 21 candles)
        result = volume_intensity(small_df, period=20, threshold=2.0)
        assert result == 0.0

    def test_handles_zero_average_volume(self, sample_candles):
        """Test that volume_intensity handles zero average volume gracefully."""
        df = candles_to_dataframe(sample_candles)

        # Set historical volumes to zero
        df.loc[df.index[:-1], 'volume'] = 0.0

        result = volume_intensity(df, period=20, threshold=2.0)
        assert result == 0.0

    def test_handles_missing_volume_column(self, sample_candles):
        """Test that volume_intensity handles missing volume column."""
        df = candles_to_dataframe(sample_candles)
        df = df.drop(columns=['volume'])

        result = volume_intensity(df, period=20, threshold=2.0)
        assert result == 0.0

    def test_various_threshold_values(self, sample_candles):
        """Test volume_intensity with different threshold values."""
        df = candles_to_dataframe(sample_candles)
        period = 20

        avg_volume = df['volume'].iloc[-(period + 1):-1].mean()

        # Test threshold 1.5
        df.loc[df.index[-1], 'volume'] = avg_volume * 1.6
        assert volume_intensity(df, period=period, threshold=1.5) == 1.0
        assert volume_intensity(df, period=period, threshold=2.0) == 0.0


class TestVwapDistance:
    """Test suite for vwap_distance primitive."""

    def test_returns_value_in_valid_range(self, sample_candles):
        """Test that vwap_distance returns value in [-3.0, 3.0]."""
        df = candles_to_dataframe(sample_candles)

        result = vwap_distance(df, period=20)
        assert -3.0 <= result <= 3.0

    def test_positive_when_price_above_vwap(self, sample_candles):
        """Test that vwap_distance is positive when current price > VWAP."""
        df = candles_to_dataframe(sample_candles)
        period = 20

        # Calculate VWAP for the period
        recent = df.iloc[-period:]
        typical_price = (recent['high'] + recent['low'] + recent['close']) / 3
        vwap = (typical_price * recent['volume']).sum() / recent['volume'].sum()

        # Set current price well above VWAP
        df.loc[df.index[-1], 'close'] = vwap * 1.1
        df.loc[df.index[-1], 'high'] = vwap * 1.15
        df.loc[df.index[-1], 'low'] = vwap * 1.05

        result = vwap_distance(df, period=period)
        assert result > 0

    def test_negative_when_price_below_vwap(self, sample_candles):
        """Test that vwap_distance is negative when current price < VWAP."""
        df = candles_to_dataframe(sample_candles)
        period = 20

        # Calculate VWAP for the period
        recent = df.iloc[-period:]
        typical_price = (recent['high'] + recent['low'] + recent['close']) / 3
        vwap = (typical_price * recent['volume']).sum() / recent['volume'].sum()

        # Set current price well below VWAP
        df.loc[df.index[-1], 'close'] = vwap * 0.9
        df.loc[df.index[-1], 'high'] = vwap * 0.95
        df.loc[df.index[-1], 'low'] = vwap * 0.85

        result = vwap_distance(df, period=period)
        assert result < 0

    def test_handles_insufficient_data(self):
        """Test that vwap_distance returns 0.0 with insufficient data."""
        # Create DataFrame with only 10 candles
        small_df = pd.DataFrame({
            'high': [101] * 10,
            'low': [99] * 10,
            'close': [100] * 10,
            'volume': [1000] * 10,
        })

        # Request period of 20
        result = vwap_distance(small_df, period=20)
        assert result == 0.0

    def test_handles_zero_std(self):
        """Test that vwap_distance handles zero std case."""
        # Create DataFrame where all typical prices are the same
        df = pd.DataFrame({
            'high': [100] * 30,
            'low': [100] * 30,
            'close': [100] * 30,
            'volume': [1000] * 30,
        })

        result = vwap_distance(df, period=20)
        assert result == 0.0

    def test_handles_zero_volume(self):
        """Test that vwap_distance handles zero volume gracefully."""
        df = pd.DataFrame({
            'high': [101] * 30,
            'low': [99] * 30,
            'close': [100] * 30,
            'volume': [0] * 30,
        })

        result = vwap_distance(df, period=20)
        assert result == 0.0

    def test_handles_missing_columns(self, sample_candles):
        """Test that vwap_distance handles missing required columns."""
        df = candles_to_dataframe(sample_candles)

        # Test missing high
        df_no_high = df.drop(columns=['high'])
        assert vwap_distance(df_no_high, period=20) == 0.0

        # Test missing volume
        df_no_volume = df.drop(columns=['volume'])
        assert vwap_distance(df_no_volume, period=20) == 0.0

    def test_capping_at_three_std(self):
        """Test that vwap_distance caps extreme values at ±3.0."""
        # Create data with very low std to force extreme z-scores
        df = pd.DataFrame({
            'high': [100.01] * 29 + [150],  # Last candle very different
            'low': [99.99] * 29 + [149],
            'close': [100.0] * 29 + [149.5],
            'volume': [1000] * 30,
        })

        result = vwap_distance(df, period=30)
        # Should be capped at 3.0
        assert result == 3.0

    def test_default_period(self, sample_candles):
        """Test that vwap_distance uses default period of 20."""
        df = candles_to_dataframe(sample_candles)

        # Call without explicit period
        result = vwap_distance(df)
        assert -3.0 <= result <= 3.0

    def test_typical_price_calculation(self, sample_candles):
        """Test that typical price (HLC/3) is calculated correctly."""
        df = candles_to_dataframe(sample_candles)
        period = 20

        # Manually calculate expected VWAP
        recent = df.iloc[-period:]
        expected_typical = (recent['high'] + recent['low'] + recent['close']) / 3
        expected_vwap = (expected_typical * recent['volume']).sum() / recent['volume'].sum()
        expected_std = expected_typical.std()
        current_price = df['close'].iloc[-1]
        expected_z = (current_price - expected_vwap) / expected_std
        expected_z = np.clip(expected_z, -3.0, 3.0)

        result = vwap_distance(df, period=period)

        # Should be very close (allowing for floating point precision)
        assert abs(result - expected_z) < 0.0001
