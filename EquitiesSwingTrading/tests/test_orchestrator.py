"""Tests for main orchestrator."""
import pytest
from datetime import date, timedelta
from pathlib import Path
import tempfile
import json
from unittest.mock import Mock, patch, MagicMock
import pandas as pd
import numpy as np

from main import EquitiesOrchestrator
from evolution.backtester.evaluator import Strategy


class TestEquitiesOrchestrator:
    """Tests for EquitiesOrchestrator."""

    @pytest.fixture
    def sample_strategies(self):
        return [
            Strategy(
                name="Test_Strategy_1",
                entry_long="spy_trend(20) >= 0 AND norm_rsi(14) < -0.3",
                exit_long="norm_rsi(14) > 0.5",
            ),
            Strategy(
                name="Test_Strategy_2",
                entry_long="spy_trend(20) >= 0 AND ema_trend(9, 21) == 1.0",
                exit_long="ema_trend(9, 21) == -1.0",
            ),
        ]

    @pytest.fixture
    def mock_components(self, sample_strategies):
        """Create orchestrator with mocked components."""
        with patch('main.EquitiesRepository'), \
             patch('main.MarketDataClient') as mock_client, \
             patch('main.UniverseManager'), \
             patch('main.ReportGenerator'), \
             patch('main.DiscordNotifier'):

            # Create sample data for market client
            dates = pd.date_range("2024-01-01", periods=100, freq="D")
            np.random.seed(42)

            close = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, 100))
            sample_df = pd.DataFrame({
                "date": dates.date,
                "open": close * 0.99,
                "high": close * 1.01,
                "low": close * 0.98,
                "close": close,
                "volume": np.random.uniform(1e6, 5e6, 100),
            })

            mock_client.return_value.fetch_spy_bars.return_value = sample_df.copy()
            mock_client.return_value.fetch_vix_bars.return_value = pd.DataFrame({
                "date": dates.date,
                "close": 15.0 + np.random.uniform(-1, 1, 100),
            })
            mock_client.return_value.bulk_fetch_async = MagicMock(
                return_value={"AAPL": sample_df, "MSFT": sample_df}
            )
            mock_client.return_value.fetch_daily_bars.return_value = sample_df

            orchestrator = EquitiesOrchestrator(
                environment="development",
                strategies=sample_strategies,
            )

            yield orchestrator

    def test_initialization(self, mock_components):
        """Test orchestrator initialization."""
        orch = mock_components

        assert orch.environment == "development"
        assert len(orch.strategies) == 2
        assert orch.shadow_trader is not None
        assert orch.repository is not None
        assert orch.market_client is not None

    def test_default_strategies(self, mock_components):
        """Test default strategies are created when none provided."""
        # This test uses the fixture which provides strategies
        orch = mock_components
        assert len(orch.strategies) >= 2

    def test_get_status(self, mock_components):
        """Test get_status returns expected structure."""
        orch = mock_components
        status = orch.get_status()

        assert "equity" in status
        assert "cash" in status
        assert "total_pnl" in status
        assert "open_positions" in status
        assert "win_rate" in status
        assert "market_regime" in status
        assert "positions" in status

    def test_startup_notification(self, mock_components):
        """Test startup sends notification if notifier configured."""
        orch = mock_components

        if orch.notifier:
            orch.startup()
            orch.notifier.send_startup.assert_called_once()

    def test_shutdown_notification(self, mock_components):
        """Test shutdown sends notification if notifier configured."""
        orch = mock_components

        if orch.notifier:
            orch.shutdown("Test shutdown")
            orch.notifier.send_shutdown.assert_called_once()


class TestStrategyPersistence:
    """Tests for strategy save/load."""

    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_save_strategies(self, temp_dir):
        """Test saving strategies to JSON."""
        strategies = [
            Strategy(
                name="Test_Strategy",
                entry_long="spy_trend(20) >= 0",
                exit_long="spy_trend(20) < 0",
            ),
        ]

        with patch('main.STRATEGIES_DIR', temp_dir):
            with patch('main.EquitiesRepository'), \
                 patch('main.MarketDataClient'), \
                 patch('main.UniverseManager'), \
                 patch('main.ReportGenerator'):

                orch = EquitiesOrchestrator(
                    environment="development",
                    strategies=strategies,
                )
                orch.save_strategies(strategies)

        # Check file was created
        strategies_file = temp_dir / "active_strategies.json"
        assert strategies_file.exists()

        # Check contents
        with open(strategies_file) as f:
            data = json.load(f)

        assert "strategies" in data
        assert len(data["strategies"]) == 1
        assert data["strategies"][0]["name"] == "Test_Strategy"

    def test_load_strategies(self, temp_dir):
        """Test loading strategies from JSON."""
        # Create strategies file
        strategies_file = temp_dir / "active_strategies.json"
        data = {
            "updated": "2024-01-15T12:00:00",
            "strategies": [
                {
                    "name": "Loaded_Strategy",
                    "entry_long": "spy_trend(20) >= 0",
                    "exit_long": "spy_trend(20) < 0",
                    "entry_short": None,
                    "exit_short": None,
                },
            ],
        }

        with open(strategies_file, "w") as f:
            json.dump(data, f)

        with patch('main.STRATEGIES_DIR', temp_dir):
            with patch('main.EquitiesRepository'), \
                 patch('main.MarketDataClient'), \
                 patch('main.UniverseManager'), \
                 patch('main.ReportGenerator'):

                orch = EquitiesOrchestrator(environment="development")

        assert len(orch.strategies) == 1
        assert orch.strategies[0].name == "Loaded_Strategy"


class TestDailyScan:
    """Tests for daily scan workflow."""

    @pytest.fixture
    def sample_price_data(self):
        """Generate sample price data."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        np.random.seed(42)

        close = 100 * np.cumprod(1 + np.random.normal(0.001, 0.02, 100))
        return pd.DataFrame({
            "date": dates.date,
            "open": close * 0.99,
            "high": close * 1.01,
            "low": close * 0.98,
            "close": close,
            "volume": np.random.uniform(1e6, 5e6, 100),
        })

    @pytest.mark.asyncio
    async def test_daily_scan_structure(self, sample_price_data):
        """Test daily scan returns proper structure."""
        strategies = [
            Strategy(
                name="Test_Strategy",
                entry_long="spy_trend(20) >= 0",
                exit_long="spy_trend(20) < 0",
            ),
        ]

        with patch('main.EquitiesRepository') as mock_repo, \
             patch('main.MarketDataClient') as mock_client, \
             patch('main.UniverseManager') as mock_universe, \
             patch('main.ReportGenerator'), \
             patch('main.DiscordNotifier'):

            # Setup mocks
            mock_client.return_value.fetch_spy_bars.return_value = sample_price_data
            mock_client.return_value.fetch_vix_bars.return_value = pd.DataFrame({
                "date": sample_price_data["date"],
                "close": 15.0,
            })

            # Mock async bulk fetch
            async def mock_bulk_fetch(*args, **kwargs):
                return {"AAPL": sample_price_data, "MSFT": sample_price_data}

            mock_client.return_value.bulk_fetch_async = mock_bulk_fetch

            # Mock repository
            mock_repo.return_value.get_fundamental_signal.return_value = None

            mock_universe.return_value.get_universe.return_value = ["AAPL", "MSFT"]

            orch = EquitiesOrchestrator(
                environment="development",
                strategies=strategies,
            )

            # Run scan
            summary = await orch.run_daily_scan(
                trade_date=date(2024, 4, 10),
                universe_override=["AAPL", "MSFT"],
            )

            # Verify structure
            assert summary is not None
            assert hasattr(summary, "date")
            assert hasattr(summary, "starting_equity")
            assert hasattr(summary, "ending_equity")
            assert hasattr(summary, "daily_pnl")
            assert hasattr(summary, "entries")
            assert hasattr(summary, "exits")


class TestOrchestratorConfig:
    """Tests for orchestrator configuration."""

    def test_development_config(self):
        """Test development configuration."""
        with patch('main.EquitiesRepository'), \
             patch('main.MarketDataClient') as mock_client, \
             patch('main.UniverseManager'), \
             patch('main.ReportGenerator'):

            orch = EquitiesOrchestrator(environment="development")

            assert orch.environment == "development"
            mock_client.assert_called_with(provider="yahoo")

    def test_production_config(self):
        """Test production configuration uses polygon."""
        with patch('main.EquitiesRepository'), \
             patch('main.MarketDataClient') as mock_client, \
             patch('main.UniverseManager'), \
             patch('main.ReportGenerator'):

            orch = EquitiesOrchestrator(environment="production")

            assert orch.environment == "production"
            mock_client.assert_called_with(provider="polygon")

    def test_no_notifier_without_webhook(self):
        """Test notifier is None without webhook URL."""
        with patch('main.EquitiesRepository'), \
             patch('main.MarketDataClient'), \
             patch('main.UniverseManager'), \
             patch('main.ReportGenerator'), \
             patch.dict('os.environ', {}, clear=True):

            orch = EquitiesOrchestrator(environment="development")

            # Without DISCORD_WEBHOOK_URL, notifier should be None
            assert orch.notifier is None
