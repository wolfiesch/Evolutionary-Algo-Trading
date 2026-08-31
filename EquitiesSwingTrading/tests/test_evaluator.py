"""
Tests for equities strategy evaluator.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

import sys
sys.path.insert(0, ".")

from evolution.backtester.evaluator import (
    EquitiesEvaluator,
    Strategy,
    FundamentalContext,
    create_evaluator,
    create_simple_evaluator,
    MOMENTUM_PULLBACK,
    INSIDER_MOMENTUM,
)


class TestStrategy:
    """Tests for Strategy dataclass."""

    def test_strategy_creation(self):
        """Should create strategy with expressions."""
        strategy = Strategy(
            name="Test_Strategy",
            entry_long="norm_rsi(14) < -0.3",
            exit_long="norm_rsi(14) > 0.5",
        )
        assert strategy.name == "Test_Strategy"
        assert strategy.entry_long == "norm_rsi(14) < -0.3"
        assert strategy.exit_long == "norm_rsi(14) > 0.5"

    def test_strategy_default_values(self):
        """Should have sensible defaults."""
        strategy = Strategy(
            name="Test",
            entry_long="True",
            exit_long="False",
        )
        assert strategy.entry_short is None
        assert strategy.exit_short is None
        assert strategy.generation == 0
        assert strategy.fitness == 0.0

    def test_example_strategies_defined(self):
        """Example strategies should be defined."""
        assert MOMENTUM_PULLBACK is not None
        assert MOMENTUM_PULLBACK.name == "Momentum_Pullback"
        assert "spy_trend" in MOMENTUM_PULLBACK.entry_long


class TestFundamentalContext:
    """Tests for FundamentalContext dataclass."""

    def test_fundamental_context_creation(self):
        """Should create context with fundamental signals."""
        context = FundamentalContext(
            symbol="AAPL",
            as_of_date=date.today(),
            insider_intensity=0.5,
            revenue_cagr=0.15,
            earnings_quality=0.8,
        )
        assert context.symbol == "AAPL"
        assert context.insider_intensity == 0.5
        assert context.revenue_cagr == 0.15

    def test_fundamental_context_defaults(self):
        """Should default to zero values."""
        context = FundamentalContext(
            symbol="AAPL",
            as_of_date=date.today(),
        )
        assert context.insider_intensity == 0.0
        assert context.insider_cluster == 0.0
        assert context.fundamental_score == 0.0


class TestSimpleEvaluator:
    """Tests for create_simple_evaluator."""

    @pytest.fixture
    def sample_candles(self):
        """Create sample OHLCV data."""
        n = 50
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]
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
        n = 50
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]
        return pd.DataFrame({
            "date": dates,
            "close": 400 + np.random.randn(n).cumsum(),
        })

    def test_simple_evaluator_returns_string(self, sample_candles, sample_benchmark):
        """Should return valid signal string."""
        def always_enter(candles, benchmark):
            return True

        def always_exit(candles, benchmark):
            return True

        evaluator = create_simple_evaluator(always_enter, always_exit)
        signal = evaluator(sample_candles, sample_benchmark, has_position=False)
        assert signal in ["ENTRY_LONG", "EXIT_LONG", "HOLD"]

    def test_simple_evaluator_entry_when_no_position(self, sample_candles, sample_benchmark):
        """Should check entry when no position."""
        def enter_condition(candles, benchmark):
            return True

        def exit_condition(candles, benchmark):
            return True

        evaluator = create_simple_evaluator(enter_condition, exit_condition)
        signal = evaluator(sample_candles, sample_benchmark, has_position=False)
        assert signal == "ENTRY_LONG"

    def test_simple_evaluator_exit_when_has_position(self, sample_candles, sample_benchmark):
        """Should check exit when has position."""
        def enter_condition(candles, benchmark):
            return True

        def exit_condition(candles, benchmark):
            return True

        evaluator = create_simple_evaluator(enter_condition, exit_condition)
        signal = evaluator(sample_candles, sample_benchmark, has_position=True)
        assert signal == "EXIT_LONG"

    def test_simple_evaluator_hold_when_no_conditions_met(self, sample_candles, sample_benchmark):
        """Should return HOLD when no conditions met."""
        def never_enter(candles, benchmark):
            return False

        def never_exit(candles, benchmark):
            return False

        evaluator = create_simple_evaluator(never_enter, never_exit)
        signal = evaluator(sample_candles, sample_benchmark, has_position=False)
        assert signal == "HOLD"

    def test_simple_evaluator_handles_exceptions(self, sample_candles, sample_benchmark):
        """Should return HOLD on exception."""
        def error_condition(candles, benchmark):
            raise ValueError("Test error")

        evaluator = create_simple_evaluator(error_condition, error_condition)
        signal = evaluator(sample_candles, sample_benchmark, has_position=False)
        assert signal == "HOLD"


class TestEquitiesEvaluator:
    """Tests for EquitiesEvaluator class."""

    @pytest.fixture
    def sample_candles(self):
        """Create sample OHLCV data."""
        n = 100
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]
        prices = 100 + np.random.randn(n).cumsum()
        return pd.DataFrame({
            "date": dates,
            "open": prices * 0.999,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.randint(1000000, 5000000, n),
        })

    @pytest.fixture
    def sample_benchmark(self):
        """Create sample benchmark data."""
        n = 100
        dates = [date.today() - timedelta(days=n-i) for i in range(n)]
        return pd.DataFrame({
            "date": dates,
            "close": 400 + np.random.randn(n).cumsum(),
        })

    def test_evaluator_creation(self):
        """Should create evaluator from strategy."""
        strategy = Strategy(
            name="Test",
            entry_long="True",
            exit_long="False",
        )
        evaluator = EquitiesEvaluator(strategy)
        assert evaluator.strategy == strategy

    def test_evaluator_with_fundamental_context(self):
        """Should incorporate fundamental context."""
        strategy = Strategy(
            name="Test",
            entry_long="insider_intensity > 0.3",
            exit_long="False",
        )
        context = FundamentalContext(
            symbol="AAPL",
            as_of_date=date.today(),
            insider_intensity=0.5,
        )
        evaluator = EquitiesEvaluator(strategy, fundamental_context=context)
        assert evaluator.fundamental_context.insider_intensity == 0.5

    def test_evaluate_returns_valid_signal(self, sample_candles, sample_benchmark):
        """Should return valid signal string."""
        strategy = Strategy(
            name="Test",
            entry_long="True",
            exit_long="True",
        )
        evaluator = EquitiesEvaluator(strategy)
        signal = evaluator.evaluate(sample_candles, sample_benchmark, has_position=False)
        assert signal in ["ENTRY_LONG", "EXIT_LONG", "HOLD"]

    def test_empty_expression_returns_hold(self, sample_candles, sample_benchmark):
        """Should return HOLD for empty expression."""
        strategy = Strategy(
            name="Test",
            entry_long="",
            exit_long="",
        )
        evaluator = EquitiesEvaluator(strategy)
        signal = evaluator.evaluate(sample_candles, sample_benchmark, has_position=False)
        assert signal == "HOLD"


class TestCreateEvaluator:
    """Tests for create_evaluator convenience function."""

    def test_create_evaluator_returns_callable(self):
        """Should return callable evaluator function."""
        strategy = Strategy(
            name="Test",
            entry_long="True",
            exit_long="False",
        )
        evaluator = create_evaluator(strategy)
        assert callable(evaluator)

    def test_create_evaluator_with_context(self):
        """Should create evaluator with fundamental context."""
        strategy = Strategy(
            name="Test",
            entry_long="True",
            exit_long="False",
        )
        context = FundamentalContext(
            symbol="AAPL",
            as_of_date=date.today(),
        )
        evaluator = create_evaluator(strategy, fundamental_context=context)
        assert callable(evaluator)


class TestPrimitiveRegistry:
    """Tests for primitive registry."""

    def test_primitives_registered(self):
        """Should have primitives registered."""
        assert "ema_trend" in EquitiesEvaluator.PRIMITIVES
        assert "norm_rsi" in EquitiesEvaluator.PRIMITIVES
        assert "spy_trend" in EquitiesEvaluator.PRIMITIVES

    def test_fundamental_keys_defined(self):
        """Should have fundamental keys defined."""
        assert "insider_intensity" in EquitiesEvaluator.FUNDAMENTAL_KEYS
        assert "revenue_cagr" in EquitiesEvaluator.FUNDAMENTAL_KEYS
        assert "earnings_quality" in EquitiesEvaluator.FUNDAMENTAL_KEYS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
