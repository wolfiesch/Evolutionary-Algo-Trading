"""Tests for gene expression parser."""
import pytest
import pandas as pd
from engine.strategy_logic.parser import (
    GeneExpressionParser,
    Strategy,
    Signal,
    PRIMITIVES,
)


def candles_to_df(candles: list) -> pd.DataFrame:
    """Convert list of Candle objects to DataFrame."""
    data = {
        'timestamp': [c.timestamp for c in candles],
        'open': [c.open for c in candles],
        'high': [c.high for c in candles],
        'low': [c.low for c in candles],
        'close': [c.close for c in candles],
        'volume': [c.volume for c in candles],
    }
    return pd.DataFrame(data)


@pytest.fixture
def parser():
    """Parser instance."""
    return GeneExpressionParser()


@pytest.fixture
def valid_strategy_json():
    """Valid strategy JSON for testing."""
    return {
        "strategy_name": "Test_RSI_Mean_Reversion",
        "entry_long": "btc_trend(60) >= 0 AND norm_rsi(14) < -0.4",
        "exit_long": "norm_rsi(14) > 0.4",
        "entry_short": None,
        "exit_short": None,
    }


@pytest.fixture
def complex_strategy_json():
    """More complex strategy with multiple conditions."""
    return {
        "strategy_name": "Complex_Multi_Condition",
        "entry_long": "btc_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4 AND volume_intensity(20,2.0) == 1.0",
        "exit_long": "norm_rsi(14) > 0.6 AND ema_trend(9,21) == -1.0",
    }


@pytest.fixture
def invalid_strategy_json():
    """Strategy with unknown primitive."""
    return {
        "strategy_name": "Invalid_Strategy",
        "entry_long": "unknown_primitive(10) > 0",
        "exit_long": "norm_rsi(14) > 0.5",
    }


class TestStrategyParsing:
    """Test strategy JSON parsing."""

    def test_parse_valid_strategy(self, parser, valid_strategy_json):
        """Should successfully parse valid strategy."""
        strategy = parser.parse(valid_strategy_json)

        assert isinstance(strategy, Strategy)
        assert strategy.name == "Test_RSI_Mean_Reversion"
        assert strategy.entry_long == "btc_trend(60) >= 0 AND norm_rsi(14) < -0.4"
        assert strategy.exit_long == "norm_rsi(14) > 0.4"
        assert strategy.entry_short is None
        assert strategy.exit_short is None

    def test_parse_complex_strategy(self, parser, complex_strategy_json):
        """Should parse strategy with multiple conditions."""
        strategy = parser.parse(complex_strategy_json)

        assert strategy.name == "Complex_Multi_Condition"
        assert "btc_trend(60)" in strategy.entry_long
        assert "ema_trend(9,21)" in strategy.entry_long
        assert "norm_rsi(14)" in strategy.entry_long
        assert "volume_intensity(20,2.0)" in strategy.entry_long

    def test_reject_unknown_primitive(self, parser, invalid_strategy_json):
        """Should raise ValueError for unknown primitive."""
        with pytest.raises(ValueError) as exc_info:
            parser.parse(invalid_strategy_json)

        assert "unknown_primitive" in str(exc_info.value)
        assert "Unknown primitive" in str(exc_info.value)

    def test_reject_unknown_primitive_in_exit(self, parser):
        """Should validate exit conditions too."""
        strategy_json = {
            "strategy_name": "Invalid_Exit",
            "entry_long": "norm_rsi(14) < -0.4",
            "exit_long": "fake_indicator(20) > 0.5",
        }

        with pytest.raises(ValueError) as exc_info:
            parser.parse(strategy_json)

        assert "fake_indicator" in str(exc_info.value)

    def test_all_primitives_allowed(self, parser):
        """Verify all documented primitives are whitelisted."""
        expected_primitives = {
            "ema_trend",
            "price_position",
            "norm_rsi",
            "bb_position",
            "bb_width_percentile",
            "volume_intensity",
            "vwap_distance",
            "atr_regime",
            "atr_percentile",
            "btc_trend",
        }

        assert set(PRIMITIVES.keys()) == expected_primitives


class TestExpressionEvaluation:
    """Test expression evaluation logic."""

    def test_evaluate_simple_condition_true(self, parser, sample_candles, btc_bull):
        """Should evaluate true when condition met."""
        # Expression that should be true for sample data
        expression = "norm_rsi(14) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is True

    def test_evaluate_simple_condition_false(self, parser, sample_candles, btc_bull):
        """Should evaluate false when condition not met."""
        # Expression that should be false - RSI can't be > 2.0 (max is 1.0)
        expression = "norm_rsi(14) > 2.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is False

    def test_evaluate_and_conditions_all_true(self, parser, btc_bull):
        """Should return true when ALL conditions met."""
        # Create strong uptrend data
        uptrend_candles = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [101.0] * 100,
            'low': [99.0] * 100,
            'close': list(range(100, 200)),  # Strong uptrend
            'volume': [1000.0] * 100,
        })

        # This should give ema_trend == 1.0, and norm_rsi >= -1.0 is always true
        expression = "ema_trend(9,21) == 1.0 AND norm_rsi(14) >= -1.0"
        result = parser.evaluate(expression, uptrend_candles, candles_to_df(btc_bull))
        assert result is True

    def test_evaluate_and_conditions_one_false(self, parser, bull_market, btc_bull):
        """Should return false when ANY condition fails."""
        # First condition true (bull market), second impossible
        expression = "ema_trend(9,21) == 1.0 AND norm_rsi(14) > 2.0"
        result = parser.evaluate(expression, candles_to_df(bull_market), candles_to_df(btc_bull))
        assert result is False

    def test_evaluate_btc_trend_requires_btc_candles(self, parser, sample_candles):
        """Should raise error if btc_trend used without btc_candles."""
        expression = "btc_trend(60) >= 0"

        with pytest.raises(ValueError) as exc_info:
            parser.evaluate(expression, candles_to_df(sample_candles), btc_candles=None)

        assert "btc_trend requires btc_candles" in str(exc_info.value)

    def test_evaluate_btc_trend_with_btc_candles(self, parser, sample_candles, btc_bull):
        """Should use btc_candles parameter for btc_trend."""
        expression = "btc_trend(60) >= 0"
        # btc_bull should have positive trend
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        # Result depends on btc_bull data, just verify no error
        assert isinstance(result, bool)

    def test_evaluate_empty_expression(self, parser, sample_candles, btc_bull):
        """Should return False for empty expression."""
        assert parser.evaluate("", candles_to_df(sample_candles), candles_to_df(btc_bull)) is False
        assert parser.evaluate(None, candles_to_df(sample_candles), candles_to_df(btc_bull)) is False


class TestComparisonOperators:
    """Test all comparison operators."""

    def test_operator_equals(self, parser, btc_bull):
        """Test == operator."""
        # Create strong uptrend data that will definitely give ema_trend == 1.0
        uptrend_candles = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [101.0] * 100,
            'low': [99.0] * 100,
            'close': list(range(100, 200)),  # Strong uptrend
            'volume': [1000.0] * 100,
        })

        expression = "ema_trend(9,21) == 1.0"
        result = parser.evaluate(expression, uptrend_candles, candles_to_df(btc_bull))
        assert result is True

        expression = "ema_trend(9,21) == -1.0"
        result = parser.evaluate(expression, uptrend_candles, candles_to_df(btc_bull))
        assert result is False

    def test_operator_not_equals(self, parser, bull_market, btc_bull):
        """Test != operator."""
        # Test with a value that will never match
        expression = "norm_rsi(14) != 999.0"
        result = parser.evaluate(expression, candles_to_df(bull_market), candles_to_df(btc_bull))
        assert result is True  # norm_rsi is in [-1, 1], so never == 999.0

        # Test with specific comparison using actual evaluation
        bull_df = candles_to_df(bull_market)
        btc_df = candles_to_df(btc_bull)

        # Get actual trend value
        trend_val_expr = "ema_trend(9,21) >= -1.0"
        parser.evaluate(trend_val_expr, bull_df, btc_df)  # Just to verify it works

        # Test != with opposite values
        expression = "norm_rsi(14) != -999.0"
        result = parser.evaluate(expression, bull_df, btc_df)
        assert result is True

    def test_operator_greater_than(self, parser, sample_candles, btc_bull):
        """Test > operator."""
        expression = "norm_rsi(14) > -2.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is True  # norm_rsi is in [-1, 1], so always > -2

    def test_operator_greater_equal(self, parser, sample_candles, btc_bull):
        """Test >= operator."""
        expression = "norm_rsi(14) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is True

    def test_operator_less_than(self, parser, sample_candles, btc_bull):
        """Test < operator."""
        expression = "norm_rsi(14) < 2.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is True  # norm_rsi is in [-1, 1], so always < 2

    def test_operator_less_equal(self, parser, sample_candles, btc_bull):
        """Test <= operator."""
        expression = "norm_rsi(14) <= 1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert result is True


class TestSignalGeneration:
    """Test trading signal generation."""

    def test_entry_signal_when_no_position_and_condition_met(self, parser, valid_strategy_json):
        """Should return ENTRY_LONG when entry condition met and no position."""
        strategy = parser.parse(valid_strategy_json)

        # Create oversold conditions (RSI < 30, normalized to -0.4)
        oversold_candles = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [101.0] * 100,
            'low': [99.0] * 100,
            'close': [100.0 - i * 0.5 for i in range(100)],  # Steady decline for oversold RSI
            'volume': [1000.0] * 100,
        })

        # Create deterministic BTC uptrend that will satisfy btc_trend >= 0
        btc_uptrend = pd.DataFrame({
            'open': [40000.0 + i * 10 for i in range(100)],
            'high': [40050.0 + i * 10 for i in range(100)],
            'low': [39950.0 + i * 10 for i in range(100)],
            'close': [40000.0 + i * 10 for i in range(100)],  # Steady uptrend
            'volume': [1000.0] * 100,
        })

        signal = parser.get_signal(strategy, oversold_candles, btc_uptrend, has_position=False)
        assert signal == Signal.ENTRY_LONG

    def test_hold_signal_when_no_position_and_condition_not_met(self, parser, valid_strategy_json, bull_market, btc_bull):
        """Should return HOLD when entry condition not met."""
        strategy = parser.parse(valid_strategy_json)

        # Bull market has high RSI, won't trigger entry (needs RSI < -0.4)
        signal = parser.get_signal(strategy, candles_to_df(bull_market), candles_to_df(btc_bull), has_position=False)
        assert signal == Signal.HOLD

    def test_exit_signal_when_has_position_and_condition_met(self, parser, valid_strategy_json, btc_bull):
        """Should return EXIT_LONG when exit condition met and has position."""
        strategy = parser.parse(valid_strategy_json)

        # Create overbought conditions (RSI > 70, normalized to > 0.4)
        overbought_candles = pd.DataFrame({
            'open': [50.0] * 50,
            'high': [51.0] * 50,
            'low': [49.0] * 50,
            'close': list(range(50, 100)),  # Rising prices
            'volume': [1000.0] * 50,
        })

        signal = parser.get_signal(strategy, overbought_candles, candles_to_df(btc_bull), has_position=True)
        assert signal == Signal.EXIT_LONG

    def test_hold_signal_when_has_position_and_condition_not_met(self, parser, valid_strategy_json, btc_bull):
        """Should return HOLD when exit condition not met and has position."""
        strategy = parser.parse(valid_strategy_json)

        # Create candles with alternating moves for neutral RSI (around 50)
        # Exit condition is norm_rsi(14) > 0.4, which means RSI > 70
        # We want RSI around 50 (norm_rsi = 0)
        closes = []
        price = 100.0
        for i in range(50):
            # Alternate up and down to keep RSI neutral
            if i % 2 == 0:
                price *= 1.005  # +0.5%
            else:
                price *= 0.995  # -0.5%
            closes.append(price)

        neutral_candles = pd.DataFrame({
            'open': [100.0] * 50,
            'high': [c * 1.01 for c in closes],
            'low': [c * 0.99 for c in closes],
            'close': closes,
            'volume': [1000.0] * 50,
        })

        signal = parser.get_signal(strategy, neutral_candles, candles_to_df(btc_bull), has_position=True)
        assert signal == Signal.HOLD

    def test_btc_filter_blocks_entry(self, parser, valid_strategy_json):
        """Should not enter when BTC trend is negative."""
        strategy = parser.parse(valid_strategy_json)

        # Create oversold conditions for the altcoin
        oversold_candles = pd.DataFrame({
            'open': [100.0] * 100,
            'high': [101.0] * 100,
            'low': [99.0] * 100,
            'close': list(range(100, 0, -1)),  # Declining prices
            'volume': [1000.0] * 100,
        })

        # Create clearly bearish BTC data (strong downtrend)
        btc_bear_df = pd.DataFrame({
            'open': [50000.0] * 100,
            'high': [50100.0] * 100,
            'low': [49900.0] * 100,
            'close': list(range(50000, 40000, -100)),  # Strong decline
            'volume': [1000000.0] * 100,
        })

        signal = parser.get_signal(strategy, oversold_candles, btc_bear_df, has_position=False)
        # Should be HOLD because btc_trend(60) will be < 0
        assert signal == Signal.HOLD


class TestErrorHandling:
    """Test error handling and validation."""

    def test_invalid_condition_format(self, parser, sample_candles, btc_bull):
        """Should raise error for malformed condition."""
        expression = "norm_rsi(14)"  # Missing comparison

        with pytest.raises(ValueError) as exc_info:
            parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))

        assert "Invalid condition format" in str(exc_info.value)

    def test_invalid_operator(self, parser):
        """Should raise error for invalid operator."""
        # This will be caught during condition parsing
        expression = "norm_rsi(14) ~~ 0.5"  # Invalid operator

        with pytest.raises(ValueError) as exc_info:
            parser.evaluate(expression, pd.DataFrame(), None)

        assert "Invalid condition format" in str(exc_info.value)

    def test_invalid_function_arguments(self, parser, sample_candles, btc_bull):
        """Should raise error for invalid function arguments."""
        expression = "ema_trend(abc,def) == 1.0"  # Non-numeric args

        with pytest.raises(ValueError) as exc_info:
            parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))

        assert "Invalid argument" in str(exc_info.value)


class TestPrimitiveCalls:
    """Test that primitives are called correctly."""

    def test_primitive_with_integer_args(self, parser, sample_candles, btc_bull):
        """Should parse integer arguments correctly."""
        expression = "norm_rsi(14) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert isinstance(result, bool)

    def test_primitive_with_multiple_args(self, parser, sample_candles, btc_bull):
        """Should parse multiple arguments correctly."""
        expression = "ema_trend(9,21) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert isinstance(result, bool)

    def test_primitive_with_float_args(self, parser, sample_candles, btc_bull):
        """Should parse float arguments correctly."""
        expression = "bb_position(20,2.0) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert isinstance(result, bool)

    def test_volume_intensity_binary_output(self, parser, sample_candles, btc_bull):
        """Should handle binary output (0.0 or 1.0) correctly."""
        expression = "volume_intensity(20,2.0) == 0.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert isinstance(result, bool)

    def test_atr_regime_three_state_output(self, parser, sample_candles, btc_bull):
        """Should handle three-state output (-1.0, 0.0, 1.0) correctly."""
        expression = "atr_regime(14,100) >= -1.0"
        result = parser.evaluate(expression, candles_to_df(sample_candles), candles_to_df(btc_bull))
        assert isinstance(result, bool)


class TestComplexStrategies:
    """Test complex multi-condition strategies."""

    def test_four_condition_strategy(self, parser, complex_strategy_json, bull_market, btc_bull):
        """Should evaluate strategy with 4 AND conditions."""
        strategy = parser.parse(complex_strategy_json)

        # Just verify it can be evaluated without error
        signal = parser.get_signal(strategy, candles_to_df(bull_market), candles_to_df(btc_bull), has_position=False)
        assert signal in [Signal.ENTRY_LONG, Signal.EXIT_LONG, Signal.HOLD]

    def test_all_primitives_in_one_strategy(self, parser, sample_candles, btc_bull):
        """Should handle strategy using many different primitives."""
        mega_strategy = {
            "strategy_name": "Mega_Strategy",
            "entry_long": (
                "btc_trend(60) >= 0 AND "
                "ema_trend(9,21) == 1.0 AND "
                "norm_rsi(14) < -0.3 AND "
                "bb_position(20,2.0) < -0.5 AND "
                "volume_intensity(20,2.0) == 1.0 AND "
                "vwap_distance(20) < 0.0 AND "
                "atr_regime(14,100) != -1.0"
            ),
            "exit_long": "norm_rsi(14) > 0.5",
        }

        # Should parse without error
        strategy = parser.parse(mega_strategy)
        assert strategy.name == "Mega_Strategy"

        # Should evaluate without error
        signal = parser.get_signal(strategy, candles_to_df(sample_candles), candles_to_df(btc_bull), has_position=False)
        assert signal in [Signal.ENTRY_LONG, Signal.EXIT_LONG, Signal.HOLD]
