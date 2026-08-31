"""
Tests for equities strategy generator.
"""

import pytest

import sys
sys.path.insert(0, ".")

from evolution.mutator.generator import (
    EquitiesStrategyGenerator,
    GeneratedStrategy,
    generate_initial_population,
)
from evolution.mutator.config import get_default_config, get_fast_config


class TestGeneratedStrategy:
    """Tests for GeneratedStrategy dataclass."""

    def test_creation(self):
        """Should create strategy with required fields."""
        strategy = GeneratedStrategy(
            name="Test_Strategy",
            entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
            exit_long="norm_rsi(14) > 0.5",
        )
        assert strategy.name == "Test_Strategy"
        assert "spy_trend" in strategy.entry_long
        assert "norm_rsi" in strategy.exit_long

    def test_optional_fields(self):
        """Should have optional fields with defaults."""
        strategy = GeneratedStrategy(
            name="Test",
            entry_long="spy_trend(20) >= 0",
            exit_long="norm_rsi(14) > 0.5",
        )
        assert strategy.rationale is None
        assert strategy.mutation_type is None
        assert strategy.generation == 0
        assert strategy.parent_names == []

    def test_to_dict(self):
        """Should serialize to dictionary."""
        strategy = GeneratedStrategy(
            name="Test",
            entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
            exit_long="norm_rsi(14) > 0.5",
            rationale="Test rationale",
            mutation_type="PARAM",
            generation=5,
            parent_names=["Parent1"],
        )
        data = strategy.to_dict()
        assert data["name"] == "Test"
        assert data["entry_long"] == strategy.entry_long
        assert data["rationale"] == "Test rationale"
        assert data["mutation_type"] == "PARAM"
        assert data["generation"] == 5

    def test_from_dict(self):
        """Should deserialize from dictionary."""
        data = {
            "name": "Restored_Strategy",
            "entry_long": "spy_trend(20) >= 0",
            "exit_long": "norm_rsi(14) > 0.5",
            "rationale": "Restored",
            "generation": 3,
        }
        strategy = GeneratedStrategy.from_dict(data)
        assert strategy.name == "Restored_Strategy"
        assert strategy.generation == 3

    def test_roundtrip(self):
        """Should survive serialization roundtrip."""
        original = GeneratedStrategy(
            name="Original",
            entry_long="spy_trend(20) >= 0 AND insider_intensity > 0.3",
            exit_long="norm_rsi(14) > 0.5",
            mutation_type="SWAP",
            parent_names=["Parent1", "Parent2"],
        )
        data = original.to_dict()
        restored = GeneratedStrategy.from_dict(data)
        assert restored.name == original.name
        assert restored.entry_long == original.entry_long
        assert restored.exit_long == original.exit_long
        assert restored.mutation_type == original.mutation_type
        assert restored.parent_names == original.parent_names


class TestStrategyValidation:
    """Tests for strategy validation logic."""

    @pytest.fixture
    def generator(self):
        """Create generator for testing."""
        return EquitiesStrategyGenerator(
            llm_client=None,  # Don't need LLM for validation tests
            config=get_default_config(),
        )

    def test_valid_strategy(self, generator):
        """Should accept valid strategy."""
        parsed = {
            "name": "Valid_Strategy",
            "entry_long": "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND norm_rsi(14) < -0.3",
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is None

    def test_missing_entry(self, generator):
        """Should reject missing entry_long."""
        parsed = {
            "name": "Bad_Strategy",
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert "entry_long" in error.lower()

    def test_missing_exit(self, generator):
        """Should reject missing exit_long."""
        parsed = {
            "name": "Bad_Strategy",
            "entry_long": "spy_trend(20) >= 0 AND insider_intensity > 0.3",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert "exit_long" in error.lower()

    def test_missing_market_filter(self, generator):
        """Should reject entry without market filter."""
        parsed = {
            "name": "No_Filter",
            "entry_long": "insider_intensity > 0.3 AND norm_rsi(14) < -0.3",
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert "market filter" in error.lower()

    def test_invalid_filter_condition(self, generator):
        """Should reject filter without >= 0 condition."""
        parsed = {
            "name": "Bad_Filter",
            "entry_long": "spy_trend(20) < 0 AND insider_intensity > 0.3",  # < 0 instead of >= 0
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert ">= 0" in error or "> 0" in error

    def test_too_many_primitives(self, generator):
        """Should reject too many primitives."""
        parsed = {
            "name": "Complex_Strategy",
            "entry_long": "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND norm_rsi(14) < -0.3 AND ema_trend(9, 21) > 0 AND volume_intensity(20, 2) > 0.5 AND bb_position(20, 2) < 0",
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert "too many" in error.lower()

    def test_invalid_primitive(self, generator):
        """Should reject unknown primitives."""
        parsed = {
            "name": "Invalid_Primitive",
            "entry_long": "spy_trend(20) >= 0 AND fake_signal(14) > 0.5",
            "exit_long": "norm_rsi(14) > 0.5",
        }
        error = generator._validate_strategy(parsed)
        assert error is not None
        assert "invalid" in error.lower().lower()

    def test_all_market_filters_accepted(self, generator):
        """Should accept all defined market filters."""
        filters = ["spy_trend", "vix_regime", "spy_momentum", "spy_above_sma"]
        for filter_name in filters:
            parsed = {
                "name": f"{filter_name}_Strategy",
                "entry_long": f"{filter_name}(20) >= 0 AND insider_intensity > 0.3",
                "exit_long": "norm_rsi(14) > 0.5",
            }
            error = generator._validate_strategy(parsed)
            assert error is None, f"Filter {filter_name} should be valid: {error}"


class TestPrimitiveExtraction:
    """Tests for primitive extraction."""

    @pytest.fixture
    def generator(self):
        return EquitiesStrategyGenerator(
            llm_client=None,
            config=get_default_config(),
        )

    def test_extract_basic(self, generator):
        """Should extract basic primitives."""
        expr = "spy_trend(20) >= 0 AND norm_rsi(14) < -0.3"
        primitives = generator._extract_primitives(expr)
        assert "spy_trend" in primitives
        assert "norm_rsi" in primitives

    def test_extract_with_fundamentals(self, generator):
        """Should extract fundamental primitives."""
        expr = "spy_trend(20) >= 0 AND insider_intensity > 0.3 AND earnings_quality > 0.5"
        primitives = generator._extract_primitives(expr)
        assert "spy_trend" in primitives
        assert "insider_intensity" in primitives
        assert "earnings_quality" in primitives

    def test_extract_includes_unknown(self, generator):
        """Should include unknown primitives (for validation to catch)."""
        expr = "spy_trend(20) >= 0 AND fake_thing(14) > 0"
        primitives = generator._extract_primitives(expr)
        assert "spy_trend" in primitives
        # Unknown primitives are now included so validation can flag them
        assert "fake_thing" in primitives

    def test_extract_multiple_params(self, generator):
        """Should handle primitives with multiple params."""
        expr = "ema_trend(9, 21) > 0 AND bb_position(20, 2) < 0"
        primitives = generator._extract_primitives(expr)
        assert "ema_trend" in primitives
        assert "bb_position" in primitives


class TestMarketFilterDetection:
    """Tests for market filter detection."""

    @pytest.fixture
    def generator(self):
        return EquitiesStrategyGenerator(
            llm_client=None,
            config=get_default_config(),
        )

    def test_has_spy_trend(self, generator):
        """Should detect spy_trend filter."""
        assert generator._has_market_filter("spy_trend(20) >= 0 AND norm_rsi(14) < -0.3")

    def test_has_vix_regime(self, generator):
        """Should detect vix_regime filter."""
        assert generator._has_market_filter("vix_regime(10) >= 0 AND norm_rsi(14) < -0.3")

    def test_no_filter(self, generator):
        """Should detect missing filter."""
        assert not generator._has_market_filter("norm_rsi(14) < -0.3 AND ema_trend(9, 21) > 0")

    def test_filter_not_first(self, generator):
        """Should reject filter not at start."""
        # Our implementation checks if expression STARTS with filter
        assert not generator._has_market_filter("norm_rsi(14) < -0.3 AND spy_trend(20) >= 0")


class TestNumericParamCheck:
    """Tests for numeric parameter validation."""

    @pytest.fixture
    def generator(self):
        return EquitiesStrategyGenerator(
            llm_client=None,
            config=get_default_config(),
        )

    def test_valid_integer_params(self, generator):
        """Should accept integer parameters."""
        error = generator._check_numeric_params("norm_rsi(14)")
        assert error is None

    def test_valid_float_params(self, generator):
        """Should accept float parameters."""
        error = generator._check_numeric_params("bb_position(20, 2.0)")
        assert error is None

    def test_valid_multiple_params(self, generator):
        """Should accept multiple params."""
        error = generator._check_numeric_params("ema_trend(9, 21)")
        assert error is None

    def test_invalid_string_param(self, generator):
        """Should reject string parameters."""
        error = generator._check_numeric_params("norm_rsi(fast)")
        assert error is not None
        assert "Non-numeric" in error


class TestJSONParsing:
    """Tests for JSON response parsing."""

    @pytest.fixture
    def generator(self):
        return EquitiesStrategyGenerator(
            llm_client=None,
            config=get_default_config(),
        )

    def test_parse_raw_json(self, generator):
        """Should parse raw JSON."""
        response = '{"name": "Test", "entry_long": "spy_trend(20) >= 0", "exit_long": "norm_rsi(14) > 0.5"}'
        parsed = generator._parse_response(response)
        assert parsed is not None
        assert parsed["name"] == "Test"

    def test_parse_markdown_json(self, generator):
        """Should parse JSON in markdown code block."""
        response = '''Here's the strategy:
```json
{"name": "Test", "entry_long": "spy_trend(20) >= 0", "exit_long": "norm_rsi(14) > 0.5"}
```
This is a good strategy.'''
        parsed = generator._parse_response(response)
        assert parsed is not None
        assert parsed["name"] == "Test"

    def test_parse_plain_code_block(self, generator):
        """Should parse JSON in plain code block."""
        response = '''Strategy:
```
{"name": "Test", "entry_long": "spy_trend(20) >= 0", "exit_long": "norm_rsi(14) > 0.5"}
```'''
        parsed = generator._parse_response(response)
        assert parsed is not None
        assert parsed["name"] == "Test"

    def test_parse_invalid_json(self, generator):
        """Should return None for invalid JSON."""
        response = "This is not JSON at all"
        parsed = generator._parse_response(response)
        assert parsed is None

    def test_parse_empty_response(self, generator):
        """Should return None for empty response."""
        parsed = generator._parse_response("")
        assert parsed is None

        parsed = generator._parse_response(None)
        assert parsed is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
