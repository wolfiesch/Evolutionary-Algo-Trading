"""Fitness module - asset-agnostic strategy scoring."""
from shared.evolution.fitness.models import FitnessResult
from shared.evolution.fitness.calculator import (
    calculate_fitness,
    calculate_fitness_with_regimes,
    aggregate_regime_results,
    drawdown_penalty,
    rank_strategies,
)
from shared.evolution.fitness.regime_classifier import (
    REGIME_NAMES,
    RegimeClassification,
    RegimeSplitResult,
    classify_period,
    split_by_regime,
    calculate_regime_pass_count,
    calculate_regime_multiplier,
    has_negative_regime,
)

__all__ = [
    # Models
    "FitnessResult",
    "RegimeClassification",
    "RegimeSplitResult",
    # Fitness calculation
    "calculate_fitness",
    "calculate_fitness_with_regimes",
    "aggregate_regime_results",
    "drawdown_penalty",
    "rank_strategies",
    # Regime classification
    "REGIME_NAMES",
    "classify_period",
    "split_by_regime",
    "calculate_regime_pass_count",
    "calculate_regime_multiplier",
    "has_negative_regime",
]
