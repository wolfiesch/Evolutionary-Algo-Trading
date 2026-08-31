"""
Walk-forward validation - Phase 2C.

Rolling window validation to prevent overfitting.
"""
import logging
import math
from typing import Callable
import pandas as pd
import numpy as np

from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    WalkForwardConfig,
    WalkForwardResults,
    Trade,
)
from shared.evolution.backtester.engine import MinimalBacktester, StrategyEvaluator

logger = logging.getLogger(__name__)

# Sharpe bounds - these are FLOOR/CEILING values, not sentinels
# Strategies hitting -10 are genuinely terrible. The fitness calculator
# uses -999 as the actual sentinel for disqualified strategies.
SHARPE_FLOOR = -10.0
SHARPE_CEILING = 10.0


class WalkForwardValidator:
    """
    Walk-forward validation for out-of-sample testing.

    Splits data into rolling train/test windows and evaluates
    strategy performance on unseen data to detect overfitting.

    Usage:
        validator = WalkForwardValidator(
            backtest_config=BacktestConfig(),
            wf_config=WalkForwardConfig(train_bars=4320, test_bars=1440),
        )

        results = validator.validate(
            evaluator=my_evaluator_fn,
            candles=sol_df,
            benchmark_candles=btc_df,
            symbol="SOLUSDT",
        )
    """

    def __init__(
        self,
        backtest_config: BacktestConfig,
        wf_config: WalkForwardConfig,
    ):
        """
        Initialize validator.

        Args:
            backtest_config: Configuration for individual backtests
            wf_config: Walk-forward window configuration
        """
        self.backtest_config = backtest_config
        self.wf_config = wf_config
        self.backtester = MinimalBacktester(backtest_config)

    def validate(
        self,
        evaluator: StrategyEvaluator,
        candles: pd.DataFrame,
        benchmark_candles: pd.DataFrame,
        symbol: str,
    ) -> WalkForwardResults:
        """
        Perform walk-forward validation.

        Args:
            evaluator: Strategy evaluation function
            candles: OHLCV DataFrame for trading symbol
            benchmark_candles: OHLCV DataFrame for benchmark
            symbol: Symbol name

        Returns:
            WalkForwardResults with per-window and aggregated metrics
        """
        results = WalkForwardResults()

        total_bars = len(candles)
        min_bars_needed = self.wf_config.train_bars + self.wf_config.test_bars

        if total_bars < min_bars_needed:
            return results

        # Generate windows
        windows = self._generate_windows(total_bars)

        if len(windows) < self.wf_config.min_windows:
            return results

        # Run backtest on each test window
        window_results: list[BacktestResults] = []
        all_trades: list[Trade] = []
        all_equity_points: list[float] = []

        # Calculate minimum warmup based on test window size
        # For 4H candles (42 bars = 7 days), we need at least 20 bars for indicators
        min_warmup = min(20, self.wf_config.test_bars // 2)

        for train_start, train_end, test_start, test_end in windows:
            # Extract test window data
            test_candles = candles.iloc[test_start:test_end].reset_index(drop=True)
            test_benchmark = benchmark_candles.iloc[test_start:test_end].reset_index(drop=True)

            if len(test_candles) < min_warmup:  # Need warmup (timeframe-aware)
                continue

            # Run backtest on test window only
            # Note: In a full implementation, we might re-train/optimize on train window
            # For now, we just test the fixed strategy on each out-of-sample window
            result = self.backtester.run(
                evaluator=evaluator,
                candles=test_candles,
                benchmark_candles=test_benchmark,
                symbol=f"{symbol}_wf_{len(window_results)}",
            )

            window_results.append(result)
            all_trades.extend(result.trades)
            if len(result.equity_curve) > 0:
                all_equity_points.extend(result.equity_curve.tolist())

        if not window_results:
            return results

        # Calculate aggregated metrics
        results.window_results = window_results
        results.window_count = len(window_results)

        sharpes = [r.sharpe_ratio for r in window_results]
        returns = [r.total_return for r in window_results]
        win_rates = [r.win_rate for r in window_results if r.trade_count > 0]

        results.avg_sharpe = np.mean(sharpes) if sharpes else 0.0
        results.sharpe_std = np.std(sharpes) if len(sharpes) > 1 else 0.0
        results.avg_return = np.mean(returns) if returns else 0.0
        results.avg_win_rate = np.mean(win_rates) if win_rates else 0.0
        results.all_windows_profitable = all(r >= 0 for r in returns)

        # Create aggregated BacktestResults
        results.aggregated = self._aggregate_results(
            window_results=window_results,
            all_trades=all_trades,
            all_equity_points=all_equity_points,
            symbol=symbol,
        )

        return results

    def _generate_windows(self, total_bars: int) -> list[tuple[int, int, int, int]]:
        """
        Generate rolling train/test window indices.

        Returns:
            List of (train_start, train_end, test_start, test_end) tuples
        """
        windows = []
        train_bars = self.wf_config.train_bars
        test_bars = self.wf_config.test_bars
        step_bars = self.wf_config.step_bars

        start = 0
        while start + train_bars + test_bars <= total_bars:
            train_start = start
            train_end = start + train_bars
            test_start = train_end
            test_end = test_start + test_bars

            windows.append((train_start, train_end, test_start, test_end))
            start += step_bars

        return windows

    def _aggregate_results(
        self,
        window_results: list[BacktestResults],
        all_trades: list[Trade],
        all_equity_points: list[float],
        symbol: str,
    ) -> BacktestResults:
        """Aggregate results from all windows into single BacktestResults."""
        trade_count = len(all_trades)
        wins = [t for t in all_trades if t.is_winner]
        losses = [t for t in all_trades if not t.is_winner]

        win_rate = len(wins) / trade_count if trade_count > 0 else 0.0
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Equity curve
        if all_equity_points:
            equity_curve = pd.Series(all_equity_points)
            final_equity = equity_curve.iloc[-1]
            total_return = (final_equity - self.backtest_config.initial_equity) / self.backtest_config.initial_equity

            # Max drawdown
            peak = equity_curve.expanding().max()
            drawdown = (equity_curve - peak) / peak
            max_drawdown = abs(drawdown.min())

            # Sharpe
            returns = equity_curve.pct_change().dropna()
            if len(returns) > 1 and returns.std() > 0:
                sharpe_raw = (returns.mean() / returns.std()) * math.sqrt(525600)
                # Apply floor/ceiling with logging
                if sharpe_raw < SHARPE_FLOOR:
                    logger.debug(f"Walk-forward Sharpe floor hit: raw={sharpe_raw:.2f}, capped to {SHARPE_FLOOR}")
                    sharpe = SHARPE_FLOOR
                elif sharpe_raw > SHARPE_CEILING:
                    logger.debug(f"Walk-forward Sharpe ceiling hit: raw={sharpe_raw:.2f}, capped to {SHARPE_CEILING}")
                    sharpe = SHARPE_CEILING
                else:
                    sharpe = sharpe_raw
            else:
                sharpe = 0.0
        else:
            equity_curve = pd.Series([self.backtest_config.initial_equity])
            final_equity = self.backtest_config.initial_equity
            total_return = 0.0
            max_drawdown = 0.0
            sharpe = 0.0

        return BacktestResults(
            symbol=f"{symbol}_walkforward",
            trades=all_trades,
            trade_count=trade_count,
            win_count=len(wins),
            loss_count=len(losses),
            win_rate=win_rate,
            profit_factor=profit_factor,
            equity_curve=equity_curve,
            final_equity=final_equity,
            total_return=total_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            candle_count=sum(r.candle_count for r in window_results),
        )


def walk_forward_fitness(
    wf_results: WalkForwardResults,
    min_windows: int = 5,
    min_avg_sharpe: float = 0.3,
) -> tuple[float, bool, str]:
    """
    Calculate fitness score from walk-forward results.

    Rewards consistency across windows, penalizes high variance.

    Args:
        wf_results: Results from walk-forward validation
        min_windows: Minimum windows required
        min_avg_sharpe: Minimum average Sharpe for viability

    Returns:
        (score, is_valid, reason)
    """
    if wf_results.window_count < min_windows:
        return 0.0, False, f"Insufficient windows: {wf_results.window_count} < {min_windows}"

    if wf_results.avg_sharpe < min_avg_sharpe:
        return 0.0, False, f"Avg Sharpe too low: {wf_results.avg_sharpe:.2f} < {min_avg_sharpe}"

    # Score formula: avg_sharpe * consistency_multiplier
    # Consistency multiplier penalizes high standard deviation
    if wf_results.sharpe_std > 0:
        # Lower std = higher multiplier (capped at 1.0)
        consistency = max(0.5, 1.0 - wf_results.sharpe_std / wf_results.avg_sharpe)
    else:
        consistency = 1.0

    # Bonus for all windows profitable
    if wf_results.all_windows_profitable:
        consistency *= 1.1

    score = wf_results.avg_sharpe * consistency

    return score, True, "OK"
