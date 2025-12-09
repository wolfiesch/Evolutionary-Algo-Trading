"""Backtester module - asset-agnostic strategy evaluation."""
from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    PortfolioBacktestResults,
    Trade,
    WalkForwardConfig,
    WalkForwardResults,
)
from shared.evolution.backtester.engine import MinimalBacktester
from shared.evolution.backtester.portfolio_engine import PortfolioBacktester
from shared.evolution.backtester.walk_forward import (
    WalkForwardValidator,
    walk_forward_fitness,
)

__all__ = [
    # Models
    "BacktestConfig",
    "BacktestResults",
    "PortfolioBacktestResults",
    "Trade",
    "WalkForwardConfig",
    "WalkForwardResults",
    # Engines
    "MinimalBacktester",
    "PortfolioBacktester",
    # Validation
    "WalkForwardValidator",
    "walk_forward_fitness",
]
