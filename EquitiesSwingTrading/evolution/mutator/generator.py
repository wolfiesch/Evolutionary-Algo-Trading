"""
Strategy Generator for Equities Swing Trading.

Generates and mutates strategies using LLM with equities-specific prompts.
Validates strategies against allowed primitives and structure requirements.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional, Any

import sys
sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks")

from shared.evolution.mutator.llm_client import LLMClient, create_default_client

from evolution.mutator.prompts import (
    get_equities_generation_prompt,
    get_equities_mutation_prompt,
    get_equities_crossover_prompt,
    EQUITIES_THEMES,
    EQUITIES_MEAN_REVERSION_THEMES,
)
from evolution.mutator.config import EquitiesEvolutionConfig, get_default_config

logger = logging.getLogger(__name__)


@dataclass
class GeneratedStrategy:
    """
    A strategy generated or mutated by the LLM.

    Represents the output of strategy generation/mutation operations.
    """
    name: str
    entry_long: str
    exit_long: str
    rationale: Optional[str] = None
    mutation_type: Optional[str] = None
    mutation_description: Optional[str] = None
    generation: int = 0
    parent_names: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "entry_long": self.entry_long,
            "exit_long": self.exit_long,
            "rationale": self.rationale,
            "mutation_type": self.mutation_type,
            "mutation_description": self.mutation_description,
            "generation": self.generation,
            "parent_names": self.parent_names,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GeneratedStrategy":
        """Create from dictionary."""
        return cls(
            name=data.get("name", "Unknown"),
            entry_long=data.get("entry_long", ""),
            exit_long=data.get("exit_long", ""),
            rationale=data.get("rationale"),
            mutation_type=data.get("mutation_type"),
            mutation_description=data.get("mutation_description"),
            generation=data.get("generation", 0),
            parent_names=data.get("parent_names", []),
        )


class EquitiesStrategyGenerator:
    """
    Generates and mutates equities swing trading strategies.

    Uses LLM to create strategies combining fundamental and technical primitives.
    Validates output against allowed primitives and structure requirements.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        config: Optional[EquitiesEvolutionConfig] = None,
    ):
        """
        Initialize generator.

        Args:
            llm_client: LLM client for generation (creates default if None)
            config: Evolution configuration
        """
        self.llm_client = llm_client or create_default_client()
        self.config = config or get_default_config()

    def generate(
        self,
        theme: Optional[str] = None,
        generation: int = 0,
    ) -> Optional[GeneratedStrategy]:
        """
        Generate a new strategy from theme.

        Args:
            theme: Strategy theme (random if None)
            generation: Current generation number

        Returns:
            GeneratedStrategy or None if generation fails
        """
        import random

        if theme is None:
            # Mix regular and mean-reversion themes
            all_themes = EQUITIES_THEMES + EQUITIES_MEAN_REVERSION_THEMES
            theme = random.choice(all_themes)

        prompt = get_equities_generation_prompt(theme)

        # Try generation with retries
        for attempt in range(self.config.llm_retry_attempts):
            try:
                response = self._call_llm(prompt)
                parsed = self._parse_response(response)

                if parsed is None:
                    logger.warning(f"Failed to parse response on attempt {attempt + 1}")
                    continue

                # Validate strategy
                validation_error = self._validate_strategy(parsed)
                if validation_error:
                    logger.warning(f"Validation failed: {validation_error}")
                    # Add error feedback and retry
                    prompt = self._add_error_feedback(prompt, validation_error)
                    continue

                strategy = GeneratedStrategy(
                    name=parsed.get("name", f"Strategy_{generation}"),
                    entry_long=parsed["entry_long"],
                    exit_long=parsed["exit_long"],
                    rationale=parsed.get("rationale"),
                    generation=generation,
                )
                return strategy

            except Exception as e:
                logger.error(f"Generation error on attempt {attempt + 1}: {e}")
                time.sleep(1 * (attempt + 1))  # Backoff

        logger.error(f"Failed to generate strategy after {self.config.llm_retry_attempts} attempts")
        return None

    def mutate(
        self,
        strategy: GeneratedStrategy,
        sharpe: float,
        win_rate: float,
        max_dd: float,
        trade_count: int,
        generation: int = 0,
    ) -> Optional[GeneratedStrategy]:
        """
        Mutate an existing strategy based on performance.

        Args:
            strategy: Strategy to mutate
            sharpe: Sharpe ratio
            win_rate: Win rate (0-1)
            max_dd: Max drawdown (0-1)
            trade_count: Number of trades
            generation: Current generation number

        Returns:
            Mutated GeneratedStrategy or None if mutation fails
        """
        prompt = get_equities_mutation_prompt(
            strategy_name=strategy.name,
            entry_long=strategy.entry_long,
            exit_long=strategy.exit_long,
            sharpe=sharpe,
            win_rate=win_rate,
            max_dd=max_dd,
            trade_count=trade_count,
        )

        # Try mutation with retries
        for attempt in range(self.config.llm_retry_attempts):
            try:
                response = self._call_llm(prompt)
                parsed = self._parse_response(response)

                if parsed is None:
                    logger.warning(f"Failed to parse mutation response on attempt {attempt + 1}")
                    continue

                # Validate strategy
                validation_error = self._validate_strategy(parsed)
                if validation_error:
                    logger.warning(f"Mutation validation failed: {validation_error}")
                    prompt = self._add_error_feedback(prompt, validation_error)
                    continue

                mutated = GeneratedStrategy(
                    name=parsed.get("name", f"{strategy.name}_mutated"),
                    entry_long=parsed["entry_long"],
                    exit_long=parsed["exit_long"],
                    rationale=parsed.get("rationale"),
                    mutation_type=parsed.get("mutation_type"),
                    mutation_description=parsed.get("mutation_description"),
                    generation=generation,
                    parent_names=[strategy.name],
                )
                return mutated

            except Exception as e:
                logger.error(f"Mutation error on attempt {attempt + 1}: {e}")
                time.sleep(1 * (attempt + 1))

        logger.error(f"Failed to mutate strategy after {self.config.llm_retry_attempts} attempts")
        return None

    def crossover(
        self,
        parent_a: GeneratedStrategy,
        sharpe_a: float,
        parent_b: GeneratedStrategy,
        sharpe_b: float,
        generation: int = 0,
    ) -> Optional[GeneratedStrategy]:
        """
        Combine two parent strategies.

        Args:
            parent_a: First parent strategy
            sharpe_a: First parent's Sharpe ratio
            parent_b: Second parent strategy
            sharpe_b: Second parent's Sharpe ratio
            generation: Current generation number

        Returns:
            Combined GeneratedStrategy or None if crossover fails
        """
        prompt = get_equities_crossover_prompt(
            entry_a=parent_a.entry_long,
            exit_a=parent_a.exit_long,
            sharpe_a=sharpe_a,
            entry_b=parent_b.entry_long,
            exit_b=parent_b.exit_long,
            sharpe_b=sharpe_b,
        )

        # Try crossover with retries
        for attempt in range(self.config.llm_retry_attempts):
            try:
                response = self._call_llm(prompt)
                parsed = self._parse_response(response)

                if parsed is None:
                    logger.warning(f"Failed to parse crossover response on attempt {attempt + 1}")
                    continue

                # Validate strategy
                validation_error = self._validate_strategy(parsed)
                if validation_error:
                    logger.warning(f"Crossover validation failed: {validation_error}")
                    prompt = self._add_error_feedback(prompt, validation_error)
                    continue

                offspring = GeneratedStrategy(
                    name=parsed.get("name", f"Crossover_{generation}"),
                    entry_long=parsed["entry_long"],
                    exit_long=parsed["exit_long"],
                    rationale=parsed.get("rationale"),
                    mutation_type="CROSSOVER",
                    generation=generation,
                    parent_names=[parent_a.name, parent_b.name],
                )
                return offspring

            except Exception as e:
                logger.error(f"Crossover error on attempt {attempt + 1}: {e}")
                time.sleep(1 * (attempt + 1))

        logger.error(f"Failed to crossover strategies after {self.config.llm_retry_attempts} attempts")
        return None

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with prompt."""
        response = self.llm_client.generate(prompt)
        return response

    def _parse_response(self, response: str) -> Optional[dict]:
        """
        Parse LLM response to extract JSON.

        Handles markdown code blocks and raw JSON.
        """
        if not response:
            return None

        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON object
            json_match = re.search(r'\{[^{}]*"name"[^{}]*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                # Last resort: try the whole response
                json_str = response.strip()

        try:
            parsed = json.loads(json_str)
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}")
            return None

    def _validate_strategy(self, parsed: dict) -> Optional[str]:
        """
        Validate parsed strategy against constraints.

        Returns error message if invalid, None if valid.
        """
        # Check required fields
        if "entry_long" not in parsed:
            return "Missing entry_long field"
        if "exit_long" not in parsed:
            return "Missing exit_long field"

        entry = parsed["entry_long"]
        exit_expr = parsed["exit_long"]

        # Check market filter in entry
        if not self._has_market_filter(entry):
            return "Entry must start with a market filter (spy_trend, vix_regime, etc.)"

        # Check market filter has >= 0 condition
        if not self._has_valid_filter_condition(entry):
            return "Market filter must have >= 0 or > 0 condition"

        # Check primitive count
        entry_primitives = self._extract_primitives(entry)
        exit_primitives = self._extract_primitives(exit_expr)

        if len(entry_primitives) > self.config.max_primitives:
            return f"Entry has too many primitives ({len(entry_primitives)} > {self.config.max_primitives})"

        if len(exit_primitives) > self.config.max_primitives:
            return f"Exit has too many primitives ({len(exit_primitives)} > {self.config.max_primitives})"

        # Check all primitives are allowed
        all_primitives = entry_primitives | exit_primitives
        invalid = all_primitives - self.config.allowed_primitives
        if invalid:
            return f"Invalid primitives: {invalid}"

        # Check parameters are numeric
        param_error = self._check_numeric_params(entry)
        if param_error:
            return param_error

        param_error = self._check_numeric_params(exit_expr)
        if param_error:
            return param_error

        return None

    def _has_market_filter(self, expression: str) -> bool:
        """Check if expression starts with a market filter."""
        expr_lower = expression.lower().strip()
        for filter_name in self.config.market_filters:
            if expr_lower.startswith(filter_name):
                return True
        return False

    def _has_valid_filter_condition(self, expression: str) -> bool:
        """Check if market filter has >= 0 or > 0 condition."""
        # Look for pattern: filter_name(params) >= 0 or > 0
        pattern = r'^(spy_trend|vix_regime|spy_momentum|spy_above_sma|market_breadth_proxy)\s*\([^)]*\)\s*(>=|>)\s*(-?\d+\.?\d*)'
        match = re.match(pattern, expression.strip(), re.IGNORECASE)
        return match is not None

    def _extract_primitives(self, expression: str) -> set[str]:
        """Extract primitive names from expression."""
        # Match word followed by opening paren (function call)
        pattern = r'\b([a-z_]+)\s*\('
        matches = re.findall(pattern, expression.lower())

        # Also match standalone comparisons like "insider_intensity > 0.3"
        standalone_pattern = r'\b([a-z_]+)\s*[><=]'
        standalone_matches = re.findall(standalone_pattern, expression.lower())

        # Combine all matches (include unknown to flag them)
        primitives = set(matches) | set(standalone_matches)

        # Exclude logical operators and common words
        exclude = {"and", "or", "not"}
        primitives = primitives - exclude

        return primitives

    def _check_numeric_params(self, expression: str) -> Optional[str]:
        """Check that all parameters are numeric."""
        # Find all function calls with parameters
        pattern = r'(\w+)\(([^)]*)\)'
        matches = re.findall(pattern, expression)

        for func_name, params in matches:
            if not params.strip():
                continue

            # Split parameters
            param_list = [p.strip() for p in params.split(',')]
            for param in param_list:
                # Allow integers and floats
                if not re.match(r'^-?\d+\.?\d*$', param):
                    return f"Non-numeric parameter in {func_name}: {param}"

        return None

    def _add_error_feedback(self, prompt: str, error: str) -> str:
        """Add error feedback to prompt for retry."""
        feedback = f"\n\nPREVIOUS ATTEMPT FAILED: {error}\nPlease fix this issue and try again."
        return prompt + feedback


def generate_initial_population(
    generator: EquitiesStrategyGenerator,
    size: int = 10,
    themes: Optional[list[str]] = None,
) -> list[GeneratedStrategy]:
    """
    Generate initial population of strategies.

    Args:
        generator: Strategy generator
        size: Population size
        themes: Optional custom themes (uses defaults if None)

    Returns:
        List of generated strategies
    """
    if themes is None:
        themes = EQUITIES_THEMES + EQUITIES_MEAN_REVERSION_THEMES

    population = []
    theme_index = 0

    while len(population) < size:
        theme = themes[theme_index % len(themes)]
        theme_index += 1

        strategy = generator.generate(theme=theme, generation=0)
        if strategy:
            population.append(strategy)
            logger.info(f"Generated: {strategy.name}")
        else:
            logger.warning(f"Failed to generate strategy for theme: {theme[:30]}...")

    return population


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test strategy generator (requires LLM API key)."""
    print("Testing strategy generator...")

    # Create generator with mock client for testing structure
    config = get_default_config()

    # Test validation
    generator = EquitiesStrategyGenerator(config=config)

    # Valid strategy
    valid = {
        "name": "Test_Strategy",
        "entry_long": "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND norm_rsi(14) < -0.3",
        "exit_long": "norm_rsi(14) > 0.5",
    }
    error = generator._validate_strategy(valid)
    print(f"Valid strategy validation: {error}")
    assert error is None, f"Should be valid: {error}"

    # Missing market filter
    no_filter = {
        "name": "Bad_Strategy",
        "entry_long": "insider_intensity > 0.3 AND norm_rsi(14) < -0.3",
        "exit_long": "norm_rsi(14) > 0.5",
    }
    error = generator._validate_strategy(no_filter)
    print(f"No filter validation: {error}")
    assert error is not None, "Should fail - no market filter"

    # Too many primitives
    too_many = {
        "name": "Complex_Strategy",
        "entry_long": "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND norm_rsi(14) < -0.3 AND ema_trend(9, 21) > 0 AND volume_intensity(20, 2) > 0.5 AND bb_position(20, 2) < 0",
        "exit_long": "norm_rsi(14) > 0.5",
    }
    error = generator._validate_strategy(too_many)
    print(f"Too many primitives validation: {error}")
    assert error is not None, "Should fail - too many primitives"

    # Invalid primitive
    invalid_primitive = {
        "name": "Invalid_Strategy",
        "entry_long": "spy_trend(20) >= 0 AND fake_primitive(14) > 0",
        "exit_long": "norm_rsi(14) > 0.5",
    }
    error = generator._validate_strategy(invalid_primitive)
    print(f"Invalid primitive validation: {error}")
    assert error is not None, "Should fail - invalid primitive"

    # Test primitive extraction
    expr = "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND norm_rsi(14) < -0.3"
    primitives = generator._extract_primitives(expr)
    print(f"Extracted primitives: {primitives}")
    assert "spy_trend" in primitives
    assert "insider_intensity" in primitives
    assert "norm_rsi" in primitives

    # Test GeneratedStrategy
    strategy = GeneratedStrategy(
        name="Test",
        entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
        exit_long="norm_rsi(14) > 0.5",
        rationale="Test strategy",
        generation=1,
    )
    data = strategy.to_dict()
    restored = GeneratedStrategy.from_dict(data)
    assert restored.name == strategy.name
    assert restored.entry_long == strategy.entry_long

    print("\nAll generator tests passed!")


if __name__ == "__main__":
    quick_test()
