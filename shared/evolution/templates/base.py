"""
Base Strategy Template with FIXED LOGIC, evolvable parameters.

Key architectural features:
1. VECTORIZED: All signals return pd.Series for fast backtesting
2. REGIME-SWITCHED: Two weight sets selected by regime indicator
3. BIDIRECTIONAL: Native support for long AND short positions

The strategy logic is fixed in this template; only parameters evolve.
"""
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Dict, Optional, Tuple
import pandas as pd
import numpy as np

from ta.trend import ADXIndicator
from ta.volatility import BollingerBands, AverageTrueRange

from shared.evolution.parameters.schema import (
    WeightVector,
    UniversalParameters,
)
from shared.engine.gene_pool import (
    ema_trend_series,
    norm_rsi_series,
    bb_position_series,
    atr_regime_series,
    volume_intensity_series,
    atr_percentile_series,
)


class StrategyTemplate(ABC):
    """
    Base strategy template with FIXED LOGIC.

    Key architectural features:
    1. VECTORIZED: All signals return pd.Series for fast backtesting
    2. REGIME-SWITCHED: Two weight sets selected by regime indicator
    3. BIDIRECTIONAL: Native support for long AND short positions

    Subclasses implement asset-specific signal calculations,
    but the aggregation and decision logic is universal.
    """

    def __init__(self, params: UniversalParameters):
        """
        Initialize template with parameters.

        Args:
            params: Strategy parameters (the DNA that gets evolved)
        """
        self.params = params
        self._signal_cache: Dict[str, pd.Series] = {}

    # === REGIME DETECTION (Vectorized) ===

    def calculate_regime_indicator(self, candles: pd.DataFrame) -> pd.Series:
        """
        Calculate regime indicator series.

        Returns:
            pd.Series: Boolean where True = Regime B (trending), False = Regime A (ranging)
        """
        if self.params.regime_indicator == "adx":
            adx = ADXIndicator(
                candles['high'], candles['low'], candles['close'],
                window=self.params.regime_period
            )
            adx_values = adx.adx()
            is_regime_b = adx_values >= self.params.regime_threshold
            # Fill NaN with False (default to Regime A)
            return is_regime_b.fillna(False)

        elif self.params.regime_indicator == "atr_percentile":
            atr_pct = atr_percentile_series(candles, self.params.regime_period)
            # Normalize threshold (0-100) to 0-1
            return atr_pct >= (self.params.regime_threshold / 100.0)

        elif self.params.regime_indicator == "bb_width":
            bb = BollingerBands(candles['close'], window=self.params.regime_period)
            bb_width = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
            # Compare to rolling quantile
            threshold_quantile = self.params.regime_threshold / 100.0
            rolling_quantile = bb_width.rolling(100).quantile(threshold_quantile)
            return bb_width >= rolling_quantile

        else:
            raise ValueError(f"Unknown regime indicator: {self.params.regime_indicator}")

    def get_active_weights(
        self,
        is_regime_b: pd.Series
    ) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
        """
        Return weight series that switch based on regime.

        Each returned series has the appropriate weight for each bar.

        Args:
            is_regime_b: Boolean series where True = Regime B (trending)

        Returns:
            Tuple of (w_trend, w_momentum, w_reversion, w_volatility, w_volume)
        """
        weights_a = self.params.weights_A
        weights_b = self.params.weights_B

        # Create weight series that switch based on regime
        w_trend = pd.Series(
            np.where(is_regime_b, weights_b.trend, weights_a.trend),
            index=is_regime_b.index
        )
        w_momentum = pd.Series(
            np.where(is_regime_b, weights_b.momentum, weights_a.momentum),
            index=is_regime_b.index
        )
        w_reversion = pd.Series(
            np.where(is_regime_b, weights_b.mean_reversion, weights_a.mean_reversion),
            index=is_regime_b.index
        )
        w_volatility = pd.Series(
            np.where(is_regime_b, weights_b.volatility, weights_a.volatility),
            index=is_regime_b.index
        )
        w_volume = pd.Series(
            np.where(is_regime_b, weights_b.volume, weights_a.volume),
            index=is_regime_b.index
        )

        return w_trend, w_momentum, w_reversion, w_volatility, w_volume

    # === SIGNAL CALCULATION (Vectorized - return pd.Series) ===

    @abstractmethod
    def calculate_market_filter(self, candles: pd.DataFrame) -> pd.Series:
        """
        Asset-specific market filter.

        Returns:
            pd.Series: Values from -1.0 to +1.0
        """
        pass

    def calculate_trend_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        EMA crossover: +1.0 (uptrend) or -1.0 (downtrend) as Series.
        """
        return ema_trend_series(
            candles,
            self.params.trend_fast_period,
            self.params.trend_slow_period
        )

    def calculate_momentum_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        Normalized RSI: -1.0 (oversold) to +1.0 (overbought) as Series.
        """
        return norm_rsi_series(candles, self.params.momentum_period)

    def calculate_mean_reversion_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        Bollinger position: -1.0 (lower band) to +1.0 (upper band) as Series.
        """
        return bb_position_series(
            candles,
            self.params.reversion_period,
            float(self.params.reversion_std_dev)
        )

    def calculate_volatility_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        ATR regime: +1.0 (high vol), 0.0 (normal), -1.0 (low vol) as Series.
        """
        return atr_regime_series(candles, self.params.volatility_period)

    def calculate_volume_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        Volume intensity: 0.0 (low) to +1.0 (high) as Series.
        """
        return volume_intensity_series(candles, self.params.volume_period, 1.5)

    # === FIXED AGGREGATION LOGIC (Vectorized, Regime-Switched) ===

    def calculate_composite_signal(self, candles: pd.DataFrame) -> pd.Series:
        """
        FIXED LOGIC: Regime-switched weighted average of all signals.

        Returns:
            pd.Series: Composite signal values (-1.0 to +1.0)
            Represents "directional intent":
            - +1.0 = Maximum LONG conviction
            -  0.0 = Neutral
            - -1.0 = Maximum SHORT conviction
        """
        # Calculate regime for each bar
        is_regime_b = self.calculate_regime_indicator(candles)

        # Get regime-dependent weights
        w_trend, w_momentum, w_reversion, w_volatility, w_volume = self.get_active_weights(is_regime_b)

        # Calculate all signal series (vectorized)
        signals = {
            'trend': self.calculate_trend_signal(candles),
            'momentum': self.calculate_momentum_signal(candles),
            'mean_reversion': self.calculate_mean_reversion_signal(candles),
            'volatility': self.calculate_volatility_signal(candles),
            'volume': self.calculate_volume_signal(candles),
        }

        weights = {
            'trend': w_trend,
            'momentum': w_momentum,
            'mean_reversion': w_reversion,
            'volatility': w_volatility,
            'volume': w_volume,
        }

        # Vectorized weighted sum
        composite = pd.Series(0.0, index=candles.index)
        total_weight = pd.Series(0.0, index=candles.index)

        for name in signals:
            w = weights[name]
            s = signals[name]

            # Only include where weight is significant (> 0.01)
            abs_w = w.abs()
            mask = abs_w > 0.01

            # Add weighted signal
            composite = composite + (s * w).where(mask, 0.0)
            total_weight = total_weight + abs_w.where(mask, 0.0)

        # Normalize by total weight (avoid division by zero)
        total_weight = total_weight.replace(0.0, 1.0)
        composite = composite / total_weight

        # Clip to [-1, 1]
        return composite.clip(-1.0, 1.0)

    # === FIXED DECISION LOGIC (Vectorized, Bidirectional) ===

    def generate_signals(self, candles: pd.DataFrame) -> pd.DataFrame:
        """
        Generate all trading signals for the entire candle history.

        Returns:
            DataFrame with columns:
            - composite: The composite signal (-1 to +1)
            - market_filter: The market filter value
            - is_regime_b: Boolean, True if in trending regime
            - entry_long: Boolean, True where should enter long
            - exit_long: Boolean, True where should exit long
            - entry_short: Boolean, True where should enter short
            - exit_short: Boolean, True where should exit short
        """
        composite = self.calculate_composite_signal(candles)
        market_filter = self.calculate_market_filter(candles)
        is_regime_b = self.calculate_regime_indicator(candles)

        signals = pd.DataFrame(index=candles.index)
        signals['composite'] = composite
        signals['market_filter'] = market_filter
        signals['is_regime_b'] = is_regime_b

        # Market filter must pass (>= threshold)
        market_ok = market_filter >= self.params.market_filter_threshold

        # Long signals (if enabled)
        if self.params.allow_long:
            signals['entry_long'] = market_ok & (composite > self.params.entry_threshold_long)
            signals['exit_long'] = composite < self.params.exit_threshold_long
        else:
            signals['entry_long'] = False
            signals['exit_long'] = False

        # Short signals (if enabled)
        if self.params.allow_short:
            signals['entry_short'] = market_ok & (composite < self.params.entry_threshold_short)
            signals['exit_short'] = composite > self.params.exit_threshold_short
        else:
            signals['entry_short'] = False
            signals['exit_short'] = False

        return signals

    # === RISK (Vectorized) ===

    def get_atr_series(self, candles: pd.DataFrame, period: int = 14) -> pd.Series:
        """Get ATR series for stop/target calculations."""
        atr = AverageTrueRange(
            candles['high'], candles['low'], candles['close'],
            window=period
        )
        return atr.average_true_range()

    def get_stop_loss_distance(self, candles: pd.DataFrame) -> pd.Series:
        """
        Stop-loss distance at N × ATR.

        Returns:
            pd.Series: Stop-loss distance in price units
        """
        return self.get_atr_series(candles) * self.params.stop_loss_atr_mult

    def get_take_profit_distance(self, candles: pd.DataFrame) -> pd.Series:
        """
        Take-profit distance at M × ATR.

        Returns:
            pd.Series: Take-profit distance in price units
        """
        return self.get_atr_series(candles) * self.params.take_profit_atr_mult

    # === EXPLAIN (For analysis at a single point) ===

    def explain_signal_at(self, candles: pd.DataFrame, idx: int = -1) -> Dict:
        """
        Returns breakdown of signal contributions at a specific index.

        Useful for understanding WHY a strategy triggered at a point.

        Args:
            candles: OHLCV DataFrame
            idx: Index to explain (-1 for last bar)

        Returns:
            Dictionary with signal breakdown
        """
        signals_df = self.generate_signals(candles)
        is_regime_b = self.calculate_regime_indicator(candles)

        # Get values at index
        row = signals_df.iloc[idx]
        regime = "B (Trending)" if is_regime_b.iloc[idx] else "A (Ranging)"
        active_weights = self.params.weights_B if is_regime_b.iloc[idx] else self.params.weights_A

        breakdown = {
            'index': idx,
            'timestamp': candles.index[idx] if hasattr(candles.index, '__getitem__') else idx,
            'regime': regime,
            'active_weights': active_weights.to_dict(),
            'composite_signal': float(row['composite']),
            'market_filter': float(row['market_filter']),
            'entry_long': bool(row['entry_long']),
            'exit_long': bool(row['exit_long']),
            'entry_short': bool(row['entry_short']),
            'exit_short': bool(row['exit_short']),
            'signal_contributions': {},
        }

        # Calculate individual contributions
        signal_names = ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']
        for name in signal_names:
            weight = getattr(active_weights, name)
            if abs(weight) > 0.01:
                signal_method = getattr(self, f'calculate_{name}_signal')
                signal_series = signal_method(candles)
                raw_signal = float(signal_series.iloc[idx])
                breakdown['signal_contributions'][name] = {
                    'weight': weight,
                    'raw_signal': raw_signal,
                    'weighted_contribution': raw_signal * weight,
                }

        return breakdown

    # === SERIALIZATION ===

    def to_dict(self) -> Dict:
        """
        Serialize template to dictionary.

        Returns:
            Dictionary with template type and parameters
        """
        return {
            'template_type': self.__class__.__name__,
            'params': self.params.to_dict(),
        }

    def get_params_json(self) -> str:
        """Get parameters as JSON string."""
        return self.params.to_json()
