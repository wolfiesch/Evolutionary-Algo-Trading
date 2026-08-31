"""Tests for parameter schema."""
import pytest
import json

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
    ForexParameters,
)


class TestWeightVector:
    """Tests for WeightVector dataclass."""

    def test_default_values(self):
        """Default WeightVector has all zeros."""
        wv = WeightVector()
        assert wv.trend == 0.0
        assert wv.momentum == 0.0
        assert wv.mean_reversion == 0.0
        assert wv.volatility == 0.0
        assert wv.volume == 0.0

    def test_custom_values(self):
        """WeightVector with custom values."""
        wv = WeightVector(
            trend=0.8,
            momentum=-0.5,
            mean_reversion=0.3,
            volatility=0.0,
            volume=0.2,
        )
        assert wv.trend == 0.8
        assert wv.momentum == -0.5

    def test_to_dict(self):
        """WeightVector converts to dictionary."""
        wv = WeightVector(trend=0.5, momentum=0.3)
        d = wv.to_dict()
        assert d["trend"] == 0.5
        assert d["momentum"] == 0.3
        assert "mean_reversion" in d

    def test_from_dict(self):
        """WeightVector creates from dictionary."""
        d = {"trend": 0.7, "momentum": -0.3, "mean_reversion": 0.5}
        wv = WeightVector.from_dict(d)
        assert wv.trend == 0.7
        assert wv.momentum == -0.3
        assert wv.mean_reversion == 0.5
        # Defaults for missing keys
        assert wv.volatility == 0.0

    def test_validate_valid(self):
        """Valid WeightVector passes validation."""
        wv = WeightVector(trend=1.0, momentum=-1.0, mean_reversion=0.5)
        errors = wv.validate()
        assert errors == []

    def test_validate_out_of_bounds(self):
        """WeightVector with out-of-bounds values fails validation."""
        wv = WeightVector(trend=1.5, momentum=-1.2)
        errors = wv.validate()
        assert len(errors) == 2
        assert any("trend" in e for e in errors)
        assert any("momentum" in e for e in errors)

    def test_total_weight(self):
        """Total weight is sum of absolute values."""
        wv = WeightVector(trend=0.8, momentum=-0.5, mean_reversion=0.3)
        assert wv.total_weight() == pytest.approx(1.6)

    def test_is_empty(self):
        """Empty check works correctly."""
        empty = WeightVector()
        assert empty.is_empty()

        non_empty = WeightVector(trend=0.1)
        assert not non_empty.is_empty()


class TestUniversalParameters:
    """Tests for UniversalParameters dataclass."""

    def test_default_values(self):
        """Default UniversalParameters has sensible defaults."""
        params = UniversalParameters()
        assert params.regime_indicator == "adx"
        assert params.regime_period == 14
        assert params.trend_fast_period == 9
        assert params.trend_slow_period == 21
        assert params.allow_long is True
        assert params.allow_short is False

    def test_default_weight_vectors(self):
        """Default weight vectors have expected regime characteristics."""
        params = UniversalParameters()

        # Regime A: Mean reversion dominant
        assert params.weights_A.mean_reversion > params.weights_A.trend

        # Regime B: Trend dominant
        assert params.weights_B.trend > params.weights_B.mean_reversion

    def test_to_dict(self):
        """UniversalParameters converts to dictionary."""
        params = UniversalParameters()
        d = params.to_dict()

        assert d["regime_indicator"] == "adx"
        assert "weights_A" in d
        assert isinstance(d["weights_A"], dict)
        assert d["weights_A"]["trend"] == 0.1

    def test_from_dict(self):
        """UniversalParameters creates from dictionary."""
        d = {
            "regime_indicator": "atr_percentile",
            "regime_period": 20,
            "regime_threshold": 30.0,
            "weights_A": {"trend": 0.5, "momentum": 0.5},
            "weights_B": {"trend": 0.9, "momentum": 0.1},
            "trend_fast_period": 12,
            "trend_slow_period": 26,
            "momentum_period": 14,
            "reversion_period": 20,
            "reversion_std_dev": 2,
            "volatility_period": 14,
            "volume_period": 20,
            "entry_threshold_long": 0.4,
            "exit_threshold_long": -0.2,
            "entry_threshold_short": -0.4,
            "exit_threshold_short": 0.2,
            "stop_loss_atr_mult": 2.5,
            "take_profit_atr_mult": 4.0,
            "min_bars_between_trades": 10,
            "max_position_bars": 200,
            "market_filter_period": 60,
            "market_filter_threshold": 0.0,
            "allow_long": True,
            "allow_short": True,
        }

        params = UniversalParameters.from_dict(d)
        assert params.regime_indicator == "atr_percentile"
        assert params.regime_period == 20
        assert params.weights_A.trend == 0.5
        assert params.weights_B.trend == 0.9
        assert params.allow_short is True

    def test_to_json_and_back(self):
        """UniversalParameters round-trips through JSON."""
        original = UniversalParameters(
            regime_indicator="bb_width",
            regime_threshold=35.0,
            entry_threshold_long=0.5,
        )

        json_str = original.to_json()
        restored = UniversalParameters.from_json(json_str)

        assert restored.regime_indicator == original.regime_indicator
        assert restored.regime_threshold == original.regime_threshold
        assert restored.entry_threshold_long == original.entry_threshold_long


class TestCryptoParameters:
    """Tests for CryptoParameters dataclass."""

    def test_inherits_universal(self):
        """CryptoParameters has all universal fields."""
        params = CryptoParameters()
        assert hasattr(params, "regime_indicator")
        assert hasattr(params, "weights_A")
        assert hasattr(params, "entry_threshold_long")

    def test_crypto_specific_fields(self):
        """CryptoParameters has crypto-specific fields."""
        params = CryptoParameters()
        assert hasattr(params, "weight_btc_correlation")
        assert hasattr(params, "btc_trend_period")
        assert hasattr(params, "weight_funding_rate")
        assert hasattr(params, "funding_rate_threshold")
        assert hasattr(params, "weight_btc_dominance")

    def test_crypto_specific_defaults(self):
        """Crypto-specific fields have sensible defaults."""
        params = CryptoParameters()
        assert params.weight_btc_correlation == 0.0
        assert params.btc_trend_period == 60
        assert params.funding_rate_threshold == 0.01

    def test_to_dict_includes_crypto(self):
        """CryptoParameters to_dict includes crypto fields."""
        params = CryptoParameters(weight_btc_correlation=0.5)
        d = params.to_dict()
        assert "weight_btc_correlation" in d
        assert d["weight_btc_correlation"] == 0.5

    def test_from_dict(self):
        """CryptoParameters creates from dictionary."""
        d = {
            "regime_indicator": "adx",
            "weights_A": {"trend": 0.3},
            "weights_B": {"trend": 0.7},
            "weight_btc_correlation": 0.6,
            "btc_trend_period": 100,
        }
        params = CryptoParameters.from_dict(d)
        assert params.weight_btc_correlation == 0.6
        assert params.btc_trend_period == 100


class TestForexParameters:
    """Tests for ForexParameters dataclass."""

    def test_inherits_universal(self):
        """ForexParameters has all universal fields."""
        params = ForexParameters()
        assert hasattr(params, "regime_indicator")
        assert hasattr(params, "weights_A")

    def test_forex_specific_fields(self):
        """ForexParameters has forex-specific fields."""
        params = ForexParameters()
        assert hasattr(params, "weight_session")
        assert hasattr(params, "preferred_session")
        assert hasattr(params, "weight_dxy")
        assert hasattr(params, "weight_rate_diff")
        assert hasattr(params, "weight_risk_sentiment")

    def test_forex_specific_defaults(self):
        """Forex-specific fields have sensible defaults."""
        params = ForexParameters()
        assert params.weight_session == 0.0
        assert params.preferred_session == "london"
        assert params.weight_dxy == 0.0

    def test_to_dict_includes_forex(self):
        """ForexParameters to_dict includes forex fields."""
        params = ForexParameters(weight_dxy=0.7, preferred_session="overlap")
        d = params.to_dict()
        assert d["weight_dxy"] == 0.7
        assert d["preferred_session"] == "overlap"

    def test_from_dict(self):
        """ForexParameters creates from dictionary."""
        d = {
            "regime_indicator": "adx",
            "weights_A": {"trend": 0.3},
            "weights_B": {"trend": 0.7},
            "weight_session": 0.4,
            "preferred_session": "newyork",
            "weight_dxy": 0.5,
        }
        params = ForexParameters.from_dict(d)
        assert params.weight_session == 0.4
        assert params.preferred_session == "newyork"
        assert params.weight_dxy == 0.5
