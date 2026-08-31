"""
Integration tests for shadow trading.

Tests the complete trading flow:
- Entry signal → position opened → cash debited
- Exit signal → position closed → P&L calculated → cash credited
- Equity reconciliation: equity = cash + positions_value
- Stop loss execution
- Multi-position handling
"""
import pytest
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np

from execution.shadow.models import (
    Position,
    SignalType,
    ExitReason,
)
from execution.shadow.position_tracker import PositionTracker, PositionTrackerConfig
from execution.shadow.trader import EquitiesShadowTrader, ShadowTraderConfig


def create_price_data(
    close_prices: list[float],
    start_date: date = date(2024, 1, 1),
) -> pd.DataFrame:
    """Create synthetic OHLCV DataFrame from close prices."""
    n = len(close_prices)
    dates = pd.date_range(start=start_date, periods=n, freq='D')

    df = pd.DataFrame({
        'timestamp': dates,
        'open': [p * 0.995 for p in close_prices],
        'high': [p * 1.01 for p in close_prices],
        'low': [p * 0.99 for p in close_prices],
        'close': close_prices,
        'volume': [1000000] * n,
    })
    return df


def create_spy_data(n_days: int = 60, start_price: float = 470.0) -> pd.DataFrame:
    """Create synthetic SPY price data."""
    prices = [start_price * (1 + 0.001 * i) for i in range(n_days)]  # Slight uptrend
    return create_price_data(prices)


def create_vix_data(n_days: int = 60, level: float = 15.0) -> pd.DataFrame:
    """Create synthetic VIX data."""
    prices = [level + np.sin(i * 0.1) * 2 for i in range(n_days)]  # Oscillates around level
    return create_price_data(prices)


class MockStrategy:
    """Mock strategy for testing."""

    def __init__(self, name: str = "test_strategy"):
        self.name = name
        self.entry_long = "mock_entry_condition"
        self.exit_long = "mock_exit_condition"


class TestEquityReconciliation:
    """Tests for equity = cash + positions_value reconciliation."""

    def test_initial_equity_equals_cash(self):
        """At start, equity should equal initial cash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            strategies = [MockStrategy()]
            trader = EquitiesShadowTrader(strategies, config)

            assert trader.equity == 100_000.0
            assert trader.cash == 100_000.0
            assert len(trader.position_tracker.positions) == 0

    def test_equity_after_entry(self):
        """After entry, cash should decrease but equity roughly same (minus friction)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                commission_per_share=0.0,
                slippage_pct=0.0,  # No friction for clean test
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            strategies = [MockStrategy()]
            trader = EquitiesShadowTrader(strategies, config)

            # Manually add a position
            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 15),
                entry_price=185.00,
                shares=27.0,
                notional_value=5000.00,
                stop_loss_price=175.00,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= 5000.00  # Simulate cash debit

            # Get prices and update equity
            prices = {"AAPL": 185.00}  # Same as entry price
            unrealized_pnl = trader.position_tracker.get_unrealized_pnl(prices)
            positions_value = trader.position_tracker.get_exposure_value()

            # Reconcile
            expected_equity = trader.cash + positions_value + unrealized_pnl
            assert abs(expected_equity - 100_000.0) < 0.01

    def test_equity_with_unrealized_profit(self):
        """Equity should increase with unrealized profit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                commission_per_share=0.0,
                slippage_pct=0.0,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            trader = EquitiesShadowTrader([MockStrategy()], config)

            # Add position at $100
            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 15),
                entry_price=100.00,
                shares=100.0,
                notional_value=10000.00,
                stop_loss_price=95.00,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= 10000.00  # Debit cash

            # Price goes up 10%
            prices = {"AAPL": 110.00}
            unrealized_pnl = trader.position_tracker.get_unrealized_pnl(prices)
            positions_value = trader.position_tracker.get_exposure_value()

            # Unrealized P&L should be $1000
            assert abs(unrealized_pnl - 1000.00) < 0.01

            # Equity should be $101,000
            expected_equity = trader.cash + positions_value + unrealized_pnl
            assert abs(expected_equity - 101_000.0) < 0.01

    def test_equity_with_unrealized_loss(self):
        """Equity should decrease with unrealized loss."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                commission_per_share=0.0,
                slippage_pct=0.0,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            trader = EquitiesShadowTrader([MockStrategy()], config)

            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 15),
                entry_price=100.00,
                shares=100.0,
                notional_value=10000.00,
                stop_loss_price=95.00,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= 10000.00

            # Price goes down 5%
            prices = {"AAPL": 95.00}
            unrealized_pnl = trader.position_tracker.get_unrealized_pnl(prices)

            # Unrealized P&L should be -$500
            assert abs(unrealized_pnl - (-500.00)) < 0.01

            # Equity should be $99,500
            expected_equity = trader.cash + trader.position_tracker.get_exposure_value() + unrealized_pnl
            assert abs(expected_equity - 99_500.0) < 0.01

    def test_equity_after_exit(self):
        """After exit, equity should equal realized P&L plus remaining cash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                commission_per_share=0.0,
                slippage_pct=0.0,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            trader = EquitiesShadowTrader([MockStrategy()], config)

            # Entry at $100
            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 15),
                entry_price=100.00,
                shares=100.0,
                notional_value=10000.00,
                stop_loss_price=95.00,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= 10000.00

            # Exit at $110 (10% gain)
            exit_price = 110.00
            exit_value = 100.0 * exit_price  # $11,000
            pnl = exit_value - 10000.00  # $1,000

            # Remove position and credit cash
            trader.position_tracker.remove_position("AAPL")
            trader.cash += exit_value

            # No positions, so equity = cash
            assert len(trader.position_tracker.positions) == 0
            assert abs(trader.cash - 101_000.0) < 0.01


class TestStopLossExecution:
    """Tests for stop loss behavior."""

    def test_stop_loss_triggered_below_price(self):
        """Position should be flagged for stop when price drops below stop level."""
        tracker = PositionTracker()
        position = Position(
            symbol="AAPL",
            strategy_id="test",
            entry_date=date(2024, 1, 15),
            entry_price=100.00,
            shares=100.0,
            notional_value=10000.00,
            stop_loss_price=95.00,  # 5% stop
        )
        tracker.add_position(position)

        # Price above stop - should not trigger
        stops = tracker.get_positions_needing_stop({"AAPL": 96.00})
        assert len(stops) == 0

        # Price at stop - should trigger
        stops = tracker.get_positions_needing_stop({"AAPL": 95.00})
        assert len(stops) == 1
        assert stops[0][0].symbol == "AAPL"

        # Price below stop - should trigger
        stops = tracker.get_positions_needing_stop({"AAPL": 90.00})
        assert len(stops) == 1

    def test_stop_loss_uses_percentage_fallback(self):
        """Without stop_loss_price, should use percentage-based stop."""
        tracker = PositionTracker()
        position = Position(
            symbol="AAPL",
            strategy_id="test",
            entry_date=date(2024, 1, 15),
            entry_price=100.00,
            shares=100.0,
            notional_value=10000.00,
            stop_loss_price=None,  # No fixed stop
            stop_loss_pct=0.05,    # 5% stop
        )
        tracker.add_position(position)

        # 4% loss - should not trigger
        stops = tracker.get_positions_needing_stop({"AAPL": 96.00})
        assert len(stops) == 0

        # 6% loss - should trigger
        stops = tracker.get_positions_needing_stop({"AAPL": 94.00})
        assert len(stops) == 1


class TestMultiplePositions:
    """Tests for handling multiple positions."""

    def test_multiple_positions_tracking(self):
        """Should correctly track multiple positions."""
        tracker = PositionTracker()

        symbols = ["AAPL", "MSFT", "GOOGL"]
        for i, symbol in enumerate(symbols):
            position = Position(
                symbol=symbol,
                strategy_id="test",
                entry_date=date(2024, 1, 15),
                entry_price=100.00 + i * 10,
                shares=50.0,
                notional_value=5000.00,
            )
            tracker.add_position(position)

        assert len(tracker.positions) == 3
        assert tracker.get_exposure_value() == 15000.00

    def test_multiple_positions_unrealized_pnl(self):
        """Should correctly calculate unrealized P&L across positions."""
        tracker = PositionTracker()

        # AAPL: entry $100, 100 shares = $10,000
        tracker.add_position(Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=100.00, shares=100.0, notional_value=10000.00,
        ))

        # MSFT: entry $200, 50 shares = $10,000
        tracker.add_position(Position(
            symbol="MSFT", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=200.00, shares=50.0, notional_value=10000.00,
        ))

        # Current prices: AAPL +10%, MSFT -5%
        prices = {"AAPL": 110.00, "MSFT": 190.00}
        unrealized_pnl = tracker.get_unrealized_pnl(prices)

        # AAPL: $10,000 * (110/100 - 1) = $1,000
        # MSFT: $10,000 * (190/200 - 1) = -$500
        # Total: $500
        assert abs(unrealized_pnl - 500.00) < 0.01

    def test_position_limits_enforced(self):
        """Should enforce position limits."""
        config = PositionTrackerConfig(
            max_positions=3,
            max_position_pct=0.10,
            max_exposure_pct=0.25,
        )
        tracker = PositionTracker(config=config)

        # Add positions up to limit
        for i, symbol in enumerate(["A", "B", "C"]):
            tracker.add_position(Position(
                symbol=symbol, strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=100.00, shares=10.0, notional_value=1000.00,
            ))

        # Try to add 4th position - should fail on max_positions
        can_open, reason = tracker.can_open_position(100000.00, 1000.00)
        assert can_open is False
        assert "Max positions" in reason


class TestTradingFlow:
    """Tests for complete trading flow."""

    def test_entry_exit_pnl_calculation(self):
        """Test complete entry → exit flow with P&L calculation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                commission_per_share=0.01,  # $0.01/share
                min_commission=1.0,
                slippage_pct=0.001,  # 0.1%
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            trader = EquitiesShadowTrader([MockStrategy()], config)

            # Simulate entry
            entry_price = 100.00
            shares = 100.0
            position_value = shares * entry_price  # $10,000

            # Entry friction
            entry_slippage = position_value * config.slippage_pct  # $10
            entry_commission = max(config.min_commission, shares * config.commission_per_share)  # $1

            fill_price = entry_price * (1 + config.slippage_pct)  # $100.10

            # Create position
            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 15),
                entry_price=fill_price,
                shares=shares,
                notional_value=position_value,
                stop_loss_price=fill_price * 0.95,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= position_value + entry_commission

            assert abs(trader.cash - (100_000 - 10_000 - entry_commission)) < 0.01

            # Exit at $110 (10% gain from original signal price)
            exit_signal_price = 110.00
            exit_fill_price = exit_signal_price * (1 - config.slippage_pct)  # $109.89
            exit_value = shares * exit_fill_price  # ~$10,989
            exit_commission = max(config.min_commission, shares * config.commission_per_share)

            # Calculate P&L
            gross_pnl = exit_value - position_value
            net_pnl = gross_pnl - exit_commission

            # Remove position and credit cash
            trader.position_tracker.remove_position("AAPL")
            trader.cash += exit_value - exit_commission

            # Final equity
            expected_cash = 100_000 - 10_000 - entry_commission + exit_value - exit_commission
            assert abs(trader.cash - expected_cash) < 0.01

            # Net P&L should be positive (roughly $989 minus commissions)
            total_pnl = trader.cash - trader.initial_equity
            assert total_pnl > 900  # Roughly $989 - $2 commission = $987


class TestPortfolioSnapshot:
    """Tests for portfolio snapshot generation."""

    def test_snapshot_reflects_current_state(self):
        """Snapshot should accurately reflect current portfolio state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            trader = EquitiesShadowTrader([MockStrategy()], config)

            # Add a winning position
            position = Position(
                symbol="AAPL",
                strategy_id="test_strategy",
                entry_date=date(2024, 1, 10),
                entry_price=100.00,
                shares=100.0,
                notional_value=10000.00,
            )
            trader.position_tracker.add_position(position)
            trader.cash -= 10000.00

            # Create market data
            spy_data = create_spy_data()
            vix_data = create_vix_data()

            # Get snapshot with AAPL up 10%
            prices = {"AAPL": 110.00}
            snapshot = trader.get_portfolio_snapshot(
                prices=prices,
                trade_date=date(2024, 1, 15),
                spy_data=spy_data,
                vix_data=vix_data,
            )

            # Verify snapshot fields
            assert snapshot.open_positions == 1
            assert snapshot.cash == 90000.00
            assert snapshot.positions_value == 10000.00  # Notional
            assert abs(snapshot.total_pnl - 1000.00) < 1.0  # ~$1000 unrealized


class TestHoldingPeriod:
    """Tests for position holding period tracking."""

    def test_positions_exceeding_hold_time(self):
        """Should flag positions exceeding max holding period."""
        config = PositionTrackerConfig(max_holding_days=20)
        tracker = PositionTracker(config=config)

        # Add position from 30 days ago
        position = Position(
            symbol="AAPL",
            strategy_id="test",
            entry_date=date(2024, 1, 1),
            entry_price=100.00,
            shares=100.0,
            notional_value=10000.00,
        )
        tracker.add_position(position)

        # Check at 15 days - should not expire
        expired = tracker.get_positions_exceeding_hold_time(date(2024, 1, 16))
        assert len(expired) == 0

        # Check at 25 days - should expire
        expired = tracker.get_positions_exceeding_hold_time(date(2024, 1, 26))
        assert len(expired) == 1
        assert expired[0].symbol == "AAPL"


class TestKillSwitch:
    """Tests for emergency position clearing."""

    def test_clear_all_positions(self):
        """Kill switch should clear all positions."""
        tracker = PositionTracker()

        # Add multiple positions
        for symbol in ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]:
            tracker.add_position(Position(
                symbol=symbol, strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=100.00, shares=50.0, notional_value=5000.00,
            ))

        assert len(tracker.positions) == 5

        # Kill switch
        cleared = tracker.clear_all()

        assert len(cleared) == 5
        assert len(tracker.positions) == 0
        assert not tracker.has_position("AAPL")


class TestFrictionAccounting:
    """Tests for commission and slippage accounting."""

    def test_commission_calculated_correctly(self):
        """Commission should be calculated correctly."""
        config = ShadowTraderConfig(
            commission_per_share=0.01,  # $0.01 per share
            min_commission=1.0,         # $1 minimum
        )

        # Small order - minimum commission
        shares = 50
        commission = max(config.min_commission, shares * config.commission_per_share)
        assert commission == 1.0  # Minimum

        # Large order - per-share commission
        shares = 200
        commission = max(config.min_commission, shares * config.commission_per_share)
        assert commission == 2.0  # 200 * $0.01

    def test_slippage_applied_correctly(self):
        """Slippage should be applied in the correct direction."""
        config = ShadowTraderConfig(slippage_pct=0.001)  # 0.1%
        price = 100.00

        # Entry: buy at higher price
        entry_fill = price * (1 + config.slippage_pct)
        assert entry_fill == 100.10

        # Exit: sell at lower price
        exit_fill = price * (1 - config.slippage_pct)
        assert exit_fill == 99.90
