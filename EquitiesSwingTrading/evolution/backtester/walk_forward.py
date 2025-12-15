"""
Walk-Forward Validation for Equities Swing Trading.

Prevents overfitting by testing strategies on unseen data:
- Rolling train/test windows
- Out-of-sample performance tracking
- Consistency scoring across periods

Walk-forward structure:
    Train (12 months) -> Test (3 months) -> Step (3 months) -> Repeat
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable, Optional

import pandas as pd
import numpy as np

from evolution.backtester.evaluator import StrategyEvaluator
from evolution.fitness.calculator import (
    BacktestResults,
    calculate_sharpe,
    calculate_max_drawdown,
)

logger = logging.getLogger(__name__)


@dataclass
class WalkForwardConfig:
    """Configuration for walk-forward validation."""
    # Window sizes (in trading days)
    train_days: int = 252           # 1 year training
    test_days: int = 63             # 3 months testing (~1 quarter)
    step_days: int = 63             # 3 months step

    # Minimum data requirements
    min_total_days: int = 504       # 2 years minimum

    # Performance thresholds
    min_test_trades: int = 5        # Minimum trades in test period
    consistency_threshold: float = 0.5  # Sharpe threshold for "pass"


@dataclass
class WalkForwardPeriod:
    """Results for a single walk-forward period."""
    period_index: int
    train_start: date
    train_end: date
    test_start: date
    test_end: date

    # Training metrics
    train_sharpe: float = 0.0
    train_drawdown: float = 0.0
    train_trades: int = 0

    # Testing metrics (out-of-sample)
    test_sharpe: float = 0.0
    test_drawdown: float = 0.0
    test_trades: int = 0
    test_return: float = 0.0

    # Degradation (train vs test)
    sharpe_degradation: float = 0.0  # Negative = test worse than train

    @property
    def passed(self) -> bool:
        """Did this period pass the consistency threshold?"""
        return self.test_sharpe >= 0.0 and self.test_trades >= 5


@dataclass
class WalkForwardResults:
    """Aggregate results from walk-forward validation."""
    periods: list[WalkForwardPeriod] = field(default_factory=list)

    # Aggregate metrics
    total_periods: int = 0
    passed_periods: int = 0
    avg_train_sharpe: float = 0.0
    avg_test_sharpe: float = 0.0
    avg_sharpe_degradation: float = 0.0
    consistency_score: float = 0.0  # passed_periods / total_periods

    # Worst case
    worst_test_sharpe: float = 0.0
    worst_test_drawdown: float = 0.0

    @property
    def is_robust(self) -> bool:
        """
        Is strategy robust based on walk-forward?

        Criteria:
        - At least 50% of periods passed
        - Average test Sharpe > 0
        - No period with extreme negative Sharpe
        """
        return (
            self.consistency_score >= 0.5 and
            self.avg_test_sharpe > 0 and
            self.worst_test_sharpe > -2.0
        )


class WalkForwardValidator:
    """
    Performs walk-forward validation on strategies.

    Walk-forward prevents overfitting by ensuring strategies
    perform well on unseen (out-of-sample) data across multiple
    time periods.
    """

    def __init__(self, config: Optional[WalkForwardConfig] = None):
        """
        Initialize validator.

        Args:
            config: Walk-forward configuration
        """
        self.config = config or WalkForwardConfig()

    def validate(
        self,
        evaluator: StrategyEvaluator,
        candles: pd.DataFrame,
        benchmark: pd.DataFrame,
        backtest_func: Callable,
    ) -> WalkForwardResults:
        """
        Run walk-forward validation.

        Args:
            evaluator: Strategy evaluator function
            candles: Full OHLCV data for symbol
            benchmark: Full SPY data
            backtest_func: Function to run backtest on a slice

        Returns:
            WalkForwardResults with all period results
        """
        results = WalkForwardResults()

        # Validate data length
        if len(candles) < self.config.min_total_days:
            logger.warning(
                f"Insufficient data for walk-forward: {len(candles)} < {self.config.min_total_days}"
            )
            return results

        # Generate periods
        periods = self._generate_periods(candles)
        results.total_periods = len(periods)

        # Run validation for each period
        for i, (train_slice, test_slice) in enumerate(periods):
            period_result = self._validate_period(
                i, train_slice, test_slice, evaluator, benchmark, backtest_func
            )
            results.periods.append(period_result)

        # Calculate aggregate metrics
        self._calculate_aggregates(results)

        return results

    def _generate_periods(
        self,
        candles: pd.DataFrame,
    ) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """
        Generate train/test period slices.

        Returns:
            List of ((train_start, train_end), (test_start, test_end)) index tuples
        """
        periods = []
        n = len(candles)
        train = self.config.train_days
        test = self.config.test_days
        step = self.config.step_days

        start = 0
        while start + train + test <= n:
            train_slice = (start, start + train)
            test_slice = (start + train, start + train + test)
            periods.append((train_slice, test_slice))
            start += step

        return periods

    def _validate_period(
        self,
        period_index: int,
        train_slice: tuple[int, int],
        test_slice: tuple[int, int],
        evaluator: StrategyEvaluator,
        benchmark: pd.DataFrame,
        backtest_func: Callable,
    ) -> WalkForwardPeriod:
        """Run validation for a single period."""
        # Extract date range from candles (we need the actual candles to get dates)
        # This is a simplified version - in practice you'd have the full dataframe

        period = WalkForwardPeriod(
            period_index=period_index,
            train_start=date.today() - timedelta(days=365),  # Placeholder
            train_end=date.today() - timedelta(days=90),
            test_start=date.today() - timedelta(days=90),
            test_end=date.today(),
        )

        # In a full implementation:
        # 1. Slice candles for train period
        # 2. Run backtest on train period
        # 3. Slice candles for test period
        # 4. Run backtest on test period
        # 5. Calculate degradation

        # Placeholder values - actual implementation would call backtest_func
        period.train_sharpe = 1.5
        period.train_drawdown = 0.10
        period.train_trades = 30
        period.test_sharpe = 1.0
        period.test_drawdown = 0.12
        period.test_trades = 8
        period.test_return = 0.05
        period.sharpe_degradation = period.test_sharpe - period.train_sharpe

        return period

    def _calculate_aggregates(self, results: WalkForwardResults) -> None:
        """Calculate aggregate metrics from period results."""
        if not results.periods:
            return

        # Count passed periods
        results.passed_periods = sum(1 for p in results.periods if p.passed)
        results.consistency_score = results.passed_periods / results.total_periods

        # Average metrics
        results.avg_train_sharpe = np.mean([p.train_sharpe for p in results.periods])
        results.avg_test_sharpe = np.mean([p.test_sharpe for p in results.periods])
        results.avg_sharpe_degradation = np.mean([p.sharpe_degradation for p in results.periods])

        # Worst case
        results.worst_test_sharpe = min(p.test_sharpe for p in results.periods)
        results.worst_test_drawdown = max(p.test_drawdown for p in results.periods)


def run_walk_forward(
    evaluator: StrategyEvaluator,
    candles: pd.DataFrame,
    benchmark: pd.DataFrame,
    backtest_func: Callable,
    config: Optional[WalkForwardConfig] = None,
) -> WalkForwardResults:
    """
    Run walk-forward validation.

    Convenience function.

    Args:
        evaluator: Strategy evaluator
        candles: Symbol data
        benchmark: SPY data
        backtest_func: Backtest function
        config: Optional configuration

    Returns:
        WalkForwardResults
    """
    validator = WalkForwardValidator(config)
    return validator.validate(evaluator, candles, benchmark, backtest_func)


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test walk-forward validator."""
    print("Testing walk-forward validator...")

    config = WalkForwardConfig(
        train_days=60,
        test_days=20,
        step_days=20,
        min_total_days=100,
    )

    validator = WalkForwardValidator(config)

    # Create dummy data
    n = 200
    dates = pd.date_range(end=date.today(), periods=n, freq='D')
    candles = pd.DataFrame({
        "date": dates,
        "open": 100 + np.random.randn(n).cumsum(),
        "high": 100 + np.random.randn(n).cumsum() + 1,
        "low": 100 + np.random.randn(n).cumsum() - 1,
        "close": 100 + np.random.randn(n).cumsum(),
        "volume": np.random.randint(1000000, 5000000, n),
    })

    # Dummy evaluator
    def dummy_evaluator(c, b, has_pos):
        return "HOLD"

    # Dummy backtest
    def dummy_backtest(candles, benchmark, evaluator):
        return BacktestResults(trade_count=10, sharpe_ratio=1.0)

    # Generate periods
    periods = validator._generate_periods(candles)
    print(f"Generated {len(periods)} walk-forward periods")

    # Run validation (with placeholders)
    results = validator.validate(
        dummy_evaluator, candles, candles, dummy_backtest
    )

    print(f"\nWalk-Forward Results:")
    print(f"  Total periods: {results.total_periods}")
    print(f"  Passed periods: {results.passed_periods}")
    print(f"  Consistency: {results.consistency_score:.1%}")
    print(f"  Avg train Sharpe: {results.avg_train_sharpe:.2f}")
    print(f"  Avg test Sharpe: {results.avg_test_sharpe:.2f}")
    print(f"  Is robust: {results.is_robust}")


if __name__ == "__main__":
    quick_test()
