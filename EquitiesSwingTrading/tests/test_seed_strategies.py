"""Tests for seed strategies."""
import pytest

from strategies.seed_strategies import (
    get_seed_strategies,
    get_default_strategies,
    validate_strategy,
    validate_all_seed_strategies,
    ALL_STRATEGIES,
    INSIDER_MOMENTUM,
    QUALITY_PULLBACK,
    GROWTH_BREAKOUT,
    TREND_FOLLOWING,
    RSI_OVERSOLD_BOUNCE,
)
from evolution.backtester.evaluator import Strategy


class TestSeedStrategies:
    """Tests for seed strategy definitions."""

    def test_all_strategies_defined(self):
        """Ensure we have a good number of seed strategies."""
        assert len(ALL_STRATEGIES) >= 10
        assert len(ALL_STRATEGIES) <= 20  # Don't want too many

    def test_all_strategies_have_names(self):
        """All strategies must have unique names."""
        names = [s.name for s in ALL_STRATEGIES]
        assert len(names) == len(set(names)), "Duplicate strategy names found"

    def test_all_strategies_have_entry_exit(self):
        """All strategies must have entry and exit conditions."""
        for strategy in ALL_STRATEGIES:
            assert strategy.entry_long, f"{strategy.name} missing entry_long"
            assert strategy.exit_long, f"{strategy.name} missing exit_long"

    def test_all_strategies_have_market_filter(self):
        """All strategies must include a market filter."""
        market_filters = ["spy_trend", "vix_regime", "spy_above_sma", "spy_momentum"]

        for strategy in ALL_STRATEGIES:
            has_filter = any(f in strategy.entry_long for f in market_filters)
            assert has_filter, (
                f"{strategy.name} missing market filter. "
                f"Entry: {strategy.entry_long}"
            )

    def test_all_strategies_max_five_primitives(self):
        """Strategies should not exceed 5 primitives in entry."""
        for strategy in ALL_STRATEGIES:
            # Count conditions (AND + 1)
            primitive_count = strategy.entry_long.count("AND") + 1
            assert primitive_count <= 5, (
                f"{strategy.name} has {primitive_count} conditions, max is 5"
            )

    def test_specific_strategies_exist(self):
        """Key strategy archetypes should exist."""
        names = [s.name for s in ALL_STRATEGIES]

        # Must have at least one of each type
        assert any("Momentum" in n or "Trend" in n for n in names)
        assert any("Pullback" in n or "Oversold" in n or "Mean" in n for n in names)
        assert any("Insider" in n or "Growth" in n or "Quality" in n for n in names)


class TestGetSeedStrategies:
    """Tests for get_seed_strategies function."""

    def test_get_all_strategies(self):
        """Get all strategies."""
        strategies = get_seed_strategies("all")
        assert len(strategies) == len(ALL_STRATEGIES)
        assert strategies is not ALL_STRATEGIES  # Should be a copy

    def test_get_momentum_strategies(self):
        """Get momentum strategies only."""
        strategies = get_seed_strategies("momentum")
        assert len(strategies) >= 2
        for s in strategies:
            # Momentum strategies typically have trend or momentum in entry
            assert "ema_trend" in s.entry_long or "Momentum" in s.name

    def test_get_mean_reversion_strategies(self):
        """Get mean reversion strategies only."""
        strategies = get_seed_strategies("mean_reversion")
        assert len(strategies) >= 2
        for s in strategies:
            # Mean reversion strategies typically have RSI or BB
            assert "norm_rsi" in s.entry_long or "bb_position" in s.entry_long

    def test_get_fundamental_strategies(self):
        """Get fundamental-driven strategies only."""
        strategies = get_seed_strategies("fundamental")
        assert len(strategies) >= 2
        for s in strategies:
            # Fundamental strategies should use EDGAR primitives
            fundamental_primitives = [
                "insider_buy_intensity",
                "insider_cluster",
                "revenue_cagr",
                "earnings_quality",
                "risk_change",
            ]
            has_fundamental = any(p in s.entry_long for p in fundamental_primitives)
            assert has_fundamental, f"{s.name} missing fundamental primitive"

    def test_get_volatility_strategies(self):
        """Get volatility-aware strategies only."""
        strategies = get_seed_strategies("volatility")
        assert len(strategies) >= 1
        for s in strategies:
            # Should use VIX or ATR
            assert "vix" in s.entry_long.lower() or "atr" in s.entry_long.lower()

    def test_get_conservative_strategies(self):
        """Get conservative strategies only."""
        strategies = get_seed_strategies("conservative")
        assert len(strategies) >= 1

    def test_invalid_category_raises(self):
        """Invalid category should raise error."""
        with pytest.raises(ValueError, match="Unknown category"):
            get_seed_strategies("invalid_category")


class TestGetDefaultStrategies:
    """Tests for get_default_strategies function."""

    def test_returns_balanced_set(self):
        """Default strategies should be a balanced subset."""
        strategies = get_default_strategies()

        # Should be a manageable number
        assert 3 <= len(strategies) <= 5

        # Should include key archetypes
        names = [s.name for s in strategies]
        assert any("Momentum" in n or "Insider" in n for n in names)
        assert any("Pullback" in n or "Quality" in n for n in names)
        assert any("Growth" in n or "Breakout" in n for n in names)

    def test_all_valid(self):
        """Default strategies should all be valid."""
        strategies = get_default_strategies()
        for strategy in strategies:
            errors = validate_strategy(strategy)
            assert not errors, f"{strategy.name} has errors: {errors}"


class TestValidateStrategy:
    """Tests for strategy validation."""

    def test_valid_strategy_no_errors(self):
        """Valid strategy should return no errors."""
        errors = validate_strategy(INSIDER_MOMENTUM)
        assert len(errors) == 0

    def test_missing_market_filter(self):
        """Strategy without market filter should error."""
        bad_strategy = Strategy(
            name="Bad_Strategy",
            entry_long="ema_trend(9, 21) == 1.0 AND norm_rsi(14) < -0.3",
            exit_long="norm_rsi(14) > 0.5",
        )
        errors = validate_strategy(bad_strategy)
        assert len(errors) > 0
        assert any("market filter" in e.lower() for e in errors)

    def test_too_many_primitives(self):
        """Strategy with more than 5 primitives should error."""
        bad_strategy = Strategy(
            name="Complex_Strategy",
            entry_long=(
                "spy_trend(20) >= 0 AND ema_trend(9, 21) == 1.0 "
                "AND norm_rsi(14) < -0.3 AND bb_position(20, 2.0) > 0.5 "
                "AND volume_intensity(20, 1.5) > 0.3 AND atr_regime(14) == 1.0"
            ),
            exit_long="norm_rsi(14) > 0.5",
        )
        errors = validate_strategy(bad_strategy)
        assert len(errors) > 0
        assert any("max is 5" in e for e in errors)

    def test_missing_exit(self):
        """Strategy without exit should error."""
        bad_strategy = Strategy(
            name="No_Exit",
            entry_long="spy_trend(20) >= 0",
            exit_long="",
        )
        errors = validate_strategy(bad_strategy)
        assert len(errors) > 0
        assert any("exit" in e.lower() for e in errors)


class TestValidateAllSeedStrategies:
    """Tests for bulk validation."""

    def test_all_seed_strategies_valid(self):
        """All seed strategies should pass validation."""
        errors = validate_all_seed_strategies()
        if errors:
            for name, errs in errors.items():
                print(f"{name}: {errs}")
        assert len(errors) == 0, f"Found {len(errors)} invalid strategies"


class TestIndividualStrategies:
    """Tests for specific strategy definitions."""

    def test_insider_momentum(self):
        """Test Insider Momentum strategy."""
        assert "spy_trend" in INSIDER_MOMENTUM.entry_long
        assert "insider_buy_intensity" in INSIDER_MOMENTUM.entry_long
        assert "ema_trend" in INSIDER_MOMENTUM.entry_long

    def test_quality_pullback(self):
        """Test Quality Pullback strategy."""
        assert "spy_trend" in QUALITY_PULLBACK.entry_long
        assert "earnings_quality" in QUALITY_PULLBACK.entry_long
        assert "norm_rsi" in QUALITY_PULLBACK.entry_long

    def test_growth_breakout(self):
        """Test Growth Breakout strategy."""
        assert "spy_trend" in GROWTH_BREAKOUT.entry_long
        assert "revenue_cagr" in GROWTH_BREAKOUT.entry_long
        assert "bb_position" in GROWTH_BREAKOUT.entry_long

    def test_trend_following(self):
        """Test Trend Following strategy."""
        assert "spy_trend" in TREND_FOLLOWING.entry_long
        assert "vix_regime" in TREND_FOLLOWING.entry_long
        assert "ema_trend" in TREND_FOLLOWING.entry_long

    def test_rsi_oversold_bounce(self):
        """Test RSI Oversold Bounce strategy."""
        assert "spy_trend" in RSI_OVERSOLD_BOUNCE.entry_long
        assert "norm_rsi" in RSI_OVERSOLD_BOUNCE.entry_long
        assert "bb_position" in RSI_OVERSOLD_BOUNCE.entry_long
