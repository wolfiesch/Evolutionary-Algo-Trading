"""Tests for shadow trading data models."""
import pytest
from datetime import date, datetime
import json

from execution.shadow.models import (
    SignalType,
    ExitReason,
    Position,
    TradeLog,
    Signal,
    PortfolioSnapshot,
    DailySummary,
)


class TestSignalType:
    """Tests for SignalType enum."""

    def test_entry_long_value(self):
        assert SignalType.ENTRY_LONG.value == "ENTRY_LONG"

    def test_exit_long_value(self):
        assert SignalType.EXIT_LONG.value == "EXIT_LONG"

    def test_stop_loss_value(self):
        assert SignalType.STOP_LOSS.value == "STOP_LOSS"

    def test_hold_value(self):
        assert SignalType.HOLD.value == "HOLD"


class TestExitReason:
    """Tests for ExitReason enum."""

    def test_signal_value(self):
        assert ExitReason.SIGNAL.value == "signal"

    def test_stop_loss_value(self):
        assert ExitReason.STOP_LOSS.value == "stop_loss"

    def test_timeout_value(self):
        assert ExitReason.TIMEOUT.value == "timeout"

    def test_kill_switch_value(self):
        assert ExitReason.KILL_SWITCH.value == "kill_switch"


class TestPosition:
    """Tests for Position dataclass."""

    @pytest.fixture
    def sample_position(self):
        return Position(
            symbol="AAPL",
            strategy_id="test_strategy",
            entry_date=date(2024, 1, 15),
            entry_price=185.00,
            shares=10.0,
            notional_value=1850.00,
            stop_loss_price=175.75,
        )

    def test_position_creation(self, sample_position):
        assert sample_position.symbol == "AAPL"
        assert sample_position.strategy_id == "test_strategy"
        assert sample_position.entry_price == 185.00
        assert sample_position.shares == 10.0

    def test_entry_datetime(self, sample_position):
        dt = sample_position.entry_datetime
        assert isinstance(dt, datetime)
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15

    def test_days_held(self, sample_position):
        current_date = date(2024, 1, 20)
        days = sample_position.days_held(current_date)
        assert days == 5

    def test_unrealized_pnl_profit(self, sample_position):
        current_price = 195.00
        pnl = sample_position.unrealized_pnl(current_price)
        expected = 1850.00 * (195.00 / 185.00 - 1)
        assert abs(pnl - expected) < 0.01

    def test_unrealized_pnl_loss(self, sample_position):
        current_price = 175.00
        pnl = sample_position.unrealized_pnl(current_price)
        assert pnl < 0

    def test_unrealized_pnl_pct_profit(self, sample_position):
        current_price = 195.00
        pnl_pct = sample_position.unrealized_pnl_pct(current_price)
        expected = (195.00 / 185.00 - 1) * 100
        assert abs(pnl_pct - expected) < 0.01

    def test_should_stop_out_with_stop_price(self, sample_position):
        # Below stop loss
        assert sample_position.should_stop_out(170.00) is True
        # Above stop loss
        assert sample_position.should_stop_out(180.00) is False
        # At stop loss
        assert sample_position.should_stop_out(175.75) is True

    def test_should_stop_out_percentage_fallback(self):
        position = Position(
            symbol="AAPL",
            strategy_id="test",
            entry_date=date(2024, 1, 15),
            entry_price=100.00,
            shares=10.0,
            notional_value=1000.00,
            stop_loss_price=None,
            stop_loss_pct=0.05,  # 5% stop
        )
        # 6% loss should trigger stop
        assert position.should_stop_out(94.00) is True
        # 4% loss should not
        assert position.should_stop_out(96.00) is False

    def test_default_side_is_long(self, sample_position):
        assert sample_position.side == "LONG"


class TestTradeLog:
    """Tests for TradeLog dataclass."""

    @pytest.fixture
    def sample_trade_log(self):
        return TradeLog(
            timestamp="2024-01-15T14:30:00",
            trade_date="2024-01-15",
            strategy_id="test_strategy",
            symbol="AAPL",
            signal="ENTRY_LONG",
            price_at_signal=185.00,
            simulated_fill=185.10,
            shares=10.0,
            notional_value=1851.00,
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
            insider_intensity=0.5,
            revenue_cagr=0.15,
        )

    def test_trade_log_creation(self, sample_trade_log):
        assert sample_trade_log.symbol == "AAPL"
        assert sample_trade_log.signal == "ENTRY_LONG"
        assert sample_trade_log.simulated_fill == 185.10

    def test_to_json(self, sample_trade_log):
        json_str = sample_trade_log.to_json()
        data = json.loads(json_str)
        assert data["symbol"] == "AAPL"
        assert data["spy_trend"] == 1.0
        assert data["insider_intensity"] == 0.5

    def test_from_json(self, sample_trade_log):
        json_str = sample_trade_log.to_json()
        reconstructed = TradeLog.from_json(json_str)
        assert reconstructed.symbol == sample_trade_log.symbol
        assert reconstructed.signal == sample_trade_log.signal
        assert reconstructed.spy_trend == sample_trade_log.spy_trend

    def test_exit_trade_log_with_pnl(self):
        trade = TradeLog(
            timestamp="2024-01-20T14:30:00",
            trade_date="2024-01-20",
            strategy_id="test_strategy",
            symbol="AAPL",
            signal="EXIT_LONG",
            price_at_signal=195.00,
            simulated_fill=194.90,
            shares=10.0,
            notional_value=1949.00,
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
            pnl=98.00,
            pnl_pct=5.3,
            days_held=5,
            exit_reason="signal",
        )
        assert trade.pnl == 98.00
        assert trade.pnl_pct == 5.3
        assert trade.days_held == 5


class TestSignal:
    """Tests for Signal dataclass."""

    def test_signal_creation(self):
        signal = Signal(
            symbol="AAPL",
            signal_type=SignalType.ENTRY_LONG,
            strategy_id="test_strategy",
            price=185.00,
            timestamp=datetime(2024, 1, 15, 14, 30),
            spy_trend=1.0,
            vix_regime=1.0,
            market_regime="bull_calm",
        )
        assert signal.symbol == "AAPL"
        assert signal.signal_type == SignalType.ENTRY_LONG


class TestPortfolioSnapshot:
    """Tests for PortfolioSnapshot dataclass."""

    @pytest.fixture
    def sample_snapshot(self):
        return PortfolioSnapshot(
            timestamp="2024-01-15T16:00:00",
            trade_date="2024-01-15",
            equity=102500.00,
            cash=50000.00,
            positions_value=52500.00,
            total_pnl=2500.00,
            total_pnl_pct=2.5,
            daily_pnl=500.00,
            daily_pnl_pct=0.49,
            open_positions=5,
            exposure_pct=51.2,
            max_drawdown_pct=1.5,
            total_trades=25,
            winning_trades=15,
            losing_trades=10,
            win_rate=0.6,
            spy_trend=1.0,
            vix_level=15.5,
            market_regime="bull_calm",
        )

    def test_snapshot_creation(self, sample_snapshot):
        assert sample_snapshot.equity == 102500.00
        assert sample_snapshot.win_rate == 0.6

    def test_to_json(self, sample_snapshot):
        json_str = sample_snapshot.to_json()
        data = json.loads(json_str)
        assert data["equity"] == 102500.00
        assert data["open_positions"] == 5


class TestDailySummary:
    """Tests for DailySummary dataclass."""

    @pytest.fixture
    def sample_summary(self):
        return DailySummary(
            date="2024-01-15",
            starting_equity=100000.00,
            ending_equity=101500.00,
            daily_pnl=1500.00,
            daily_pnl_pct=1.5,
            entries=3,
            exits=2,
            stop_losses=0,
            open_positions=6,
            exposure_pct=55.0,
            best_trade={"symbol": "AAPL", "pnl": 500.00, "pnl_pct": 5.0},
            worst_trade={"symbol": "MSFT", "pnl": -150.00, "pnl_pct": -1.5},
            spy_change_pct=0.75,
            vix_level=15.0,
            market_regime="bull_calm",
        )

    def test_summary_creation(self, sample_summary):
        assert sample_summary.daily_pnl == 1500.00
        assert sample_summary.entries == 3
        assert sample_summary.exits == 2

    def test_to_json(self, sample_summary):
        json_str = sample_summary.to_json()
        data = json.loads(json_str)
        assert data["daily_pnl"] == 1500.00
        assert data["best_trade"]["symbol"] == "AAPL"

    def test_new_entries_list(self):
        summary = DailySummary(
            date="2024-01-15",
            starting_equity=100000.00,
            ending_equity=100500.00,
            daily_pnl=500.00,
            daily_pnl_pct=0.5,
            entries=2,
            exits=0,
            stop_losses=0,
            open_positions=2,
            exposure_pct=10.0,
            new_entries=[
                {"symbol": "AAPL", "price": 185.00, "size": 5000.00},
                {"symbol": "MSFT", "price": 380.00, "size": 5000.00},
            ],
        )
        assert len(summary.new_entries) == 2
        assert summary.new_entries[0]["symbol"] == "AAPL"
