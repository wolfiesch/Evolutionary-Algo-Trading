"""Tests for equities shadow trader."""
import pytest
from datetime import date
from pathlib import Path
import tempfile
import pandas as pd
import numpy as np

from execution.shadow.trader import EquitiesShadowTrader, ShadowTraderConfig
from evolution.backtester.evaluator import Strategy


class TestShadowTraderConfig:
    """Tests for ShadowTraderConfig."""

    def test_default_values(self):
        config = ShadowTraderConfig()
        assert config.initial_equity == 100_000.0
        assert config.risk_per_trade == 0.01
        assert config.max_position_pct == 0.05
        assert config.max_open_positions == 20
        assert config.default_stop_loss_pct == 0.05

    def test_custom_values(self):
        config = ShadowTraderConfig(
            initial_equity=50_000.0,
            max_position_pct=0.10,
        )
        assert config.initial_equity == 50_000.0
        assert config.max_position_pct == 0.10


class TestEquitiesShadowTrader:
    """Tests for EquitiesShadowTrader."""

    @pytest.fixture
    def sample_strategy(self):
        return Strategy(
            name="Test_Strategy",
            entry_long="spy_trend(20) >= 0 AND norm_rsi(14) < -0.3",
            exit_long="norm_rsi(14) > 0.5",
        )

    @pytest.fixture
    def trader(self, sample_strategy):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            yield EquitiesShadowTrader(
                strategies=[sample_strategy],
                config=config,
            )

    @pytest.fixture
    def sample_candles(self):
        """Generate sample OHLCV data."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        np.random.seed(42)

        # Create trending price series
        returns = np.random.normal(0.001, 0.02, 100)
        close = 100 * np.cumprod(1 + returns)

        return pd.DataFrame({
            "date": dates,
            "open": close * (1 + np.random.uniform(-0.01, 0.01, 100)),
            "high": close * (1 + np.abs(np.random.normal(0, 0.01, 100))),
            "low": close * (1 - np.abs(np.random.normal(0, 0.01, 100))),
            "close": close,
            "volume": np.random.uniform(1e6, 5e6, 100),
        })

    @pytest.fixture
    def sample_spy_data(self, sample_candles):
        """SPY benchmark data (uptrend)."""
        df = sample_candles.copy()
        # Make it slightly more bullish
        df["close"] = df["close"] * 1.02
        return df

    @pytest.fixture
    def sample_vix_data(self):
        """VIX data (low volatility)."""
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        return pd.DataFrame({
            "date": dates,
            "open": 15.0,
            "high": 16.0,
            "low": 14.0,
            "close": 15.0 + np.random.uniform(-1, 1, 100),
            "volume": np.random.uniform(1e6, 5e6, 100),
        })

    def test_trader_initialization(self, trader):
        assert trader.equity == 100_000.0
        assert trader.cash == 100_000.0
        assert trader.trade_count == 0
        assert len(trader.strategies) == 1

    def test_classify_regime_bull_calm(self, trader):
        # Create bullish SPY data (10% gain over 100 days)
        spy_data = pd.DataFrame({
            "close": np.linspace(100, 115, 100),  # Clear uptrend >2%
        })
        # Low VIX
        vix_data = pd.DataFrame({
            "close": np.full(100, 15.0),
        })

        regime = trader._classify_regime(spy_data, vix_data)
        assert regime == "bull_calm"

    def test_classify_regime_bear_volatile(self, trader):
        # Create bearish SPY data (10% drop over 100 days)
        spy_data = pd.DataFrame({
            "close": np.linspace(115, 100, 100),  # Clear downtrend >2%
        })
        # High VIX
        vix_data = pd.DataFrame({
            "close": np.full(100, 30.0),
        })

        regime = trader._classify_regime(spy_data, vix_data)
        assert regime == "bear_volatile"

    def test_classify_regime_sideways(self, trader):
        # Create flat SPY data (<2% change)
        spy_data = pd.DataFrame({
            "close": np.full(100, 100.0),
        })
        vix_data = pd.DataFrame({
            "close": np.full(100, 18.0),
        })

        regime = trader._classify_regime(spy_data, vix_data)
        assert regime == "sideways"

    def test_win_rate_empty(self, trader):
        assert trader.win_rate == 0.0

    def test_total_pnl_empty(self, trader):
        assert trader.total_pnl == 0.0

    def test_total_pnl_pct_empty(self, trader):
        assert trader.total_pnl_pct == 0.0

    def test_max_drawdown_pct_empty(self, trader):
        assert trader.max_drawdown_pct == 0.0


class TestShadowTraderPositionManagement:
    """Tests for position management in shadow trader."""

    @pytest.fixture
    def sample_strategy(self):
        return Strategy(
            name="Test_Strategy",
            entry_long="spy_trend(20) >= 0",
            exit_long="spy_trend(20) < 0",
        )

    @pytest.fixture
    def trader_with_config(self, sample_strategy):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                initial_equity=100_000.0,
                max_position_pct=0.05,
                max_open_positions=5,
                risk_per_trade=0.01,
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            yield EquitiesShadowTrader(
                strategies=[sample_strategy],
                config=config,
            )

    def test_position_tracker_initialized(self, trader_with_config):
        tracker = trader_with_config.position_tracker
        assert tracker is not None
        assert tracker.config.max_positions == 5
        assert tracker.config.max_position_pct == 0.05


class TestShadowTraderMetrics:
    """Tests for shadow trader metric calculations."""

    @pytest.fixture
    def sample_strategy(self):
        return Strategy(
            name="Test_Strategy",
            entry_long="spy_trend(20) >= 0",
            exit_long="spy_trend(20) < 0",
        )

    @pytest.fixture
    def trader(self, sample_strategy):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ShadowTraderConfig(
                log_dir=Path(tmpdir) / "logs",
                state_dir=Path(tmpdir) / "state",
            )
            yield EquitiesShadowTrader(
                strategies=[sample_strategy],
                config=config,
            )

    def test_win_rate_calculation(self, trader):
        # Simulate some trades
        trader.trade_count = 10
        trader.winning_trades = 6
        trader.losing_trades = 4

        assert trader.win_rate == 0.6

    def test_total_pnl_calculation(self, trader):
        trader.equity = 105_000.0
        assert trader.total_pnl == 5_000.0

    def test_total_pnl_pct_calculation(self, trader):
        trader.equity = 105_000.0
        assert abs(trader.total_pnl_pct - 5.0) < 0.01

    def test_max_drawdown_calculation(self, trader):
        trader.peak_equity = 110_000.0
        trader.equity = 100_000.0
        expected_dd = (110_000.0 - 100_000.0) / 110_000.0 * 100
        assert abs(trader.max_drawdown_pct - expected_dd) < 0.01
