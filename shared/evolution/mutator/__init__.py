"""Mutator module - LLM-driven strategy generation and mutation."""
from shared.evolution.mutator.llm_client import (
    LLMProvider,
    LLMConfig,
    LLMClient,
    OpenAIClient,
    AnthropicClient,
    create_llm_client,
    create_default_client,
    create_analysis_client,
)
from shared.evolution.mutator.generator import (
    GeneratedStrategy,
    StrategyGenerator,
    generate_initial_population,
)
from shared.evolution.mutator.prompts import (
    STRATEGY_THEMES,
    MEAN_REVERSION_THEMES,
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
    ProgressCallback,
)
from shared.evolution.mutator.deduplication import (
    StrategyDeduplicator,
    DeduplicationStats,
    deduplicate_population,
)
from shared.evolution.mutator.analyzer import (
    StrategyAnalysis,
    StrategyAnalyzer,
    analyze_evolution_winners,
)
from shared.evolution.mutator.parameter_mutation import (
    MutationResult,
    mutate_parameters,
    random_mutate_parameters,
    crossover_parameters,
    random_crossover_parameters,
    generate_initial_parameters,
    ParameterEvolutionState,
    PARAMETER_MUTATION_SYSTEM_PROMPT,
    PARAMETER_MUTATION_PROMPT,
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
    "create_analysis_client",
    # Generator
    "GeneratedStrategy",
    "StrategyGenerator",
    "generate_initial_population",
    # Prompts
    "STRATEGY_THEMES",
    "MEAN_REVERSION_THEMES",
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
    "ProgressCallback",
    # Deduplication (Phase 2E)
    "StrategyDeduplicator",
    "DeduplicationStats",
    "deduplicate_population",
    # Strategy Analyzer (Opus-powered)
    "StrategyAnalysis",
    "StrategyAnalyzer",
    "analyze_evolution_winners",
    # Parameter Evolution (Phase 5)
    "MutationResult",
    "mutate_parameters",
    "random_mutate_parameters",
    "crossover_parameters",
    "random_crossover_parameters",
    "generate_initial_parameters",
    "ParameterEvolutionState",
    "PARAMETER_MUTATION_SYSTEM_PROMPT",
    "PARAMETER_MUTATION_PROMPT",
]
