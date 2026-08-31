"""
Tests for equities evolution configuration.
"""

import pytest
from pathlib import Path

import sys
sys.path.insert(0, ".")

from evolution.mutator.config import (
    EquitiesEvolutionConfig,
    FitnessWeights,
    get_default_config,
    get_fast_config,
    get_thorough_config,
    get_default_weights,
)


class TestEquitiesEvolutionConfig:
    """Tests for EquitiesEvolutionConfig."""

    def test_default_values(self):
        """Default config should have sensible values."""
        config = EquitiesEvolutionConfig()
        assert config.population_size == 20
        assert config.generations == 50
        assert config.elite_count == 3
        assert config.mutation_rate == 0.6
        assert config.crossover_rate == 0.4

    def test_trade_requirements(self):
        """Should have trade thresholds."""
        config = EquitiesEvolutionConfig()
        assert config.min_trades == 20
        assert config.target_trades == 60
        assert config.max_trades == 200
        assert config.min_trades < config.target_trades < config.max_trades

    def test_performance_thresholds(self):
        """Should have performance thresholds."""
        config = EquitiesEvolutionConfig()
        assert config.min_sharpe == 0.5
        assert config.target_sharpe == 1.5
        assert config.max_drawdown == 0.25

    def test_regime_requirements(self):
        """Should have regime requirements."""
        config = EquitiesEvolutionConfig()
        assert config.min_regime_passes == 4  # 4/5 regimes
        assert config.regime_sharpe_threshold == 0.5

    def test_allowed_primitives(self):
        """Should include all primitive types."""
        config = EquitiesEvolutionConfig()

        # Technical
        assert "ema_trend" in config.allowed_primitives
        assert "norm_rsi" in config.allowed_primitives
        assert "bb_position" in config.allowed_primitives

        # Market filters
        assert "spy_trend" in config.allowed_primitives
        assert "vix_regime" in config.allowed_primitives

        # Fundamental
        assert "insider_intensity" in config.allowed_primitives
        assert "revenue_cagr" in config.allowed_primitives
        assert "earnings_quality" in config.allowed_primitives

    def test_market_filters_subset(self):
        """Market filters should be subset of allowed primitives."""
        config = EquitiesEvolutionConfig()
        assert config.market_filters.issubset(config.allowed_primitives)

    def test_fundamental_primitives_subset(self):
        """Fundamental primitives should be subset of allowed primitives."""
        config = EquitiesEvolutionConfig()
        assert config.fundamental_primitives.issubset(config.allowed_primitives)

    def test_validation_population_size(self):
        """Should validate population size vs elite count."""
        with pytest.raises(AssertionError):
            EquitiesEvolutionConfig(
                population_size=3,
                elite_count=3,
            )

    def test_validation_mutation_crossover_rates(self):
        """Should validate mutation + crossover <= 1."""
        with pytest.raises(AssertionError):
            EquitiesEvolutionConfig(
                mutation_rate=0.8,
                crossover_rate=0.5,
            )

    def test_validation_trade_ordering(self):
        """Should validate trade threshold ordering."""
        with pytest.raises(AssertionError):
            EquitiesEvolutionConfig(
                min_trades=50,
                target_trades=30,  # Less than min
                max_trades=100,
            )


class TestConfigFactories:
    """Tests for config factory functions."""

    def test_get_default_config(self):
        """Should return default config."""
        config = get_default_config()
        assert isinstance(config, EquitiesEvolutionConfig)
        assert config.population_size == 20

    def test_get_default_config_with_paths(self):
        """Should accept checkpoint paths."""
        config = get_default_config(
            checkpoint_dir=Path("/tmp/checkpoints"),
            progress_file=Path("/tmp/progress.json"),
        )
        assert config.checkpoint_dir == Path("/tmp/checkpoints")
        assert config.progress_file == Path("/tmp/progress.json")

    def test_get_fast_config(self):
        """Should return fast config for testing."""
        config = get_fast_config()
        assert config.population_size == 5
        assert config.generations == 10
        assert config.elite_count == 1

    def test_get_thorough_config(self):
        """Should return thorough config for production."""
        config = get_thorough_config()
        assert config.population_size == 30
        assert config.generations == 100
        assert config.elite_count == 5


class TestFitnessWeights:
    """Tests for FitnessWeights."""

    def test_default_weights(self):
        """Default weights should be sensible."""
        weights = FitnessWeights()
        assert weights.sharpe_weight == 1.0
        assert weights.drawdown_penalty_factor == 2.0
        assert weights.regime_consistency_bonus == 0.5

    def test_disqualified_score(self):
        """Should have sentinel for disqualification."""
        weights = FitnessWeights()
        assert weights.disqualified_score == -999.0

    def test_get_default_weights(self):
        """Factory should return default weights."""
        weights = get_default_weights()
        assert isinstance(weights, FitnessWeights)


class TestLLMSettings:
    """Tests for LLM-related settings."""

    def test_llm_defaults(self):
        """Should have LLM settings."""
        config = EquitiesEvolutionConfig()
        assert config.llm_temperature == 0.7
        assert config.llm_max_tokens == 400
        assert config.llm_retry_attempts == 3

    def test_max_primitives(self):
        """Should limit primitives per expression."""
        config = EquitiesEvolutionConfig()
        assert config.max_primitives == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
