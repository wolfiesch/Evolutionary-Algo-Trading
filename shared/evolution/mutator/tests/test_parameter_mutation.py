"""Tests for parameter mutation module."""
import pytest
import json
from copy import deepcopy

from shared.evolution.parameters.schema import (
    WeightVector,
    CryptoParameters,
)
from shared.evolution.mutator.parameter_mutation import (
    MutationResult,
    parse_mutation_response,
    apply_mutation,
    random_mutate_parameters,
    random_crossover_parameters,
    generate_initial_parameters,
    ParameterEvolutionState,
)


@pytest.fixture
def default_params():
    """Default crypto parameters."""
    return CryptoParameters()


@pytest.fixture
def custom_params():
    """Custom parameters for testing."""
    return CryptoParameters(
        weights_A=WeightVector(
            trend=0.5,
            momentum=0.3,
            mean_reversion=0.2,
            volatility=0.0,
            volume=0.0,
        ),
        weights_B=WeightVector(
            trend=0.7,
            momentum=0.1,
            mean_reversion=0.1,
            volatility=0.1,
            volume=0.0,
        ),
        entry_threshold_long=0.4,
        exit_threshold_long=-0.1,
    )


class TestParseMutationResponse:
    """Tests for parse_mutation_response."""

    def test_parse_valid_json(self):
        """Parses valid JSON response."""
        response = '''
        Here's my suggestion:
        {
            "mutation_type": "adjust_weight",
            "parameter_path": "weights_A.trend",
            "old_value": 0.5,
            "new_value": 0.7,
            "reasoning": "Increase trend weight for stronger momentum capture"
        }
        '''
        result = parse_mutation_response(response)

        assert result is not None
        assert result.mutation_type == "adjust_weight"
        assert result.parameter_path == "weights_A.trend"
        assert result.old_value == 0.5
        assert result.new_value == 0.7
        assert "trend weight" in result.reasoning

    def test_parse_minimal_json(self):
        """Parses minimal JSON with just required fields."""
        response = '{"mutation_type": "tune_period", "parameter_path": "momentum_period"}'
        result = parse_mutation_response(response)

        assert result is not None
        assert result.mutation_type == "tune_period"
        assert result.parameter_path == "momentum_period"

    def test_parse_invalid_json(self):
        """Returns None for invalid JSON."""
        response = "This is not JSON at all"
        result = parse_mutation_response(response)
        assert result is None

    def test_parse_no_json(self):
        """Returns None when no JSON found."""
        response = "I suggest changing the trend weight to 0.7"
        result = parse_mutation_response(response)
        assert result is None


class TestApplyMutation:
    """Tests for apply_mutation."""

    def test_apply_top_level_mutation(self, default_params):
        """Applies mutation to top-level parameter."""
        mutation = MutationResult(
            mutation_type="adjust_threshold",
            parameter_path="entry_threshold_long",
            old_value=0.3,
            new_value=0.5,
            reasoning="Tighten entry",
        )

        new_params = apply_mutation(default_params, mutation)

        # Value should be discretized to nearest 0.05
        assert new_params.entry_threshold_long == 0.5
        assert new_params is not default_params  # Should be a copy

    def test_apply_nested_mutation(self, default_params):
        """Applies mutation to nested parameter (weight vector)."""
        mutation = MutationResult(
            mutation_type="adjust_weight",
            parameter_path="weights_A.trend",
            old_value=0.3,
            new_value=0.6,
            reasoning="Increase trend",
        )

        new_params = apply_mutation(default_params, mutation)

        # Value should be discretized to nearest 0.1
        assert new_params.weights_A.trend == pytest.approx(0.6, abs=0.001)

    def test_apply_mutation_repairs_constraints(self, custom_params):
        """Mutation result respects constraints after repair."""
        # Try to set trend_fast_period > trend_slow_period
        mutation = MutationResult(
            mutation_type="tune_period",
            parameter_path="trend_fast_period",
            old_value=9,
            new_value=100,  # Would violate constraint
            reasoning="Test",
        )

        new_params = apply_mutation(custom_params, mutation)

        # Should be repaired: trend_fast < trend_slow
        assert new_params.trend_fast_period < new_params.trend_slow_period

    def test_apply_mutation_clamps_bounds(self, default_params):
        """Mutation result is clamped to valid bounds."""
        mutation = MutationResult(
            mutation_type="adjust_weight",
            parameter_path="weights_A.trend",
            old_value=0.5,
            new_value=5.0,  # Out of bounds
            reasoning="Test",
        )

        new_params = apply_mutation(default_params, mutation)

        # Should be clamped to [-1, 1]
        assert -1.0 <= new_params.weights_A.trend <= 1.0


class TestRandomMutateParameters:
    """Tests for random_mutate_parameters."""

    def test_returns_different_params(self, default_params):
        """Random mutation produces different parameters."""
        new_params, mutation = random_mutate_parameters(default_params)

        # At least one parameter should be different
        assert new_params is not default_params
        assert mutation.success

    def test_mutation_result_recorded(self, default_params):
        """Mutation result contains valid information."""
        new_params, mutation = random_mutate_parameters(default_params)

        assert mutation.mutation_type in [
            "adjust_weight", "tune_period", "adjust_threshold",
            "adjust_risk", "flip_polarity"
        ]
        assert mutation.parameter_path != ""
        assert mutation.reasoning != ""

    def test_constraints_preserved(self, default_params):
        """Constraints are preserved after random mutation."""
        for _ in range(20):  # Run multiple times due to randomness
            new_params, _ = random_mutate_parameters(default_params)

            # Check key constraints
            assert new_params.trend_fast_period < new_params.trend_slow_period
            assert new_params.entry_threshold_long > new_params.exit_threshold_long
            assert new_params.take_profit_atr_mult > new_params.stop_loss_atr_mult

    def test_discretization_applied(self, default_params):
        """Results are properly discretized."""
        for _ in range(10):
            new_params, _ = random_mutate_parameters(default_params)

            # Weights should be multiples of 0.1
            assert abs(new_params.weights_A.trend * 10) % 1 < 0.001

            # Thresholds should be multiples of 0.05
            assert abs(new_params.entry_threshold_long * 20) % 1 < 0.001


class TestRandomCrossoverParameters:
    """Tests for random_crossover_parameters."""

    def test_crossover_produces_child(self, default_params, custom_params):
        """Crossover produces valid child parameters."""
        child = random_crossover_parameters(
            default_params, custom_params, fitness_a=1.0, fitness_b=2.0
        )

        assert child is not None
        assert isinstance(child, CryptoParameters)

    def test_crossover_constraints_preserved(self, default_params, custom_params):
        """Crossover result respects constraints."""
        for _ in range(10):  # Run multiple times due to randomness
            child = random_crossover_parameters(
                default_params, custom_params, fitness_a=1.0, fitness_b=2.0
            )

            assert child.trend_fast_period < child.trend_slow_period
            assert child.entry_threshold_long > child.exit_threshold_long
            assert child.take_profit_atr_mult > child.stop_loss_atr_mult

    def test_crossover_fitness_weighted(self, default_params, custom_params):
        """Higher fitness parent contributes more (statistically)."""
        # Make parent A have distinctive weights
        default_params.weights_A.trend = 0.1  # Low value
        default_params.weights_A.momentum = 0.1

        # Make parent B have distinctive weights
        custom_params.weights_A.trend = 0.9  # High value
        custom_params.weights_A.momentum = 0.9

        # Run many crossovers with very different fitness (B much higher)
        children_with_high_trend = 0
        trials = 100

        for _ in range(trials):
            child = random_crossover_parameters(
                default_params, custom_params,
                fitness_a=0.1,  # Low fitness
                fitness_b=10.0,  # High fitness
            )
            # weights_A is copied as a group, so check trend from parent B
            if child.weights_A.trend == pytest.approx(0.9, abs=0.001):
                children_with_high_trend += 1

        # With 10:1 fitness ratio, custom_params (B) should dominate
        # But it's group-based, so expect ~90% selection of B's groups
        # Allow some tolerance due to randomness
        assert children_with_high_trend > trials * 0.6  # At least 60%


class TestGenerateInitialParameters:
    """Tests for generate_initial_parameters."""

    def test_generates_correct_count(self):
        """Generates requested number of parameter sets."""
        population = generate_initial_parameters(CryptoParameters, count=5)
        assert len(population) == 5

    def test_preserves_seed(self):
        """First member is the seed if provided."""
        seed = CryptoParameters(
            weights_A=WeightVector(trend=0.9, momentum=0.9),
            entry_threshold_long=0.6,
        )

        population = generate_initial_parameters(CryptoParameters, count=5, seed_params=seed)

        # First should be identical to seed
        assert population[0].weights_A.trend == 0.9
        assert population[0].weights_A.momentum == 0.9
        assert population[0].entry_threshold_long == 0.6

    def test_generates_diverse_population(self):
        """Population has diversity in parameters."""
        population = generate_initial_parameters(CryptoParameters, count=10)

        # Check diversity in at least one parameter
        trend_weights = [p.weights_A.trend for p in population]
        unique_weights = len(set(trend_weights))

        # Should have some diversity (at least 3 different values)
        assert unique_weights >= 3

    def test_all_constraints_valid(self):
        """All generated parameters respect constraints."""
        population = generate_initial_parameters(CryptoParameters, count=20)

        for params in population:
            assert params.trend_fast_period < params.trend_slow_period
            assert params.entry_threshold_long > params.exit_threshold_long
            assert params.take_profit_atr_mult > params.stop_loss_atr_mult


class TestParameterEvolutionState:
    """Tests for ParameterEvolutionState."""

    def test_initial_state(self):
        """Initial state has correct defaults."""
        state = ParameterEvolutionState()

        assert state.generation == 0
        assert state.best_score == 0.0
        assert state.stagnation_count == 0
        assert state.mutation_history == []

    def test_record_mutation(self):
        """Records mutation history correctly."""
        state = ParameterEvolutionState(generation=5)

        mutation = MutationResult(
            mutation_type="adjust_weight",
            parameter_path="weights_A.trend",
            old_value=0.3,
            new_value=0.5,
            reasoning="Increase trend weight",
        )

        state.record_mutation(mutation, new_score=1.5)

        assert len(state.mutation_history) == 1
        record = state.mutation_history[0]
        assert record["generation"] == 5
        assert record["mutation_type"] == "adjust_weight"
        assert record["parameter_path"] == "weights_A.trend"
        assert record["score_after"] == 1.5


class TestMutationTypes:
    """Tests for specific mutation types."""

    def test_weight_adjustment_bounded(self, default_params):
        """Weight adjustments stay in bounds."""
        # Run many mutations
        for _ in range(50):
            params = deepcopy(default_params)
            params.weights_A.trend = 0.9  # Near upper bound
            new_params, mutation = random_mutate_parameters(params)

            # Should never exceed bounds
            assert -1.0 <= new_params.weights_A.trend <= 1.0
            assert -1.0 <= new_params.weights_B.trend <= 1.0

    def test_period_adjustments_positive(self, default_params):
        """Period adjustments stay positive."""
        for _ in range(20):
            params = deepcopy(default_params)
            params.momentum_period = 5  # Near lower bound
            new_params, _ = random_mutate_parameters(params)

            # All periods should be positive
            assert new_params.momentum_period >= 3
            assert new_params.trend_fast_period >= 3
            assert new_params.trend_slow_period >= 10

    def test_polarity_flip(self, default_params):
        """Polarity flip changes sign."""
        # Force many mutations to get a flip
        flips_seen = 0
        for _ in range(100):
            new_params, mutation = random_mutate_parameters(default_params)
            if mutation.mutation_type == "flip_polarity":
                flips_seen += 1
                # New value should be negative of old
                assert mutation.new_value == -mutation.old_value

        # Should see at least some flips
        assert flips_seen > 0
