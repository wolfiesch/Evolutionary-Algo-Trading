"""
Shadow (paper) trading engine for equities.

Runs daily scans on the universe, evaluates strategies,
and tracks hypothetical P&L without risking real capital.
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional

import pandas as pd

from .models import (
    Position,
    TradeLog,
    Signal,
    SignalType,
    ExitReason,
    PortfolioSnapshot,
    DailySummary,
)
from .position_tracker import PositionTracker, PositionTrackerConfig

# Evaluator imports
import sys
sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks/EquitiesSwingTrading")

from evolution.backtester.evaluator import (
    Strategy,
    EquitiesEvaluator,
    FundamentalContext,
)
from engine.gene_pool.market_filter import spy_trend, vix_regime


logger = logging.getLogger(__name__)


@dataclass
class ShadowTraderConfig:
    """Configuration for shadow trader."""
    # Capital
    initial_equity: float = 100_000.0

    # Friction model (per side)
    commission_per_share: float = 0.005  # $0.005 per share (IBKR tiered)
    min_commission: float = 1.0  # $1 minimum
    slippage_pct: float = 0.0005  # 0.05% estimated slippage

    # Position sizing
    risk_per_trade: float = 0.01  # 1% risk per trade
    max_position_pct: float = 0.05  # 5% max per position
    max_open_positions: int = 20
    max_exposure_pct: float = 0.80  # 80% max total

    # Stop loss
    default_stop_loss_pct: float = 0.05  # 5% stop

    # Paths
    log_dir: Path = Path("logs")
    state_dir: Path = Path("state")


class EquitiesShadowTrader:
    """
    Paper trading engine for equities strategy validation.

    Features:
    - Daily universe scanning
    - Multi-strategy evaluation
    - Position tracking with stop losses
    - Trade logging for audit
    - P&L tracking
    """

    def __init__(
        self,
        strategies: list[Strategy],
        config: Optional[ShadowTraderConfig] = None,
    ):
        self.strategies = {s.name: s for s in strategies}
        self.config = config or ShadowTraderConfig()

        # Initialize equity
        self.equity = self.config.initial_equity
        self.initial_equity = self.config.initial_equity
        self.peak_equity = self.config.initial_equity
        self.cash = self.config.initial_equity

        # Position tracking
        tracker_config = PositionTrackerConfig(
            max_positions=self.config.max_open_positions,
            max_position_pct=self.config.max_position_pct,
            max_exposure_pct=self.config.max_exposure_pct,
            default_stop_loss_pct=self.config.default_stop_loss_pct,
        )
        self.position_tracker = PositionTracker(
            config=tracker_config,
            state_path=self.config.state_dir / "positions.json",
        )

        # Trading stats
        self.trade_count = 0
        self.winning_trades = 0
        self.losing_trades = 0

        # Daily tracking
        self.daily_start_equity = self.equity
        self.daily_entries: list[TradeLog] = []
        self.daily_exits: list[TradeLog] = []

        # Ensure directories exist
        self.config.log_dir.mkdir(parents=True, exist_ok=True)
        self.config.state_dir.mkdir(parents=True, exist_ok=True)

        # Trade log file
        self.trade_log_path = self.config.log_dir / "shadow_trades.jsonl"

    def run_daily_scan(
        self,
        trade_date: date,
        universe: list[str],
        price_data: dict[str, pd.DataFrame],  # symbol -> OHLCV
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        fundamental_data: Optional[dict[str, FundamentalContext]] = None,
    ) -> DailySummary:
        """
        Run end-of-day scan on the universe.

        Args:
            trade_date: Current trading date
            universe: List of symbols to scan
            price_data: OHLCV DataFrames for each symbol
            spy_data: SPY OHLCV data
            vix_data: VIX data
            fundamental_data: Pre-computed fundamental signals by symbol

        Returns:
            DailySummary with results
        """
        logger.info(f"Starting daily scan for {trade_date} with {len(universe)} symbols")

        # Reset daily tracking
        self.daily_start_equity = self.equity
        self.daily_entries = []
        self.daily_exits = []

        # Get market context
        spy_trend_val = spy_trend(spy_data, 20)
        vix_regime_val = vix_regime(vix_data, 10)
        market_regime = self._classify_regime(spy_data, vix_data)

        # Get current prices for P&L calculation
        current_prices = {}
        for symbol in universe:
            if symbol in price_data and len(price_data[symbol]) > 0:
                current_prices[symbol] = price_data[symbol]["close"].iloc[-1]

        # Update equity with unrealized P&L
        unrealized_pnl = self.position_tracker.get_unrealized_pnl(current_prices)
        self.equity = self.cash + self.position_tracker.get_exposure_value() + unrealized_pnl
        self.peak_equity = max(self.peak_equity, self.equity)

        # Phase 1: Check stop losses
        self._check_stop_losses(trade_date, current_prices, spy_trend_val, vix_regime_val, market_regime)

        # Phase 2: Check exit signals for open positions
        self._check_exit_signals(
            trade_date, price_data, spy_data, vix_data,
            spy_trend_val, vix_regime_val, market_regime, fundamental_data
        )

        # Phase 3: Check entry signals for new positions
        self._check_entry_signals(
            trade_date, universe, price_data, spy_data, vix_data,
            spy_trend_val, vix_regime_val, market_regime, fundamental_data
        )

        # Build summary
        summary = self._build_daily_summary(trade_date, spy_data, vix_data, market_regime)

        logger.info(
            f"Daily scan complete: {len(self.daily_entries)} entries, "
            f"{len(self.daily_exits)} exits, equity: ${self.equity:,.2f}"
        )

        return summary

    def _check_stop_losses(
        self,
        trade_date: date,
        prices: dict[str, float],
        spy_trend_val: float,
        vix_regime_val: float,
        market_regime: str,
    ) -> None:
        """Check and execute stop losses."""
        stops = self.position_tracker.get_positions_needing_stop(prices)

        for position, current_price in stops:
            self._execute_exit(
                position=position,
                trade_date=trade_date,
                current_price=current_price,
                spy_trend_val=spy_trend_val,
                vix_regime_val=vix_regime_val,
                market_regime=market_regime,
                exit_reason=ExitReason.STOP_LOSS,
            )

    def _check_exit_signals(
        self,
        trade_date: date,
        price_data: dict[str, pd.DataFrame],
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        spy_trend_val: float,
        vix_regime_val: float,
        market_regime: str,
        fundamental_data: Optional[dict[str, FundamentalContext]],
    ) -> None:
        """Check exit signals for open positions."""
        for position in list(self.position_tracker.get_all_positions()):
            symbol = position.symbol
            strategy = self.strategies.get(position.strategy_id)

            if not strategy or symbol not in price_data:
                continue

            candles = price_data[symbol]
            if len(candles) < 50:
                continue

            # Get fundamental context
            fundamental = fundamental_data.get(symbol) if fundamental_data else None

            # Create evaluator and check exit
            evaluator = EquitiesEvaluator(
                strategy=strategy,
                fundamental_context=fundamental,
                vix_candles=vix_data,
            )

            signal = evaluator.evaluate(candles, spy_data, has_position=True)

            if signal == "EXIT_LONG":
                current_price = candles["close"].iloc[-1]
                self._execute_exit(
                    position=position,
                    trade_date=trade_date,
                    current_price=current_price,
                    spy_trend_val=spy_trend_val,
                    vix_regime_val=vix_regime_val,
                    market_regime=market_regime,
                    exit_reason=ExitReason.SIGNAL,
                )

    def _check_entry_signals(
        self,
        trade_date: date,
        universe: list[str],
        price_data: dict[str, pd.DataFrame],
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        spy_trend_val: float,
        vix_regime_val: float,
        market_regime: str,
        fundamental_data: Optional[dict[str, FundamentalContext]],
    ) -> None:
        """Check entry signals for symbols not in portfolio."""
        for symbol in universe:
            # Skip if we already have a position
            if self.position_tracker.has_position(symbol):
                continue

            if symbol not in price_data:
                continue

            candles = price_data[symbol]
            if len(candles) < 50:
                continue

            # Get fundamental context
            fundamental = fundamental_data.get(symbol) if fundamental_data else None

            # Try each strategy
            for strategy_name, strategy in self.strategies.items():
                evaluator = EquitiesEvaluator(
                    strategy=strategy,
                    fundamental_context=fundamental,
                    vix_candles=vix_data,
                )

                signal = evaluator.evaluate(candles, spy_data, has_position=False)

                if signal == "ENTRY_LONG":
                    current_price = candles["close"].iloc[-1]
                    self._execute_entry(
                        symbol=symbol,
                        strategy=strategy,
                        trade_date=trade_date,
                        current_price=current_price,
                        spy_trend_val=spy_trend_val,
                        vix_regime_val=vix_regime_val,
                        market_regime=market_regime,
                        fundamental=fundamental,
                    )
                    break  # Only one position per symbol

    def _execute_entry(
        self,
        symbol: str,
        strategy: Strategy,
        trade_date: date,
        current_price: float,
        spy_trend_val: float,
        vix_regime_val: float,
        market_regime: str,
        fundamental: Optional[FundamentalContext],
    ) -> bool:
        """Execute a simulated long entry."""
        # Calculate position size
        position_value = min(
            self.equity * self.config.risk_per_trade / self.config.default_stop_loss_pct,
            self.equity * self.config.max_position_pct,
        )

        # Check if we can open
        can_open, reason = self.position_tracker.can_open_position(self.equity, position_value)
        if not can_open:
            logger.debug(f"Cannot open position for {symbol}: {reason}")
            return False

        # Calculate shares and friction
        shares = position_value / current_price
        commission = max(self.config.min_commission, shares * self.config.commission_per_share)
        slippage = position_value * self.config.slippage_pct

        # Fill price includes slippage (buy at higher price)
        fill_price = current_price * (1 + self.config.slippage_pct)

        # Calculate stop loss price
        stop_loss_price = fill_price * (1 - self.config.default_stop_loss_pct)

        # Recalculate shares at fill price
        shares = position_value / fill_price

        # Create position
        position = Position(
            symbol=symbol,
            strategy_id=strategy.name,
            entry_date=trade_date,
            entry_price=fill_price,
            shares=shares,
            notional_value=position_value,
            stop_loss_price=stop_loss_price,
            stop_loss_pct=self.config.default_stop_loss_pct,
            insider_intensity=fundamental.insider_intensity if fundamental else None,
            revenue_cagr=fundamental.revenue_cagr if fundamental else None,
        )

        # Update cash (deduct position value + commission)
        self.cash -= position_value + commission

        # Add position
        self.position_tracker.add_position(position)

        # Log trade
        trade_log = TradeLog(
            timestamp=datetime.utcnow().isoformat(),
            trade_date=trade_date.isoformat(),
            strategy_id=strategy.name,
            symbol=symbol,
            signal=SignalType.ENTRY_LONG.value,
            price_at_signal=current_price,
            simulated_fill=fill_price,
            shares=shares,
            notional_value=position_value,
            spy_trend=spy_trend_val,
            vix_regime=vix_regime_val,
            market_regime=market_regime,
            insider_intensity=fundamental.insider_intensity if fundamental else None,
            revenue_cagr=fundamental.revenue_cagr if fundamental else None,
            earnings_quality=fundamental.earnings_quality if fundamental else None,
            gene_expression=strategy.entry_long,
            commission=commission,
            slippage_estimate=slippage,
        )

        self._log_trade(trade_log)
        self.daily_entries.append(trade_log)

        logger.info(
            f"ENTRY {symbol} @ ${fill_price:.2f} "
            f"({shares:.2f} shares, ${position_value:.2f})"
        )

        return True

    def _execute_exit(
        self,
        position: Position,
        trade_date: date,
        current_price: float,
        spy_trend_val: float,
        vix_regime_val: float,
        market_regime: str,
        exit_reason: ExitReason,
    ) -> bool:
        """Execute a simulated long exit."""
        strategy = self.strategies.get(position.strategy_id)
        if not strategy:
            logger.warning(f"Strategy {position.strategy_id} not found for exit")
            return False

        # Calculate friction
        commission = max(
            self.config.min_commission,
            position.shares * self.config.commission_per_share
        )
        slippage = position.notional_value * self.config.slippage_pct

        # Fill price includes slippage (sell at lower price)
        fill_price = current_price * (1 - self.config.slippage_pct)

        # Calculate P&L
        exit_value = position.shares * fill_price
        pnl = exit_value - position.notional_value - commission
        pnl_pct = (pnl / position.notional_value) * 100

        # Update cash
        self.cash += exit_value - commission

        # Update stats
        self.trade_count += 1
        if pnl >= 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        # Remove position
        self.position_tracker.remove_position(position.symbol)

        # Days held
        days_held = position.days_held(trade_date)

        # Log trade
        trade_log = TradeLog(
            timestamp=datetime.utcnow().isoformat(),
            trade_date=trade_date.isoformat(),
            strategy_id=position.strategy_id,
            symbol=position.symbol,
            signal=SignalType.STOP_LOSS.value if exit_reason == ExitReason.STOP_LOSS else SignalType.EXIT_LONG.value,
            price_at_signal=current_price,
            simulated_fill=fill_price,
            shares=position.shares,
            notional_value=exit_value,
            spy_trend=spy_trend_val,
            vix_regime=vix_regime_val,
            market_regime=market_regime,
            insider_intensity=position.insider_intensity,
            revenue_cagr=position.revenue_cagr,
            pnl=pnl,
            pnl_pct=pnl_pct,
            days_held=days_held,
            exit_reason=exit_reason.value,
            gene_expression=strategy.exit_long,
            commission=commission,
            slippage_estimate=slippage,
        )

        self._log_trade(trade_log)
        self.daily_exits.append(trade_log)

        logger.info(
            f"EXIT {position.symbol} @ ${fill_price:.2f} "
            f"(P&L: ${pnl:.2f} / {pnl_pct:.1f}%, held {days_held}d, reason: {exit_reason.value})"
        )

        return True

    def _classify_regime(
        self,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
    ) -> str:
        """Classify current market regime."""
        if len(spy_data) < 20 or len(vix_data) < 10:
            return "unknown"

        # SPY trend over 20 days
        spy_return = spy_data["close"].iloc[-1] / spy_data["close"].iloc[-20] - 1

        # VIX level
        vix_level = vix_data["close"].iloc[-1]

        # Classify
        if abs(spy_return) < 0.02:  # < 2% move
            return "sideways"
        elif spy_return > 0:
            if vix_level < 20:
                return "bull_calm"
            else:
                return "bull_volatile"
        else:
            if vix_level < 25:
                return "bear_calm"
            else:
                return "bear_volatile"

    def _log_trade(self, trade: TradeLog) -> None:
        """Append trade to log file."""
        with open(self.trade_log_path, "a") as f:
            f.write(trade.to_json() + "\n")

    def _build_daily_summary(
        self,
        trade_date: date,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        market_regime: str,
    ) -> DailySummary:
        """Build end-of-day summary."""
        # Calculate daily P&L
        daily_pnl = self.equity - self.daily_start_equity
        daily_pnl_pct = (daily_pnl / self.daily_start_equity) * 100 if self.daily_start_equity > 0 else 0.0

        # SPY change
        spy_change_pct = 0.0
        if len(spy_data) >= 2:
            spy_change_pct = (spy_data["close"].iloc[-1] / spy_data["close"].iloc[-2] - 1) * 100

        # VIX level
        vix_level = vix_data["close"].iloc[-1] if len(vix_data) > 0 else 0.0

        # Best/worst trades
        best_trade = None
        worst_trade = None
        if self.daily_exits:
            sorted_exits = sorted(self.daily_exits, key=lambda x: x.pnl or 0, reverse=True)
            if sorted_exits[0].pnl and sorted_exits[0].pnl > 0:
                best_trade = {
                    "symbol": sorted_exits[0].symbol,
                    "pnl": sorted_exits[0].pnl,
                    "pnl_pct": sorted_exits[0].pnl_pct,
                }
            if sorted_exits[-1].pnl and sorted_exits[-1].pnl < 0:
                worst_trade = {
                    "symbol": sorted_exits[-1].symbol,
                    "pnl": sorted_exits[-1].pnl,
                    "pnl_pct": sorted_exits[-1].pnl_pct,
                }

        # New entries
        new_entries = [
            {"symbol": e.symbol, "price": e.simulated_fill, "size": e.notional_value}
            for e in self.daily_entries
        ]

        # Closed positions
        closed_positions = [
            {
                "symbol": e.symbol,
                "pnl": e.pnl,
                "pnl_pct": e.pnl_pct,
                "days_held": e.days_held,
            }
            for e in self.daily_exits
        ]

        # Count stop losses
        stop_losses = sum(1 for e in self.daily_exits if e.exit_reason == ExitReason.STOP_LOSS.value)

        return DailySummary(
            date=trade_date.isoformat(),
            starting_equity=self.daily_start_equity,
            ending_equity=self.equity,
            daily_pnl=daily_pnl,
            daily_pnl_pct=daily_pnl_pct,
            entries=len(self.daily_entries),
            exits=len(self.daily_exits),
            stop_losses=stop_losses,
            open_positions=len(self.position_tracker.positions),
            exposure_pct=self.position_tracker.get_exposure(self.equity) * 100,
            best_trade=best_trade,
            worst_trade=worst_trade,
            new_entries=new_entries,
            closed_positions=closed_positions,
            spy_change_pct=spy_change_pct,
            vix_level=vix_level,
            market_regime=market_regime,
        )

    def get_portfolio_snapshot(
        self,
        prices: dict[str, float],
        trade_date: date,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
    ) -> PortfolioSnapshot:
        """Get current portfolio state."""
        unrealized_pnl = self.position_tracker.get_unrealized_pnl(prices)
        positions_value = self.position_tracker.get_exposure_value()
        current_equity = self.cash + positions_value + unrealized_pnl

        # Calculate drawdown
        max_drawdown_pct = ((self.peak_equity - current_equity) / self.peak_equity) * 100 if self.peak_equity > 0 else 0.0

        # Market context
        spy_trend_val = spy_trend(spy_data, 20) if len(spy_data) >= 20 else 0.0
        vix_level = vix_data["close"].iloc[-1] if len(vix_data) > 0 else 0.0
        market_regime = self._classify_regime(spy_data, vix_data)

        return PortfolioSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            trade_date=trade_date.isoformat(),
            equity=current_equity,
            cash=self.cash,
            positions_value=positions_value,
            total_pnl=current_equity - self.initial_equity,
            total_pnl_pct=((current_equity / self.initial_equity) - 1) * 100,
            daily_pnl=current_equity - self.daily_start_equity,
            daily_pnl_pct=((current_equity / self.daily_start_equity) - 1) * 100 if self.daily_start_equity > 0 else 0.0,
            open_positions=len(self.position_tracker.positions),
            exposure_pct=self.position_tracker.get_exposure(current_equity) * 100,
            max_drawdown_pct=max_drawdown_pct,
            total_trades=self.trade_count,
            winning_trades=self.winning_trades,
            losing_trades=self.losing_trades,
            win_rate=self.winning_trades / self.trade_count if self.trade_count > 0 else 0.0,
            spy_trend=spy_trend_val,
            vix_level=vix_level,
            market_regime=market_regime,
        )

    @property
    def win_rate(self) -> float:
        """Win rate as fraction."""
        if self.trade_count == 0:
            return 0.0
        return self.winning_trades / self.trade_count

    @property
    def total_pnl(self) -> float:
        """Total P&L in dollars."""
        return self.equity - self.initial_equity

    @property
    def total_pnl_pct(self) -> float:
        """Total P&L as percentage."""
        return ((self.equity / self.initial_equity) - 1) * 100

    @property
    def max_drawdown_pct(self) -> float:
        """Maximum drawdown percentage."""
        if self.peak_equity <= 0:
            return 0.0
        return ((self.peak_equity - self.equity) / self.peak_equity) * 100
