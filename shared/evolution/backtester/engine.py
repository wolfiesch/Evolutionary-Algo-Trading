"""
Minimal backtester engine - asset-agnostic.

Phase 2A: Single symbol, basic metrics.
"""
import math
from typing import Callable, Optional
import pandas as pd
import numpy as np

from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    Trade,
)


# Type alias for strategy evaluation function
# signature: (candles_df, benchmark_df, has_position) -> signal_str
StrategyEvaluator = Callable[[pd.DataFrame, pd.DataFrame, bool], str]


class MinimalBacktester:
    """
    Minimal vectorized backtester for single-symbol strategy evaluation.

    This is a Phase 2A implementation - single symbol, basic metrics.
    Phase 2C will add multi-symbol portfolio backtesting.

    Usage:
        config = BacktestConfig(friction_per_side=0.0025)
        backtester = MinimalBacktester(config)

        results = backtester.run(
            evaluator=my_evaluator_fn,
            candles=sol_df,
            benchmark_candles=btc_df,
            symbol="SOLUSDT"
        )
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize backtester with configuration.

        Args:
            config: BacktestConfig with friction, position sizing, etc.
        """
        self.config = config

    def run(
        self,
        evaluator: StrategyEvaluator,
        candles: pd.DataFrame,
        benchmark_candles: pd.DataFrame,
        symbol: str,
    ) -> BacktestResults:
        """
        Run backtest on historical data.

        Args:
            evaluator: Function that evaluates strategy signals.
                       Takes (candles_df, benchmark_df, has_position) -> "ENTRY_LONG"|"EXIT_LONG"|"HOLD"
            candles: OHLCV DataFrame for the trading symbol (oldest first)
            benchmark_candles: OHLCV DataFrame for benchmark (BTC for crypto)
            symbol: Symbol name for logging

        Returns:
            BacktestResults with all metrics calculated
        """
        # Initialize state
        equity = self.config.initial_equity
        position: Optional[Trade] = None
        trades: list[Trade] = []
        equity_history: list[float] = []

        # We need at least 60 candles for indicators (reduced for testing)
        # [*TO-DO*] - Increase to 100+ when more data is available
        warmup_period = 60

        if len(candles) < warmup_period:
            return self._empty_results(symbol)

        # Simulate through candles
        for i in range(warmup_period, len(candles)):
            # Get historical window for indicator calculation
            window_candles = candles.iloc[:i+1].copy()
            window_benchmark = benchmark_candles.iloc[:min(i+1, len(benchmark_candles))].copy()

            current_candle = candles.iloc[i]
            current_price = current_candle['close']
            timestamp = int(current_candle.get('timestamp', i))

            # Track equity (mark-to-market if in position)
            if position:
                unrealized_pnl = (current_price - position.entry_price) * position.position_size
                current_equity = equity + unrealized_pnl
            else:
                current_equity = equity

            equity_history.append(current_equity)

            # Check stop-loss if in position
            if position:
                loss_pct = (current_price - position.entry_price) / position.entry_price
                if loss_pct <= -self.config.stop_loss_pct:
                    # Stop-loss triggered
                    position = self._close_position(
                        position, current_price, timestamp, "stop_loss"
                    )
                    equity += position.pnl
                    trades.append(position)
                    position = None
                    continue

            # Get signal from strategy
            has_position = position is not None
            try:
                signal = evaluator(window_candles, window_benchmark, has_position)
            except Exception:
                signal = "HOLD"

            # Execute signal
            if signal == "EXIT_LONG" and position:
                position = self._close_position(
                    position, current_price, timestamp, "signal"
                )
                equity += position.pnl
                trades.append(position)
                position = None

            elif signal == "ENTRY_LONG" and not position:
                position = self._open_position(
                    symbol, current_price, timestamp, equity
                )

        # Close any open position at end
        if position:
            final_price = candles.iloc[-1]['close']
            final_timestamp = int(candles.iloc[-1].get('timestamp', len(candles)))
            position = self._close_position(
                position, final_price, final_timestamp, "end_of_data"
            )
            equity += position.pnl
            trades.append(position)

        equity_history.append(equity)

        # Calculate metrics
        return self._calculate_results(
            trades=trades,
            equity_history=equity_history,
            symbol=symbol,
            candles=candles,
        )

    def _open_position(
        self,
        symbol: str,
        price: float,
        timestamp: int,
        equity: float,
    ) -> Trade:
        """Open a new long position."""
        # Position size: max_position_pct of equity
        position_value = equity * self.config.max_position_pct
        position_size = position_value / price

        # Apply entry friction
        friction_cost = position_value * self.config.friction_per_side
        position_value -= friction_cost

        return Trade(
            symbol=symbol,
            entry_time=timestamp,
            entry_price=price,
            position_size=position_size,
            position_value=position_value,
        )

    def _close_position(
        self,
        position: Trade,
        exit_price: float,
        timestamp: int,
        reason: str,
    ) -> Trade:
        """Close an existing position and calculate P&L."""
        # Calculate gross P&L
        gross_pnl = (exit_price - position.entry_price) * position.position_size

        # Apply exit friction
        exit_value = exit_price * position.position_size
        friction_cost = exit_value * self.config.friction_per_side

        # Net P&L after both entry and exit friction
        net_pnl = gross_pnl - friction_cost

        position.exit_time = timestamp
        position.exit_price = exit_price
        position.pnl = net_pnl
        position.pnl_pct = net_pnl / position.position_value if position.position_value > 0 else 0
        position.exit_reason = reason

        return position

    def _calculate_results(
        self,
        trades: list[Trade],
        equity_history: list[float],
        symbol: str,
        candles: pd.DataFrame,
    ) -> BacktestResults:
        """Calculate all backtest metrics."""
        results = BacktestResults(
            symbol=symbol,
            candle_count=len(candles),
            trades=trades,
            trade_count=len(trades),
        )

        if not trades:
            results.equity_curve = pd.Series(equity_history)
            results.final_equity = equity_history[-1] if equity_history else self.config.initial_equity
            return results

        # Win/loss stats
        wins = [t for t in trades if t.is_winner]
        losses = [t for t in trades if not t.is_winner]
        results.win_count = len(wins)
        results.loss_count = len(losses)
        results.win_rate = results.win_count / results.trade_count if results.trade_count > 0 else 0

        # Average win/loss
        if wins:
            results.avg_win = sum(t.pnl for t in wins) / len(wins)
        if losses:
            results.avg_loss = sum(t.pnl for t in losses) / len(losses)

        # Profit factor
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        results.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Equity curve and returns
        equity_series = pd.Series(equity_history)
        results.equity_curve = equity_series
        results.final_equity = equity_series.iloc[-1]
        results.total_return = (results.final_equity - self.config.initial_equity) / self.config.initial_equity

        # Max drawdown
        results.max_drawdown = self._calculate_max_drawdown(equity_series)

        # Sharpe ratio (annualized)
        results.sharpe_ratio = self._calculate_sharpe(equity_series)

        # Timestamps
        if 'timestamp' in candles.columns:
            results.start_time = int(candles['timestamp'].iloc[0])
            results.end_time = int(candles['timestamp'].iloc[-1])

        return results

    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """
        Calculate maximum drawdown from equity curve.

        Returns positive decimal (0.15 = 15% drawdown).
        """
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak

        return abs(drawdown.min())

    def _calculate_sharpe(
        self,
        equity_curve: pd.Series,
        periods_per_year: int = 525600,  # 1-minute candles in a year
    ) -> float:
        """
        Calculate annualized Sharpe ratio.

        Assumes risk-free rate = 0 for simplicity.

        Args:
            equity_curve: Series of equity values
            periods_per_year: Number of periods in a year (525600 for 1-min candles)

        Returns:
            Annualized Sharpe ratio
        """
        if len(equity_curve) < 2:
            return 0.0

        # Calculate returns
        returns = equity_curve.pct_change().dropna()

        if len(returns) < 2 or returns.std() == 0:
            return 0.0

        # Sharpe = mean(returns) / std(returns) * sqrt(periods_per_year)
        sharpe = (returns.mean() / returns.std()) * math.sqrt(periods_per_year)

        # Cap at reasonable bounds
        return max(-10.0, min(10.0, sharpe))

    def _empty_results(self, symbol: str) -> BacktestResults:
        """Return empty results for insufficient data."""
        return BacktestResults(
            symbol=symbol,
            final_equity=self.config.initial_equity,
            equity_curve=pd.Series([self.config.initial_equity]),
        )

    def run_by_regime(
        self,
        evaluator: StrategyEvaluator,
        candles: pd.DataFrame,
        benchmark_candles: pd.DataFrame,
        symbol: str,
        window_size: int = 60,
        step_size: int = 30,
    ) -> dict[str, BacktestResults]:
        """
        Run backtests separately for each market regime.

        This splits the data by regime, then runs the backtester on each
        regime's data independently.

        Args:
            evaluator: Strategy evaluation function
            candles: OHLCV DataFrame for the trading symbol
            benchmark_candles: OHLCV DataFrame for benchmark
            symbol: Symbol name
            window_size: Regime classification window size
            step_size: Regime classification step size

        Returns:
            Dict mapping regime name to BacktestResults
        """
        from shared.evolution.fitness.regime_classifier import (
            split_by_regime,
            REGIME_NAMES,
        )

        # Split data by regime
        split_result = split_by_regime(
            candles=candles,
            benchmark_candles=benchmark_candles,
            window_size=window_size,
            step_size=step_size,
        )

        # Run backtest for each regime
        regime_results: dict[str, BacktestResults] = {}

        for regime in REGIME_NAMES:
            regime_candles = split_result.candles_by_regime.get(regime, pd.DataFrame())
            regime_benchmark = split_result.benchmark_by_regime.get(regime, pd.DataFrame())

            if len(regime_candles) < 60:  # Need warmup period
                # Return empty results for this regime
                regime_results[regime] = self._empty_results(f"{symbol}_{regime}")
                continue

            # Run backtest on this regime's data
            regime_results[regime] = self.run(
                evaluator=evaluator,
                candles=regime_candles,
                benchmark_candles=regime_benchmark,
                symbol=f"{symbol}_{regime}",
            )

        return regime_results
