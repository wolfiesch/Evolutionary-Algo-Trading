"""
Stress tests for RiskWatchdog.

Tests realistic scenarios:
- Multiple positions hit stop simultaneously
- Rapid equity decline over multiple days
- Cascading triggers (daily → weekly → peak)
- Recovery and reset flows
- Edge cases and boundary conditions
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from execution.live.watchdog import (
    RiskWatchdog,
    KillSwitchConfig,
    KillSwitchTrigger,
    WatchdogState,
)
from execution.live.broker import (
    AccountInfo,
    BrokerPosition,
)


# === Fixtures ===

@pytest.fixture
def mock_broker():
    """Create a mock broker adapter."""
    broker = MagicMock()
    broker.get_account = AsyncMock()
    broker.get_positions = AsyncMock(return_value=[])
    broker.close_position = AsyncMock()
    broker.close_all_positions = AsyncMock(return_value=[])
    return broker


@pytest.fixture
def strict_config():
    """Configuration with tight thresholds for testing."""
    return KillSwitchConfig(
        daily_drawdown_pct=0.02,      # 2% daily max
        weekly_drawdown_pct=0.05,     # 5% weekly max
        peak_drawdown_pct=0.10,       # 10% from peak
        single_position_loss_pct=0.03,  # 3% per position
        max_daily_trades=10,
        max_daily_loss_usd=500.0,
        max_consecutive_losses=3,
        daily_pause_hours=4,
        weekly_pause_hours=24,
    )


# === Multi-Position Stress Tests ===

class TestMultiplePositionStops:
    """Test handling multiple positions hitting stops simultaneously."""

    @pytest.mark.asyncio
    async def test_multiple_positions_exceed_threshold(self, mock_broker, strict_config):
        """All positions exceeding threshold should be force closed."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Setup: 5 positions all down 4%
        losing_positions = [
            BrokerPosition(
                symbol=f"STOCK{i}",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("96"),  # 4% loss
                market_value=Decimal("9600"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("-400"),
                unrealized_pnl_pct=-4.0,
            )
            for i in range(5)
        ]

        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("98000"),  # 2% down
            cash=Decimal("48000"),
            buying_power=Decimal("196000"),
            portfolio_value=Decimal("98000"),
        )
        mock_broker.get_positions.return_value = losing_positions

        # Initialize high water marks
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        # Should have called close_position for each losing position
        assert mock_broker.close_position.call_count == 5

        # Should have recorded 5 force close events
        force_close_events = [
            e for e in watchdog.events
            if e.trigger_type == KillSwitchTrigger.SINGLE_POSITION_LOSS
        ]
        assert len(force_close_events) == 5

    @pytest.mark.asyncio
    async def test_mixed_positions_only_losers_closed(self, mock_broker, strict_config):
        """Only losing positions should be force closed."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        positions = [
            # 2 winning positions (should not be touched)
            BrokerPosition(
                symbol="WINNER1",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("110"),
                market_value=Decimal("11000"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("1000"),
                unrealized_pnl_pct=10.0,
            ),
            BrokerPosition(
                symbol="WINNER2",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("105"),
                market_value=Decimal("10500"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("500"),
                unrealized_pnl_pct=5.0,
            ),
            # 1 small loser (below threshold)
            BrokerPosition(
                symbol="SMALL_LOSER",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("98"),  # 2% loss < 3% threshold
                market_value=Decimal("9800"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("-200"),
                unrealized_pnl_pct=-2.0,
            ),
            # 2 big losers (above threshold)
            BrokerPosition(
                symbol="BIG_LOSER1",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("95"),  # 5% loss > 3% threshold
                market_value=Decimal("9500"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("-500"),
                unrealized_pnl_pct=-5.0,
            ),
            BrokerPosition(
                symbol="BIG_LOSER2",
                quantity=Decimal("100"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("94"),  # 6% loss > 3% threshold
                market_value=Decimal("9400"),
                cost_basis=Decimal("10000"),
                unrealized_pnl=Decimal("-600"),
                unrealized_pnl_pct=-6.0,
            ),
        ]

        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"),
        )
        mock_broker.get_positions.return_value = positions

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        # Should only close the 2 big losers
        assert mock_broker.close_position.call_count == 2
        closed_symbols = [
            call.args[0] for call in mock_broker.close_position.call_args_list
        ]
        assert "BIG_LOSER1" in closed_symbols
        assert "BIG_LOSER2" in closed_symbols
        assert "WINNER1" not in closed_symbols
        assert "SMALL_LOSER" not in closed_symbols


# === Cascading Trigger Tests ===

class TestCascadingTriggers:
    """Test cascading drawdown triggers (daily → weekly → peak)."""

    @pytest.mark.asyncio
    async def test_daily_before_weekly(self, mock_broker, strict_config):
        """Daily trigger should fire before weekly."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Setup: 2.5% down (breaches 2% daily but not 5% weekly)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("97500"),
            cash=Decimal("47500"),
            buying_power=Decimal("195000"),
            portfolio_value=Decimal("97500"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        assert watchdog.state == WatchdogState.PAUSED
        # Should be daily trigger
        daily_events = [
            e for e in watchdog.events
            if e.trigger_type == KillSwitchTrigger.DAILY_DRAWDOWN
        ]
        assert len(daily_events) == 1

    @pytest.mark.asyncio
    async def test_peak_shutdown_when_daily_not_breached(self, mock_broker, strict_config):
        """Peak drawdown triggers shutdown when daily threshold not breached first.

        The watchdog checks in priority order: daily → weekly → peak.
        Peak only triggers if daily wasn't already triggered.
        This test uses a config where daily is high but peak is breached.
        """
        # Use config where daily is very high but peak is breached
        config = KillSwitchConfig(
            daily_drawdown_pct=0.20,     # 20% daily (not breached)
            weekly_drawdown_pct=0.25,    # 25% weekly (not breached)
            peak_drawdown_pct=0.10,      # 10% peak (breached)
        )
        watchdog = RiskWatchdog(broker=mock_broker, config=config)

        # Setup: 12% down (breaches only peak threshold)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("88000"),
            cash=Decimal("38000"),
            buying_power=Decimal("176000"),
            portfolio_value=Decimal("88000"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        assert watchdog.state == WatchdogState.SHUTDOWN
        mock_broker.close_all_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_large_drawdown_hits_daily_first(self, mock_broker, strict_config):
        """Large drawdown triggers daily pause first, not immediate shutdown.

        This is by design - the watchdog prefers to pause trading early
        (at 2% daily loss) rather than waiting until catastrophic 10% peak loss.
        """
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Setup: 12% down (breaches all thresholds)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("88000"),
            cash=Decimal("38000"),
            buying_power=Decimal("176000"),
            portfolio_value=Decimal("88000"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        # Daily triggers first (priority order), not shutdown
        assert watchdog.state == WatchdogState.PAUSED
        daily_events = [
            e for e in watchdog.events
            if e.trigger_type == KillSwitchTrigger.DAILY_DRAWDOWN
        ]
        assert len(daily_events) == 1


# === Recovery Tests ===

class TestRecoveryScenarios:
    """Test recovery from triggered states."""

    @pytest.mark.asyncio
    async def test_recovery_after_daily_pause_expires(self, mock_broker, strict_config):
        """Should resume trading after daily pause expires."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Set paused state that has expired
        watchdog.state = WatchdogState.PAUSED
        watchdog.paused_until = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is True  # Trading allowed
        assert watchdog.state == WatchdogState.ACTIVE

    def test_reset_from_shutdown_resets_all_metrics(self, mock_broker, strict_config):
        """Reset from shutdown should reset all tracking metrics."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)
        watchdog.state = WatchdogState.SHUTDOWN
        watchdog.stats.consecutive_losses = 10
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.daily_high_water = Decimal("90000")
        watchdog.stats.weekly_high_water = Decimal("85000")

        # Reset with new peak
        watchdog.reset_shutdown(Decimal("80000"))

        assert watchdog.state == WatchdogState.ACTIVE
        assert watchdog.stats.peak_equity == Decimal("80000")
        assert watchdog.stats.daily_high_water == Decimal("80000")
        assert watchdog.stats.weekly_high_water == Decimal("80000")
        assert watchdog.stats.consecutive_losses == 0


# === Edge Cases ===

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_exactly_at_threshold(self, mock_broker, strict_config):
        """Exactly at threshold should trigger."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Exactly 2% down (exactly at daily threshold)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("98000"),  # Exactly 2% down
            cash=Decimal("48000"),
            buying_power=Decimal("196000"),
            portfolio_value=Decimal("98000"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        assert watchdog.state == WatchdogState.PAUSED

    @pytest.mark.asyncio
    async def test_just_below_threshold(self, mock_broker, strict_config):
        """Just below threshold should not trigger."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # 1.9% down (just below 2% threshold)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("98100"),
            cash=Decimal("48100"),
            buying_power=Decimal("196200"),
            portfolio_value=Decimal("98100"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        result = await watchdog.check()

        assert result is True
        assert watchdog.state == WatchdogState.ACTIVE

    @pytest.mark.asyncio
    async def test_zero_equity_edge_case(self, mock_broker, strict_config):
        """Should handle zero equity gracefully."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Catastrophic scenario
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("0"),
            cash=Decimal("0"),
            buying_power=Decimal("0"),
            portfolio_value=Decimal("0"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        # Should trigger shutdown but not crash
        await watchdog.check()

        assert watchdog.state == WatchdogState.SHUTDOWN

    def test_rapid_consecutive_losses(self, mock_broker, strict_config):
        """Should track rapid consecutive losses correctly."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)
        strict_config.max_consecutive_losses = 3

        # Simulate rapid losses
        for i in range(5):
            watchdog.record_trade(is_winner=False, pnl=Decimal("-100"))

        assert watchdog.stats.consecutive_losses == 5
        assert watchdog.stats.daily_pnl == Decimal("-500")
        assert watchdog.stats.daily_trades == 5

    def test_win_resets_consecutive_losses(self, mock_broker, strict_config):
        """Single win should reset consecutive loss counter."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # Build up losses
        for _ in range(4):
            watchdog.record_trade(is_winner=False, pnl=Decimal("-100"))

        assert watchdog.stats.consecutive_losses == 4

        # Single win resets
        watchdog.record_trade(is_winner=True, pnl=Decimal("50"))

        assert watchdog.stats.consecutive_losses == 0
        assert watchdog.stats.daily_pnl == Decimal("-350")


# === Notification Integration Tests ===

class TestNotifications:
    """Test notification integration."""

    @pytest.mark.asyncio
    async def test_shutdown_triggers_callback(self, mock_broker, strict_config):
        """Shutdown should trigger callback."""
        callback_triggered = []
        watchdog = RiskWatchdog(
            broker=mock_broker,
            config=strict_config,
            on_shutdown=lambda: callback_triggered.append(True),
        )

        # Trigger shutdown
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("85000"),  # 15% down
            cash=Decimal("35000"),
            buying_power=Decimal("170000"),
            portfolio_value=Decimal("85000"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        await watchdog.check()

        assert len(callback_triggered) == 1

    @pytest.mark.asyncio
    async def test_notifier_called_on_pause(self, mock_broker, strict_config):
        """Notifier should be called on pause."""
        notifier = MagicMock()
        notifier.send_alert = AsyncMock()

        watchdog = RiskWatchdog(
            broker=mock_broker,
            config=strict_config,
            notifier=notifier,
        )

        # Trigger daily pause
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("97500"),  # 2.5% down
            cash=Decimal("47500"),
            buying_power=Decimal("195000"),
            portfolio_value=Decimal("97500"),
        )

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        notifier.send_alert.assert_called()


# === Realistic Scenario Tests ===

class TestRealisticScenarios:
    """Test realistic multi-day trading scenarios."""

    @pytest.mark.asyncio
    async def test_gradual_drawdown_over_multiple_checks(self, mock_broker, strict_config):
        """Simulate gradual drawdown over multiple check cycles."""
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Check 1: Small loss (1%)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("99000"),
            cash=Decimal("49000"),
            buying_power=Decimal("198000"),
            portfolio_value=Decimal("99000"),
        )
        result = await watchdog.check()
        assert result is True
        assert watchdog.state == WatchdogState.ACTIVE

        # Check 2: Larger loss (2.5% from high)
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("97500"),
            cash=Decimal("47500"),
            buying_power=Decimal("195000"),
            portfolio_value=Decimal("97500"),
        )
        result = await watchdog.check()
        assert result is False
        assert watchdog.state == WatchdogState.PAUSED

    @pytest.mark.asyncio
    async def test_flash_crash_scenario(self, mock_broker, strict_config):
        """Simulate flash crash where all positions gap down.

        In the current implementation, flash crash triggers daily pause first
        (priority order), then force closes all positions exceeding individual
        loss threshold. The daily pause prevents new trades while position
        closes execute.
        """
        watchdog = RiskWatchdog(broker=mock_broker, config=strict_config)

        # All 10 positions down 8% (exceeds 3% single position threshold)
        flash_crash_positions = [
            BrokerPosition(
                symbol=f"STOCK{i}",
                quantity=Decimal("50"),
                avg_entry_price=Decimal("100"),
                current_price=Decimal("92"),  # 8% loss
                market_value=Decimal("4600"),
                cost_basis=Decimal("5000"),
                unrealized_pnl=Decimal("-400"),
                unrealized_pnl_pct=-8.0,
            )
            for i in range(10)
        ]

        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("88000"),  # 12% down
            cash=Decimal("42000"),
            buying_power=Decimal("176000"),
            portfolio_value=Decimal("88000"),
        )
        mock_broker.get_positions.return_value = flash_crash_positions

        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")
        watchdog.stats.last_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_week_reset_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        await watchdog.check()

        # Daily drawdown triggers first (priority order)
        assert watchdog.state == WatchdogState.PAUSED

        # All 10 positions should be force closed (exceed single position threshold)
        assert mock_broker.close_position.call_count == 10
        force_close_events = [
            e for e in watchdog.events
            if e.trigger_type == KillSwitchTrigger.SINGLE_POSITION_LOSS
        ]
        assert len(force_close_events) == 10
