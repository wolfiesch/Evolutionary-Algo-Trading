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
from shared.evolution.backtester.snapshot import (
    DataSnapshot,
    SnapshotMetadata,
    create_run_snapshot,
)
from shared.evolution.backtester.template_engine import (
    TemplateBacktester,
    TemplateBacktestConfig,
    PositionSide,
    Position,
    create_evaluator_from_template,
)
# T0 Fix: Multi-timeframe support
from shared.evolution.backtester.timeframe import (
    Timeframe,
    TimeframeConfig,
    TIMEFRAME_CONFIGS,
    aggregate_candles,
    get_timeframe_config,
    get_periods_per_year,
    estimate_data_requirements,
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
    # Snapshot (data freezing)
    "DataSnapshot",
    "SnapshotMetadata",
    "create_run_snapshot",
    # Template backtesting (Phase 6)
    "TemplateBacktester",
    "TemplateBacktestConfig",
    "PositionSide",
    "Position",
    "create_evaluator_from_template",
    # Timeframe utilities (T0 Fix)
    "Timeframe",
    "TimeframeConfig",
    "TIMEFRAME_CONFIGS",
    "aggregate_candles",
    "get_timeframe_config",
    "get_periods_per_year",
    "estimate_data_requirements",
]
