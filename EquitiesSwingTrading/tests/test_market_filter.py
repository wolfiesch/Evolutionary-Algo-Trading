"""
Tests for market filter primitives.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
import sys

sys.path.insert(0, ".")
from engine.gene_pool.market_filter import (
    spy_trend,
    vix_regime,
    vix_percentile,
    spy_momentum,
    spy_above_sma,
    market_breadth_proxy,
)


class TestSpyTrend:
    """Tests for spy_trend primitive."""

    def test_uptrend_returns_positive(self, sample_spy_uptrend):
        """SPY in clear uptrend should return +1.0."""
        result = spy_trend(sample_spy_uptrend, period=20)
        assert result == 1.0

    def test_downtrend_returns_negative(self, sample_spy_downtrend):
        """SPY in clear downtrend should return -1.0."""
        result = spy_trend(sample_spy_downtrend, period=20)
        assert result == -1.0

    def test_insufficient_data_returns_negative(self):
        """Insufficient data should return conservative -1.0."""
        short_df = pd.DataFrame({
            "close": [100, 101, 102],
            "date": [date.today() - timedelta(days=i) for i in range(3)],
        })
        result = spy_trend(short_df, period=20)
        assert result == -1.0

    def test_returns_float(self, sample_spy_uptrend):
        """Result should be a float."""
        result = spy_trend(sample_spy_uptrend, period=20)
        assert isinstance(result, float)


class TestVixRegime:
    """Tests for vix_regime primitive."""

    def test_low_vix_returns_positive(self, sample_vix_low):
        """Low VIX (<15) should return +1.0 (risk-on)."""
        result = vix_regime(sample_vix_low, period=14)
        assert result == 1.0

    def test_high_vix_returns_negative(self, sample_vix_high):
        """High VIX (>25) should return -1.0 (risk-off)."""
        result = vix_regime(sample_vix_high, period=14)
        assert result == -1.0

    def test_normal_vix_returns_neutral(self):
        """Normal VIX (15-25) should return 0.0."""
        np.random.seed(46)
        n_days = 50

        # VIX around 20 (normal range)
        vix_values = 20 + np.random.normal(0, 1, n_days)

        df = pd.DataFrame({
            "close": vix_values,
            "date": [date.today() - timedelta(days=i) for i in range(n_days)],
        })

        result = vix_regime(df, period=10)
        assert result == 0.0

    def test_insufficient_data_returns_neutral(self):
        """Insufficient data should return neutral 0.0."""
        short_df = pd.DataFrame({
            "close": [15, 16, 17],
            "date": [date.today() - timedelta(days=i) for i in range(3)],
        })
        result = vix_regime(short_df, period=10)
        assert result == 0.0


class TestVixPercentile:
    """Tests for vix_percentile primitive."""

    def test_returns_between_zero_and_one(self, sample_vix_low):
        """Result should be between 0.0 and 1.0."""
        result = vix_percentile(sample_vix_low, period=60)
        assert 0.0 <= result <= 1.0

    def test_low_vix_has_low_percentile(self, sample_vix_low):
        """Consistently low VIX should have lower percentile."""
        result = vix_percentile(sample_vix_low, period=60)
        assert result < 0.6  # Should be below median

    def test_high_vix_has_high_percentile(self, sample_vix_high):
        """Consistently high VIX should have higher percentile."""
        result = vix_percentile(sample_vix_high, period=60)
        assert result > 0.4  # Should be above median


class TestSpyMomentum:
    """Tests for spy_momentum primitive."""

    def test_uptrend_has_positive_momentum(self, sample_spy_uptrend):
        """SPY in uptrend should have positive momentum."""
        result = spy_momentum(sample_spy_uptrend, period=20)
        assert result > 0

    def test_downtrend_has_negative_momentum(self, sample_spy_downtrend):
        """SPY in downtrend should have negative momentum."""
        result = spy_momentum(sample_spy_downtrend, period=20)
        assert result < 0

    def test_clamped_at_bounds(self):
        """Extreme moves should be clamped at ±1.0."""
        # Create extreme uptrend (50% in 20 days)
        prices = [100 * (1.02 ** i) for i in range(25)]

        df = pd.DataFrame({
            "close": prices,
            "date": [date.today() - timedelta(days=24-i) for i in range(25)],
        })

        result = spy_momentum(df, period=20)
        assert result == 1.0


class TestSpyAboveSma:
    """Tests for spy_above_sma primitive."""

    def test_uptrend_above_sma(self, sample_spy_uptrend):
        """SPY in uptrend should be above SMA."""
        result = spy_above_sma(sample_spy_uptrend, period=50)
        assert result == 1.0

    def test_downtrend_below_sma(self, sample_spy_downtrend):
        """SPY in downtrend should be below SMA."""
        result = spy_above_sma(sample_spy_downtrend, period=50)
        assert result == -1.0


class TestMarketBreadthProxy:
    """Tests for market_breadth_proxy primitive."""

    def test_returns_between_bounds(self, sample_spy_uptrend):
        """Result should be between -1.0 and 1.0."""
        result = market_breadth_proxy(sample_spy_uptrend, period=20)
        assert -1.0 <= result <= 1.0

    def test_at_highs_returns_positive(self, sample_spy_uptrend):
        """Price near period highs should return positive."""
        result = market_breadth_proxy(sample_spy_uptrend, period=20)
        # In uptrend, should be near highs
        assert result > 0


class TestIntegration:
    """Integration tests combining multiple primitives."""

    def test_risk_on_environment(self, sample_spy_uptrend, sample_vix_low):
        """Risk-on environment should show aligned signals."""
        spy_signal = spy_trend(sample_spy_uptrend, period=20)
        vix_signal = vix_regime(sample_vix_low, period=14)

        # Both should indicate risk-on
        assert spy_signal == 1.0
        assert vix_signal == 1.0

    def test_risk_off_environment(self, sample_spy_downtrend, sample_vix_high):
        """Risk-off environment should show aligned signals."""
        spy_signal = spy_trend(sample_spy_downtrend, period=20)
        vix_signal = vix_regime(sample_vix_high, period=14)

        # Both should indicate risk-off
        assert spy_signal == -1.0
        assert vix_signal == -1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
