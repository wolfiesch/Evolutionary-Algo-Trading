"""Fitness module - asset-agnostic strategy scoring."""
from shared.evolution.fitness.models import FitnessResult
from shared.evolution.fitness.calculator import (
    calculate_fitness,
    drawdown_penalty,
    rank_strategies,
)

__all__ = [
    "FitnessResult",
    "calculate_fitness",
    "drawdown_penalty",
    "rank_strategies",
]
