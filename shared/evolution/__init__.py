"""Evolution module - LLM-driven strategy evolution system."""

# Re-export key components
from shared.evolution.backtester import (
    BacktestConfig,
    BacktestResults,
    Trade,
    MinimalBacktester,
)
from shared.evolution.fitness import (
    FitnessResult,
    calculate_fitness,
    drawdown_penalty,
    rank_strategies,
)
from shared.evolution.mutator import (
    LLMProvider,
    LLMConfig,
    LLMClient,
    create_llm_client,
    create_default_client,
    GeneratedStrategy,
    StrategyGenerator,
    generate_initial_population,
)

__all__ = [
    # Backtester
    "BacktestConfig",
    "BacktestResults",
    "Trade",
    "MinimalBacktester",
    # Fitness
    "FitnessResult",
    "calculate_fitness",
    "drawdown_penalty",
    "rank_strategies",
    # Mutator
    "LLMProvider",
    "LLMConfig",
    "LLMClient",
    "create_llm_client",
    "create_default_client",
    "GeneratedStrategy",
    "StrategyGenerator",
    "generate_initial_population",
]
