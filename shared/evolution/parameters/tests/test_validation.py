"""Tests for parameter validation."""
import pytest

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
    ForexParameters,
)
from shared.evolution.parameters.validation import (
    validate_parameters,
    repair_constraints,
    clamp_to_bounds,
    check_cross_constraints,
    validate_single_constraint,
    validate_weight_vector,
)


class TestValidateWeightVector:
    """Tests for weight vector validation."""

    def test_valid_weight_vector(self):
        """Valid weight vector passes."""
        wv = WeightVector(trend=0.5, momentum=-0.3, mean_reversion=1.0)
        errors = validate_weight_vector("weights_A", wv)
        assert errors == []

    def test_weight_out_of_bounds_positive(self):
        """Weight > 1.0 fails."""
        wv = WeightVector(trend=1.5)
        errors = validate_weight_vector("weights_A", wv)
        assert len(errors) == 1
        assert "weights_A.trend" in errors[0]

    def test_weight_out_of_bounds_negative(self):
        """Weight < -1.0 fails."""
        wv = WeightVector(momentum=-1.5)
        errors = validate_weight_vector("weights_B", wv)
        assert len(errors) == 1
        assert "weights_B.momentum" in errors[0]


class TestValidateSingleConstraint:
    """Tests for single constraint validation."""

    def test_int_type_valid(self):
        """Valid integer passes."""
        errors = validate_single_constraint(
            "trend_fast_period", 9, {"min": 3, "max": 50, "type": int}
        )
        assert errors == []

    def test_int_type_invalid(self):
        """Float for int field fails."""
        errors = validate_single_constraint(
            "trend_fast_period", 9.5, {"min": 3, "max": 50, "type": int}
        )
        assert len(errors) == 1
        assert "integer" in errors[0]

    def test_float_type_valid(self):
        """Valid float passes."""
        errors = validate_single_constraint(
            "entry_threshold_long", 0.3, {"min": 0.1, "max": 0.8, "type": float}
        )
        assert errors == []

    def test_range_below_min(self):
        """Value below min fails."""
        errors = validate_single_constraint(
            "trend_fast_period", 1, {"min": 3, "max": 50, "type": int}
        )
        assert len(errors) == 1
        assert ">= 3" in errors[0]

    def test_range_above_max(self):
        """Value above max fails."""
        errors = validate_single_constraint(
            "trend_fast_period", 100, {"min": 3, "max": 50, "type": int}
        )
        assert len(errors) == 1
        assert "<= 50" in errors[0]

    def test_allowed_values_valid(self):
        """Value in allowed list passes."""
        errors = validate_single_constraint(
            "regime_indicator", "adx", {"allowed": ["adx", "atr_percentile", "bb_width"]}
        )
        assert errors == []

    def test_allowed_values_invalid(self):
        """Value not in allowed list fails."""
        errors = validate_single_constraint(
            "regime_indicator", "invalid", {"allowed": ["adx", "atr_percentile", "bb_width"]}
        )
        assert len(errors) == 1

    def test_bool_type_valid(self):
        """Valid boolean passes."""
        errors = validate_single_constraint(
            "allow_long", True, {"type": bool}
        )
        assert errors == []

    def test_bool_type_invalid(self):
        """Non-boolean for bool field fails."""
        errors = validate_single_constraint(
            "allow_long", 1, {"type": bool}
        )
        assert len(errors) == 1


class TestCrossConstraints:
    """Tests for cross-parameter constraints."""

    def test_valid_constraints(self):
        """Default parameters pass cross-constraints."""
        params = UniversalParameters()
        errors = check_cross_constraints(params)
        assert errors == []

    def test_trend_periods_invalid(self):
        """fast >= slow fails."""
        params = UniversalParameters(
            trend_fast_period=21,
            trend_slow_period=9,
        )
        errors = check_cross_constraints(params)
        assert any("trend_fast_period" in e for e in errors)

    def test_entry_exit_threshold_long_invalid(self):
        """entry <= exit (long) fails."""
        params = UniversalParameters(
            entry_threshold_long=0.1,
            exit_threshold_long=0.2,
        )
        errors = check_cross_constraints(params)
        assert any("entry_threshold_long" in e for e in errors)

    def test_entry_exit_threshold_short_invalid(self):
        """entry >= exit (short) fails."""
        params = UniversalParameters(
            entry_threshold_short=-0.1,
            exit_threshold_short=-0.2,
        )
        errors = check_cross_constraints(params)
        assert any("entry_threshold_short" in e for e in errors)

    def test_risk_invalid(self):
        """take_profit <= stop_loss fails."""
        params = UniversalParameters(
            stop_loss_atr_mult=3.0,
            take_profit_atr_mult=2.0,
        )
        errors = check_cross_constraints(params)
        assert any("take_profit_atr_mult" in e for e in errors)

    def test_empty_weights_fails(self):
        """Both weight vectors empty fails."""
        params = UniversalParameters(
            weights_A=WeightVector(),
            weights_B=WeightVector(),
        )
        errors = check_cross_constraints(params)
        assert any("empty" in e.lower() for e in errors)

    def test_no_direction_enabled_fails(self):
        """Neither long nor short enabled fails."""
        params = UniversalParameters(
            allow_long=False,
            allow_short=False,
        )
        errors = check_cross_constraints(params)
        assert any("allow_long" in e or "allow_short" in e for e in errors)


class TestValidateParameters:
    """Tests for full parameter validation."""

    def test_valid_universal_params(self):
        """Valid UniversalParameters passes."""
        params = UniversalParameters()
        is_valid, errors = validate_parameters(params)
        assert is_valid is True
        assert errors == []

    def test_valid_crypto_params(self):
        """Valid CryptoParameters passes."""
        params = CryptoParameters()
        is_valid, errors = validate_parameters(params)
        assert is_valid is True
        assert errors == []

    def test_valid_forex_params(self):
        """Valid ForexParameters passes."""
        params = ForexParameters()
        is_valid, errors = validate_parameters(params)
        assert is_valid is True
        assert errors == []

    def test_invalid_weight_bounds(self):
        """Invalid weight bounds fails."""
        params = UniversalParameters(
            weights_A=WeightVector(trend=1.5),
        )
        is_valid, errors = validate_parameters(params)
        assert is_valid is False
        assert any("weights_A" in e for e in errors)

    def test_invalid_period(self):
        """Invalid period fails."""
        params = UniversalParameters(
            momentum_period=100,  # Max is 50
        )
        is_valid, errors = validate_parameters(params)
        assert is_valid is False
        assert any("momentum_period" in e for e in errors)

    def test_multiple_errors(self):
        """Multiple errors are all reported."""
        params = UniversalParameters(
            trend_fast_period=100,  # Invalid
            trend_slow_period=50,   # Now fast > slow too
            momentum_period=100,    # Invalid
        )
        is_valid, errors = validate_parameters(params)
        assert is_valid is False
        assert len(errors) >= 2

    def test_crypto_specific_validation(self):
        """Crypto-specific constraints are validated."""
        params = CryptoParameters(
            weight_btc_correlation=1.5,  # Invalid: > 1.0
        )
        is_valid, errors = validate_parameters(params)
        assert is_valid is False
        assert any("btc_correlation" in e for e in errors)


class TestRepairConstraints:
    """Tests for constraint repair."""

    def test_repair_trend_periods(self):
        """Repairs trend_fast >= trend_slow."""
        params = UniversalParameters(
            trend_fast_period=30,
            trend_slow_period=20,
        )
        repaired = repair_constraints(params)
        assert repaired.trend_fast_period < repaired.trend_slow_period

    def test_repair_entry_exit_long(self):
        """Repairs entry <= exit (long)."""
        params = UniversalParameters(
            entry_threshold_long=0.1,
            exit_threshold_long=0.2,
        )
        repaired = repair_constraints(params)
        assert repaired.entry_threshold_long > repaired.exit_threshold_long

    def test_repair_entry_exit_short(self):
        """Repairs entry >= exit (short)."""
        params = UniversalParameters(
            entry_threshold_short=-0.1,
            exit_threshold_short=-0.2,
        )
        repaired = repair_constraints(params)
        assert repaired.entry_threshold_short < repaired.exit_threshold_short

    def test_repair_risk(self):
        """Repairs take_profit <= stop_loss."""
        params = UniversalParameters(
            stop_loss_atr_mult=4.0,
            take_profit_atr_mult=3.0,
        )
        repaired = repair_constraints(params)
        assert repaired.take_profit_atr_mult > repaired.stop_loss_atr_mult

    def test_repair_no_direction(self):
        """Repairs both directions disabled."""
        params = UniversalParameters(
            allow_long=False,
            allow_short=False,
        )
        repaired = repair_constraints(params)
        assert repaired.allow_long or repaired.allow_short

    def test_repair_preserves_type(self):
        """Repair preserves parameter type."""
        crypto_params = CryptoParameters(
            trend_fast_period=30,
            trend_slow_period=20,
        )
        repaired = repair_constraints(crypto_params)
        assert isinstance(repaired, CryptoParameters)

        forex_params = ForexParameters(
            trend_fast_period=30,
            trend_slow_period=20,
        )
        repaired = repair_constraints(forex_params)
        assert isinstance(repaired, ForexParameters)


class TestClampToBounds:
    """Tests for clamping to bounds."""

    def test_clamp_weight_vector(self):
        """Weights are clamped to [-1, 1]."""
        params = UniversalParameters(
            weights_A=WeightVector(trend=1.5, momentum=-1.5),
        )
        clamped = clamp_to_bounds(params)
        assert clamped.weights_A.trend == 1.0
        assert clamped.weights_A.momentum == -1.0

    def test_clamp_period(self):
        """Periods are clamped to valid range."""
        params = UniversalParameters(
            momentum_period=100,  # Max is 50
        )
        clamped = clamp_to_bounds(params)
        assert clamped.momentum_period == 50

    def test_clamp_threshold(self):
        """Thresholds are clamped to valid range."""
        params = UniversalParameters(
            entry_threshold_long=1.5,  # Max is 0.8
        )
        clamped = clamp_to_bounds(params)
        assert clamped.entry_threshold_long == 0.8

    def test_clamp_preserves_type(self):
        """Clamp preserves parameter type."""
        crypto_params = CryptoParameters(
            weight_btc_correlation=1.5,
        )
        clamped = clamp_to_bounds(crypto_params)
        assert isinstance(clamped, CryptoParameters)
        assert clamped.weight_btc_correlation == 1.0
