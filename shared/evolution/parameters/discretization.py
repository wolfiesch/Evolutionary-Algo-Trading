"""
Discretization utilities for parameter evolution.

Prevents overfitting by:
1. Rounding continuous values to discrete steps
2. Reducing effective search space to enumerable values
3. Maintaining consistency between similar strategies

This follows the project principle: "Integer parameters only - No hyper-tuning"
"""
from typing import Dict
import math

from .schema import WeightVector, UniversalParameters, CryptoParameters, ForexParameters


# === DISCRETIZATION STEPS ===

DISCRETIZATION_STEPS = {
    # Weights: round to nearest 0.1 (-1.0, -0.9, ..., 0.9, 1.0) = 21 values
    "weights": 0.1,

    # Thresholds: round to nearest 0.05
    "thresholds": 0.05,

    # ATR multipliers: round to nearest 0.5 (1.0, 1.5, 2.0, ...) = ~8 values
    "atr_multipliers": 0.5,

    # Regime threshold: round to nearest 5 (10, 15, 20, ..., 50) = 9 values
    "regime_threshold": 5.0,

    # Periods: already integers
    "periods": 1,
}


def discretize_value(value: float, step: float) -> float:
    """
    Round a value to the nearest step.

    Args:
        value: Value to discretize
        step: Step size

    Returns:
        Discretized value
    """
    return round(value / step) * step


def discretize_weight_vector(weights: WeightVector) -> WeightVector:
    """
    Discretize all weights in a WeightVector.

    Args:
        weights: WeightVector to discretize

    Returns:
        Discretized WeightVector
    """
    step = DISCRETIZATION_STEPS["weights"]
    return WeightVector(
        trend=discretize_value(weights.trend, step),
        momentum=discretize_value(weights.momentum, step),
        mean_reversion=discretize_value(weights.mean_reversion, step),
        volatility=discretize_value(weights.volatility, step),
        volume=discretize_value(weights.volume, step),
    )


def discretize_parameters(params: UniversalParameters) -> UniversalParameters:
    """
    Discretize all continuous parameters.

    Args:
        params: Parameters to discretize

    Returns:
        Discretized parameters (new instance)
    """
    data = params.to_dict()

    # Discretize weight vectors
    data["weights_A"] = discretize_weight_vector(
        WeightVector.from_dict(data["weights_A"])
    ).to_dict()
    data["weights_B"] = discretize_weight_vector(
        WeightVector.from_dict(data["weights_B"])
    ).to_dict()

    # Discretize regime threshold
    data["regime_threshold"] = discretize_value(
        data["regime_threshold"],
        DISCRETIZATION_STEPS["regime_threshold"]
    )

    # Discretize entry/exit thresholds
    threshold_step = DISCRETIZATION_STEPS["thresholds"]
    data["entry_threshold_long"] = discretize_value(data["entry_threshold_long"], threshold_step)
    data["exit_threshold_long"] = discretize_value(data["exit_threshold_long"], threshold_step)
    data["entry_threshold_short"] = discretize_value(data["entry_threshold_short"], threshold_step)
    data["exit_threshold_short"] = discretize_value(data["exit_threshold_short"], threshold_step)

    # Discretize ATR multipliers
    atr_step = DISCRETIZATION_STEPS["atr_multipliers"]
    data["stop_loss_atr_mult"] = discretize_value(data["stop_loss_atr_mult"], atr_step)
    data["take_profit_atr_mult"] = discretize_value(data["take_profit_atr_mult"], atr_step)

    # Discretize market filter threshold
    data["market_filter_threshold"] = discretize_value(
        data["market_filter_threshold"],
        threshold_step
    )

    # Periods are already integers, but ensure they are
    for period_key in [
        "regime_period", "trend_fast_period", "trend_slow_period",
        "momentum_period", "reversion_period", "volatility_period",
        "volume_period", "market_filter_period", "min_bars_between_trades",
        "max_position_bars"
    ]:
        if period_key in data:
            data[period_key] = int(round(data[period_key]))

    # reversion_std_dev is also integer
    data["reversion_std_dev"] = int(round(data["reversion_std_dev"]))

    # Reconstruct the appropriate parameter type
    if isinstance(params, CryptoParameters):
        # Also discretize crypto-specific weights
        data["weight_btc_correlation"] = discretize_value(
            data.get("weight_btc_correlation", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        data["weight_funding_rate"] = discretize_value(
            data.get("weight_funding_rate", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        data["weight_btc_dominance"] = discretize_value(
            data.get("weight_btc_dominance", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        # Discretize funding rate threshold (use threshold step)
        data["funding_rate_threshold"] = discretize_value(
            data.get("funding_rate_threshold", 0.01),
            0.005  # Finer granularity for funding rates
        )
        return CryptoParameters.from_dict(data)

    elif isinstance(params, ForexParameters):
        # Also discretize forex-specific weights
        data["weight_session"] = discretize_value(
            data.get("weight_session", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        data["weight_dxy"] = discretize_value(
            data.get("weight_dxy", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        data["weight_rate_diff"] = discretize_value(
            data.get("weight_rate_diff", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        data["weight_risk_sentiment"] = discretize_value(
            data.get("weight_risk_sentiment", 0.0),
            DISCRETIZATION_STEPS["weights"]
        )
        return ForexParameters.from_dict(data)

    else:
        return UniversalParameters.from_dict(data)


def calculate_search_space_size() -> Dict[str, int]:
    """
    Calculate the effective search space size with discretization.

    Returns:
        Dictionary with parameter counts and total combinations
    """
    # Weight vector: 21 values per weight (-1.0 to +1.0 in 0.1 steps)
    weight_values = int(2.0 / DISCRETIZATION_STEPS["weights"]) + 1  # 21

    # Two weight vectors, 5 weights each
    weight_combinations = weight_values ** 5  # Per vector
    total_weight_combinations = weight_combinations ** 2  # Two vectors

    # Periods (vary by parameter, estimate)
    period_combinations = 40 * 40 * 45 * 90 * 45 * 90  # Approximate

    # Thresholds (entry/exit long and short)
    threshold_values = int(0.7 / DISCRETIZATION_STEPS["thresholds"]) + 1  # ~15 per threshold
    threshold_combinations = threshold_values ** 4

    # Risk (stop_loss: 1.0-5.0, take_profit: 1.5-8.0 in 0.5 steps)
    stop_loss_values = int((5.0 - 1.0) / DISCRETIZATION_STEPS["atr_multipliers"]) + 1  # 9
    take_profit_values = int((8.0 - 1.5) / DISCRETIZATION_STEPS["atr_multipliers"]) + 1  # 14
    risk_combinations = stop_loss_values * take_profit_values

    # Regime selector
    regime_indicator_values = 3  # adx, atr_percentile, bb_width
    regime_threshold_values = int((50.0 - 10.0) / DISCRETIZATION_STEPS["regime_threshold"]) + 1  # 9

    return {
        "weight_values_per_param": weight_values,
        "weight_combinations_per_vector": weight_combinations,
        "total_weight_combinations": total_weight_combinations,
        "threshold_combinations": threshold_combinations,
        "risk_combinations": risk_combinations,
        "regime_combinations": regime_indicator_values * regime_threshold_values,
        "estimated_total": "~10^12 (tractable with evolutionary search)",
    }


def hash_parameters(params: UniversalParameters) -> str:
    """
    Generate a hash string for deduplication.

    Uses discretized values to ensure similar strategies hash the same.

    Args:
        params: Parameters to hash

    Returns:
        Hash string
    """
    # Discretize first
    disc = discretize_parameters(params)
    data = disc.to_dict()

    # Sort keys for consistent ordering
    sorted_items = sorted(data.items(), key=lambda x: x[0])

    # Build hash string
    parts = []
    for key, value in sorted_items:
        if isinstance(value, dict):
            # Weight vector
            wv_parts = sorted(value.items(), key=lambda x: x[0])
            wv_str = "|".join(f"{k}:{v:.1f}" for k, v in wv_parts)
            parts.append(f"{key}:{{{wv_str}}}")
        elif isinstance(value, bool):
            parts.append(f"{key}:{int(value)}")
        elif isinstance(value, float):
            parts.append(f"{key}:{value:.2f}")
        else:
            parts.append(f"{key}:{value}")

    return "|".join(parts)


def parameters_are_equivalent(
    params1: UniversalParameters,
    params2: UniversalParameters,
    tolerance: float = 0.01
) -> bool:
    """
    Check if two parameter sets are effectively equivalent.

    After discretization, checks if all values are within tolerance.

    Args:
        params1: First parameter set
        params2: Second parameter set
        tolerance: Maximum difference for float comparison

    Returns:
        True if equivalent
    """
    # Type must match
    if type(params1) != type(params2):
        return False

    # Discretize both
    disc1 = discretize_parameters(params1)
    disc2 = discretize_parameters(params2)

    # Compare hashes (fast path)
    return hash_parameters(disc1) == hash_parameters(disc2)
