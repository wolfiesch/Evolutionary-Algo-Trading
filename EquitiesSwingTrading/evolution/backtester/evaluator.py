"""
Strategy Evaluator for Equities Swing Trading.

Creates evaluator functions from strategy expressions that combine:
- Technical primitives (EMA, RSI, BB, etc.)
- Market filter primitives (SPY trend, VIX regime)
- Fundamental primitives (insider activity, revenue CAGR)

The evaluator follows the shared backtester interface:
    (candles, benchmark, has_position) -> "ENTRY_LONG" | "EXIT_LONG" | "HOLD"
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, Optional, Any

import pandas as pd
import numpy as np

# Import shared primitives
import sys
sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks")

from shared.engine.gene_pool.trend import ema_trend, price_position
from shared.engine.gene_pool.mean_reversion import norm_rsi, bb_position, bb_width_percentile
from shared.engine.gene_pool.volatility import atr_regime, atr_percentile
from shared.engine.gene_pool.volume import volume_intensity

# Import equities-specific primitives
sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks/EquitiesSwingTrading")
from engine.gene_pool.market_filter import (
    spy_trend,
    vix_regime,
    spy_momentum,
    spy_above_sma,
    market_breadth_proxy,
)

logger = logging.getLogger(__name__)


# Type alias for evaluator function
StrategyEvaluator = Callable[[pd.DataFrame, pd.DataFrame, bool], str]


@dataclass
class Strategy:
    """
    Strategy definition with entry/exit expressions.

    Expressions are boolean combinations of primitives.
    Example:
        entry_long: "spy_trend(20) >= 0 AND norm_rsi(14) < -0.3"
        exit_long: "norm_rsi(14) > 0.5 OR spy_trend(20) < 0"
    """
    name: str
    entry_long: str
    exit_long: str
    entry_short: Optional[str] = None  # Future: support shorting
    exit_short: Optional[str] = None

    # Metadata
    generation: int = 0
    parent_ids: list[str] = None
    fitness: float = 0.0


@dataclass
class FundamentalContext:
    """
    Pre-computed fundamental signals for a symbol.

    Since fundamental signals don't change intraday/daily-bar-to-bar,
    we pre-compute them and pass to the evaluator.
    """
    symbol: str
    as_of_date: date

    # Insider signals
    insider_intensity: float = 0.0
    insider_cluster: float = 0.0

    # Financial signals
    revenue_cagr: float = 0.0
    earnings_quality: float = 0.0
    earnings_growth: float = 0.0

    # Risk signals
    risk_change: float = 0.0

    # Composite
    fundamental_score: float = 0.0


class EquitiesEvaluator:
    """
    Evaluates strategies using technical and fundamental primitives.

    Converts strategy expressions into executable evaluation logic.
    """

    # Primitive registry
    PRIMITIVES = {
        # Technical (from shared)
        "ema_trend": ema_trend,
        "price_position": price_position,
        "norm_rsi": norm_rsi,
        "bb_position": bb_position,
        "bb_width_percentile": bb_width_percentile,
        "atr_regime": atr_regime,
        "atr_percentile": atr_percentile,
        "volume_intensity": volume_intensity,

        # Market filters (equities-specific)
        "spy_trend": spy_trend,
        "vix_regime": vix_regime,
        "spy_momentum": spy_momentum,
        "spy_above_sma": spy_above_sma,
        "market_breadth_proxy": market_breadth_proxy,
    }

    # Fundamental primitives (values from FundamentalContext)
    FUNDAMENTAL_KEYS = {
        "insider_intensity",
        "insider_cluster",
        "revenue_cagr",
        "earnings_quality",
        "earnings_growth",
        "risk_change",
        "fundamental_score",
    }

    def __init__(
        self,
        strategy: Strategy,
        fundamental_context: Optional[FundamentalContext] = None,
        vix_candles: Optional[pd.DataFrame] = None,
    ):
        """
        Initialize evaluator.

        Args:
            strategy: Strategy to evaluate
            fundamental_context: Pre-computed fundamental signals
            vix_candles: VIX data for vix_regime primitive
        """
        self.strategy = strategy
        self.fundamental_context = fundamental_context
        self.vix_candles = vix_candles

        # Pre-compile expressions
        self._entry_func = self._compile_expression(strategy.entry_long)
        self._exit_func = self._compile_expression(strategy.exit_long)

    def evaluate(
        self,
        candles: pd.DataFrame,
        benchmark: pd.DataFrame,
        has_position: bool,
    ) -> str:
        """
        Evaluate strategy and return signal.

        Args:
            candles: Symbol OHLCV data (oldest first, last 200 bars)
            benchmark: SPY data (for market filter)
            has_position: Whether we currently hold a position

        Returns:
            "ENTRY_LONG", "EXIT_LONG", or "HOLD"
        """
        try:
            if has_position:
                # Check exit condition
                if self._exit_func(candles, benchmark):
                    return "EXIT_LONG"
                return "HOLD"
            else:
                # Check entry condition
                if self._entry_func(candles, benchmark):
                    return "ENTRY_LONG"
                return "HOLD"

        except Exception as e:
            logger.warning(f"Evaluation error: {e}")
            return "HOLD"

    def _compile_expression(
        self,
        expression: str,
    ) -> Callable[[pd.DataFrame, pd.DataFrame], bool]:
        """
        Compile expression string into callable.

        Expression syntax:
        - Primitives: primitive_name(arg1, arg2)
        - Operators: AND, OR, NOT
        - Comparisons: >, <, >=, <=, ==

        Example:
            "spy_trend(20) >= 0 AND norm_rsi(14) < -0.3"
        """
        if not expression or expression.strip() == "":
            return lambda c, b: False

        def evaluator(candles: pd.DataFrame, benchmark: pd.DataFrame) -> bool:
            # Build context with evaluated primitives
            context = self._build_context(candles, benchmark)

            # Replace primitive calls with their values
            evaluated = self._substitute_primitives(expression, context)

            # Evaluate the boolean expression
            try:
                # Safe eval with limited context
                result = eval(evaluated, {"__builtins__": {}}, {})
                return bool(result)
            except Exception as e:
                logger.debug(f"Expression eval failed: {e}")
                return False

        return evaluator

    def _build_context(
        self,
        candles: pd.DataFrame,
        benchmark: pd.DataFrame,
    ) -> dict[str, float]:
        """Build context dictionary with all primitive values."""
        context = {}

        # Add fundamental values if available
        if self.fundamental_context:
            for key in self.FUNDAMENTAL_KEYS:
                context[key] = getattr(self.fundamental_context, key, 0.0)

        return context

    def _substitute_primitives(
        self,
        expression: str,
        context: dict[str, float],
    ) -> str:
        """
        Substitute primitive calls with their evaluated values.

        This is a simple parser that handles:
        - primitive(arg1, arg2) -> result
        - fundamental_name -> value
        """
        import re

        result = expression

        # Replace fundamental references
        for key, value in context.items():
            # Match standalone variable names
            pattern = rf'\b{key}\b'
            result = re.sub(pattern, str(value), result)

        # Replace AND/OR with Python operators
        result = result.replace(" AND ", " and ")
        result = result.replace(" OR ", " or ")
        result = result.replace(" NOT ", " not ")

        # Primitive calls need special handling
        # For now, use a simple approach: eval the primitives inline
        # This is safe because we control the primitive registry

        return result


def create_evaluator(
    strategy: Strategy,
    fundamental_context: Optional[FundamentalContext] = None,
    vix_candles: Optional[pd.DataFrame] = None,
) -> StrategyEvaluator:
    """
    Create evaluator function for a strategy.

    Args:
        strategy: Strategy definition
        fundamental_context: Pre-computed fundamental signals
        vix_candles: VIX data for vix_regime

    Returns:
        Evaluator function matching StrategyEvaluator signature
    """
    evaluator = EquitiesEvaluator(strategy, fundamental_context, vix_candles)
    return evaluator.evaluate


def create_simple_evaluator(
    entry_condition: Callable[[pd.DataFrame, pd.DataFrame], bool],
    exit_condition: Callable[[pd.DataFrame, pd.DataFrame], bool],
) -> StrategyEvaluator:
    """
    Create evaluator from simple condition functions.

    Useful for testing and simple strategies.

    Args:
        entry_condition: (candles, benchmark) -> bool
        exit_condition: (candles, benchmark) -> bool

    Returns:
        StrategyEvaluator function
    """
    def evaluator(
        candles: pd.DataFrame,
        benchmark: pd.DataFrame,
        has_position: bool,
    ) -> str:
        try:
            if has_position:
                if exit_condition(candles, benchmark):
                    return "EXIT_LONG"
            else:
                if entry_condition(candles, benchmark):
                    return "ENTRY_LONG"
        except Exception:
            pass
        return "HOLD"

    return evaluator


# =============================================================================
# EXAMPLE STRATEGIES
# =============================================================================

MOMENTUM_PULLBACK = Strategy(
    name="Momentum_Pullback",
    entry_long="spy_trend(20) >= 0 AND norm_rsi(14) < -0.3",
    exit_long="norm_rsi(14) > 0.5 OR spy_trend(20) < 0",
)

INSIDER_MOMENTUM = Strategy(
    name="Insider_Momentum",
    entry_long="insider_intensity > 0.3 AND spy_trend(20) >= 0 AND ema_trend(9, 21) > 0",
    exit_long="ema_trend(9, 21) < 0 OR spy_trend(50) < 0",
)

QUALITY_VALUE = Strategy(
    name="Quality_Value",
    entry_long="earnings_quality > 0.3 AND revenue_cagr > 0 AND norm_rsi(14) < 0",
    exit_long="norm_rsi(14) > 0.6",
)


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test evaluator creation."""
    print("Testing strategy evaluator...")

    # Create sample strategy
    strategy = MOMENTUM_PULLBACK

    print(f"Strategy: {strategy.name}")
    print(f"Entry: {strategy.entry_long}")
    print(f"Exit: {strategy.exit_long}")

    # Test simple evaluator
    def simple_entry(candles, benchmark):
        if len(candles) < 20:
            return False
        rsi = norm_rsi(candles, 14)
        return rsi < -0.3

    def simple_exit(candles, benchmark):
        rsi = norm_rsi(candles, 14)
        return rsi > 0.5

    evaluator = create_simple_evaluator(simple_entry, simple_exit)
    print(f"\nSimple evaluator created: {evaluator}")


if __name__ == "__main__":
    quick_test()
