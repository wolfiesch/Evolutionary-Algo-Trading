"""
Tests for equities evolution prompts.
"""

import pytest

import sys
sys.path.insert(0, ".")

from evolution.mutator.prompts import (
    EQUITIES_SYSTEM_PROMPT,
    EQUITIES_GENERATION_PROMPT,
    EQUITIES_MUTATION_PROMPT,
    EQUITIES_CROSSOVER_PROMPT,
    EQUITIES_THEMES,
    EQUITIES_MEAN_REVERSION_THEMES,
    get_equities_generation_prompt,
    get_equities_mutation_prompt,
    get_equities_crossover_prompt,
    get_equities_analysis_prompt,
)


class TestSystemPrompt:
    """Tests for system prompt content."""

    def test_contains_technical_primitives(self):
        """Should list technical primitives."""
        assert "ema_trend" in EQUITIES_SYSTEM_PROMPT
        assert "norm_rsi" in EQUITIES_SYSTEM_PROMPT
        assert "bb_position" in EQUITIES_SYSTEM_PROMPT
        assert "volume_intensity" in EQUITIES_SYSTEM_PROMPT

    def test_contains_market_filters(self):
        """Should list market filter primitives."""
        assert "spy_trend" in EQUITIES_SYSTEM_PROMPT
        assert "vix_regime" in EQUITIES_SYSTEM_PROMPT

    def test_contains_fundamental_primitives(self):
        """Should list EDGAR-derived primitives."""
        assert "insider_intensity" in EQUITIES_SYSTEM_PROMPT
        assert "insider_cluster" in EQUITIES_SYSTEM_PROMPT
        assert "revenue_cagr" in EQUITIES_SYSTEM_PROMPT
        assert "earnings_quality" in EQUITIES_SYSTEM_PROMPT
        assert "risk_change" in EQUITIES_SYSTEM_PROMPT

    def test_contains_rules(self):
        """Should include strategy rules."""
        assert "RULES:" in EQUITIES_SYSTEM_PROMPT
        assert "market filter" in EQUITIES_SYSTEM_PROMPT.lower()
        assert "Maximum 5 primitives" in EQUITIES_SYSTEM_PROMPT

    def test_contains_good_patterns(self):
        """Should include good strategy patterns."""
        assert "GOOD PATTERNS:" in EQUITIES_SYSTEM_PROMPT
        assert "Insider" in EQUITIES_SYSTEM_PROMPT

    def test_contains_bad_patterns(self):
        """Should warn about bad patterns."""
        assert "BAD PATTERNS" in EQUITIES_SYSTEM_PROMPT
        assert "overfitting" in EQUITIES_SYSTEM_PROMPT.lower()


class TestGenerationPrompt:
    """Tests for generation prompt."""

    def test_format_with_theme(self):
        """Should format with theme."""
        prompt = get_equities_generation_prompt("Test theme")
        assert "Test theme" in prompt
        assert "spy_trend" in prompt  # From system prompt

    def test_includes_json_format(self):
        """Should include expected JSON format."""
        prompt = get_equities_generation_prompt("Any theme")
        assert "entry_long" in prompt
        assert "exit_long" in prompt
        assert "JSON" in prompt

    def test_includes_system_prompt(self):
        """Should include full system prompt."""
        prompt = get_equities_generation_prompt("Theme")
        assert "insider_intensity" in prompt
        assert "RULES:" in prompt


class TestMutationPrompt:
    """Tests for mutation prompt."""

    def test_format_with_performance(self):
        """Should include performance metrics."""
        prompt = get_equities_mutation_prompt(
            strategy_name="Test_Strategy",
            entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=1.2,
            win_rate=0.55,
            max_dd=0.10,
            trade_count=30,
        )
        assert "Test_Strategy" in prompt
        assert "1.2" in prompt  # Sharpe
        assert "55" in prompt  # Win rate %
        assert "10" in prompt  # Max DD %

    def test_includes_mutation_options(self):
        """Should list mutation options."""
        prompt = get_equities_mutation_prompt(
            strategy_name="Test",
            entry_long="spy_trend(20) >= 0",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=1.0,
            win_rate=0.5,
            max_dd=0.1,
            trade_count=25,
        )
        assert "SWAP" in prompt
        assert "PARAM" in prompt
        assert "THRESHOLD" in prompt
        assert "ADD" in prompt
        assert "REMOVE" in prompt

    def test_guidance_for_low_sharpe(self):
        """Should add guidance for poor performance."""
        prompt = get_equities_mutation_prompt(
            strategy_name="Test",
            entry_long="spy_trend(20) >= 0",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=-0.5,  # Negative Sharpe
            win_rate=0.35,
            max_dd=0.25,
            trade_count=25,
        )
        assert "losing money" in prompt.lower() or "conservative" in prompt.lower()

    def test_guidance_for_few_trades(self):
        """Should add guidance for too few trades."""
        prompt = get_equities_mutation_prompt(
            strategy_name="Test",
            entry_long="spy_trend(20) >= 0",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=1.0,
            win_rate=0.5,
            max_dd=0.1,
            trade_count=5,  # Very few trades
        )
        assert "loosen" in prompt.lower() or "few trades" in prompt.lower()


class TestCrossoverPrompt:
    """Tests for crossover prompt."""

    def test_format_with_parents(self):
        """Should include both parent strategies."""
        prompt = get_equities_crossover_prompt(
            entry_a="spy_trend(20) >= 0 AND insider_intensity > 0.3",
            exit_a="norm_rsi(14) > 0.5",
            sharpe_a=1.5,
            entry_b="spy_trend(50) >= 0 AND revenue_cagr > 0.2",
            exit_b="ema_trend(9, 21) < 0",
            sharpe_b=1.0,
        )
        assert "PARENT A" in prompt
        assert "PARENT B" in prompt
        assert "1.5" in prompt  # Sharpe A
        assert "1.0" in prompt  # Sharpe B
        assert "insider_intensity" in prompt
        assert "revenue_cagr" in prompt

    def test_includes_bias_instruction(self):
        """Should instruct to bias toward better parent."""
        prompt = get_equities_crossover_prompt(
            entry_a="spy_trend(20) >= 0",
            exit_a="norm_rsi(14) > 0.5",
            sharpe_a=2.0,
            entry_b="spy_trend(20) >= 0",
            exit_b="ema_trend(9, 21) < 0",
            sharpe_b=0.5,
        )
        assert "higher" in prompt.lower() or "better" in prompt.lower()


class TestAnalysisPrompt:
    """Tests for analysis prompt."""

    def test_format_with_regime_scores(self):
        """Should include regime performance."""
        prompt = get_equities_analysis_prompt(
            strategy_name="Quality_Pullback",
            entry_long="spy_trend(20) >= 0 AND earnings_quality > 0.3",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=1.5,
            max_dd=0.08,
            win_rate=0.58,
            trade_count=45,
            total_return=0.35,
            regime_scores={
                "bull_calm": 1.8,
                "bull_volatile": 0.9,
                "bear_calm": 0.4,
                "bear_volatile": -0.2,
                "sideways": 0.6,
            },
        )
        assert "bull_calm" in prompt
        assert "bear_volatile" in prompt
        assert "PASS" in prompt
        assert "FAIL" in prompt

    def test_includes_analysis_sections(self):
        """Should include analysis sections."""
        prompt = get_equities_analysis_prompt(
            strategy_name="Test",
            entry_long="spy_trend(20) >= 0",
            exit_long="norm_rsi(14) > 0.5",
            sharpe=1.0,
            max_dd=0.1,
            win_rate=0.5,
            trade_count=30,
            total_return=0.2,
            regime_scores={},
        )
        assert "MARKET HYPOTHESIS" in prompt
        assert "LOGIC ASSESSMENT" in prompt
        assert "EDGE SOURCE" in prompt
        assert "ROBUSTNESS RATING" in prompt


class TestThemes:
    """Tests for strategy themes."""

    def test_themes_not_empty(self):
        """Should have themes defined."""
        assert len(EQUITIES_THEMES) >= 5
        assert len(EQUITIES_MEAN_REVERSION_THEMES) >= 3

    def test_themes_are_strings(self):
        """Themes should be non-empty strings."""
        for theme in EQUITIES_THEMES + EQUITIES_MEAN_REVERSION_THEMES:
            assert isinstance(theme, str)
            assert len(theme) > 10

    def test_themes_mention_relevant_concepts(self):
        """Themes should mention trading concepts."""
        all_themes = " ".join(EQUITIES_THEMES + EQUITIES_MEAN_REVERSION_THEMES).lower()
        assert "insider" in all_themes
        assert "quality" in all_themes
        assert "momentum" in all_themes or "trend" in all_themes


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
