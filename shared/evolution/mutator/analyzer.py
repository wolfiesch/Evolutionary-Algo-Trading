"""
Strategy Analyzer - Opus-powered deep analysis of winning strategies.

Uses powerful reasoning models (Opus/GPT-4o) to explain WHY strategies work,
identify failure modes, and assess robustness. This is where expensive
reasoning capabilities actually pay off.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from shared.evolution.mutator.llm_client import LLMClient, create_analysis_client
from shared.evolution.mutator.generator import GeneratedStrategy
from shared.evolution.fitness import FitnessResult

logger = logging.getLogger(__name__)


# Gene pool documentation for context
PRIMITIVE_DOCS = """
## Available Primitives

### Trend Primitives
- `ema_trend(fast, slow)`: EMA crossover state. Returns +1.0 (uptrend) or -1.0 (downtrend).
- `price_position(period)`: Price distance from EMA, normalized by ATR. Range: -3.0 to +3.0.

### Mean Reversion Primitives
- `norm_rsi(period)`: Normalized RSI. Range: -1.0 (oversold, RSI=0) to +1.0 (overbought, RSI=100).
- `bb_position(period, std)`: Position within Bollinger Bands. -1.0 = lower band, +1.0 = upper band.
- `bb_width_percentile(period)`: Band width vs history. 0.0 = narrowest, 1.0 = widest.

### Market Filter Primitives
- `btc_trend(window)`: BTC market health filter. +1.0 = safe, -1.0 = avoid.
- `asset_trend(window)`: Self-referential trend filter for current asset.

### Volatility Primitives
- `atr_regime(period)`: ATR regime classification. +1.0 = high vol, -1.0 = low vol.
- `atr_percentile(period)`: Current ATR vs historical percentile.
"""


ANALYSIS_PROMPT = """You are an expert quantitative trader analyzing an algorithmically-discovered trading strategy.

{primitive_docs}

## Strategy to Analyze

**Name:** {strategy_name}
**Entry Long:** `{entry_long}`
**Exit Long:** `{exit_long}`

## Performance Metrics

- **Sharpe Ratio:** {sharpe:.2f}
- **Total Return:** {total_return:.1%}
- **Max Drawdown:** {max_drawdown:.1%}
- **Win Rate:** {win_rate:.1%}
- **Total Trades:** {total_trades}
- **Profit Factor:** {profit_factor:.2f}

{regime_performance}

## Your Analysis

Provide a thorough analysis covering:

1. **Market Hypothesis**: What market behavior is this strategy trying to exploit? (e.g., mean reversion after oversold conditions, trend continuation, volatility breakout)

2. **Logic Assessment**: Does the combination of primitives make sense? Are there any logical inconsistencies or redundancies?

3. **Edge Source**: Where does the potential edge come from? Is it exploiting a known market inefficiency, behavioral bias, or structural feature?

4. **Favorable Conditions**: In what market regimes would this strategy perform best? (bull/bear, high/low volatility, trending/ranging)

5. **Failure Modes**: What could cause this strategy to fail? Consider:
   - Market regime changes
   - Parameter sensitivity
   - Overfitting concerns
   - Correlation breakdown

6. **Risk Assessment**: Rate the strategy's robustness on a scale of 1-10 with justification.

7. **Improvement Suggestions**: What modifications might improve robustness (not returns)?

Be specific and reference the actual primitives and their parameters. Be skeptical - good backtest performance doesn't guarantee future success.
"""


@dataclass
class StrategyAnalysis:
    """Analysis results from Opus/GPT-4o."""
    strategy_name: str
    analysis_text: str
    model_used: str
    sharpe: float
    total_return: float

    def to_dict(self) -> dict:
        return {
            "strategy_name": self.strategy_name,
            "analysis": self.analysis_text,
            "model": self.model_used,
            "sharpe": self.sharpe,
            "total_return": self.total_return,
        }

    def __str__(self) -> str:
        return f"""
{'='*60}
STRATEGY ANALYSIS: {self.strategy_name}
Model: {self.model_used}
Sharpe: {self.sharpe:.2f} | Return: {self.total_return:.1%}
{'='*60}

{self.analysis_text}
"""


class StrategyAnalyzer:
    """
    Analyzes winning strategies using powerful reasoning models.

    Uses Opus (Anthropic) or GPT-4o (OpenAI) for deep analysis
    of why strategies work and potential failure modes.
    """

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        log_dir: Optional[Path] = None,
    ):
        """
        Initialize analyzer with LLM client.

        Args:
            client: LLM client (defaults to create_analysis_client)
            log_dir: Directory for logging interactions
        """
        self.client = client or create_analysis_client(log_dir=log_dir)
        self.model_name = self.client.config.model

    def analyze(
        self,
        strategy: GeneratedStrategy,
        fitness: FitnessResult,
        regime_results: Optional[dict] = None,
    ) -> StrategyAnalysis:
        """
        Analyze a strategy using Opus/GPT-4o.

        Args:
            strategy: The strategy to analyze
            fitness: Fitness results from backtesting
            regime_results: Optional per-regime performance breakdown

        Returns:
            StrategyAnalysis with detailed explanation
        """
        # Format regime performance if available
        regime_text = ""
        if regime_results:
            regime_text = "\n## Performance by Market Regime\n"
            for regime, metrics in regime_results.items():
                if isinstance(metrics, dict):
                    regime_sharpe = metrics.get("sharpe", 0)
                    regime_return = metrics.get("total_return", 0)
                    regime_text += f"- **{regime}**: Sharpe {regime_sharpe:.2f}, Return {regime_return:.1%}\n"

        # Build the prompt
        prompt = ANALYSIS_PROMPT.format(
            primitive_docs=PRIMITIVE_DOCS,
            strategy_name=strategy.name,
            entry_long=strategy.entry_long,
            exit_long=strategy.exit_long,
            sharpe=fitness.sharpe,
            total_return=fitness.total_return,
            max_drawdown=fitness.max_drawdown,
            win_rate=fitness.win_rate,
            total_trades=fitness.total_trades,
            profit_factor=fitness.profit_factor,
            regime_performance=regime_text,
        )

        logger.info(f"Analyzing strategy '{strategy.name}' with {self.model_name}")

        try:
            response = self.client.generate(
                prompt,
                context={"operation": "strategy_analysis", "strategy": strategy.name}
            )

            return StrategyAnalysis(
                strategy_name=strategy.name,
                analysis_text=response,
                model_used=self.model_name,
                sharpe=fitness.sharpe,
                total_return=fitness.total_return,
            )

        except Exception as e:
            logger.error(f"Analysis failed for '{strategy.name}': {e}")
            return StrategyAnalysis(
                strategy_name=strategy.name,
                analysis_text=f"Analysis failed: {e}",
                model_used=self.model_name,
                sharpe=fitness.sharpe,
                total_return=fitness.total_return,
            )

    def analyze_top_strategies(
        self,
        strategies_with_fitness: list[tuple[GeneratedStrategy, FitnessResult]],
        top_n: int = 3,
        regime_results: Optional[dict[str, dict]] = None,
    ) -> list[StrategyAnalysis]:
        """
        Analyze top N strategies from evolution results.

        Args:
            strategies_with_fitness: List of (strategy, fitness) tuples
            top_n: Number of top strategies to analyze
            regime_results: Optional dict mapping strategy names to regime performance

        Returns:
            List of StrategyAnalysis for top performers
        """
        # Sort by Sharpe ratio
        sorted_strategies = sorted(
            strategies_with_fitness,
            key=lambda x: x[1].sharpe,
            reverse=True
        )[:top_n]

        analyses = []
        for strategy, fitness in sorted_strategies:
            # Get regime results for this strategy if available
            strategy_regimes = None
            if regime_results and strategy.name in regime_results:
                strategy_regimes = regime_results[strategy.name]

            analysis = self.analyze(strategy, fitness, strategy_regimes)
            analyses.append(analysis)
            logger.info(f"Completed analysis for '{strategy.name}'")

        return analyses


def analyze_evolution_winners(
    results: "EvolutionResult",
    top_n: int = 3,
    log_dir: Optional[Path] = None,
) -> list[StrategyAnalysis]:
    """
    Convenience function to analyze top strategies from evolution results.

    Args:
        results: EvolutionResult from evolution run
        top_n: Number of top strategies to analyze
        log_dir: Optional logging directory

    Returns:
        List of StrategyAnalysis objects
    """
    analyzer = StrategyAnalyzer(log_dir=log_dir)
    return analyzer.analyze_top_strategies(
        results.final_population,
        top_n=top_n,
    )
