"""
Tests for equities regime classifier.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

import sys
sys.path.insert(0, ".")

from evolution.fitness.regime_classifier import (
    EquitiesRegimeClassifier,
    MarketRegime,
    RegimeConfig,
    classify_regime,
    label_regimes,
    get_regime_distribution,
)


class TestRegimeClassifier:
    """Tests for EquitiesRegimeClassifier."""

    @pytest.fixture
    def classifier(self):
        """Create default classifier."""
        return EquitiesRegimeClassifier()

    @pytest.fixture
    def bull_calm_data(self):
        """Create data for bull calm regime (SPY up, VIX low)."""
        n = 50
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]

        # SPY trending up (10% in 20 days = 0.5%/day)
        spy_prices = 400 * np.cumprod(1 + np.full(n, 0.005))

        spy = pd.DataFrame({
            "date": dates,
            "open": spy_prices * 0.999,
            "high": spy_prices * 1.005,
            "low": spy_prices * 0.995,
            "close": spy_prices,
            "volume": [100_000_000] * n,
        })

        # VIX low around 15
        vix_values = 15 + np.random.normal(0, 1, n)
        vix = pd.DataFrame({
            "date": dates,
            "open": vix_values,
            "high": vix_values + 0.5,
            "low": vix_values - 0.5,
            "close": vix_values,
            "volume": [5_000_000] * n,
        })

        return spy, vix

    @pytest.fixture
    def bear_volatile_data(self):
        """Create data for bear volatile regime (SPY down, VIX high)."""
        n = 50
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]

        # SPY trending down (-10% in 20 days)
        spy_prices = 400 * np.cumprod(1 + np.full(n, -0.005))

        spy = pd.DataFrame({
            "date": dates,
            "open": spy_prices * 1.001,
            "high": spy_prices * 1.005,
            "low": spy_prices * 0.995,
            "close": spy_prices,
            "volume": [100_000_000] * n,
        })

        # VIX high around 30
        vix_values = 30 + np.random.normal(0, 2, n)
        vix = pd.DataFrame({
            "date": dates,
            "open": vix_values,
            "high": vix_values + 1,
            "low": vix_values - 1,
            "close": vix_values,
            "volume": [10_000_000] * n,
        })

        return spy, vix

    @pytest.fixture
    def sideways_data(self):
        """Create data for sideways regime (SPY flat)."""
        n = 50
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]

        # SPY range-bound (< 2% move)
        spy_prices = 400 + np.random.normal(0, 2, n).cumsum() * 0.1

        spy = pd.DataFrame({
            "date": dates,
            "open": spy_prices * 0.999,
            "high": spy_prices * 1.002,
            "low": spy_prices * 0.998,
            "close": spy_prices,
            "volume": [80_000_000] * n,
        })

        # VIX normal around 18
        vix_values = 18 + np.random.normal(0, 1, n)
        vix = pd.DataFrame({
            "date": dates,
            "close": vix_values,
        })

        return spy, vix

    def test_bull_calm_classification(self, classifier, bull_calm_data):
        """Should classify uptrend + low VIX as bull_calm."""
        spy, vix = bull_calm_data
        regime = classifier.classify(spy, vix)
        assert regime == MarketRegime.BULL_CALM

    def test_bear_volatile_classification(self, classifier, bear_volatile_data):
        """Should classify downtrend + high VIX as bear_volatile."""
        spy, vix = bear_volatile_data
        regime = classifier.classify(spy, vix)
        assert regime == MarketRegime.BEAR_VOLATILE

    def test_sideways_classification(self, classifier, sideways_data):
        """Should classify range-bound market as sideways."""
        spy, vix = sideways_data
        regime = classifier.classify(spy, vix)
        assert regime == MarketRegime.SIDEWAYS

    def test_insufficient_data_returns_sideways(self, classifier):
        """Should return sideways when insufficient data."""
        short_spy = pd.DataFrame({"close": [400, 401, 402]})
        short_vix = pd.DataFrame({"close": [15, 16, 15]})

        regime = classifier.classify(short_spy, short_vix)
        assert regime == MarketRegime.SIDEWAYS


class TestRegimeConfig:
    """Tests for RegimeConfig."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = RegimeConfig()
        assert config.trend_window == 20
        assert config.trend_threshold == 0.02
        assert config.vix_low == 20.0
        assert config.vix_high == 25.0

    def test_custom_config(self):
        """Should accept custom config values."""
        config = RegimeConfig(
            trend_window=10,
            trend_threshold=0.03,
            vix_low=15.0,
        )
        classifier = EquitiesRegimeClassifier(config)
        assert classifier.config.trend_window == 10
        assert classifier.config.vix_low == 15.0


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    @pytest.fixture
    def sample_data(self):
        """Create sample data for testing."""
        n = 100
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]

        spy = pd.DataFrame({
            "date": dates,
            "close": 400 + np.random.randn(n).cumsum(),
            "high": 400 + np.random.randn(n).cumsum() + 1,
            "low": 400 + np.random.randn(n).cumsum() - 1,
        })

        vix = pd.DataFrame({
            "date": dates,
            "close": 20 + np.random.randn(n),
        })

        return spy, vix

    def test_classify_regime_returns_string(self, sample_data):
        """classify_regime should return string regime name."""
        spy, vix = sample_data
        regime = classify_regime(spy, vix)
        assert isinstance(regime, str)
        assert regime in ["bull_calm", "bull_volatile", "bear_calm", "bear_volatile", "sideways"]

    def test_label_regimes_returns_dataframe(self, sample_data):
        """label_regimes should return DataFrame with regime labels."""
        spy, vix = sample_data
        labels = label_regimes(spy, vix, window_size=20, step_size=10)

        assert isinstance(labels, pd.DataFrame)
        assert "regime" in labels.columns
        assert "spy_return" in labels.columns
        assert "vix_level" in labels.columns

    def test_get_regime_distribution(self, sample_data):
        """get_regime_distribution should return valid percentages."""
        spy, vix = sample_data
        labels = label_regimes(spy, vix, window_size=20, step_size=10)
        dist = get_regime_distribution(labels)

        assert isinstance(dist, dict)
        total = sum(dist.values())
        assert 0.99 <= total <= 1.01  # Should sum to ~1.0


class TestMarketRegimeEnum:
    """Tests for MarketRegime enum."""

    def test_all_regimes_have_values(self):
        """All regimes should have string values."""
        expected = ["bull_calm", "bull_volatile", "bear_calm", "bear_volatile", "sideways"]
        actual = [r.value for r in MarketRegime]
        assert sorted(actual) == sorted(expected)

    def test_regime_value_access(self):
        """Should access regime value correctly."""
        assert MarketRegime.BULL_CALM.value == "bull_calm"
        assert MarketRegime.BEAR_VOLATILE.value == "bear_volatile"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
