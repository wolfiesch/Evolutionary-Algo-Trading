"""Backtester module - asset-agnostic strategy evaluation."""
from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    Trade,
)
from shared.evolution.backtester.engine import MinimalBacktester

__all__ = [
    "BacktestConfig",
    "BacktestResults",
    "Trade",
    "MinimalBacktester",
]
