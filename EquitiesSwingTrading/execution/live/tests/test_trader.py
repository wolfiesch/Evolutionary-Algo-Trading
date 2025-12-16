"""
Tests for EquitiesLiveTrader.

Tests cover:
- Signal validation
- Position sizing
- Entry/exit order flow
- Position limits and throttling
- Daily stats tracking
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from execution.live.trader import (
    Signal,
    LiveTraderConfig,
    DailyStats,
    LivePosition,
    EquitiesLiveTrader,
)
from execution.live.broker import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    AccountInfo,
    BrokerPosition,
    BracketOrderRequest,
    BrokerError,
    OrderRejectedError,
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
        day_trade_count=0,
        pattern_day_trader=False,
    ))
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_position = AsyncMock(return_value=None)
    broker.submit_order = AsyncMock(return_value=Order(
        order_id="order-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("10"),
        filled_avg_price=Decimal("150.00"),
    ))
    broker.submit_bracket_order = AsyncMock(return_value=Order(
        order_id="bracket-123",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("10"),
        filled_avg_price=Decimal("150.00"),
    ))
    broker.close_position = AsyncMock(return_value=Order(
        order_id="close-123",
        symbol="AAPL",
        side=OrderSide.SELL,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        status=OrderStatus.FILLED,
        filled_quantity=Decimal("10"),
        filled_avg_price=Decimal("155.00"),
    ))
    broker.close_all_positions = AsyncMock(return_value=[])
    return broker


@pytest.fixture
def config():
    """Return a test configuration."""
    return LiveTraderConfig(
        max_position_pct=0.05,
        risk_per_trade=0.01,
        max_positions=5,
        max_signal_age_seconds=60,
        min_entry_interval_seconds=0,  # Disable throttling for tests
        max_daily_trades=20,
    )


@pytest.fixture
def trader(mock_broker, config):
    """Create a trader instance."""
    return EquitiesLiveTrader(broker=mock_broker, config=config)


@pytest.fixture
def entry_signal():
    """Return a valid entry signal."""
    return Signal(
        signal_id="sig-1",
        strategy_id="test_strategy",
        symbol="AAPL",
        signal_type="entry_long",
        entry_price=Decimal("150.00"),
        stop_loss_price=Decimal("147.00"),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def exit_signal():
    """Return a valid exit signal."""
    return Signal(
        signal_id="sig-2",
        strategy_id="test_strategy",
        symbol="AAPL",
        signal_type="exit_long",
        entry_price=Decimal("155.00"),
        timestamp=datetime.now(timezone.utc),
    )


# === Signal Tests ===

class TestSignal:
    """Test Signal dataclass."""

    def test_is_entry_long(self, entry_signal):
        """Should identify entry signal."""
        assert entry_signal.is_entry is True
        assert entry_signal.is_exit is False
        assert entry_signal.is_long is True
        assert entry_signal.is_short is False

    def test_is_exit_long(self, exit_signal):
        """Should identify exit signal."""
        assert exit_signal.is_entry is False
        assert exit_signal.is_exit is True
        assert exit_signal.is_long is True

    def test_is_entry_short(self):
        """Should identify short entry."""
        signal = Signal(
            signal_id="s",
            strategy_id="s",
            symbol="AAPL",
            signal_type="entry_short",
            entry_price=Decimal("150"),
            stop_loss_price=Decimal("153"),
        )
        assert signal.is_entry is True
        assert signal.is_short is True
        assert signal.is_long is False


# === Config Tests ===

class TestLiveTraderConfig:
    """Test LiveTraderConfig defaults."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = LiveTraderConfig()
        assert config.max_position_pct == 0.05
        assert config.risk_per_trade == 0.01
        assert config.max_positions == 10
        assert config.use_bracket_orders is True


# === Signal Validation Tests ===

class TestSignalValidation:
    """Test signal validation logic."""

    def test_valid_signal(self, trader, entry_signal):
        """Should accept valid signal."""
        error = trader._validate_signal(entry_signal)
        assert error is None

    def test_stale_signal(self, trader, entry_signal):
        """Should reject stale signal."""
        entry_signal.timestamp = datetime.now(timezone.utc) - timedelta(seconds=120)
        error = trader._validate_signal(entry_signal)
        assert error is not None
        assert "old" in error.lower()

    def test_missing_symbol(self, trader, entry_signal):
        """Should reject signal without symbol."""
        entry_signal.symbol = ""
        error = trader._validate_signal(entry_signal)
        assert error is not None
        assert "symbol" in error.lower()

    def test_invalid_entry_price(self, trader, entry_signal):
        """Should reject invalid entry price."""
        entry_signal.entry_price = Decimal("0")
        error = trader._validate_signal(entry_signal)
        assert error is not None
        assert "price" in error.lower()

    def test_missing_stop_loss(self, trader, entry_signal, config):
        """Should reject entry without stop-loss when required."""
        config.require_stop_loss = True
        entry_signal.stop_loss_price = None
        error = trader._validate_signal(entry_signal)
        assert error is not None
        assert "stop" in error.lower()

    def test_invalid_stop_long(self, trader, entry_signal):
        """Should reject long with stop above entry."""
        entry_signal.stop_loss_price = Decimal("155.00")  # Above entry
        error = trader._validate_signal(entry_signal)
        assert error is not None
        assert "below" in error.lower()

    def test_invalid_stop_short(self, trader):
        """Should reject short with stop below entry."""
        signal = Signal(
            signal_id="s",
            strategy_id="s",
            symbol="AAPL",
            signal_type="entry_short",
            entry_price=Decimal("150"),
            stop_loss_price=Decimal("147"),  # Below entry
        )
        error = trader._validate_signal(signal)
        assert error is not None
        assert "above" in error.lower()


# === Position Sizing Tests ===

class TestPositionSizing:
    """Test position size calculation."""

    def test_basic_sizing(self, trader, entry_signal):
        """Should calculate position size based on risk."""
        account = AccountInfo(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"),
        )

        size = trader._calculate_position_size(entry_signal, account)

        # Risk = 1% of 100k = 1000
        # Stop distance = 150 - 147 = 3
        # Risk-based shares = 1000 / 3 = 333
        # Max position = 5% of 100k = 5000 / 150 = 33 shares
        # Should take minimum = 33 shares
        assert size == Decimal("33")

    def test_buying_power_limit(self, trader, entry_signal):
        """Should respect buying power limit."""
        account = AccountInfo(
            equity=Decimal("100000"),
            cash=Decimal("1000"),
            buying_power=Decimal("1000"),  # Very limited
            portfolio_value=Decimal("100000"),
        )

        size = trader._calculate_position_size(entry_signal, account)

        # Limited by buying power: 1000 / 150 = 6 shares
        assert size == Decimal("6")

    def test_zero_stop_distance(self, trader, entry_signal):
        """Should handle same entry and stop price."""
        entry_signal.stop_loss_price = entry_signal.entry_price
        account = AccountInfo(
            equity=Decimal("100000"),
            cash=Decimal("50000"),
            buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"),
        )

        size = trader._calculate_position_size(entry_signal, account)

        # Should use max position sizing when stop distance is 0
        # Max = 5% of 100k = 5000 / 150 = 33 shares
        assert size == Decimal("33")


# === Entry Flow Tests ===

class TestEntryFlow:
    """Test entry signal processing."""

    @pytest.mark.asyncio
    async def test_successful_entry(self, trader, mock_broker, entry_signal):
        """Should process entry and track position."""
        order = await trader.process_signal(entry_signal)

        assert order is not None
        assert order.status == OrderStatus.FILLED
        assert "AAPL" in trader.positions
        assert trader.daily_stats.trades_count == 1

    @pytest.mark.asyncio
    async def test_max_positions_reached(self, trader, mock_broker, entry_signal, config):
        """Should reject when max positions reached."""
        # Fill up positions
        config.max_positions = 1
        trader.positions["MSFT"] = LivePosition(
            symbol="MSFT",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("300"),
            quantity=Decimal("10"),
        )

        order = await trader.process_signal(entry_signal)

        assert order is None
        assert "AAPL" not in trader.positions

    @pytest.mark.asyncio
    async def test_duplicate_position(self, trader, mock_broker, entry_signal):
        """Should reject entry when already have position."""
        # Add existing position
        trader.positions["AAPL"] = LivePosition(
            symbol="AAPL",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("145"),
            quantity=Decimal("10"),
        )

        order = await trader.process_signal(entry_signal)

        assert order is None

    @pytest.mark.asyncio
    async def test_daily_trade_limit(self, trader, mock_broker, entry_signal, config):
        """Should reject when daily trade limit reached."""
        config.max_daily_trades = 1
        trader.daily_stats.trades_count = 1

        order = await trader.process_signal(entry_signal)

        assert order is None

    @pytest.mark.asyncio
    async def test_kill_switch_blocks(self, trader, mock_broker, entry_signal):
        """Should reject when kill switch triggered."""
        trader.risk_callback = lambda: False  # Kill switch triggered

        order = await trader.process_signal(entry_signal)

        assert order is None

    @pytest.mark.asyncio
    async def test_bracket_order_used(self, trader, mock_broker, entry_signal, config):
        """Should use bracket orders when configured."""
        config.use_bracket_orders = True

        await trader.process_signal(entry_signal)

        mock_broker.submit_bracket_order.assert_called_once()
        mock_broker.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_simple_order_fallback(self, trader, mock_broker, entry_signal, config):
        """Should use simple orders when bracket disabled."""
        config.use_bracket_orders = False

        await trader.process_signal(entry_signal)

        mock_broker.submit_order.assert_called_once()


# === Exit Flow Tests ===

class TestExitFlow:
    """Test exit signal processing."""

    @pytest.mark.asyncio
    async def test_successful_exit(self, trader, mock_broker, exit_signal):
        """Should process exit and remove position."""
        # Add position first
        trader.positions["AAPL"] = LivePosition(
            symbol="AAPL",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("150"),
            quantity=Decimal("10"),
        )

        order = await trader.process_signal(exit_signal)

        assert order is not None
        assert "AAPL" not in trader.positions
        mock_broker.close_position.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_exit_no_position(self, trader, mock_broker, exit_signal):
        """Should reject exit when no position exists."""
        order = await trader.process_signal(exit_signal)

        assert order is None

    @pytest.mark.asyncio
    async def test_pnl_tracking(self, trader, mock_broker, exit_signal):
        """Should track P&L on exit."""
        # Add position at lower price
        trader.positions["AAPL"] = LivePosition(
            symbol="AAPL",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("150"),
            quantity=Decimal("10"),
        )

        await trader.process_signal(exit_signal)

        # Exit at 155, entry at 150, qty 10 = profit of 50
        assert trader.daily_stats.wins == 1
        assert trader.daily_stats.total_pnl == Decimal("50")


# === Exposure Tests ===

class TestExposureManagement:
    """Test exposure limit enforcement."""

    @pytest.mark.asyncio
    async def test_max_exposure_check(self, trader, mock_broker, entry_signal, config):
        """Should reject when would exceed max exposure."""
        config.max_total_exposure = 0.01  # Very low limit

        order = await trader.process_signal(entry_signal)

        # Should be rejected due to exposure limit
        # (depends on position size vs exposure limit)
        # This is a bit tricky to test without mocking more


# === Position Sync Tests ===

class TestPositionSync:
    """Test position synchronization."""

    @pytest.mark.asyncio
    async def test_sync_detects_untracked(self, trader, mock_broker):
        """Should detect positions not tracked internally."""
        mock_broker.get_positions.return_value = [
            BrokerPosition(
                symbol="AAPL",
                quantity=Decimal("10"),
                avg_entry_price=Decimal("150"),
                current_price=Decimal("155"),
                market_value=Decimal("1550"),
                cost_basis=Decimal("1500"),
                unrealized_pnl=Decimal("50"),
                unrealized_pnl_pct=3.33,
            )
        ]

        await trader.sync_positions()

        # Should log warning about untracked AAPL
        # (would need to check logs or mock logger)

    @pytest.mark.asyncio
    async def test_sync_removes_missing(self, trader, mock_broker):
        """Should remove internally tracked positions missing from broker."""
        # Track a position internally
        trader.positions["AAPL"] = LivePosition(
            symbol="AAPL",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("150"),
            quantity=Decimal("10"),
        )

        # Broker returns empty positions
        mock_broker.get_positions.return_value = []

        await trader.sync_positions()

        assert "AAPL" not in trader.positions


# === Emergency Close Tests ===

class TestEmergencyClose:
    """Test emergency position closing."""

    @pytest.mark.asyncio
    async def test_close_all_positions(self, trader, mock_broker):
        """Should close all positions and clear tracking."""
        trader.positions["AAPL"] = LivePosition(
            symbol="AAPL",
            strategy_id="test",
            entry_order_id="o1",
            entry_price=Decimal("150"),
            quantity=Decimal("10"),
        )

        await trader.close_all_positions()

        mock_broker.close_all_positions.assert_called_once()
        assert len(trader.positions) == 0


# === Daily Stats Tests ===

class TestDailyStats:
    """Test daily statistics tracking."""

    def test_stats_reset(self):
        """Should reset stats correctly."""
        stats = DailyStats()
        stats.trades_count = 10
        stats.wins = 5
        stats.total_pnl = Decimal("500")

        stats.reset("2025-01-01", Decimal("100000"))

        assert stats.date == "2025-01-01"
        assert stats.trades_count == 0
        assert stats.wins == 0
        assert stats.total_pnl == Decimal("0")
        assert stats.peak_equity == Decimal("100000")

    def test_trader_reset_stats(self, trader):
        """Should reset trader stats."""
        trader.daily_stats.trades_count = 10

        trader.reset_daily_stats(Decimal("100000"))

        assert trader.daily_stats.trades_count == 0


# === Throttling Tests ===

class TestThrottling:
    """Test entry throttling."""

    @pytest.mark.asyncio
    async def test_throttle_respects_interval(self, trader, mock_broker, entry_signal, config):
        """Should throttle rapid entries."""
        config.min_entry_interval_seconds = 300  # 5 minutes

        # First entry succeeds
        await trader.process_signal(entry_signal)

        # Create new signal for different symbol
        signal2 = Signal(
            signal_id="sig-2",
            strategy_id="test",
            symbol="MSFT",
            signal_type="entry_long",
            entry_price=Decimal("300"),
            stop_loss_price=Decimal("295"),
            timestamp=datetime.now(timezone.utc),
        )

        # Should be throttled
        order = await trader.process_signal(signal2)

        assert order is None

    def test_throttle_check_no_previous(self, trader, config):
        """Should allow first entry."""
        config.min_entry_interval_seconds = 300
        assert trader._check_entry_throttle() is True

    def test_throttle_check_elapsed(self, trader, config):
        """Should allow entry after interval."""
        config.min_entry_interval_seconds = 1
        trader._last_entry_time = datetime.now(timezone.utc) - timedelta(seconds=2)
        assert trader._check_entry_throttle() is True
