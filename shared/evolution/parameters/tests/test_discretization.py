"""Tests for parameter discretization."""
import pytest

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
    ForexParameters,
)
from shared.evolution.parameters.discretization import (
    discretize_value,
    discretize_weight_vector,
    discretize_parameters,
    hash_parameters,
    parameters_are_equivalent,
    calculate_search_space_size,
    DISCRETIZATION_STEPS,
)


class TestDiscretizeValue:
    """Tests for value discretization."""

    def test_discretize_to_nearest(self):
        """Values round to nearest step."""
        # 0.1 step
        assert discretize_value(0.53, 0.1) == pytest.approx(0.5)
        assert discretize_value(0.57, 0.1) == pytest.approx(0.6)
        assert discretize_value(0.55, 0.1) == pytest.approx(0.6)  # Round half up

    def test_discretize_negative(self):
        """Negative values discretize correctly."""
        assert discretize_value(-0.53, 0.1) == pytest.approx(-0.5)
        assert discretize_value(-0.57, 0.1) == pytest.approx(-0.6)

    def test_discretize_larger_step(self):
        """Larger steps work correctly."""
        # 0.5 step (for ATR multipliers)
        assert discretize_value(2.3, 0.5) == 2.5
        assert discretize_value(2.2, 0.5) == 2.0

    def test_discretize_already_discrete(self):
        """Already discrete values unchanged."""
        assert discretize_value(0.5, 0.1) == 0.5
        assert discretize_value(2.0, 0.5) == 2.0


class TestDiscretizeWeightVector:
    """Tests for weight vector discretization."""

    def test_discretize_all_weights(self):
        """All weights are discretized."""
        wv = WeightVector(
            trend=0.53,
            momentum=-0.27,
            mean_reversion=0.86,  # Rounds to 0.9 (0.85 rounds to 0.8 due to banker's rounding)
            volatility=0.12,
            volume=0.08,
        )
        disc = discretize_weight_vector(wv)

        assert disc.trend == pytest.approx(0.5)
        assert disc.momentum == pytest.approx(-0.3)
        assert disc.mean_reversion == pytest.approx(0.9)
        assert disc.volatility == pytest.approx(0.1)
        assert disc.volume == pytest.approx(0.1)

    def test_discretize_preserves_sign(self):
        """Discretization preserves sign."""
        wv = WeightVector(trend=-0.03, momentum=0.03)
        disc = discretize_weight_vector(wv)

        assert disc.trend == 0.0
        assert disc.momentum == 0.0


class TestDiscretizeParameters:
    """Tests for full parameter discretization."""

    def test_discretize_universal_params(self):
        """UniversalParameters are discretized."""
        params = UniversalParameters(
            regime_threshold=27.3,
            entry_threshold_long=0.33,
            stop_loss_atr_mult=2.3,
        )
        disc = discretize_parameters(params)

        # regime_threshold: 5.0 step -> 25.0 or 30.0
        assert disc.regime_threshold == pytest.approx(25.0) or disc.regime_threshold == pytest.approx(30.0)

        # entry_threshold_long: 0.05 step -> 0.30 or 0.35
        assert disc.entry_threshold_long == pytest.approx(0.30) or disc.entry_threshold_long == pytest.approx(0.35)

        # stop_loss_atr_mult: 0.5 step -> 2.0 or 2.5
        assert disc.stop_loss_atr_mult == pytest.approx(2.0) or disc.stop_loss_atr_mult == pytest.approx(2.5)

    def test_discretize_preserves_integers(self):
        """Integer periods remain integers."""
        params = UniversalParameters(
            trend_fast_period=9,
            momentum_period=14,
        )
        disc = discretize_parameters(params)

        assert isinstance(disc.trend_fast_period, int)
        assert isinstance(disc.momentum_period, int)

    def test_discretize_weight_vectors(self):
        """Weight vectors are discretized."""
        params = UniversalParameters(
            weights_A=WeightVector(trend=0.53),
            weights_B=WeightVector(trend=0.87),
        )
        disc = discretize_parameters(params)

        assert disc.weights_A.trend == pytest.approx(0.5)
        assert disc.weights_B.trend == pytest.approx(0.9)

    def test_discretize_preserves_type(self):
        """Discretization preserves parameter type."""
        crypto = CryptoParameters()
        disc_crypto = discretize_parameters(crypto)
        assert isinstance(disc_crypto, CryptoParameters)

        forex = ForexParameters()
        disc_forex = discretize_parameters(forex)
        assert isinstance(disc_forex, ForexParameters)

    def test_discretize_crypto_specific(self):
        """Crypto-specific weights are discretized."""
        params = CryptoParameters(
            weight_btc_correlation=0.53,
            weight_funding_rate=-0.27,
        )
        disc = discretize_parameters(params)

        assert disc.weight_btc_correlation == pytest.approx(0.5)
        assert disc.weight_funding_rate == pytest.approx(-0.3)

    def test_discretize_forex_specific(self):
        """Forex-specific weights are discretized."""
        params = ForexParameters(
            weight_dxy=0.73,
            weight_session=-0.47,
        )
        disc = discretize_parameters(params)

        assert disc.weight_dxy == pytest.approx(0.7)
        assert disc.weight_session == pytest.approx(-0.5)


class TestHashParameters:
    """Tests for parameter hashing."""

    def test_same_params_same_hash(self):
        """Identical parameters produce same hash."""
        params1 = UniversalParameters()
        params2 = UniversalParameters()

        assert hash_parameters(params1) == hash_parameters(params2)

    def test_different_params_different_hash(self):
        """Different parameters produce different hash."""
        params1 = UniversalParameters(entry_threshold_long=0.3)
        params2 = UniversalParameters(entry_threshold_long=0.5)

        assert hash_parameters(params1) != hash_parameters(params2)

    def test_similar_params_same_hash_after_discretization(self):
        """Similar parameters (within discretization) have same hash."""
        params1 = UniversalParameters(entry_threshold_long=0.31)
        params2 = UniversalParameters(entry_threshold_long=0.32)

        # Both round to 0.30 with 0.05 step
        assert hash_parameters(params1) == hash_parameters(params2)

    def test_hash_includes_all_fields(self):
        """Hash changes for any field change."""
        params_base = UniversalParameters()

        # Test a few representative fields
        test_variations = [
            UniversalParameters(regime_indicator="bb_width"),
            UniversalParameters(trend_fast_period=12),
            UniversalParameters(allow_short=True),
            UniversalParameters(weights_A=WeightVector(trend=0.5)),
        ]

        base_hash = hash_parameters(params_base)
        for variation in test_variations:
            assert hash_parameters(variation) != base_hash


class TestParametersAreEquivalent:
    """Tests for parameter equivalence checking."""

    def test_identical_params_equivalent(self):
        """Identical parameters are equivalent."""
        params1 = UniversalParameters()
        params2 = UniversalParameters()

        assert parameters_are_equivalent(params1, params2)

    def test_different_params_not_equivalent(self):
        """Different parameters are not equivalent."""
        params1 = UniversalParameters(entry_threshold_long=0.3)
        params2 = UniversalParameters(entry_threshold_long=0.5)

        assert not parameters_are_equivalent(params1, params2)

    def test_similar_params_equivalent(self):
        """Similar parameters (within discretization) are equivalent."""
        params1 = UniversalParameters(entry_threshold_long=0.31)
        params2 = UniversalParameters(entry_threshold_long=0.32)

        # Both round to 0.30 with 0.05 step
        assert parameters_are_equivalent(params1, params2)

    def test_different_types_not_equivalent(self):
        """Different parameter types are not equivalent."""
        universal = UniversalParameters()
        crypto = CryptoParameters()

        assert not parameters_are_equivalent(universal, crypto)


class TestCalculateSearchSpaceSize:
    """Tests for search space size calculation."""

    def test_returns_dict(self):
        """Returns dictionary with size info."""
        sizes = calculate_search_space_size()

        assert isinstance(sizes, dict)
        assert "weight_values_per_param" in sizes
        assert "total_weight_combinations" in sizes

    def test_weight_values_correct(self):
        """Weight values count is correct."""
        # -1.0 to +1.0 in 0.1 steps = 21 values
        sizes = calculate_search_space_size()
        assert sizes["weight_values_per_param"] == 21

    def test_weight_combinations_correct(self):
        """Weight combinations per vector is correct."""
        # 5 weights, 21 values each = 21^5 = 4,084,101
        sizes = calculate_search_space_size()
        assert sizes["weight_combinations_per_vector"] == 21 ** 5
