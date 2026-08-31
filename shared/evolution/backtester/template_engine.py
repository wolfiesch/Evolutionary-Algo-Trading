"""
Template-based backtester engine.

Key improvements over MinimalBacktester:
1. Pre-computes ALL signals in one vectorized pass
2. Supports bidirectional trading (long AND short)
3. Uses ATR-based stops from template parameters
4. Much faster due to vectorized signal generation
"""
import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import pandas as pd
import numpy as np

from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    Trade,
)
from shared.evolution.templates.base import StrategyTemplate

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """Position direction."""
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Open position state."""
    side: PositionSide
    symbol: str
    entry_time: int
    entry_price: float
    position_size: float
    position_value: float
    stop_loss_price: float
    take_profit_price: Optional[float] = None
    entry_bar: int = 0


@dataclass
class TemplateBacktestConfig(BacktestConfig):
    """
    Extended backtest config for template-based backtesting.

    Inherits from BacktestConfig and adds template-specific options.
    """
    use_atr_stops: bool = True  # Use ATR-based stops from template
    use_atr_targets: bool = True  # Use ATR-based take-profits
    allow_pyramiding: bool = False  # Allow multiple positions same direction
    min_bars_in_position: int = 1  # Minimum bars before exit allowed


class TemplateBacktester:
    """
    Vectorized backtester for strategy templates.

    Key features:
    1. Pre-computes all signals once using template.generate_signals()
    2. Supports bidirectional trading (long AND short)
    3. Uses ATR-based stops/targets from template parameters
    4. Much faster than per-bar evaluation

    Usage:
        from shared.evolution.templates import CryptoStrategyTemplate
        from shared.evolution.parameters import CryptoParameters

        params = CryptoParameters(...)
        template = CryptoStrategyTemplate(params)

        config = TemplateBacktestConfig(friction_per_side=0.0025)
        backtester = TemplateBacktester(config)

        results = backtester.run(
            template=template,
            candles=sol_df,
            symbol="SOLUSDT"
        )
    """

    def __init__(self, config: TemplateBacktestConfig):
        """
        Initialize template backtester.

        Args:
            config: Backtest configuration
        """
        self.config = config

    def run(
        self,
        template: StrategyTemplate,
        candles: pd.DataFrame,
        symbol: str,
        benchmark_candles: Optional[pd.DataFrame] = None,
    ) -> BacktestResults:
        """
        Run backtest using strategy template.

        Args:
            template: Strategy template with parameters
            candles: OHLCV DataFrame for trading symbol
            symbol: Symbol name
            benchmark_candles: Optional benchmark (for extended crypto signals)

        Returns:
            BacktestResults with all metrics
        """
        # Warmup period for indicators
        warmup_period = 100

        if len(candles) < warmup_period:
            return self._empty_results(symbol, candles)

        # === VECTORIZED SIGNAL GENERATION ===
        # This is the key optimization: compute ALL signals in one pass
        signals = template.generate_signals(candles)

        # Get ATR-based stop/target distances
        if self.config.use_atr_stops:
            stop_distances = template.get_stop_loss_distance(candles)
            target_distances = template.get_take_profit_distance(candles)
        else:
            stop_distances = None
            target_distances = None

        # === SIMULATION LOOP ===
        # Now we iterate through pre-computed signals (O(n))
        equity = self.config.initial_equity
        position: Optional[Position] = None
        trades: list[Trade] = []
        equity_history: list[float] = []

        for i in range(warmup_period, len(candles)):
            current_candle = candles.iloc[i]
            current_price = current_candle['close']
            current_high = current_candle['high']
            current_low = current_candle['low']
            timestamp = self._get_timestamp(current_candle, i)

            # Get pre-computed signals for this bar
            entry_long = signals['entry_long'].iloc[i]
            exit_long = signals['exit_long'].iloc[i]
            entry_short = signals['entry_short'].iloc[i]
            exit_short = signals['exit_short'].iloc[i]

            # Mark-to-market equity
            current_equity = self._mark_to_market(equity, position, current_price)
            equity_history.append(current_equity)

            # === CHECK STOPS/TARGETS ===
            if position:
                closed, exit_reason = self._check_stops_and_targets(
                    position, current_high, current_low, current_price
                )
                if closed:
                    trade, equity = self._close_position(
                        position, closed, timestamp, exit_reason, equity
                    )
                    trades.append(trade)
                    position = None
                    continue

            # === CHECK EXIT SIGNALS ===
            if position:
                # Check minimum bars in position
                bars_held = i - position.entry_bar
                if bars_held >= self.config.min_bars_in_position:
                    if position.side == PositionSide.LONG and exit_long:
                        trade, equity = self._close_position(
                            position, current_price, timestamp, "signal", equity
                        )
                        trades.append(trade)
                        position = None

                    elif position.side == PositionSide.SHORT and exit_short:
                        trade, equity = self._close_position(
                            position, current_price, timestamp, "signal", equity
                        )
                        trades.append(trade)
                        position = None

            # === CHECK ENTRY SIGNALS ===
            if position is None:
                # Check minimum bars between trades
                if trades and self.config.min_position_interval_bars > 0:
                    last_trade = trades[-1]
                    if last_trade.exit_time:
                        # Find bar index of last exit (approximate)
                        bars_since_exit = 1  # At least 1 bar
                        if bars_since_exit < self.config.min_position_interval_bars:
                            continue

                # Get stop distance for this bar
                stop_dist = None
                target_dist = None
                if stop_distances is not None:
                    stop_dist = stop_distances.iloc[i]
                    if pd.isna(stop_dist) or stop_dist <= 0:
                        stop_dist = current_price * self.config.stop_loss_pct
                if target_distances is not None:
                    target_dist = target_distances.iloc[i]
                    if pd.isna(target_dist) or target_dist <= 0:
                        target_dist = None

                if entry_long:
                    position = self._open_position(
                        PositionSide.LONG, symbol, current_price, timestamp,
                        equity, stop_dist, target_dist, i
                    )
                    equity -= position.position_value * (1 + self.config.friction_per_side)

                elif entry_short:
                    position = self._open_position(
                        PositionSide.SHORT, symbol, current_price, timestamp,
                        equity, stop_dist, target_dist, i
                    )
                    # For shorts, we receive the value (but still pay friction)
                    equity -= position.position_value * self.config.friction_per_side

        # Close any open position at end
        if position:
            final_price = candles.iloc[-1]['close']
            final_timestamp = self._get_timestamp(candles.iloc[-1], len(candles) - 1)
            trade, equity = self._close_position(
                position, final_price, final_timestamp, "end_of_data", equity
            )
            trades.append(trade)

        equity_history.append(equity)

        # Calculate metrics
        return self._calculate_results(trades, equity_history, symbol, candles)

    def _get_timestamp(self, candle: pd.Series, idx: int) -> int:
        """Extract timestamp from candle or use index."""
        if 'timestamp' in candle.index:
            return int(candle['timestamp'])
        return idx

    def _mark_to_market(
        self,
        equity: float,
        position: Optional[Position],
        current_price: float,
    ) -> float:
        """Calculate current equity including unrealized P&L."""
        if position is None:
            return equity

        if position.side == PositionSide.LONG:
            unrealized = (current_price - position.entry_price) * position.position_size
        else:  # SHORT
            unrealized = (position.entry_price - current_price) * position.position_size

        return equity + position.position_value + unrealized

    def _check_stops_and_targets(
        self,
        position: Position,
        high: float,
        low: float,
        close: float,
    ) -> tuple[Optional[float], str]:
        """
        Check if stop-loss or take-profit was hit.

        Returns:
            Tuple of (exit_price, exit_reason) or (None, "")
        """
        if position.side == PositionSide.LONG:
            # Long: stop if low <= stop_loss, target if high >= take_profit
            if low <= position.stop_loss_price:
                return position.stop_loss_price, "stop_loss"
            if position.take_profit_price and high >= position.take_profit_price:
                return position.take_profit_price, "take_profit"

        else:  # SHORT
            # Short: stop if high >= stop_loss, target if low <= take_profit
            if high >= position.stop_loss_price:
                return position.stop_loss_price, "stop_loss"
            if position.take_profit_price and low <= position.take_profit_price:
                return position.take_profit_price, "take_profit"

        return None, ""

    def _open_position(
        self,
        side: PositionSide,
        symbol: str,
        price: float,
        timestamp: int,
        equity: float,
        stop_distance: Optional[float],
        target_distance: Optional[float],
        bar_idx: int,
    ) -> Position:
        """Open a new position."""
        # Position sizing: max_position_pct of equity
        position_value = equity * self.config.max_position_pct
        position_size = position_value / price

        # Calculate stop-loss price
        if stop_distance is None:
            stop_distance = price * self.config.stop_loss_pct

        if side == PositionSide.LONG:
            stop_loss_price = price - stop_distance
            take_profit_price = price + target_distance if target_distance else None
        else:
            stop_loss_price = price + stop_distance
            take_profit_price = price - target_distance if target_distance else None

        return Position(
            side=side,
            symbol=symbol,
            entry_time=timestamp,
            entry_price=price,
            position_size=position_size,
            position_value=position_value,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            entry_bar=bar_idx,
        )

    def _close_position(
        self,
        position: Position,
        exit_price: float,
        timestamp: int,
        reason: str,
        current_equity: float,
    ) -> tuple[Trade, float]:
        """
        Close position and calculate P&L.

        Returns:
            Tuple of (Trade, new_equity)
        """
        # Calculate P&L based on direction
        if position.side == PositionSide.LONG:
            gross_pnl = (exit_price - position.entry_price) * position.position_size
        else:  # SHORT
            gross_pnl = (position.entry_price - exit_price) * position.position_size

        # Exit friction
        exit_value = exit_price * position.position_size
        friction_cost = exit_value * self.config.friction_per_side

        # Net P&L
        net_pnl = gross_pnl - friction_cost

        # New equity
        if position.side == PositionSide.LONG:
            new_equity = current_equity + exit_value - friction_cost
        else:
            # For short: we had borrowed, now we buy back
            # P&L is already calculated, add back position value + P&L
            new_equity = current_equity + position.position_value + net_pnl

        # Create trade record
        trade = Trade(
            symbol=position.symbol,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            exit_time=timestamp,
            exit_price=exit_price,
            position_size=position.position_size,
            position_value=position.position_value,
            pnl=net_pnl,
            pnl_pct=net_pnl / position.position_value if position.position_value > 0 else 0,
            exit_reason=f"{reason}_{position.side.value}",
        )

        return trade, new_equity

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

        # Equity curve
        equity_series = pd.Series(equity_history)
        results.equity_curve = equity_series
        results.final_equity = equity_series.iloc[-1]
        results.total_return = (results.final_equity - self.config.initial_equity) / self.config.initial_equity

        # Max drawdown
        results.max_drawdown = self._calculate_max_drawdown(equity_series)

        # Sharpe ratio
        results.sharpe_ratio = self._calculate_sharpe(equity_series)

        # Timestamps
        if 'timestamp' in candles.columns:
            results.start_time = int(candles['timestamp'].iloc[0])
            results.end_time = int(candles['timestamp'].iloc[-1])

        return results

    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """Calculate maximum drawdown."""
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak
        return abs(drawdown.min())

    def _calculate_sharpe(
        self,
        equity_curve: pd.Series,
        periods_per_year: int = 525600,  # 1-minute candles
    ) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(equity_curve) < 2:
            return 0.0

        returns = equity_curve.pct_change().dropna()

        if len(returns) < 2 or returns.std() == 0:
            return 0.0

        sharpe = (returns.mean() / returns.std()) * math.sqrt(periods_per_year)

        # Cap at reasonable bounds
        return max(-10.0, min(10.0, sharpe))

    def _empty_results(self, symbol: str, candles: pd.DataFrame) -> BacktestResults:
        """Return empty results for insufficient data."""
        return BacktestResults(
            symbol=symbol,
            candle_count=len(candles),
            final_equity=self.config.initial_equity,
            equity_curve=pd.Series([self.config.initial_equity]),
        )

    def run_by_regime(
        self,
        template: StrategyTemplate,
        candles: pd.DataFrame,
        benchmark_candles: pd.DataFrame,
        symbol: str,
        window_size: int = 60,
        step_size: int = 30,
    ) -> dict[str, BacktestResults]:
        """
        Run backtests separately for each market regime.

        Args:
            template: Strategy template
            candles: OHLCV DataFrame for trading symbol
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

            if len(regime_candles) < 100:  # Need warmup
                regime_results[regime] = self._empty_results(f"{symbol}_{regime}", regime_candles)
                continue

            regime_results[regime] = self.run(
                template=template,
                candles=regime_candles,
                symbol=f"{symbol}_{regime}",
            )

        return regime_results


def create_evaluator_from_template(
    template: StrategyTemplate,
) -> "StrategyEvaluator":
    """
    Create a legacy evaluator function from a template.

    This allows templates to be used with the existing MinimalBacktester.
    The evaluator pre-computes signals and returns cached results.

    Args:
        template: Strategy template

    Returns:
        Evaluator function compatible with MinimalBacktester
    """
    # Cache for pre-computed signals
    _signal_cache = {}

    def evaluator(
        candles: pd.DataFrame,
        benchmark: pd.DataFrame,
        has_position: bool,
    ) -> str:
        # Use candle hash as cache key
        cache_key = len(candles)

        # Check if we need to recompute (new candles added)
        if cache_key not in _signal_cache:
            # Compute signals for the full window
            signals = template.generate_signals(candles)
            _signal_cache[cache_key] = signals

        signals = _signal_cache[cache_key]

        # Get signals for current bar (last bar)
        idx = -1
        entry_long = signals['entry_long'].iloc[idx]
        exit_long = signals['exit_long'].iloc[idx]

        if has_position:
            if exit_long:
                return "EXIT_LONG"
            return "HOLD"
        else:
            if entry_long:
                return "ENTRY_LONG"
            return "HOLD"

    return evaluator
