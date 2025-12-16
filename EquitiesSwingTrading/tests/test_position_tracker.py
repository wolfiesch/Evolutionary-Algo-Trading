"""Tests for position tracker."""
import pytest
from datetime import date
from pathlib import Path
import tempfile
import json

from execution.shadow.position_tracker import PositionTracker, PositionTrackerConfig
from execution.shadow.models import Position


class TestPositionTrackerConfig:
    """Tests for PositionTrackerConfig."""

    def test_default_values(self):
        config = PositionTrackerConfig()
        assert config.max_positions == 20
        assert config.max_position_pct == 0.05
        assert config.max_exposure_pct == 0.80
        assert config.default_stop_loss_pct == 0.05
        assert config.max_holding_days == 20

    def test_custom_values(self):
        config = PositionTrackerConfig(
            max_positions=10,
            max_position_pct=0.10,
        )
        assert config.max_positions == 10
        assert config.max_position_pct == 0.10


class TestPositionTracker:
    """Tests for PositionTracker."""

    @pytest.fixture
    def tracker(self):
        return PositionTracker()

    @pytest.fixture
    def sample_position(self):
        return Position(
            symbol="AAPL",
            strategy_id="test_strategy",
            entry_date=date(2024, 1, 15),
            entry_price=185.00,
            shares=27.0,
            notional_value=5000.00,
            stop_loss_price=175.75,
        )

    def test_empty_tracker(self, tracker):
        assert len(tracker.positions) == 0
        assert not tracker.has_position("AAPL")

    def test_add_position(self, tracker, sample_position):
        tracker.add_position(sample_position)
        assert tracker.has_position("AAPL")
        assert len(tracker.positions) == 1

    def test_get_position(self, tracker, sample_position):
        tracker.add_position(sample_position)
        pos = tracker.get_position("AAPL")
        assert pos is not None
        assert pos.symbol == "AAPL"
        assert pos.entry_price == 185.00

    def test_get_nonexistent_position(self, tracker):
        pos = tracker.get_position("AAPL")
        assert pos is None

    def test_remove_position(self, tracker, sample_position):
        tracker.add_position(sample_position)
        removed = tracker.remove_position("AAPL")
        assert removed is not None
        assert removed.symbol == "AAPL"
        assert not tracker.has_position("AAPL")

    def test_remove_nonexistent_position(self, tracker):
        removed = tracker.remove_position("AAPL")
        assert removed is None

    def test_get_all_positions(self, tracker):
        pos1 = Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=185.00, shares=27.0, notional_value=5000.00,
        )
        pos2 = Position(
            symbol="MSFT", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=380.00, shares=13.0, notional_value=5000.00,
        )
        tracker.add_position(pos1)
        tracker.add_position(pos2)

        all_positions = tracker.get_all_positions()
        assert len(all_positions) == 2
        symbols = {p.symbol for p in all_positions}
        assert symbols == {"AAPL", "MSFT"}

    def test_can_open_position_success(self, tracker):
        can_open, reason = tracker.can_open_position(
            equity=100000.00,
            position_value=5000.00,  # 5%
        )
        assert can_open is True
        assert reason == "OK"

    def test_can_open_position_max_positions(self, tracker):
        config = PositionTrackerConfig(max_positions=2)
        tracker = PositionTracker(config=config)

        # Add 2 positions
        for i, symbol in enumerate(["AAPL", "MSFT"]):
            pos = Position(
                symbol=symbol, strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=100.00, shares=10.0, notional_value=1000.00,
            )
            tracker.add_position(pos)

        can_open, reason = tracker.can_open_position(100000.00, 1000.00)
        assert can_open is False
        assert "Max positions" in reason

    def test_can_open_position_exceeds_max_size(self, tracker):
        can_open, reason = tracker.can_open_position(
            equity=100000.00,
            position_value=10000.00,  # 10% > 5% max
        )
        assert can_open is False
        assert "exceeds max" in reason

    def test_can_open_position_exceeds_exposure(self, tracker):
        # Add positions totaling 78% exposure (within 80% limit)
        for i, symbol in enumerate(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
                                     "K", "L", "M", "N", "O", "P"]):
            pos = Position(
                symbol=symbol, strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=100.00, shares=48.75, notional_value=4875.00,  # ~4.9% each
            )
            tracker.add_position(pos)

        # Try to add 5% more (total would be ~83% > 80%)
        # Using position value within max_position_pct (5%)
        can_open, reason = tracker.can_open_position(100000.00, 4000.00)
        assert can_open is False
        assert "breach max exposure" in reason

    def test_get_exposure(self, tracker):
        pos = Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=100.00, shares=50.0, notional_value=5000.00,
        )
        tracker.add_position(pos)

        exposure = tracker.get_exposure(100000.00)
        assert exposure == 0.05  # 5%

    def test_get_exposure_value(self, tracker):
        pos1 = Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=100.00, shares=50.0, notional_value=5000.00,
        )
        pos2 = Position(
            symbol="MSFT", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=100.00, shares=30.0, notional_value=3000.00,
        )
        tracker.add_position(pos1)
        tracker.add_position(pos2)

        value = tracker.get_exposure_value()
        assert value == 8000.00

    def test_get_unrealized_pnl(self, tracker, sample_position):
        tracker.add_position(sample_position)

        prices = {"AAPL": 195.00}  # Up from 185
        pnl = tracker.get_unrealized_pnl(prices)
        expected = 5000.00 * (195.00 / 185.00 - 1)
        assert abs(pnl - expected) < 0.01

    def test_get_positions_needing_stop(self, tracker):
        pos = Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
            entry_price=185.00, shares=27.0, notional_value=5000.00,
            stop_loss_price=175.00,
        )
        tracker.add_position(pos)

        # Price below stop
        stops = tracker.get_positions_needing_stop({"AAPL": 170.00})
        assert len(stops) == 1
        assert stops[0][0].symbol == "AAPL"

        # Price above stop
        stops = tracker.get_positions_needing_stop({"AAPL": 180.00})
        assert len(stops) == 0

    def test_get_positions_exceeding_hold_time(self, tracker):
        pos = Position(
            symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 1),
            entry_price=185.00, shares=27.0, notional_value=5000.00,
        )
        tracker.add_position(pos)

        # 30 days later (exceeds 20 day max)
        expired = tracker.get_positions_exceeding_hold_time(date(2024, 1, 31))
        assert len(expired) == 1
        assert expired[0].symbol == "AAPL"

        # 10 days later (within limit)
        expired = tracker.get_positions_exceeding_hold_time(date(2024, 1, 11))
        assert len(expired) == 0

    def test_get_position_summary(self, tracker, sample_position):
        tracker.add_position(sample_position)

        prices = {"AAPL": 195.00}
        summary = tracker.get_position_summary(prices, date(2024, 1, 20))

        assert len(summary) == 1
        assert summary[0]["symbol"] == "AAPL"
        assert summary[0]["current_price"] == 195.00
        assert summary[0]["days_held"] == 5

    def test_clear_all(self, tracker):
        for symbol in ["AAPL", "MSFT", "GOOGL"]:
            pos = Position(
                symbol=symbol, strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=100.00, shares=10.0, notional_value=1000.00,
            )
            tracker.add_position(pos)

        cleared = tracker.clear_all()
        assert len(cleared) == 3
        assert len(tracker.positions) == 0


class TestPositionTrackerPersistence:
    """Tests for position tracker state persistence."""

    def test_save_and_load_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "positions.json"

            # Create tracker and add positions
            tracker1 = PositionTracker(state_path=state_path)
            pos = Position(
                symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=185.00, shares=27.0, notional_value=5000.00,
                stop_loss_price=175.00,
                insider_intensity=0.5,
            )
            tracker1.add_position(pos)

            # Create new tracker that loads state
            tracker2 = PositionTracker(state_path=state_path)

            assert tracker2.has_position("AAPL")
            loaded_pos = tracker2.get_position("AAPL")
            assert loaded_pos.entry_price == 185.00
            assert loaded_pos.insider_intensity == 0.5

    def test_state_file_structure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "positions.json"

            tracker = PositionTracker(state_path=state_path)
            pos = Position(
                symbol="AAPL", strategy_id="test", entry_date=date(2024, 1, 15),
                entry_price=185.00, shares=27.0, notional_value=5000.00,
            )
            tracker.add_position(pos)

            # Check file contents
            with open(state_path, "r") as f:
                state = json.load(f)

            assert "timestamp" in state
            assert "positions" in state
            assert "AAPL" in state["positions"]
            assert state["positions"]["AAPL"]["entry_price"] == 185.00
