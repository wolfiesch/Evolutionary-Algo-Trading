"""
Equities evolution mutator components.

Extends shared evolution infrastructure with equities-specific:
- LLM prompts (fundamental + technical primitives)
- Strategy themes
- Evolution configuration
"""

from evolution.mutator.prompts import (
    EQUITIES_SYSTEM_PROMPT,
    EQUITIES_MUTATION_PROMPT,
    EQUITIES_CROSSOVER_PROMPT,
    EQUITIES_THEMES,
    EQUITIES_MEAN_REVERSION_THEMES,
    get_equities_generation_prompt,
    get_equities_mutation_prompt,
    get_equities_crossover_prompt,
)
from evolution.mutator.config import (
    EquitiesEvolutionConfig,
    get_default_config,
)
from evolution.mutator.generator import EquitiesStrategyGenerator

__all__ = [
    "EQUITIES_SYSTEM_PROMPT",
    "EQUITIES_MUTATION_PROMPT",
    "EQUITIES_CROSSOVER_PROMPT",
    "EQUITIES_THEMES",
    "EQUITIES_MEAN_REVERSION_THEMES",
    "get_equities_generation_prompt",
    "get_equities_mutation_prompt",
    "get_equities_crossover_prompt",
    "EquitiesEvolutionConfig",
    "get_default_config",
    "EquitiesStrategyGenerator",
]
