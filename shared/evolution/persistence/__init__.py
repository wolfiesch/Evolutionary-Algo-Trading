"""
Strategy persistence module - save/load evolved strategies.
"""
from shared.evolution.persistence.strategy_store import (
    StrategyStore,
    StrategyRecord,
    save_strategy,
    load_strategy,
    list_strategies,
    delete_strategy,
)
from shared.evolution.persistence.handoff import (
    HandoffConfig,
    qualify_for_shadow,
    handoff_to_shadow,
    load_shadow_pool,
    retire_shadow_strategy,
    promote_best_from_evolution,
    get_shadow_pool_summary,
)

__all__ = [
    # Strategy store
    "StrategyStore",
    "StrategyRecord",
    "save_strategy",
    "load_strategy",
    "list_strategies",
    "delete_strategy",
    # Handoff
    "HandoffConfig",
    "qualify_for_shadow",
    "handoff_to_shadow",
    "load_shadow_pool",
    "retire_shadow_strategy",
    "promote_best_from_evolution",
    "get_shadow_pool_summary",
]
