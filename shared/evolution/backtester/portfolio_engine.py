"""
Portfolio backtester engine - Phase 2C.

Multi-symbol backtesting with position limits and risk management.
"""
import math
from typing import Callable, Optional
import pandas as pd
import numpy as np

from shared.evolution.backtester.models import (
    BacktestConfig,
    BacktestResults,
    PortfolioBacktestResults,
    Trade,
)


# Type alias for strategy evaluation function
# signature: (symbol, candles_df, benchmark_df, has_position) -> signal_str
PortfolioEvaluator = Callable[[str, pd.DataFrame, pd.DataFrame, bool], str]


class PortfolioBacktester:
    """
    Multi-symbol portfolio backtester with risk management.

    Phase 2C implementation supporting:
    - Multiple symbols with independent positions
    - Max open positions limit
    - Total exposure limit
    - Position throttling (min interval between new positions)

    Usage:
        config = BacktestConfig(max_open_positions=5, max_total_exposure=0.50)
        backtester = PortfolioBacktester(config)

        results = backtester.run(
            evaluator=my_evaluator_fn,
            candles={"SOLUSDT": sol_df, "ETHUSDT": eth_df},
            benchmark_candles=btc_df,
        )
    """

    def __init__(self, config: BacktestConfig):
        """
        Initialize backtester with configuration.

        Args:
            config: BacktestConfig with position limits, exposure caps, etc.
        """
        self.config = config

    def run(
        self,
        evaluator: PortfolioEvaluator,
        candles: dict[str, pd.DataFrame],
        benchmark_candles: pd.DataFrame,
    ) -> PortfolioBacktestResults:
        """
        Run portfolio backtest on historical data.

        Args:
            evaluator: Function that evaluates strategy signals per symbol.
                       Takes (symbol, candles_df, benchmark_df, has_position) -> signal
            candles: Dict of symbol -> OHLCV DataFrame (oldest first)
            benchmark_candles: OHLCV DataFrame for benchmark (BTC for crypto)

        Returns:
            PortfolioBacktestResults with all metrics
        """
        symbols = list(candles.keys())
        if not symbols:
            return self._empty_results([])

        # Align all dataframes to common timestamps
        aligned_candles, aligned_benchmark = self._align_data(candles, benchmark_candles)
        if len(aligned_benchmark) < 60:
            return self._empty_results(symbols)

        # Initialize state
        equity = self.config.initial_equity
        positions: dict[str, Trade] = {}  # symbol -> open position
        all_trades: list[Trade] = []
        equity_history: list[float] = []
        bars_since_last_entry = 999  # Allow immediate entry at start

        warmup_period = 60

        # Get aligned length (minimum across all)
        aligned_length = min(len(aligned_benchmark), min(len(df) for df in aligned_candles.values()))

        # Simulate through candles
        for i in range(warmup_period, aligned_length):
            # Get historical windows for all symbols
            window_benchmark = aligned_benchmark.iloc[:i+1].copy()

            # Calculate current portfolio value (mark-to-market)
            portfolio_value = equity
            for sym, pos in positions.items():
                if sym in aligned_candles:
                    current_price = aligned_candles[sym].iloc[i]['close']
                    unrealized_pnl = (current_price - pos.entry_price) * pos.position_size
                    portfolio_value += unrealized_pnl

            equity_history.append(portfolio_value)
            bars_since_last_entry += 1

            # Check stop-losses for all positions
            symbols_to_close = []
            for sym, pos in positions.items():
                if sym not in aligned_candles:
                    continue
                current_price = aligned_candles[sym].iloc[i]['close']
                loss_pct = (current_price - pos.entry_price) / pos.entry_price
                if loss_pct <= -self.config.stop_loss_pct:
                    # Stop-loss triggered
                    timestamp = int(aligned_candles[sym].iloc[i].get('timestamp', i))
                    closed = self._close_position(pos, current_price, timestamp, "stop_loss")
                    equity += closed.pnl
                    all_trades.append(closed)
                    symbols_to_close.append(sym)

            for sym in symbols_to_close:
                del positions[sym]

            # Calculate current exposure
            total_exposure = sum(
                pos.position_value / self.config.initial_equity
                for pos in positions.values()
            )

            # Process each symbol
            for sym in symbols:
                if sym not in aligned_candles:
                    continue

                window_candles = aligned_candles[sym].iloc[:i+1].copy()
                current_candle = aligned_candles[sym].iloc[i]
                current_price = current_candle['close']
                timestamp = int(current_candle.get('timestamp', i))

                has_position = sym in positions

                # Get signal from strategy
                try:
                    signal = evaluator(sym, window_candles, window_benchmark, has_position)
                except Exception:
                    signal = "HOLD"

                # Execute signal
                if signal == "EXIT_LONG" and has_position:
                    pos = positions[sym]
                    closed = self._close_position(pos, current_price, timestamp, "signal")
                    equity += closed.pnl
                    all_trades.append(closed)
                    del positions[sym]

                elif signal == "ENTRY_LONG" and not has_position:
                    # Check position limits
                    can_enter = (
                        len(positions) < self.config.max_open_positions
                        and total_exposure < self.config.max_total_exposure
                        and bars_since_last_entry >= self.config.min_position_interval_bars
                    )

                    if can_enter:
                        pos = self._open_position(sym, current_price, timestamp, equity)
                        positions[sym] = pos
                        bars_since_last_entry = 0
                        total_exposure += pos.position_value / self.config.initial_equity

        # Close all open positions at end
        for sym, pos in positions.items():
            if sym in aligned_candles:
                final_price = aligned_candles[sym].iloc[-1]['close']
                final_timestamp = int(aligned_candles[sym].iloc[-1].get('timestamp', aligned_length))
                closed = self._close_position(pos, final_price, final_timestamp, "end_of_data")
                equity += closed.pnl
                all_trades.append(closed)

        equity_history.append(equity)

        # Calculate metrics
        return self._calculate_results(
            trades=all_trades,
            equity_history=equity_history,
            symbols=symbols,
            aligned_candles=aligned_candles,
        )

    def _align_data(
        self,
        candles: dict[str, pd.DataFrame],
        benchmark_candles: pd.DataFrame,
    ) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
        """
        Align all dataframes to common length.

        Simple approach: truncate to minimum length.
        More sophisticated timestamp alignment can be added later.
        """
        min_length = len(benchmark_candles)
        for df in candles.values():
            min_length = min(min_length, len(df))

        aligned_candles = {
            sym: df.iloc[-min_length:].reset_index(drop=True)
            for sym, df in candles.items()
        }
        aligned_benchmark = benchmark_candles.iloc[-min_length:].reset_index(drop=True)

        return aligned_candles, aligned_benchmark

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
        symbols: list[str],
        aligned_candles: dict[str, pd.DataFrame],
    ) -> PortfolioBacktestResults:
        """Calculate all portfolio backtest metrics."""
        results = PortfolioBacktestResults(
            symbols=symbols,
            candle_count=sum(len(df) for df in aligned_candles.values()),
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

        # Per-symbol breakdown
        for sym in symbols:
            sym_trades = [t for t in trades if t.symbol == sym]
            if sym_trades:
                sym_wins = [t for t in sym_trades if t.is_winner]
                sym_losses = [t for t in sym_trades if not t.is_winner]
                results.symbol_results[sym] = BacktestResults(
                    symbol=sym,
                    trades=sym_trades,
                    trade_count=len(sym_trades),
                    win_count=len(sym_wins),
                    loss_count=len(sym_losses),
                    win_rate=len(sym_wins) / len(sym_trades) if sym_trades else 0,
                )

        # Timestamps
        if aligned_candles:
            first_sym = list(aligned_candles.keys())[0]
            if 'timestamp' in aligned_candles[first_sym].columns:
                results.start_time = int(aligned_candles[first_sym]['timestamp'].iloc[0])
                results.end_time = int(aligned_candles[first_sym]['timestamp'].iloc[-1])

        return results

    def _calculate_max_drawdown(self, equity_curve: pd.Series) -> float:
        """Calculate maximum drawdown from equity curve."""
        if len(equity_curve) < 2:
            return 0.0

        peak = equity_curve.expanding().max()
        drawdown = (equity_curve - peak) / peak

        return abs(drawdown.min())

    def _calculate_sharpe(
        self,
        equity_curve: pd.Series,
        periods_per_year: int = 525600,
    ) -> float:
        """Calculate annualized Sharpe ratio."""
        if len(equity_curve) < 2:
            return 0.0

        returns = equity_curve.pct_change().dropna()

        if len(returns) < 2 or returns.std() == 0:
            return 0.0

        sharpe = (returns.mean() / returns.std()) * math.sqrt(periods_per_year)

        return max(-10.0, min(10.0, sharpe))

    def _empty_results(self, symbols: list[str]) -> PortfolioBacktestResults:
        """Return empty results for insufficient data."""
        return PortfolioBacktestResults(
            symbols=symbols,
            final_equity=self.config.initial_equity,
            equity_curve=pd.Series([self.config.initial_equity]),
        )
