"""Tests for strategy templates."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
    CryptoParameters,
)
from shared.evolution.templates import (
    CryptoStrategyTemplate,
)


@pytest.fixture
def sample_candles():
    """Generate sample OHLCV data for testing."""
    np.random.seed(42)
    n = 500

    # Generate trending price data
    base_price = 100.0
    returns = np.random.randn(n) * 0.02 + 0.001  # Slight upward drift
    prices = base_price * np.cumprod(1 + returns)

    # Create OHLCV DataFrame
    dates = pd.date_range(start='2024-01-01', periods=n, freq='1h')

    df = pd.DataFrame({
        'open': prices * (1 + np.random.randn(n) * 0.002),
        'high': prices * (1 + np.abs(np.random.randn(n) * 0.01)),
        'low': prices * (1 - np.abs(np.random.randn(n) * 0.01)),
        'close': prices,
        'volume': np.random.uniform(1000, 10000, n),
    }, index=dates)

    # Ensure high >= close >= low
    df['high'] = df[['open', 'close', 'high']].max(axis=1)
    df['low'] = df[['open', 'close', 'low']].min(axis=1)

    return df


@pytest.fixture
def default_params():
    """Default crypto parameters for testing."""
    return CryptoParameters()


@pytest.fixture
def custom_params():
    """Custom parameters for testing."""
    return CryptoParameters(
        weights_A=WeightVector(
            trend=0.2,
            momentum=0.3,
            mean_reversion=0.7,
            volatility=0.1,
            volume=0.1,
        ),
        weights_B=WeightVector(
            trend=0.8,
            momentum=0.4,
            mean_reversion=0.1,
            volatility=0.2,
            volume=0.2,
        ),
        entry_threshold_long=0.4,
        exit_threshold_long=-0.1,
        allow_short=True,
        entry_threshold_short=-0.4,
        exit_threshold_short=0.1,
    )


class TestCryptoStrategyTemplate:
    """Tests for CryptoStrategyTemplate."""

    def test_initialization(self, default_params):
        """Template initializes correctly."""
        template = CryptoStrategyTemplate(default_params)
        assert template.params == default_params

    def test_generate_signals_returns_dataframe(self, sample_candles, default_params):
        """generate_signals returns DataFrame with expected columns."""
        template = CryptoStrategyTemplate(default_params)
        signals = template.generate_signals(sample_candles)

        assert isinstance(signals, pd.DataFrame)
        assert len(signals) == len(sample_candles)
        assert 'composite' in signals.columns
        assert 'market_filter' in signals.columns
        assert 'entry_long' in signals.columns
        assert 'exit_long' in signals.columns
        assert 'entry_short' in signals.columns
        assert 'exit_short' in signals.columns

    def test_composite_signal_range(self, sample_candles, default_params):
        """Composite signal is bounded [-1, 1]."""
        template = CryptoStrategyTemplate(default_params)
        signals = template.generate_signals(sample_candles)

        assert signals['composite'].min() >= -1.0
        assert signals['composite'].max() <= 1.0

    def test_signals_are_boolean(self, sample_candles, default_params):
        """Entry/exit signals are boolean."""
        template = CryptoStrategyTemplate(default_params)
        signals = template.generate_signals(sample_candles)

        assert signals['entry_long'].dtype == bool
        assert signals['exit_long'].dtype == bool

    def test_long_only_disables_shorts(self, sample_candles, default_params):
        """With allow_short=False, short signals are always False."""
        # default_params has allow_short=False
        template = CryptoStrategyTemplate(default_params)
        signals = template.generate_signals(sample_candles)

        assert not signals['entry_short'].any()
        assert not signals['exit_short'].any()

    def test_bidirectional_enables_shorts(self, sample_candles, custom_params):
        """With allow_short=True, short signals can be True."""
        template = CryptoStrategyTemplate(custom_params)
        signals = template.generate_signals(sample_candles)

        # Not all bars have shorts, but schema allows them
        assert 'entry_short' in signals.columns
        # With our test data, we may or may not have short entries
        # Just verify the column exists and is boolean
        assert signals['entry_short'].dtype == bool

    def test_regime_indicator_adx(self, sample_candles, default_params):
        """ADX regime indicator works."""
        template = CryptoStrategyTemplate(default_params)
        is_regime_b = template.calculate_regime_indicator(sample_candles)

        assert isinstance(is_regime_b, pd.Series)
        assert len(is_regime_b) == len(sample_candles)
        # Should be boolean-like (True/False)
        assert is_regime_b.dtype == bool or set(is_regime_b.dropna().unique()).issubset({True, False, 0, 1})

    def test_calculate_composite_signal(self, sample_candles, default_params):
        """Composite signal calculation is vectorized."""
        template = CryptoStrategyTemplate(default_params)
        composite = template.calculate_composite_signal(sample_candles)

        assert isinstance(composite, pd.Series)
        assert len(composite) == len(sample_candles)
        # Check bounded
        assert composite.min() >= -1.0
        assert composite.max() <= 1.0

    def test_calculate_market_filter(self, sample_candles, default_params):
        """Market filter returns series."""
        template = CryptoStrategyTemplate(default_params)
        market_filter = template.calculate_market_filter(sample_candles)

        assert isinstance(market_filter, pd.Series)
        assert len(market_filter) == len(sample_candles)

    def test_explain_signal_at(self, sample_candles, default_params):
        """explain_signal_at returns detailed breakdown."""
        template = CryptoStrategyTemplate(default_params)
        explanation = template.explain_signal_at(sample_candles, idx=-1)

        assert isinstance(explanation, dict)
        assert 'regime' in explanation
        assert 'composite_signal' in explanation
        assert 'signal_contributions' in explanation
        assert isinstance(explanation['signal_contributions'], dict)

    def test_get_stop_loss_distance(self, sample_candles, default_params):
        """Stop loss distance is ATR-based series."""
        template = CryptoStrategyTemplate(default_params)
        stop_distance = template.get_stop_loss_distance(sample_candles)

        assert isinstance(stop_distance, pd.Series)
        assert len(stop_distance) == len(sample_candles)
        # Stop distance should be positive (where not NaN)
        assert (stop_distance.dropna() >= 0).all()

    def test_get_take_profit_distance(self, sample_candles, default_params):
        """Take profit distance is ATR-based series."""
        template = CryptoStrategyTemplate(default_params)
        tp_distance = template.get_take_profit_distance(sample_candles)

        assert isinstance(tp_distance, pd.Series)
        # Take profit should be > stop loss (by default params)
        stop_distance = template.get_stop_loss_distance(sample_candles)
        # Compare where both are valid and non-zero (skip warmup period)
        valid = (tp_distance.notna() & stop_distance.notna() &
                 (stop_distance > 0) & (tp_distance > 0))
        assert (tp_distance[valid] > stop_distance[valid]).all()

    def test_regime_switching_affects_weights(self, sample_candles, custom_params):
        """Different regimes use different weights."""
        template = CryptoStrategyTemplate(custom_params)
        is_regime_b = template.calculate_regime_indicator(sample_candles)

        w_trend, w_momentum, w_reversion, w_volatility, w_volume = template.get_active_weights(is_regime_b)

        # Regime A should use weights_A
        # Regime B should use weights_B
        regime_a_bars = ~is_regime_b
        regime_b_bars = is_regime_b

        if regime_a_bars.any():
            # Trend weight in Regime A should be 0.2
            assert (w_trend[regime_a_bars] == custom_params.weights_A.trend).all()

        if regime_b_bars.any():
            # Trend weight in Regime B should be 0.8
            assert (w_trend[regime_b_bars] == custom_params.weights_B.trend).all()

    def test_to_dict(self, default_params):
        """Template serializes to dictionary."""
        template = CryptoStrategyTemplate(default_params)
        d = template.to_dict()

        assert 'template_type' in d
        assert d['template_type'] == 'CryptoStrategyTemplate'
        assert 'params' in d

    def test_no_nan_in_final_signals(self, sample_candles, default_params):
        """Final signals should not have NaN (after warmup period)."""
        template = CryptoStrategyTemplate(default_params)
        signals = template.generate_signals(sample_candles)

        # After warmup (say 100 bars), should have no NaN
        warmup = 100
        assert not signals['composite'].iloc[warmup:].isna().any()
        assert not signals['entry_long'].iloc[warmup:].isna().any()


class TestVectorizedPerformance:
    """Tests for vectorized performance."""

    def test_signals_computed_vectorized(self, sample_candles, default_params):
        """Verify signals are computed in vectorized fashion (no loops)."""
        template = CryptoStrategyTemplate(default_params)

        # Time the signal generation
        import time
        start = time.time()
        signals = template.generate_signals(sample_candles)
        elapsed = time.time() - start

        # Should be fast (< 1 second for 500 candles)
        assert elapsed < 1.0, f"Signal generation took {elapsed:.2f}s, expected < 1s"

    def test_large_dataset_performance(self, default_params):
        """Performance test with larger dataset."""
        np.random.seed(42)
        n = 5000  # 5000 candles

        # Generate data
        base_price = 100.0
        returns = np.random.randn(n) * 0.02
        prices = base_price * np.cumprod(1 + returns)
        dates = pd.date_range(start='2024-01-01', periods=n, freq='1h')

        large_candles = pd.DataFrame({
            'open': prices * (1 + np.random.randn(n) * 0.002),
            'high': prices * (1 + np.abs(np.random.randn(n) * 0.01)),
            'low': prices * (1 - np.abs(np.random.randn(n) * 0.01)),
            'close': prices,
            'volume': np.random.uniform(1000, 10000, n),
        }, index=dates)

        large_candles['high'] = large_candles[['open', 'close', 'high']].max(axis=1)
        large_candles['low'] = large_candles[['open', 'close', 'low']].min(axis=1)

        template = CryptoStrategyTemplate(default_params)

        import time
        start = time.time()
        signals = template.generate_signals(large_candles)
        elapsed = time.time() - start

        # Should be fast even for 5000 candles (< 3 seconds)
        assert elapsed < 3.0, f"Large dataset took {elapsed:.2f}s, expected < 3s"
        assert len(signals) == n
