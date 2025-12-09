"""
Crossover operator for evolutionary strategy search.

Phase 2D: LLM-guided crossover combining parent strategies.
"""
import logging
import time
from typing import Optional

from shared.evolution.fitness import FitnessResult
from shared.evolution.mutator.llm_client import LLMClient
from shared.evolution.mutator.generator import GeneratedStrategy
from shared.evolution.mutator.prompts import get_crossover_prompt

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]


class CrossoverOperator:
    """
    LLM-guided crossover operator.

    Combines two parent strategies into a child strategy by:
    1. Analyzing both parent's entry/exit conditions
    2. Using LLM to intelligently combine the best elements
    3. Validating the resulting strategy

    Usage:
        crossover = CrossoverOperator(llm_client)
        child = crossover.crossover(parent_a, fitness_a, parent_b, fitness_b)
    """

    # Allowed primitives for validation (same as StrategyGenerator)
    ALLOWED_PRIMITIVES = {
        "ema_trend",
        "price_position",
        "norm_rsi",
        "bb_position",
        "bb_width_percentile",
        "volume_intensity",
        "vwap_distance",
        "atr_regime",
        "atr_percentile",
    }

    def __init__(
        self,
        llm_client: LLMClient,
        market_filter_name: str = "btc_trend",
    ):
        """
        Initialize crossover operator.

        Args:
            llm_client: LLM client for generating crossover strategies
            market_filter_name: Name of market filter primitive
        """
        self.llm_client = llm_client
        self.market_filter_name = market_filter_name
        self._allowed = self.ALLOWED_PRIMITIVES | {market_filter_name}

    def crossover(
        self,
        parent_a: GeneratedStrategy,
        fitness_a: FitnessResult,
        parent_b: GeneratedStrategy,
        fitness_b: FitnessResult,
    ) -> Optional[GeneratedStrategy]:
        """
        Perform crossover between two parent strategies.

        Args:
            parent_a: First parent strategy
            fitness_a: Fitness of first parent
            parent_b: Second parent strategy
            fitness_b: Fitness of second parent

        Returns:
            Child strategy combining elements from both parents, or None if failed
        """
        # Build crossover prompt
        prompt = get_crossover_prompt(
            name_a=parent_a.name,
            entry_a=parent_a.entry_long,
            exit_a=parent_a.exit_long,
            sharpe_a=fitness_a.sharpe_ratio,
            name_b=parent_b.name,
            entry_b=parent_b.entry_long,
            exit_b=parent_b.exit_long,
            sharpe_b=fitness_b.sharpe_ratio,
            market_filter_name=self.market_filter_name,
        )

        context = {
            "action": "crossover",
            "parent_a": parent_a.name,
            "parent_b": parent_b.name,
        }

        return self._call_with_retry(prompt, context)

    def _call_with_retry(
        self,
        prompt: str,
        context: dict,
    ) -> Optional[GeneratedStrategy]:
        """
        Call LLM with retry logic.

        Args:
            prompt: Prompt to send
            context: Context for logging

        Returns:
            GeneratedStrategy or None if all retries fail
        """
        import json
        import re

        last_error = None

        for attempt in range(MAX_RETRIES):
            try:
                response = self.llm_client.generate(prompt, context)
                strategy = self._parse_response(response)

                if strategy:
                    # Validate the strategy
                    validation_error = self._validate_strategy(strategy)
                    if validation_error:
                        logger.warning(
                            f"Crossover validation failed (attempt {attempt + 1}): {validation_error}"
                        )
                        last_error = validation_error
                        # Add error feedback to prompt for retry
                        prompt = self._add_error_feedback(prompt, validation_error)
                    else:
                        return strategy
                else:
                    last_error = "Failed to parse JSON response"
                    logger.warning(f"Crossover parse failed (attempt {attempt + 1})")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Crossover LLM call failed (attempt {attempt + 1}): {e}")

            # Wait before retry (except on last attempt)
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_BACKOFF[attempt])

        logger.error(f"Crossover failed after {MAX_RETRIES} attempts. Last error: {last_error}")
        return None

    def _parse_response(self, response: str) -> Optional[GeneratedStrategy]:
        """
        Parse LLM response to extract crossover strategy JSON.

        Args:
            response: Raw LLM response text

        Returns:
            GeneratedStrategy or None if parsing fails
        """
        import json
        import re

        # Try to extract JSON from response
        json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r"\{[^{}]*\}", response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return None

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            return None

        # Extract required fields
        name = data.get("strategy_name", "")
        entry_long = data.get("entry_long", "")
        exit_long = data.get("exit_long", "")

        if not name or not entry_long or not exit_long:
            return None

        return GeneratedStrategy(
            name=name,
            entry_long=entry_long,
            exit_long=exit_long,
            rationale=data.get("crossover_description"),
            mutation_type="crossover",
            mutation_description=data.get("crossover_description"),
        )

    def _validate_strategy(self, strategy: GeneratedStrategy) -> Optional[str]:
        """
        Validate strategy against constraints.

        Args:
            strategy: Strategy to validate

        Returns:
            Error message string or None if valid
        """
        import re

        # Check market filter is present in entry
        if self.market_filter_name not in strategy.entry_long:
            return f"Entry must include {self.market_filter_name}() check"

        # Check market filter has >= 0 condition
        filter_pattern = rf"{self.market_filter_name}\(\d+\)\s*>=\s*0"
        if not re.search(filter_pattern, strategy.entry_long):
            return f"Entry must include '{self.market_filter_name}(N) >= 0' check"

        # Extract all function calls
        func_pattern = re.compile(r"(\w+)\([^)]*\)")
        entry_funcs = set(func_pattern.findall(strategy.entry_long))
        exit_funcs = set(func_pattern.findall(strategy.exit_long))
        all_funcs = entry_funcs | exit_funcs

        # Check all primitives are allowed
        unknown = all_funcs - self._allowed
        if unknown:
            return f"Unknown primitives: {', '.join(unknown)}"

        # Check primitive count (max 5 per expression)
        if len(entry_funcs) > 5:
            return f"Entry has too many primitives: {len(entry_funcs)} > 5"
        if len(exit_funcs) > 5:
            return f"Exit has too many primitives: {len(exit_funcs)} > 5"

        return None  # Valid

    def _add_error_feedback(self, prompt: str, error: str) -> str:
        """Add error feedback to prompt for retry."""
        feedback = f"\n\n## IMPORTANT: Previous attempt failed with error:\n{error}\n\nPlease fix this issue and try again."
        return prompt + feedback
