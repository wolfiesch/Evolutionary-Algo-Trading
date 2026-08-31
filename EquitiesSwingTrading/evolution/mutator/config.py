"""
Evolution Configuration for Equities Swing Trading.

Customizes shared evolution parameters for daily-bar equities trading.
Key differences from crypto:
- Larger population (more diverse strategies)
- More generations (fundamental signals need exploration)
- Lower target trades (daily bars = fewer opportunities)
- Different primitive set (includes fundamentals)
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class EquitiesEvolutionConfig:
    """
    Configuration for equities strategy evolution.

    Tuned for swing trading with fundamental signals.
    """
    # Population
    population_size: int = 20           # Larger than crypto (10)
    generations: int = 50               # More iterations needed
    elite_count: int = 3                # Top 3 survive unchanged

    # Genetic operators
    mutation_rate: float = 0.6          # 60% mutation
    crossover_rate: float = 0.4         # 40% crossover
    tournament_size: int = 4            # Selection pressure

    # Diversity & stagnation
    min_diversity: float = 0.3          # Minimum unique strategies
    max_stagnation: int = 10            # Gens without improvement

    # Trade requirements
    min_trades: int = 20                # Minimum for validity
    target_trades: int = 60             # ~1 trade every 4 days
    max_trades: int = 200               # Cap to prevent overtrading

    # Performance thresholds
    min_sharpe: float = 0.5             # Minimum acceptable Sharpe
    target_sharpe: float = 1.5          # Good strategy threshold
    max_drawdown: float = 0.25          # 25% max drawdown limit

    # Regime requirements
    min_regime_passes: int = 4          # 4/5 regimes with Sharpe > 0.5
    regime_sharpe_threshold: float = 0.5

    # Checkpointing
    checkpoint_interval: int = 5        # Save every 5 generations
    checkpoint_dir: Optional[Path] = None
    progress_file: Optional[Path] = None

    # Deduplication
    enable_deduplication: bool = True
    max_dedup_retries: int = 3

    # LLM settings
    llm_temperature: float = 0.7
    llm_max_tokens: int = 400
    llm_retry_attempts: int = 3

    # Allowed primitives (for validation)
    allowed_primitives: set = field(default_factory=lambda: {
        # Technical
        "ema_trend",
        "price_position",
        "norm_rsi",
        "bb_position",
        "bb_width_percentile",
        "volume_intensity",
        "atr_regime",
        "atr_percentile",
        # Market filters
        "spy_trend",
        "vix_regime",
        "spy_momentum",
        "spy_above_sma",
        "market_breadth_proxy",
        # Fundamental (EDGAR-derived)
        "insider_intensity",
        "insider_cluster",
        "revenue_cagr",
        "earnings_growth",
        "earnings_quality",
        "risk_change",
        "fundamental_score",
    })

    # Market filters (at least one required in entry)
    market_filters: set = field(default_factory=lambda: {
        "spy_trend",
        "vix_regime",
        "spy_momentum",
        "spy_above_sma",
        "market_breadth_proxy",
    })

    # Fundamental primitives (at least one encouraged)
    fundamental_primitives: set = field(default_factory=lambda: {
        "insider_intensity",
        "insider_cluster",
        "revenue_cagr",
        "earnings_growth",
        "earnings_quality",
        "risk_change",
        "fundamental_score",
    })

    # Max primitives per expression
    max_primitives: int = 5

    def __post_init__(self):
        """Validate configuration."""
        assert self.population_size >= self.elite_count + 2, \
            "Population must be larger than elite_count + 2"
        assert self.mutation_rate + self.crossover_rate <= 1.0, \
            "Mutation + crossover rates must sum to <= 1.0"
        assert self.min_trades < self.target_trades < self.max_trades, \
            "Trade thresholds must be ordered: min < target < max"


def get_default_config(
    checkpoint_dir: Optional[Path] = None,
    progress_file: Optional[Path] = None,
) -> EquitiesEvolutionConfig:
    """
    Get default equities evolution configuration.

    Args:
        checkpoint_dir: Directory for checkpoints
        progress_file: Path for progress JSON

    Returns:
        EquitiesEvolutionConfig with defaults
    """
    return EquitiesEvolutionConfig(
        checkpoint_dir=checkpoint_dir,
        progress_file=progress_file,
    )


def get_fast_config() -> EquitiesEvolutionConfig:
    """
    Get fast configuration for testing.

    Reduced population and generations for quick iteration.
    """
    return EquitiesEvolutionConfig(
        population_size=5,
        generations=10,
        elite_count=1,
        checkpoint_interval=2,
        max_stagnation=3,
    )


def get_thorough_config(
    checkpoint_dir: Optional[Path] = None,
) -> EquitiesEvolutionConfig:
    """
    Get thorough configuration for production.

    Larger population and more generations for better exploration.
    """
    return EquitiesEvolutionConfig(
        population_size=30,
        generations=100,
        elite_count=5,
        tournament_size=5,
        max_stagnation=15,
        checkpoint_interval=10,
        checkpoint_dir=checkpoint_dir,
    )


# =============================================================================
# FITNESS WEIGHTS - How different metrics contribute to fitness
# =============================================================================

@dataclass
class FitnessWeights:
    """
    Weights for fitness score calculation.

    Final score = (sharpe * sharpe_weight + regime_bonus)
                  - drawdown_penalty - trade_penalty
    """
    # Base score weights
    sharpe_weight: float = 1.0

    # Penalties
    drawdown_penalty_factor: float = 2.0    # Per unit drawdown
    trade_deficit_penalty: float = 0.5      # For trades < target
    trade_excess_penalty: float = 0.2       # For trades > max

    # Bonuses
    regime_consistency_bonus: float = 0.5   # For passing 4/5 regimes
    fundamental_usage_bonus: float = 0.1    # For using fundamentals

    # Disqualification score
    disqualified_score: float = -999.0


def get_default_weights() -> FitnessWeights:
    """Get default fitness weights."""
    return FitnessWeights()


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test configuration creation."""
    print("Testing evolution configuration...")

    # Default config
    config = get_default_config()
    print(f"\nDefault config:")
    print(f"  Population: {config.population_size}")
    print(f"  Generations: {config.generations}")
    print(f"  Elite count: {config.elite_count}")
    print(f"  Allowed primitives: {len(config.allowed_primitives)}")

    # Fast config
    fast = get_fast_config()
    print(f"\nFast config:")
    print(f"  Population: {fast.population_size}")
    print(f"  Generations: {fast.generations}")

    # Thorough config
    thorough = get_thorough_config()
    print(f"\nThorough config:")
    print(f"  Population: {thorough.population_size}")
    print(f"  Generations: {thorough.generations}")

    # Validate primitives
    assert "spy_trend" in config.allowed_primitives
    assert "insider_intensity" in config.allowed_primitives
    assert "norm_rsi" in config.allowed_primitives

    # Validate market filters subset
    assert config.market_filters.issubset(config.allowed_primitives)

    # Validate fundamental primitives subset
    assert config.fundamental_primitives.issubset(config.allowed_primitives)

    print("\nAll configuration tests passed!")


if __name__ == "__main__":
    quick_test()
