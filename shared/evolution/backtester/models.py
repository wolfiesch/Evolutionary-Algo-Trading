"""Backtest data models - asset-agnostic."""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd


@dataclass
class BacktestConfig:
    """
    Backtest configuration.

    Asset-specific values should be passed by caller (crypto or forex).
    """
    initial_equity: float = 10_000
    friction_per_side: float = 0.0025  # 0.25% default (crypto taker)
    max_position_pct: float = 0.10     # 10% max per position
    risk_per_trade: float = 0.01       # 1% risk per trade
    max_open_positions: int = 5        # Phase 2C: multi-symbol support
    max_total_exposure: float = 0.50   # 50% max total exposure
    stop_loss_pct: float = 0.03        # 3% stop-loss
    min_position_interval_bars: int = 5  # Min bars between new positions (throttle)


@dataclass
class Trade:
    """
    Single trade record.
    """
    symbol: str
    entry_time: int              # Unix timestamp ms
    entry_price: float
    exit_time: Optional[int] = None
    exit_price: Optional[float] = None
    position_size: float = 0.0   # Units of asset
    position_value: float = 0.0  # USD value at entry
    pnl: float = 0.0             # Realized P&L (after friction)
    pnl_pct: float = 0.0         # P&L as percentage
    exit_reason: str = ""        # "signal" | "stop_loss" | "end_of_data"

    @property
    def is_winner(self) -> bool:
        """Return True if trade was profitable."""
        return self.pnl > 0


@dataclass
class BacktestResults:
    """
    Complete backtest results.

    Provides all metrics needed for fitness calculation.
    """
    # Equity tracking
    equity_curve: pd.Series = field(default_factory=pd.Series)
    final_equity: float = 0.0

    # Trade statistics
    trades: list[Trade] = field(default_factory=list)
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    # Performance metrics
    total_return: float = 0.0      # (final - initial) / initial
    sharpe_ratio: float = 0.0      # Annualized
    max_drawdown: float = 0.0      # Peak-to-trough as positive decimal
    win_rate: float = 0.0          # win_count / trade_count
    profit_factor: float = 0.0     # gross_profit / gross_loss
    avg_win: float = 0.0           # Average winning trade
    avg_loss: float = 0.0          # Average losing trade

    # Metadata
    symbol: str = ""
    candle_count: int = 0
    start_time: Optional[int] = None
    end_time: Optional[int] = None

    def summary(self) -> dict:
        """Return summary dict for logging."""
        return {
            "symbol": self.symbol,
            "trade_count": self.trade_count,
            "win_rate": f"{self.win_rate:.1%}",
            "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
            "max_drawdown": f"{self.max_drawdown:.1%}",
            "total_return": f"{self.total_return:.1%}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "final_equity": f"${self.final_equity:.2f}",
        }


@dataclass
class PortfolioBacktestResults:
    """
    Portfolio-level backtest results (Phase 2C).

    Aggregates results across multiple symbols.
    """
    # Equity tracking
    equity_curve: pd.Series = field(default_factory=pd.Series)
    final_equity: float = 0.0

    # Trade statistics (aggregated)
    trades: list[Trade] = field(default_factory=list)
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    # Performance metrics (portfolio-level)
    total_return: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0

    # Per-symbol breakdown
    symbol_results: dict[str, BacktestResults] = field(default_factory=dict)

    # Metadata
    symbols: list[str] = field(default_factory=list)
    candle_count: int = 0
    start_time: Optional[int] = None
    end_time: Optional[int] = None

    def summary(self) -> dict:
        """Return summary dict for logging."""
        return {
            "symbols": self.symbols,
            "trade_count": self.trade_count,
            "win_rate": f"{self.win_rate:.1%}",
            "sharpe_ratio": f"{self.sharpe_ratio:.2f}",
            "max_drawdown": f"{self.max_drawdown:.1%}",
            "total_return": f"{self.total_return:.1%}",
            "profit_factor": f"{self.profit_factor:.2f}",
            "final_equity": f"${self.final_equity:.2f}",
        }


@dataclass
class WalkForwardConfig:
    """
    Walk-forward validation configuration (Phase 2C).

    Rolling windows for out-of-sample testing.
    """
    train_bars: int = 4320      # Training window (~3 days at 1-min)
    test_bars: int = 1440       # Test window (~1 day at 1-min)
    step_bars: int = 1440       # Step between windows (~1 day)
    min_windows: int = 5        # Minimum windows for validity


@dataclass
class WalkForwardResults:
    """Results from walk-forward validation."""
    window_results: list[BacktestResults] = field(default_factory=list)
    aggregated: Optional[BacktestResults] = None
    window_count: int = 0
    avg_sharpe: float = 0.0
    avg_return: float = 0.0
    avg_win_rate: float = 0.0
    sharpe_std: float = 0.0     # Consistency measure
    all_windows_profitable: bool = False

    def summary(self) -> dict:
        """Return summary dict for logging."""
        return {
            "window_count": self.window_count,
            "avg_sharpe": f"{self.avg_sharpe:.2f}",
            "sharpe_std": f"{self.sharpe_std:.2f}",
            "avg_return": f"{self.avg_return:.1%}",
            "avg_win_rate": f"{self.avg_win_rate:.1%}",
            "all_profitable": self.all_windows_profitable,
        }
