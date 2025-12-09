"""Mutator module - LLM-driven strategy generation and mutation."""
from shared.evolution.mutator.llm_client import (
    LLMProvider,
    LLMConfig,
    LLMClient,
    OpenAIClient,
    AnthropicClient,
    create_llm_client,
    create_default_client,
)
from shared.evolution.mutator.generator import (
    GeneratedStrategy,
    StrategyGenerator,
    generate_initial_population,
)
from shared.evolution.mutator.prompts import (
    STRATEGY_THEMES,
    get_generation_prompt,
    get_mutation_prompt,
    get_crossover_prompt,
)
from shared.evolution.mutator.selection import (
    tournament_selection,
    elite_selection,
    roulette_selection,
    rank_selection,
    select_diverse_parents,
)
from shared.evolution.mutator.crossover import CrossoverOperator
from shared.evolution.mutator.evolution import (
    EvolutionConfig,
    EvolutionState,
    EvolutionResult,
    EvolutionEngine,
)

__all__ = [
    # LLM Client
    "LLMProvider",
    "LLMConfig",
    "LLMClient",
    "OpenAIClient",
    "AnthropicClient",
    "create_llm_client",
    "create_default_client",
    # Generator
    "GeneratedStrategy",
    "StrategyGenerator",
    "generate_initial_population",
    # Prompts
    "STRATEGY_THEMES",
    "get_generation_prompt",
    "get_mutation_prompt",
    "get_crossover_prompt",
    # Selection (Phase 2D)
    "tournament_selection",
    "elite_selection",
    "roulette_selection",
    "rank_selection",
    "select_diverse_parents",
    # Crossover (Phase 2D)
    "CrossoverOperator",
    # Evolution Engine (Phase 2D)
    "EvolutionConfig",
    "EvolutionState",
    "EvolutionResult",
    "EvolutionEngine",
]
