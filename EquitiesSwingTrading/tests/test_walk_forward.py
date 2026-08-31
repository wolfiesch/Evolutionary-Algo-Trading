"""
Tests for walk-forward validation.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

import sys
sys.path.insert(0, ".")

from evolution.backtester.walk_forward import (
    WalkForwardValidator,
    WalkForwardConfig,
    WalkForwardPeriod,
    WalkForwardResults,
    run_walk_forward,
)
from evolution.fitness.calculator import BacktestResults


class TestWalkForwardConfig:
    """Tests for WalkForwardConfig."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = WalkForwardConfig()
        assert config.train_days == 252  # 1 year
        assert config.test_days == 63    # 3 months
        assert config.step_days == 63    # 3 months
        assert config.min_total_days == 504  # 2 years

    def test_custom_config(self):
        """Should accept custom config values."""
        config = WalkForwardConfig(
            train_days=126,
            test_days=21,
            step_days=21,
        )
        assert config.train_days == 126
        assert config.test_days == 21


class TestWalkForwardPeriod:
    """Tests for WalkForwardPeriod."""

    def test_period_creation(self):
        """Should create period with results."""
        period = WalkForwardPeriod(
            period_index=0,
            train_start=date(2024, 1, 1),
            train_end=date(2024, 6, 30),
            test_start=date(2024, 7, 1),
            test_end=date(2024, 9, 30),
            train_sharpe=1.5,
            test_sharpe=1.0,
            test_trades=10,
        )
        assert period.period_index == 0
        assert period.train_sharpe == 1.5
        assert period.test_sharpe == 1.0

    def test_period_passed_property(self):
        """Should evaluate passed correctly."""
        # Passing period
        passing = WalkForwardPeriod(
            period_index=0,
            train_start=date.today(),
            train_end=date.today(),
            test_start=date.today(),
            test_end=date.today(),
            test_sharpe=0.5,
            test_trades=10,
        )
        assert passing.passed is True

        # Failing period (negative Sharpe)
        failing = WalkForwardPeriod(
            period_index=0,
            train_start=date.today(),
            train_end=date.today(),
            test_start=date.today(),
            test_end=date.today(),
            test_sharpe=-0.5,
            test_trades=10,
        )
        assert failing.passed is False

        # Failing period (too few trades)
        few_trades = WalkForwardPeriod(
            period_index=0,
            train_start=date.today(),
            train_end=date.today(),
            test_start=date.today(),
            test_end=date.today(),
            test_sharpe=1.0,
            test_trades=3,
        )
        assert few_trades.passed is False


class TestWalkForwardResults:
    """Tests for WalkForwardResults."""

    def test_results_default_values(self):
        """Should have sensible defaults."""
        results = WalkForwardResults()
        assert results.total_periods == 0
        assert results.passed_periods == 0
        assert results.consistency_score == 0.0

    def test_is_robust_property(self):
        """Should evaluate robustness correctly."""
        # Robust results
        robust = WalkForwardResults(
            consistency_score=0.7,
            avg_test_sharpe=0.5,
            worst_test_sharpe=-1.0,
        )
        assert robust.is_robust is True

        # Not robust (low consistency)
        low_consistency = WalkForwardResults(
            consistency_score=0.3,
            avg_test_sharpe=0.5,
            worst_test_sharpe=-1.0,
        )
        assert low_consistency.is_robust is False

        # Not robust (negative avg Sharpe)
        negative_sharpe = WalkForwardResults(
            consistency_score=0.7,
            avg_test_sharpe=-0.1,
            worst_test_sharpe=-1.0,
        )
        assert negative_sharpe.is_robust is False


class TestWalkForwardValidator:
    """Tests for WalkForwardValidator."""

    @pytest.fixture
    def validator(self):
        """Create validator with short windows for testing."""
        config = WalkForwardConfig(
            train_days=60,
            test_days=20,
            step_days=20,
            min_total_days=100,
        )
        return WalkForwardValidator(config)

    @pytest.fixture
    def sample_candles(self):
        """Create sample candle data."""
        n = 200
        dates = pd.date_range(end=date.today(), periods=n, freq='D')
        return pd.DataFrame({
            "date": dates,
            "open": 100 + np.random.randn(n).cumsum(),
            "high": 100 + np.random.randn(n).cumsum() + 1,
            "low": 100 + np.random.randn(n).cumsum() - 1,
            "close": 100 + np.random.randn(n).cumsum(),
            "volume": np.random.randint(1000000, 5000000, n),
        })

    @pytest.fixture
    def sample_benchmark(self):
        """Create sample benchmark data."""
        n = 200
        dates = pd.date_range(end=date.today(), periods=n, freq='D')
        return pd.DataFrame({
            "date": dates,
            "close": 400 + np.random.randn(n).cumsum(),
        })

    def test_validator_creation(self, validator):
        """Should create validator with config."""
        assert validator.config.train_days == 60
        assert validator.config.test_days == 20

    def test_generate_periods(self, validator, sample_candles):
        """Should generate correct number of periods."""
        periods = validator._generate_periods(sample_candles)
        assert len(periods) > 0
        for train_slice, test_slice in periods:
            assert train_slice[1] - train_slice[0] == 60
            assert test_slice[1] - test_slice[0] == 20

    def test_insufficient_data_returns_empty(self, validator):
        """Should return empty results for insufficient data."""
        short_candles = pd.DataFrame({
            "close": [100, 101, 102],
        })

        def dummy_evaluator(c, b, has_pos):
            return "HOLD"

        def dummy_backtest(candles, benchmark, evaluator):
            return BacktestResults(trade_count=10, sharpe_ratio=1.0)

        results = validator.validate(
            dummy_evaluator, short_candles, short_candles, dummy_backtest
        )
        assert results.total_periods == 0

    def test_validate_returns_results(self, validator, sample_candles, sample_benchmark):
        """Should return WalkForwardResults."""
        def dummy_evaluator(c, b, has_pos):
            return "HOLD"

        def dummy_backtest(candles, benchmark, evaluator):
            return BacktestResults(trade_count=10, sharpe_ratio=1.0)

        results = validator.validate(
            dummy_evaluator, sample_candles, sample_benchmark, dummy_backtest
        )
        assert isinstance(results, WalkForwardResults)
        assert results.total_periods > 0

    def test_calculate_aggregates(self, validator):
        """Should calculate aggregate metrics correctly."""
        results = WalkForwardResults()
        results.periods = [
            WalkForwardPeriod(
                period_index=0,
                train_start=date.today(),
                train_end=date.today(),
                test_start=date.today(),
                test_end=date.today(),
                train_sharpe=1.5,
                test_sharpe=1.0,
                test_trades=10,
                test_drawdown=0.05,
                sharpe_degradation=-0.5,
            ),
            WalkForwardPeriod(
                period_index=1,
                train_start=date.today(),
                train_end=date.today(),
                test_start=date.today(),
                test_end=date.today(),
                train_sharpe=1.2,
                test_sharpe=0.8,
                test_trades=8,
                test_drawdown=0.08,
                sharpe_degradation=-0.4,
            ),
        ]
        results.total_periods = 2

        validator._calculate_aggregates(results)

        assert results.passed_periods == 2
        assert results.consistency_score == 1.0
        assert results.avg_train_sharpe == 1.35
        assert results.avg_test_sharpe == 0.9
        assert results.worst_test_sharpe == 0.8
        assert results.worst_test_drawdown == 0.08


class TestRunWalkForward:
    """Tests for run_walk_forward convenience function."""

    @pytest.fixture
    def sample_candles(self):
        """Create sample candle data."""
        n = 200
        dates = pd.date_range(end=date.today(), periods=n, freq='D')
        return pd.DataFrame({
            "date": dates,
            "close": 100 + np.random.randn(n).cumsum(),
        })

    def test_run_walk_forward_returns_results(self, sample_candles):
        """Should return WalkForwardResults."""
        config = WalkForwardConfig(
            train_days=60,
            test_days=20,
            step_days=20,
            min_total_days=100,
        )

        def dummy_evaluator(c, b, has_pos):
            return "HOLD"

        def dummy_backtest(candles, benchmark, evaluator):
            return BacktestResults(trade_count=10, sharpe_ratio=1.0)

        results = run_walk_forward(
            dummy_evaluator, sample_candles, sample_candles, dummy_backtest, config
        )
        assert isinstance(results, WalkForwardResults)


class TestPeriodGeneration:
    """Tests for period slicing logic."""

    def test_period_boundaries_correct(self):
        """Period boundaries should not overlap incorrectly."""
        config = WalkForwardConfig(
            train_days=100,
            test_days=25,
            step_days=25,
            min_total_days=125,
        )
        validator = WalkForwardValidator(config)

        n = 200
        candles = pd.DataFrame({"close": range(n)})
        periods = validator._generate_periods(candles)

        for train_slice, test_slice in periods:
            # Test should start where train ends
            assert test_slice[0] == train_slice[1]
            # No overlap between train and test
            assert train_slice[1] <= test_slice[0]

    def test_step_size_respected(self):
        """Periods should step by step_days."""
        config = WalkForwardConfig(
            train_days=60,
            test_days=20,
            step_days=30,  # Custom step
            min_total_days=80,
        )
        validator = WalkForwardValidator(config)

        n = 200
        candles = pd.DataFrame({"close": range(n)})
        periods = validator._generate_periods(candles)

        for i in range(1, len(periods)):
            prev_train_start = periods[i-1][0][0]
            curr_train_start = periods[i][0][0]
            assert curr_train_start - prev_train_start == 30


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
