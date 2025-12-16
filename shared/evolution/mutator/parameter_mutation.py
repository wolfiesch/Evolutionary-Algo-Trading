"""
Parameter Mutation - LLM-driven parameter evolution.

Unlike string-based strategy evolution, this module evolves PARAMETERS
of fixed strategy templates. The strategy logic is fixed; only the
parameters (weights, periods, thresholds) are evolved.

Key benefits:
- Tractable search space (finite combinations)
- No syntax errors possible
- Guaranteed valid strategies
- Easier for LLM to reason about
"""
import json
import logging
import random
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Optional, Type, TypeVar

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
    ForexParameters,
)
from shared.evolution.parameters.validation import (
    repair_constraints,
    clamp_to_bounds,
)
from shared.evolution.parameters.discretization import (
    discretize_parameters,
)

logger = logging.getLogger(__name__)

# Type variable for parameter classes
P = TypeVar("P", bound=UniversalParameters)


# === PARAMETER MUTATION PROMPTS ===

PARAMETER_MUTATION_SYSTEM_PROMPT = """You are evolving trading strategy PARAMETERS (not logic).

The strategy template has FIXED logic:
- Calculates weighted signals from: trend, momentum, mean_reversion, volatility, volume
- Uses REGIME SWITCHING: weights_A for ranging markets, weights_B for trending markets
- Entry when: market_filter >= threshold AND composite_signal > entry_threshold
- Exit when: composite_signal < exit_threshold
- Supports BIDIRECTIONAL trading: long AND/OR short positions

Your job: TUNE THE PARAMETERS to improve performance.

PARAMETER TYPES:

1. WEIGHTS (-1.0 to +1.0): How much each signal contributes
   - Positive = use signal normally
   - Negative = use signal in reverse (contrarian)
   - Zero = signal disabled
   - weights_A: Used when market is RANGING (low ADX/volatility)
   - weights_B: Used when market is TRENDING (high ADX/volatility)

2. PERIODS (integers): Lookback windows for calculations
   - Smaller = faster, more reactive, more noise
   - Larger = slower, smoother, more lag
   - CONSTRAINT: trend_fast_period < trend_slow_period

3. THRESHOLDS: Decision boundaries
   - Higher entry_threshold_long = fewer trades, higher conviction required
   - Lower exit_threshold_long = hold longer, wider swings
   - For shorts: entry_threshold_short is NEGATIVE (e.g., -0.4)
   - CONSTRAINT: entry_threshold_long > exit_threshold_long
   - CONSTRAINT: entry_threshold_short < exit_threshold_short

4. RISK: Stop-loss and take-profit ATR multipliers
   - Higher = wider stops/targets, fewer stopped out, larger swings
   - Lower = tighter stops/targets, more stopped out, smaller swings
   - CONSTRAINT: take_profit_atr_mult > stop_loss_atr_mult

5. REGIME SELECTOR: How to detect market regime
   - regime_indicator: "adx", "atr_percentile", or "bb_width"
   - regime_period: lookback for regime calculation
   - regime_threshold: cutoff for regime B (trending)

6. DIRECTION CONTROL:
   - allow_long: True/False to enable long trades
   - allow_short: True/False to enable short trades

MUTATION GUIDANCE:
- If Sharpe is positive but low: Fine-tune weights and thresholds
- If win rate is low: Tighten entry_threshold or adjust signal weights
- If drawdown is high: Lower risk multipliers or disable volatile signals
- If too few trades: Loosen thresholds or enable more signals
- If different in ranging vs trending: Adjust weights_A vs weights_B differently
- If shorts underperform: Consider disabling allow_short or adjusting short thresholds"""

PARAMETER_MUTATION_PROMPT = """Current strategy parameters:
{current_params_json}

Performance metrics:
- Sharpe: {sharpe:.2f}
- Win Rate: {win_rate:.1f}%
- Max Drawdown: {max_dd:.1f}%
- Trade Count: {trade_count}
- Profit Factor: {profit_factor:.2f}

Suggest ONE parameter mutation to improve performance.

Return JSON:
{{
  "mutation_type": "adjust_weight|tune_period|adjust_threshold|adjust_risk|flip_polarity|enable_signal|disable_signal|switch_regime|enable_direction|disable_direction",
  "parameter_path": "path.to.parameter (e.g., weights_A.trend or entry_threshold_long)",
  "old_value": <current value>,
  "new_value": <proposed value>,
  "reasoning": "brief explanation"
}}

JSON only:"""

PARAMETER_CROSSOVER_PROMPT = """Combine parameters from two parent strategies:

Parent A (Sharpe={sharpe_a:.2f}):
{params_a_json}

Parent B (Sharpe={sharpe_b:.2f}):
{params_b_json}

Create a child strategy by selecting the better parameters from each parent.
Preserve constraint relationships (e.g., trend_fast < trend_slow).

Return JSON with the full parameter set for the child.

JSON only:"""


@dataclass
class MutationResult:
    """Result of a parameter mutation."""

    mutation_type: str
    parameter_path: str
    old_value: any
    new_value: any
    reasoning: str
    success: bool = True
    error: Optional[str] = None


def parse_mutation_response(response_text: str) -> Optional[MutationResult]:
    """
    Parse LLM response into MutationResult.

    Args:
        response_text: Raw LLM response text

    Returns:
        MutationResult or None if parsing fails
    """
    try:
        # Find JSON in response
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start == -1 or end == 0:
            logger.warning("No JSON found in mutation response")
            return None

        json_str = response_text[start:end]
        data = json.loads(json_str)

        return MutationResult(
            mutation_type=data.get("mutation_type", "unknown"),
            parameter_path=data.get("parameter_path", ""),
            old_value=data.get("old_value"),
            new_value=data.get("new_value"),
            reasoning=data.get("reasoning", ""),
        )
    except Exception as e:
        logger.warning(f"Failed to parse mutation response: {e}")
        return None


def apply_mutation(
    params: P,
    mutation: MutationResult,
) -> P:
    """
    Apply a mutation to parameters.

    Args:
        params: Current parameters
        mutation: Mutation to apply

    Returns:
        New parameter object with mutation applied
    """
    # Deep copy to avoid modifying original
    new_params = deepcopy(params)

    # Parse parameter path (e.g., "weights_A.trend" or "entry_threshold_long")
    path_parts = mutation.parameter_path.split(".")

    try:
        if len(path_parts) == 1:
            # Top-level parameter
            setattr(new_params, path_parts[0], mutation.new_value)
        elif len(path_parts) == 2:
            # Nested parameter (e.g., weights_A.trend)
            parent = getattr(new_params, path_parts[0])
            setattr(parent, path_parts[1], mutation.new_value)
        else:
            logger.warning(f"Invalid parameter path: {mutation.parameter_path}")
            return params

        # Validate and repair constraints
        new_params = repair_constraints(new_params)
        new_params = clamp_to_bounds(new_params)
        new_params = discretize_parameters(new_params)

        return new_params

    except Exception as e:
        logger.warning(f"Failed to apply mutation: {e}")
        return params


def mutate_parameters(
    params: P,
    sharpe: float,
    win_rate: float,
    max_dd: float,
    trade_count: int,
    profit_factor: float = 1.0,
    llm_client=None,
) -> tuple[P, MutationResult]:
    """
    Mutate parameters using LLM guidance.

    Args:
        params: Current parameters
        sharpe: Sharpe ratio from backtest
        win_rate: Win rate (0-1)
        max_dd: Max drawdown (0-1)
        trade_count: Number of trades
        profit_factor: Profit factor
        llm_client: Optional LLM client (if None, uses random mutation)

    Returns:
        Tuple of (new_params, mutation_result)
    """
    if llm_client is None:
        # Random mutation fallback
        return random_mutate_parameters(params)

    # Build prompt
    prompt = PARAMETER_MUTATION_PROMPT.format(
        current_params_json=json.dumps(params.to_dict(), indent=2),
        sharpe=sharpe,
        win_rate=win_rate * 100,
        max_dd=max_dd * 100,
        trade_count=trade_count,
        profit_factor=profit_factor,
    )

    # Call LLM
    try:
        response = llm_client.chat(
            system_prompt=PARAMETER_MUTATION_SYSTEM_PROMPT,
            user_prompt=prompt,
        )

        mutation = parse_mutation_response(response)
        if mutation is None:
            logger.warning("Failed to parse LLM mutation, using random")
            return random_mutate_parameters(params)

        new_params = apply_mutation(params, mutation)
        return new_params, mutation

    except Exception as e:
        logger.warning(f"LLM mutation failed: {e}, using random")
        return random_mutate_parameters(params)


def random_mutate_parameters(
    params: P,
) -> tuple[P, MutationResult]:
    """
    Apply a random mutation to parameters.

    Used as fallback when LLM is unavailable or fails.

    Args:
        params: Current parameters

    Returns:
        Tuple of (new_params, mutation_result)
    """
    new_params = deepcopy(params)

    # Choose mutation type
    mutation_types = [
        "adjust_weight",
        "tune_period",
        "adjust_threshold",
        "adjust_risk",
        "flip_polarity",
    ]
    mutation_type = random.choice(mutation_types)

    # Apply based on type
    if mutation_type == "adjust_weight":
        # Pick random weight from either regime
        regime = random.choice(["weights_A", "weights_B"])
        signal = random.choice(["trend", "momentum", "mean_reversion", "volatility", "volume"])
        weights = getattr(new_params, regime)
        old_value = getattr(weights, signal)
        # Adjust by ±0.1 to ±0.3
        delta = random.choice([-0.3, -0.2, -0.1, 0.1, 0.2, 0.3])
        new_value = max(-1.0, min(1.0, old_value + delta))
        setattr(weights, signal, new_value)
        parameter_path = f"{regime}.{signal}"

    elif mutation_type == "tune_period":
        # Pick random period parameter
        period_params = [
            "trend_fast_period", "trend_slow_period", "momentum_period",
            "reversion_period", "volatility_period", "volume_period",
            "regime_period", "market_filter_period",
        ]
        param_name = random.choice(period_params)
        old_value = getattr(new_params, param_name)
        # Adjust by ±20%
        delta = int(old_value * random.choice([-0.2, -0.1, 0.1, 0.2]))
        delta = max(1, abs(delta)) * (1 if delta >= 0 else -1)
        new_value = max(3, old_value + delta)
        setattr(new_params, param_name, new_value)
        parameter_path = param_name

    elif mutation_type == "adjust_threshold":
        # Pick random threshold
        threshold_params = [
            "entry_threshold_long", "exit_threshold_long",
            "entry_threshold_short", "exit_threshold_short",
            "market_filter_threshold", "regime_threshold",
        ]
        param_name = random.choice(threshold_params)
        old_value = getattr(new_params, param_name)
        # Adjust by ±0.05 to ±0.15
        delta = random.choice([-0.15, -0.1, -0.05, 0.05, 0.1, 0.15])
        new_value = old_value + delta
        setattr(new_params, param_name, new_value)
        parameter_path = param_name

    elif mutation_type == "adjust_risk":
        # Pick stop loss or take profit
        param_name = random.choice(["stop_loss_atr_mult", "take_profit_atr_mult"])
        old_value = getattr(new_params, param_name)
        # Adjust by ±0.5
        delta = random.choice([-0.5, 0.5])
        new_value = max(0.5, old_value + delta)
        setattr(new_params, param_name, new_value)
        parameter_path = param_name

    else:  # flip_polarity
        # Flip a weight's sign
        regime = random.choice(["weights_A", "weights_B"])
        signal = random.choice(["trend", "momentum", "mean_reversion", "volatility", "volume"])
        weights = getattr(new_params, regime)
        old_value = getattr(weights, signal)
        new_value = -old_value
        setattr(weights, signal, new_value)
        parameter_path = f"{regime}.{signal}"

    # Validate and repair
    new_params = repair_constraints(new_params)
    new_params = clamp_to_bounds(new_params)
    new_params = discretize_parameters(new_params)

    mutation = MutationResult(
        mutation_type=mutation_type,
        parameter_path=parameter_path,
        old_value=old_value,
        new_value=new_value,
        reasoning="Random mutation (LLM fallback)",
    )

    return new_params, mutation


def crossover_parameters(
    parent_a: P,
    parent_b: P,
    fitness_a: float = 0.0,
    fitness_b: float = 0.0,
    llm_client=None,
) -> P:
    """
    Crossover two parameter sets.

    Args:
        parent_a: First parent parameters
        parent_b: Second parent parameters
        fitness_a: Fitness of parent A (for weighted selection)
        fitness_b: Fitness of parent B (for weighted selection)
        llm_client: Optional LLM client (if None, uses random crossover)

    Returns:
        Child parameters
    """
    if llm_client is not None:
        # Try LLM-guided crossover
        try:
            prompt = PARAMETER_CROSSOVER_PROMPT.format(
                sharpe_a=fitness_a,
                params_a_json=json.dumps(parent_a.to_dict(), indent=2),
                sharpe_b=fitness_b,
                params_b_json=json.dumps(parent_b.to_dict(), indent=2),
            )

            response = llm_client.chat(
                system_prompt=PARAMETER_MUTATION_SYSTEM_PROMPT,
                user_prompt=prompt,
            )

            # Parse response as JSON
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > 0:
                json_str = response[start:end]
                data = json.loads(json_str)

                # Reconstruct parameters
                child = type(parent_a).from_dict(data)
                child = repair_constraints(child)
                child = clamp_to_bounds(child)
                child = discretize_parameters(child)
                return child

        except Exception as e:
            logger.warning(f"LLM crossover failed: {e}, using random")

    # Random crossover fallback
    return random_crossover_parameters(parent_a, parent_b, fitness_a, fitness_b)


def random_crossover_parameters(
    parent_a: P,
    parent_b: P,
    fitness_a: float = 0.0,
    fitness_b: float = 0.0,
) -> P:
    """
    Perform random grouped crossover of parameters.

    Uses group-based crossover: keeps related parameters together.
    Higher fitness parent is more likely to contribute each group.

    Args:
        parent_a: First parent parameters
        parent_b: Second parent parameters
        fitness_a: Fitness of parent A
        fitness_b: Fitness of parent B

    Returns:
        Child parameters
    """
    # Start with copy of parent_a
    child = deepcopy(parent_a)

    # Calculate selection probability for parent A
    total = abs(fitness_a) + abs(fitness_b)
    p_a = 0.5 if total == 0 else abs(fitness_a) / total

    # Group-based crossover
    param_groups = {
        "weights_A": ["weights_A"],
        "weights_B": ["weights_B"],
        "periods": [
            "trend_fast_period", "trend_slow_period", "momentum_period",
            "reversion_period", "volatility_period", "volume_period",
        ],
        "long_thresholds": ["entry_threshold_long", "exit_threshold_long"],
        "short_thresholds": ["entry_threshold_short", "exit_threshold_short"],
        "risk": ["stop_loss_atr_mult", "take_profit_atr_mult"],
        "regime": ["regime_indicator", "regime_period", "regime_threshold"],
        "market_filter": ["market_filter_period", "market_filter_threshold"],
        "direction": ["allow_long", "allow_short"],
    }

    for group_name, params in param_groups.items():
        # Select source parent
        source = parent_a if random.random() < p_a else parent_b

        for param_name in params:
            if param_name in ["weights_A", "weights_B"]:
                # Copy entire weight vector
                setattr(child, param_name, deepcopy(getattr(source, param_name)))
            else:
                # Copy single parameter
                if hasattr(source, param_name):
                    setattr(child, param_name, getattr(source, param_name))

    # Validate and repair
    child = repair_constraints(child)
    child = clamp_to_bounds(child)
    child = discretize_parameters(child)

    return child


@dataclass
class ParameterEvolutionState:
    """State for parameter-based evolution."""

    generation: int = 0
    best_score: float = 0.0
    stagnation_count: int = 0
    mutation_history: list[dict] = field(default_factory=list)

    def record_mutation(self, mutation: MutationResult, new_score: float):
        """Record a mutation for history tracking."""
        self.mutation_history.append({
            "generation": self.generation,
            "mutation_type": mutation.mutation_type,
            "parameter_path": mutation.parameter_path,
            "old_value": mutation.old_value,
            "new_value": mutation.new_value,
            "reasoning": mutation.reasoning,
            "score_after": new_score,
        })


def generate_initial_parameters(
    param_class: Type[P],
    count: int = 10,
    seed_params: Optional[P] = None,
) -> list[P]:
    """
    Generate initial population of parameters.

    Args:
        param_class: Parameter class to instantiate
        count: Number of parameter sets to generate
        seed_params: Optional seed parameters to vary

    Returns:
        List of parameter objects
    """
    population = []

    for i in range(count):
        if seed_params is not None and i == 0:
            # Keep seed as first member
            population.append(deepcopy(seed_params))
        elif seed_params is not None and i < count // 2:
            # Vary from seed for first half
            varied, _ = random_mutate_parameters(deepcopy(seed_params))
            # Apply multiple mutations for more diversity
            for _ in range(random.randint(1, 3)):
                varied, _ = random_mutate_parameters(varied)
            population.append(varied)
        else:
            # Random parameters for rest
            params = param_class()
            # Randomize weights
            for regime in ["weights_A", "weights_B"]:
                weights = getattr(params, regime)
                for signal in ["trend", "momentum", "mean_reversion", "volatility", "volume"]:
                    # Random weight in steps of 0.1
                    value = random.choice([-0.5, -0.3, 0.0, 0.0, 0.0, 0.3, 0.5, 0.7])
                    setattr(weights, signal, value)

            # Randomize some thresholds
            params.entry_threshold_long = random.choice([0.2, 0.3, 0.4, 0.5])
            params.exit_threshold_long = random.choice([-0.2, -0.1, 0.0, 0.1])
            params.entry_threshold_short = random.choice([-0.5, -0.4, -0.3, -0.2])
            params.exit_threshold_short = random.choice([-0.1, 0.0, 0.1, 0.2])

            # Validate
            params = repair_constraints(params)
            params = clamp_to_bounds(params)
            params = discretize_parameters(params)

            population.append(params)

    return population
