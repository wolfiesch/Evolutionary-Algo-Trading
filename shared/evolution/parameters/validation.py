"""
Parameter validation for Strategy Templates.

Enforces:
1. Type constraints (int vs float)
2. Range constraints (min/max bounds)
3. Cross-parameter constraints (e.g., trend_fast < trend_slow)
"""
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import fields

from .schema import WeightVector, UniversalParameters, CryptoParameters, ForexParameters


# Type alias for validation result
ValidationResult = Tuple[bool, List[str]]


# === PARAMETER CONSTRAINTS ===

UNIVERSAL_CONSTRAINTS = {
    # Regime selector
    "regime_indicator": {"allowed": ["adx", "atr_percentile", "bb_width"]},
    "regime_period": {"min": 5, "max": 50, "type": int},
    "regime_threshold": {"min": 10.0, "max": 50.0, "type": float},

    # Periods: bounded, integer-only
    "trend_fast_period": {"min": 3, "max": 50, "type": int},
    "trend_slow_period": {"min": 10, "max": 200, "type": int},
    "momentum_period": {"min": 5, "max": 50, "type": int},
    "reversion_period": {"min": 10, "max": 100, "type": int},
    "reversion_std_dev": {"min": 1, "max": 3, "type": int},
    "volatility_period": {"min": 5, "max": 50, "type": int},
    "volume_period": {"min": 10, "max": 100, "type": int},

    # Thresholds: bounded, bidirectional
    "entry_threshold_long": {"min": 0.1, "max": 0.8, "type": float},
    "exit_threshold_long": {"min": -0.5, "max": 0.2, "type": float},
    "entry_threshold_short": {"min": -0.8, "max": -0.1, "type": float},
    "exit_threshold_short": {"min": -0.2, "max": 0.5, "type": float},

    # Risk: bounded, continuous
    "stop_loss_atr_mult": {"min": 1.0, "max": 5.0, "type": float},
    "take_profit_atr_mult": {"min": 1.5, "max": 8.0, "type": float},

    # Timing
    "min_bars_between_trades": {"min": 1, "max": 50, "type": int},
    "max_position_bars": {"min": 0, "max": 500, "type": int},  # 0 = unlimited

    # Market filter
    "market_filter_period": {"min": 20, "max": 200, "type": int},
    "market_filter_threshold": {"min": -1.0, "max": 1.0, "type": float},

    # Direction control
    "allow_long": {"type": bool},
    "allow_short": {"type": bool},
}


CRYPTO_CONSTRAINTS = {
    **UNIVERSAL_CONSTRAINTS,
    "weight_btc_correlation": {"min": -1.0, "max": 1.0, "type": float},
    "btc_trend_period": {"min": 20, "max": 200, "type": int},
    "weight_funding_rate": {"min": -1.0, "max": 1.0, "type": float},
    "funding_rate_threshold": {"min": 0.001, "max": 0.05, "type": float},
    "weight_btc_dominance": {"min": -1.0, "max": 1.0, "type": float},
    "btc_dominance_period": {"min": 10, "max": 100, "type": int},
}


FOREX_CONSTRAINTS = {
    **UNIVERSAL_CONSTRAINTS,
    "weight_session": {"min": -1.0, "max": 1.0, "type": float},
    "preferred_session": {"allowed": ["asian", "london", "newyork", "overlap"]},
    "weight_dxy": {"min": -1.0, "max": 1.0, "type": float},
    "dxy_trend_period": {"min": 20, "max": 200, "type": int},
    "weight_rate_diff": {"min": -1.0, "max": 1.0, "type": float},
    "weight_risk_sentiment": {"min": -1.0, "max": 1.0, "type": float},
}


# === CROSS-PARAMETER CONSTRAINTS ===

def check_cross_constraints(params: UniversalParameters) -> List[str]:
    """
    Check cross-parameter constraints.

    Returns list of error messages (empty if all valid).
    """
    errors = []

    # trend_fast_period < trend_slow_period
    if params.trend_fast_period >= params.trend_slow_period:
        errors.append(
            f"trend_fast_period ({params.trend_fast_period}) must be < "
            f"trend_slow_period ({params.trend_slow_period})"
        )

    # entry_threshold_long > exit_threshold_long
    if params.entry_threshold_long <= params.exit_threshold_long:
        errors.append(
            f"entry_threshold_long ({params.entry_threshold_long}) must be > "
            f"exit_threshold_long ({params.exit_threshold_long})"
        )

    # entry_threshold_short < exit_threshold_short
    if params.entry_threshold_short >= params.exit_threshold_short:
        errors.append(
            f"entry_threshold_short ({params.entry_threshold_short}) must be < "
            f"exit_threshold_short ({params.exit_threshold_short})"
        )

    # take_profit_atr_mult > stop_loss_atr_mult
    if params.take_profit_atr_mult <= params.stop_loss_atr_mult:
        errors.append(
            f"take_profit_atr_mult ({params.take_profit_atr_mult}) must be > "
            f"stop_loss_atr_mult ({params.stop_loss_atr_mult})"
        )

    # At least one of weights_A or weights_B should have non-zero weights
    if params.weights_A.is_empty() and params.weights_B.is_empty():
        errors.append("Both weights_A and weights_B are empty; at least one must have non-zero weights")

    # At least one direction must be enabled
    if not params.allow_long and not params.allow_short:
        errors.append("At least one of allow_long or allow_short must be True")

    return errors


def validate_single_constraint(
    name: str,
    value: Any,
    constraint: Dict
) -> List[str]:
    """
    Validate a single parameter against its constraint.

    Args:
        name: Parameter name
        value: Parameter value
        constraint: Constraint dictionary with 'type', 'min', 'max', 'allowed'

    Returns:
        List of error messages (empty if valid)
    """
    errors = []

    # Type check
    if "type" in constraint:
        expected_type = constraint["type"]
        if expected_type == float:
            if not isinstance(value, (int, float)):
                errors.append(f"{name} must be numeric, got {type(value).__name__}")
                return errors  # Can't do range checks if wrong type
        elif expected_type == int:
            if not isinstance(value, int) or isinstance(value, bool):
                errors.append(f"{name} must be integer, got {type(value).__name__}")
                return errors
        elif expected_type == bool:
            if not isinstance(value, bool):
                errors.append(f"{name} must be boolean, got {type(value).__name__}")
                return errors

    # Allowed values check (for enums/literals)
    if "allowed" in constraint:
        if value not in constraint["allowed"]:
            errors.append(f"{name} must be one of {constraint['allowed']}, got {value}")

    # Range checks (for numerics)
    if "min" in constraint and isinstance(value, (int, float)):
        if value < constraint["min"]:
            errors.append(f"{name} ({value}) must be >= {constraint['min']}")

    if "max" in constraint and isinstance(value, (int, float)):
        if value > constraint["max"]:
            errors.append(f"{name} ({value}) must be <= {constraint['max']}")

    return errors


def validate_weight_vector(
    name: str,
    weights: WeightVector
) -> List[str]:
    """
    Validate a WeightVector.

    Args:
        name: Name prefix for error messages (e.g., "weights_A")
        weights: WeightVector to validate

    Returns:
        List of error messages
    """
    errors = []
    for field_name in ["trend", "momentum", "mean_reversion", "volatility", "volume"]:
        val = getattr(weights, field_name)
        if not isinstance(val, (int, float)):
            errors.append(f"{name}.{field_name} must be numeric, got {type(val).__name__}")
        elif not -1.0 <= val <= 1.0:
            errors.append(f"{name}.{field_name} ({val}) must be in [-1.0, 1.0]")
    return errors


def validate_parameters(params: UniversalParameters) -> ValidationResult:
    """
    Validate all parameters.

    Args:
        params: Parameters to validate

    Returns:
        Tuple of (is_valid: bool, errors: List[str])
    """
    errors = []

    # Determine which constraint set to use
    if isinstance(params, CryptoParameters):
        constraints = CRYPTO_CONSTRAINTS
    elif isinstance(params, ForexParameters):
        constraints = FOREX_CONSTRAINTS
    else:
        constraints = UNIVERSAL_CONSTRAINTS

    # Validate weight vectors
    errors.extend(validate_weight_vector("weights_A", params.weights_A))
    errors.extend(validate_weight_vector("weights_B", params.weights_B))

    # Validate individual parameters
    for param_name, constraint in constraints.items():
        if hasattr(params, param_name):
            value = getattr(params, param_name)
            errors.extend(validate_single_constraint(param_name, value, constraint))

    # Validate cross-parameter constraints
    errors.extend(check_cross_constraints(params))

    is_valid = len(errors) == 0
    return (is_valid, errors)


def repair_constraints(params: UniversalParameters) -> UniversalParameters:
    """
    Attempt to repair constraint violations.

    This is useful after crossover when parents may have incompatible values.
    Repairs are conservative (minimal changes to fix violations).

    Args:
        params: Parameters with potential violations

    Returns:
        Repaired parameters (new instance)
    """
    # Create a copy by converting to dict and back
    data = params.to_dict()

    # trend_fast < trend_slow
    if data["trend_fast_period"] >= data["trend_slow_period"]:
        # Set fast to slow - 5 (minimum gap)
        data["trend_fast_period"] = max(3, data["trend_slow_period"] - 5)

    # entry > exit threshold (long)
    if data["entry_threshold_long"] <= data["exit_threshold_long"]:
        gap = abs(data["entry_threshold_long"] - data["exit_threshold_long"]) / 2 + 0.1
        data["entry_threshold_long"] = min(0.8, data["exit_threshold_long"] + gap + 0.1)
        data["exit_threshold_long"] = max(-0.5, data["entry_threshold_long"] - gap - 0.1)

    # entry < exit threshold (short)
    if data["entry_threshold_short"] >= data["exit_threshold_short"]:
        gap = abs(data["exit_threshold_short"] - data["entry_threshold_short"]) / 2 + 0.1
        data["entry_threshold_short"] = max(-0.8, data["exit_threshold_short"] - gap - 0.1)
        data["exit_threshold_short"] = min(0.5, data["entry_threshold_short"] + gap + 0.1)

    # take_profit > stop_loss
    if data["take_profit_atr_mult"] <= data["stop_loss_atr_mult"]:
        data["take_profit_atr_mult"] = data["stop_loss_atr_mult"] + 0.5

    # At least one direction enabled
    if not data["allow_long"] and not data["allow_short"]:
        data["allow_long"] = True

    # Reconstruct the appropriate parameter type
    if isinstance(params, CryptoParameters):
        return CryptoParameters.from_dict(data)
    elif isinstance(params, ForexParameters):
        return ForexParameters.from_dict(data)
    else:
        return UniversalParameters.from_dict(data)


def clamp_to_bounds(params: UniversalParameters) -> UniversalParameters:
    """
    Clamp all parameters to their valid bounds.

    Args:
        params: Parameters to clamp

    Returns:
        Clamped parameters (new instance)
    """
    # Determine which constraint set to use
    if isinstance(params, CryptoParameters):
        constraints = CRYPTO_CONSTRAINTS
    elif isinstance(params, ForexParameters):
        constraints = FOREX_CONSTRAINTS
    else:
        constraints = UNIVERSAL_CONSTRAINTS

    data = params.to_dict()

    # Clamp weight vectors
    for weights_key in ["weights_A", "weights_B"]:
        for field_name in ["trend", "momentum", "mean_reversion", "volatility", "volume"]:
            val = data[weights_key][field_name]
            data[weights_key][field_name] = max(-1.0, min(1.0, val))

    # Clamp other parameters
    for param_name, constraint in constraints.items():
        if param_name in data and "min" in constraint and "max" in constraint:
            val = data[param_name]
            if isinstance(val, (int, float)):
                clamped = max(constraint["min"], min(constraint["max"], val))
                # Preserve type
                if constraint.get("type") == int:
                    clamped = int(round(clamped))
                data[param_name] = clamped

    # Reconstruct
    if isinstance(params, CryptoParameters):
        return CryptoParameters.from_dict(data)
    elif isinstance(params, ForexParameters):
        return ForexParameters.from_dict(data)
    else:
        return UniversalParameters.from_dict(data)
