"""
Tests for RiskWatchdog.

Tests cover:
- Drawdown calculations
- Kill switch triggers (daily, weekly, peak)
- Position-level loss checks
- Pause and shutdown mechanics
- State management
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
    WatchdogStats,
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
    broker.get_account = AsyncMock(return_value=AccountInfo(
        equity=Decimal("100000"),
        cash=Decimal("50000"),
        buying_power=Decimal("200000"),
        portfolio_value=Decimal("100000"),
    ))
    broker.get_positions = AsyncMock(return_value=[])
    broker.close_position = AsyncMock()
    broker.close_all_positions = AsyncMock(return_value=[])
    return broker


@pytest.fixture
def config():
    """Return a test configuration."""
    return KillSwitchConfig(
        daily_drawdown_pct=0.03,
        weekly_drawdown_pct=0.07,
        peak_drawdown_pct=0.15,
        single_position_loss_pct=0.05,
        max_daily_trades=20,
        max_daily_loss_usd=1000.0,
        max_consecutive_losses=5,
    )


@pytest.fixture
def watchdog(mock_broker, config):
    """Create a watchdog instance."""
    return RiskWatchdog(broker=mock_broker, config=config)


# === Config Tests ===

class TestKillSwitchConfig:
    """Test KillSwitchConfig defaults."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = KillSwitchConfig()
        assert config.daily_drawdown_pct == 0.03
        assert config.weekly_drawdown_pct == 0.07
        assert config.peak_drawdown_pct == 0.15
        assert config.single_position_loss_pct == 0.05


# === State Tests ===

class TestWatchdogState:
    """Test watchdog state management."""

    def test_initial_state(self, watchdog):
        """Should start in active state."""
        assert watchdog.state == WatchdogState.ACTIVE
        assert watchdog.paused_until is None

    def test_is_trading_allowed_active(self, watchdog):
        """Should allow trading when active."""
        assert watchdog.is_trading_allowed() is True

    def test_is_trading_allowed_paused(self, watchdog):
        """Should not allow trading when paused."""
        watchdog.state = WatchdogState.PAUSED
        watchdog.paused_until = datetime.now(timezone.utc) + timedelta(hours=1)
        assert watchdog.is_trading_allowed() is False

    def test_is_trading_allowed_shutdown(self, watchdog):
        """Should not allow trading when shutdown."""
        watchdog.state = WatchdogState.SHUTDOWN
        assert watchdog.is_trading_allowed() is False

    def test_pause_expires(self, watchdog):
        """Should resume when pause expires."""
        watchdog.state = WatchdogState.PAUSED
        watchdog.paused_until = datetime.now(timezone.utc) - timedelta(hours=1)

        assert watchdog.is_trading_allowed() is True
        assert watchdog.state == WatchdogState.ACTIVE


# === Drawdown Calculation Tests ===

class TestDrawdownCalculation:
    """Test drawdown calculations."""

    def test_daily_drawdown_calculation(self, watchdog):
        """Should calculate daily drawdown correctly."""
        watchdog.stats.daily_high_water = Decimal("100000")
        current = Decimal("97000")

        watchdog._calculate_drawdowns(current)

        assert watchdog.stats.daily_drawdown_pct == pytest.approx(0.03, rel=0.01)

    def test_weekly_drawdown_calculation(self, watchdog):
        """Should calculate weekly drawdown correctly."""
        watchdog.stats.weekly_high_water = Decimal("100000")
        current = Decimal("93000")

        watchdog._calculate_drawdowns(current)

        assert watchdog.stats.weekly_drawdown_pct == pytest.approx(0.07, rel=0.01)

    def test_peak_drawdown_calculation(self, watchdog):
        """Should calculate peak drawdown correctly."""
        watchdog.stats.peak_equity = Decimal("100000")
        current = Decimal("85000")

        watchdog._calculate_drawdowns(current)

        assert watchdog.stats.peak_drawdown_pct == pytest.approx(0.15, rel=0.01)

    def test_no_drawdown_when_at_high(self, watchdog):
        """Should show 0 drawdown at high water."""
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        watchdog._calculate_drawdowns(Decimal("100000"))

        assert watchdog.stats.daily_drawdown_pct == 0.0
        assert watchdog.stats.weekly_drawdown_pct == 0.0
        assert watchdog.stats.peak_drawdown_pct == 0.0


# === High Water Mark Tests ===

class TestHighWaterMark:
    """Test high water mark updates."""

    def test_updates_all_high_water_marks(self, watchdog):
        """Should update all high water marks on new high."""
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        watchdog._update_high_water(Decimal("105000"))

        assert watchdog.stats.daily_high_water == Decimal("105000")
        assert watchdog.stats.weekly_high_water == Decimal("105000")
        assert watchdog.stats.peak_equity == Decimal("105000")

    def test_does_not_lower_high_water(self, watchdog):
        """Should not lower high water marks."""
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        watchdog._update_high_water(Decimal("95000"))

        assert watchdog.stats.daily_high_water == Decimal("100000")
        assert watchdog.stats.weekly_high_water == Decimal("100000")
        assert watchdog.stats.peak_equity == Decimal("100000")


# === Kill Switch Trigger Tests ===

class TestKillSwitchTriggers:
    """Test kill switch triggers."""

    @pytest.mark.asyncio
    async def test_daily_drawdown_trigger(self, watchdog, mock_broker):
        """Should pause on daily drawdown breach."""
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("97000"),  # 3% down from 100k
            cash=Decimal("47000"),
            buying_power=Decimal("194000"),
            portfolio_value=Decimal("97000"),
        )
        # Set reset dates to prevent automatic reset
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_reset_date = today
        watchdog.stats.last_week_reset_date = today
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.PAUSED
        assert watchdog.paused_until is not None

    @pytest.mark.asyncio
    async def test_weekly_drawdown_trigger(self, watchdog, mock_broker):
        """Should pause on weekly drawdown breach."""
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("93000"),  # 7% down from 100k
            cash=Decimal("43000"),
            buying_power=Decimal("186000"),
            portfolio_value=Decimal("93000"),
        )
        # Set reset dates to prevent automatic reset
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_reset_date = today
        watchdog.stats.last_week_reset_date = today
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.PAUSED

    @pytest.mark.asyncio
    async def test_peak_drawdown_trigger(self, watchdog, mock_broker):
        """Should shutdown on peak drawdown breach."""
        mock_broker.get_account.return_value = AccountInfo(
            equity=Decimal("85000"),  # 15% down from 100k
            cash=Decimal("35000"),
            buying_power=Decimal("170000"),
            portfolio_value=Decimal("85000"),
        )
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.SHUTDOWN
        mock_broker.close_all_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_max_daily_trades_trigger(self, watchdog, mock_broker, config):
        """Should pause when max daily trades reached."""
        config.max_daily_trades = 5
        # Set reset dates to prevent automatic reset
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_reset_date = today
        watchdog.stats.last_week_reset_date = today
        watchdog.stats.daily_trades = 5
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.PAUSED

    @pytest.mark.asyncio
    async def test_max_daily_loss_trigger(self, watchdog, mock_broker, config):
        """Should pause when max daily loss reached."""
        config.max_daily_loss_usd = 500
        # Set reset dates to prevent automatic reset
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        watchdog.stats.last_reset_date = today
        watchdog.stats.last_week_reset_date = today
        watchdog.stats.daily_pnl = Decimal("-600")
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.PAUSED

    @pytest.mark.asyncio
    async def test_consecutive_losses_trigger(self, watchdog, mock_broker, config):
        """Should pause on consecutive losses."""
        config.max_consecutive_losses = 3
        watchdog.stats.consecutive_losses = 3
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.weekly_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        result = await watchdog.check()

        assert result is False
        assert watchdog.state == WatchdogState.PAUSED


# === Position Loss Tests ===

class TestPositionLoss:
    """Test position-level loss checks."""

    def test_check_position_loss_below_threshold(self, watchdog, config):
        """Should not flag position below threshold."""
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150"),
            current_price=Decimal("148"),  # ~1.3% loss
            market_value=Decimal("1480"),
            cost_basis=Decimal("1500"),
            unrealized_pnl=Decimal("-20"),
            unrealized_pnl_pct=-1.33,
        )

        assert watchdog._check_position_loss(position) is False

    def test_check_position_loss_above_threshold(self, watchdog, config):
        """Should flag position above threshold."""
        config.single_position_loss_pct = 0.05
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150"),
            current_price=Decimal("140"),  # ~6.7% loss
            market_value=Decimal("1400"),
            cost_basis=Decimal("1500"),
            unrealized_pnl=Decimal("-100"),
            unrealized_pnl_pct=-6.67,
        )

        assert watchdog._check_position_loss(position) is True

    def test_check_position_with_profit(self, watchdog):
        """Should not flag profitable position."""
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150"),
            current_price=Decimal("160"),
            market_value=Decimal("1600"),
            cost_basis=Decimal("1500"),
            unrealized_pnl=Decimal("100"),
            unrealized_pnl_pct=6.67,
        )

        assert watchdog._check_position_loss(position) is False

    @pytest.mark.asyncio
    async def test_force_close_position(self, watchdog, mock_broker):
        """Should close position exceeding loss threshold."""
        position = BrokerPosition(
            symbol="AAPL",
            quantity=Decimal("10"),
            avg_entry_price=Decimal("150"),
            current_price=Decimal("140"),
            market_value=Decimal("1400"),
            cost_basis=Decimal("1500"),
            unrealized_pnl=Decimal("-100"),
            unrealized_pnl_pct=-6.67,
        )

        await watchdog._force_close_position(position)

        mock_broker.close_position.assert_called_once_with("AAPL")


# === Manual Control Tests ===

class TestManualControl:
    """Test manual pause/resume/shutdown."""

    def test_manual_pause(self, watchdog):
        """Should pause on manual trigger."""
        watchdog.manual_pause(hours=2)

        assert watchdog.state == WatchdogState.PAUSED
        assert watchdog.paused_until is not None
        assert len(watchdog.events) == 1
        assert watchdog.events[0].trigger_type == KillSwitchTrigger.MANUAL

    def test_manual_resume(self, watchdog):
        """Should resume from pause."""
        watchdog.state = WatchdogState.PAUSED
        watchdog.paused_until = datetime.now(timezone.utc) + timedelta(hours=1)

        watchdog.manual_resume()

        assert watchdog.state == WatchdogState.ACTIVE
        assert watchdog.paused_until is None

    def test_manual_resume_not_from_shutdown(self, watchdog):
        """Should not resume from shutdown via manual_resume."""
        watchdog.state = WatchdogState.SHUTDOWN

        watchdog.manual_resume()

        assert watchdog.state == WatchdogState.SHUTDOWN

    def test_manual_shutdown(self, watchdog):
        """Should trigger shutdown."""
        callback_called = []
        watchdog.on_shutdown = lambda: callback_called.append(True)

        watchdog.manual_shutdown()

        assert watchdog.state == WatchdogState.SHUTDOWN
        assert len(callback_called) == 1

    def test_reset_shutdown(self, watchdog):
        """Should reset from shutdown with new peak."""
        watchdog.state = WatchdogState.SHUTDOWN

        watchdog.reset_shutdown(Decimal("90000"))

        assert watchdog.state == WatchdogState.ACTIVE
        assert watchdog.stats.peak_equity == Decimal("90000")
        assert watchdog.stats.daily_high_water == Decimal("90000")
        assert watchdog.stats.weekly_high_water == Decimal("90000")


# === Trade Recording Tests ===

class TestTradeRecording:
    """Test trade recording."""

    def test_record_winning_trade(self, watchdog):
        """Should record winning trade."""
        watchdog.stats.consecutive_losses = 3

        watchdog.record_trade(is_winner=True, pnl=Decimal("100"))

        assert watchdog.stats.daily_trades == 1
        assert watchdog.stats.daily_pnl == Decimal("100")
        assert watchdog.stats.consecutive_losses == 0

    def test_record_losing_trade(self, watchdog):
        """Should record losing trade."""
        watchdog.record_trade(is_winner=False, pnl=Decimal("-50"))

        assert watchdog.stats.daily_trades == 1
        assert watchdog.stats.daily_pnl == Decimal("-50")
        assert watchdog.stats.consecutive_losses == 1

    def test_consecutive_losses_tracking(self, watchdog):
        """Should track consecutive losses."""
        watchdog.record_trade(is_winner=False, pnl=Decimal("-50"))
        watchdog.record_trade(is_winner=False, pnl=Decimal("-50"))
        watchdog.record_trade(is_winner=False, pnl=Decimal("-50"))

        assert watchdog.stats.consecutive_losses == 3


# === Event Recording Tests ===

class TestEventRecording:
    """Test event recording."""

    def test_event_recorded(self, watchdog):
        """Should record events."""
        watchdog._record_event(
            KillSwitchTrigger.DAILY_DRAWDOWN,
            threshold_value=0.03,
            actual_value=0.035,
            action_taken="Paused trading",
        )

        assert len(watchdog.events) == 1
        assert watchdog.events[0].trigger_type == KillSwitchTrigger.DAILY_DRAWDOWN

    def test_event_limit(self, watchdog):
        """Should limit event history."""
        watchdog._max_events = 5

        for i in range(10):
            watchdog._record_event(
                KillSwitchTrigger.MANUAL,
                threshold_value=0,
                actual_value=0,
                action_taken=f"Event {i}",
            )

        assert len(watchdog.events) == 5


# === Status Tests ===

class TestStatus:
    """Test status reporting."""

    def test_get_status(self, watchdog):
        """Should return status dict."""
        watchdog.stats.daily_high_water = Decimal("100000")
        watchdog.stats.peak_equity = Decimal("100000")

        status = watchdog.get_status()

        assert status["state"] == "active"
        assert "stats" in status
        assert "config" in status
        assert "recent_events" in status
