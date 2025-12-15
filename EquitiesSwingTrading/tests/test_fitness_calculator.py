"""
Tests for equities fitness calculator.
"""

import pytest
import pandas as pd
import numpy as np

import sys
sys.path.insert(0, ".")

from evolution.fitness.calculator import (
    EquitiesFitnessCalculator,
    FitnessConfig,
    FitnessResult,
    BacktestResults,
    calculate_sharpe,
    calculate_max_drawdown,
    calculate_fitness,
)


class TestFitnessCalculator:
    """Tests for EquitiesFitnessCalculator."""

    @pytest.fixture
    def calculator(self):
        """Create default calculator."""
        return EquitiesFitnessCalculator()

    @pytest.fixture
    def good_results(self):
        """Create good backtest results."""
        # Include some drawdown: peak at 105000, dip to 103000 (1.9% DD)
        equity = pd.Series([100000, 102000, 105000, 103000, 104500, 105500, 106000])
        return BacktestResults(
            equity_curve=equity,
            final_equity=106000,
            trade_count=25,
            win_count=15,
            loss_count=10,
            total_return=0.06,
            sharpe_ratio=calculate_sharpe(equity),
            max_drawdown=calculate_max_drawdown(equity),
            win_rate=0.60,
        )

    @pytest.fixture
    def poor_results(self):
        """Create poor backtest results (high drawdown)."""
        equity = pd.Series([100000, 95000, 90000, 85000, 80000, 75000, 70000])
        return BacktestResults(
            equity_curve=equity,
            final_equity=70000,
            trade_count=25,
            sharpe_ratio=calculate_sharpe(equity),
            max_drawdown=calculate_max_drawdown(equity),
        )

    def test_calculate_good_results(self, calculator, good_results):
        """Should calculate positive fitness for good results."""
        result = calculator.calculate(good_results)
        assert isinstance(result, FitnessResult)
        assert not result.is_disqualified
        assert result.score > 0

    def test_disqualify_too_few_trades(self, calculator):
        """Should disqualify for too few trades."""
        results = BacktestResults(trade_count=3)
        fitness = calculator.calculate(results)
        assert fitness.is_disqualified
        assert "Too few trades" in fitness.disqualification_reason

    def test_disqualify_high_drawdown(self, calculator, poor_results):
        """Should disqualify for extreme drawdown."""
        poor_results.max_drawdown = 0.55  # 55%
        fitness = calculator.calculate(poor_results)
        assert fitness.is_disqualified
        assert "drawdown" in fitness.disqualification_reason.lower()

    def test_drawdown_penalty_applied(self, calculator, good_results):
        """Should apply drawdown penalty."""
        result = calculator.calculate(good_results)
        assert result.drawdown_penalty > 0

    def test_trade_penalty_low_count(self, calculator):
        """Should apply penalty for trades below threshold."""
        results = BacktestResults(
            trade_count=10,  # Below 20 threshold
            sharpe_ratio=1.5,
            max_drawdown=0.10,
        )
        result = calculator.calculate(results)
        assert result.trade_penalty > 0

    def test_no_trade_penalty_high_count(self, calculator):
        """Should not penalize high trade counts."""
        results = BacktestResults(
            trade_count=30,  # Above 20 threshold
            sharpe_ratio=1.5,
            max_drawdown=0.10,
        )
        result = calculator.calculate(results)
        assert result.trade_penalty == 0


class TestRegimeScoring:
    """Tests for regime-aware fitness scoring."""

    @pytest.fixture
    def calculator(self):
        return EquitiesFitnessCalculator()

    @pytest.fixture
    def base_results(self):
        return BacktestResults(
            trade_count=25,
            sharpe_ratio=1.5,
            max_drawdown=0.10,
        )

    def test_regime_bonus_applied(self, calculator, base_results):
        """Should apply bonus for consistent regime performance."""
        regime_results = {
            "bull_calm": BacktestResults(sharpe_ratio=0.8),
            "bull_volatile": BacktestResults(sharpe_ratio=0.6),
            "bear_calm": BacktestResults(sharpe_ratio=0.7),
            "bear_volatile": BacktestResults(sharpe_ratio=0.5),
            "sideways": BacktestResults(sharpe_ratio=0.9),
        }
        result = calculator.calculate(base_results, regime_results)
        assert result.regime_bonus > 0

    def test_regime_penalty_for_negative(self, calculator, base_results):
        """Should penalize negative Sharpe in any regime."""
        regime_results = {
            "bull_calm": BacktestResults(sharpe_ratio=1.0),
            "bull_volatile": BacktestResults(sharpe_ratio=-0.5),  # Negative
            "bear_calm": BacktestResults(sharpe_ratio=0.8),
            "bear_volatile": BacktestResults(sharpe_ratio=-0.3),  # Negative
            "sideways": BacktestResults(sharpe_ratio=0.5),
        }
        result = calculator.calculate(base_results, regime_results)
        assert result.regime_penalty > 0

    def test_regime_scores_tracked(self, calculator, base_results):
        """Should track individual regime scores."""
        regime_results = {
            "bull_calm": BacktestResults(sharpe_ratio=1.2),
            "sideways": BacktestResults(sharpe_ratio=0.8),
        }
        result = calculator.calculate(base_results, regime_results)
        assert "bull_calm" in result.regime_scores
        assert result.regime_scores["bull_calm"] == 1.2


class TestCalculateSharpe:
    """Tests for Sharpe ratio calculation."""

    def test_sharpe_positive_returns(self):
        """Should calculate positive Sharpe for upward equity."""
        equity = pd.Series([100, 101, 102, 103, 104, 105])
        sharpe = calculate_sharpe(equity)
        assert sharpe > 0

    def test_sharpe_negative_returns(self):
        """Should calculate negative Sharpe for downward equity."""
        equity = pd.Series([100, 99, 98, 97, 96, 95])
        sharpe = calculate_sharpe(equity)
        assert sharpe < 0

    def test_sharpe_flat_returns_zero(self):
        """Should return 0 for flat equity."""
        equity = pd.Series([100, 100, 100, 100, 100])
        sharpe = calculate_sharpe(equity)
        assert sharpe == 0.0

    def test_sharpe_clamped(self):
        """Should clamp extreme Sharpe values."""
        # Create extreme returns
        equity = pd.Series([100] + [100 * 1.5**i for i in range(1, 20)])
        sharpe = calculate_sharpe(equity)
        assert -10.0 <= sharpe <= 10.0

    def test_sharpe_insufficient_data(self):
        """Should return 0 for insufficient data."""
        equity = pd.Series([100])
        sharpe = calculate_sharpe(equity)
        assert sharpe == 0.0


class TestCalculateMaxDrawdown:
    """Tests for max drawdown calculation."""

    def test_drawdown_calculation(self):
        """Should calculate correct max drawdown."""
        # Peak at 110, trough at 90 = 18.18% drawdown
        equity = pd.Series([100, 105, 110, 100, 90, 95, 100])
        dd = calculate_max_drawdown(equity)
        assert 0.18 <= dd <= 0.19  # ~18.18%

    def test_no_drawdown(self):
        """Should return 0 for monotonically increasing equity."""
        equity = pd.Series([100, 101, 102, 103, 104, 105])
        dd = calculate_max_drawdown(equity)
        assert dd == 0.0

    def test_drawdown_returns_positive(self):
        """Max drawdown should be positive."""
        equity = pd.Series([100, 90, 80, 85])
        dd = calculate_max_drawdown(equity)
        assert dd > 0

    def test_drawdown_insufficient_data(self):
        """Should return 0 for insufficient data."""
        equity = pd.Series([100])
        dd = calculate_max_drawdown(equity)
        assert dd == 0.0


class TestFitnessConfig:
    """Tests for FitnessConfig."""

    def test_default_config(self):
        """Default config should have sensible values."""
        config = FitnessConfig()
        assert config.min_trades == 5
        assert config.max_drawdown_threshold == 0.50
        assert config.min_regimes_positive == 4

    def test_custom_config(self):
        """Should accept custom config values."""
        config = FitnessConfig(
            min_trades=10,
            max_drawdown_threshold=0.30,
        )
        calculator = EquitiesFitnessCalculator(config)
        assert calculator.config.min_trades == 10
        assert calculator.config.max_drawdown_threshold == 0.30


class TestConvenienceFunction:
    """Tests for calculate_fitness convenience function."""

    def test_returns_float(self):
        """Should return just the score as float."""
        results = BacktestResults(
            trade_count=25,
            sharpe_ratio=1.5,
            max_drawdown=0.10,
        )
        score = calculate_fitness(results)
        assert isinstance(score, float)

    def test_disqualified_returns_sentinel(self):
        """Should return sentinel for disqualified."""
        results = BacktestResults(trade_count=2)
        score = calculate_fitness(results)
        assert score == -999.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
