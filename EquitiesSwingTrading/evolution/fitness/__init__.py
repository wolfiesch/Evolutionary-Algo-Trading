"""
Fitness calculation for Equities Swing Trading.

Contains:
- Regime classifier (SPY/VIX based)
- Fitness calculator with regime-aware scoring
"""

from evolution.fitness.regime_classifier import (
    EquitiesRegimeClassifier,
    MarketRegime,
    classify_regime,
    label_regimes,
)
from evolution.fitness.calculator import (
    EquitiesFitnessCalculator,
    calculate_fitness,
)

__all__ = [
    "EquitiesRegimeClassifier",
    "MarketRegime",
    "classify_regime",
    "label_regimes",
    "EquitiesFitnessCalculator",
    "calculate_fitness",
]
