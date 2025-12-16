"""
Crypto Strategy Template.

Extends base StrategyTemplate with crypto-specific features:
- BTC trend as market filter
- BTC correlation signal
- Funding rate signal (for perpetuals)
- BTC dominance signal (for altcoins)
"""
from typing import Dict, Optional
import pandas as pd
import numpy as np

from shared.evolution.parameters.schema import CryptoParameters
from shared.evolution.templates.base import StrategyTemplate
from shared.engine.gene_pool import ema_trend_series


class CryptoStrategyTemplate(StrategyTemplate):
    """
    Crypto-specific strategy template.

    Extends the base template with:
    - BTC trend as market filter
    - Optional BTC correlation signal
    - Optional funding rate signal
    - Optional BTC dominance signal
    """

    def __init__(self, params: CryptoParameters):
        """
        Initialize crypto strategy template.

        Args:
            params: Crypto strategy parameters (the DNA)
        """
        super().__init__(params)
        self.params: CryptoParameters = params

    def calculate_market_filter(self, candles: pd.DataFrame) -> pd.Series:
        """
        Crypto market filter: BTC trend.

        For BTC pairs, uses the asset's own trend.
        For altcoins, should use BTC price data (requires btc_candles).

        Args:
            candles: OHLCV DataFrame

        Returns:
            pd.Series: +1.0 (uptrend) or -1.0 (downtrend)
        """
        # Use the asset's own trend as market filter
        # For proper BTC correlation, btc_candles should be passed separately
        return ema_trend_series(
            candles,
            fast=self.params.market_filter_period // 3,  # ~20 for 60
            slow=self.params.market_filter_period
        )

    def calculate_market_filter_with_btc(
        self,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame
    ) -> pd.Series:
        """
        Crypto market filter using actual BTC data.

        Args:
            candles: Asset OHLCV DataFrame
            btc_candles: BTC OHLCV DataFrame (must be aligned with candles index)

        Returns:
            pd.Series: BTC trend signal
        """
        btc_trend = ema_trend_series(
            btc_candles,
            fast=self.params.market_filter_period // 3,
            slow=self.params.market_filter_period
        )
        # Reindex to match candles index
        return btc_trend.reindex(candles.index, method='ffill').fillna(0.0)

    # === CRYPTO-SPECIFIC SIGNALS ===

    def calculate_btc_correlation_signal(
        self,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame] = None
    ) -> pd.Series:
        """
        BTC trend as a signal (for alts that follow BTC).

        Args:
            candles: Asset OHLCV DataFrame
            btc_candles: Optional BTC OHLCV DataFrame

        Returns:
            pd.Series: BTC trend signal
        """
        if btc_candles is not None:
            btc_trend = ema_trend_series(
                btc_candles,
                fast=self.params.btc_trend_period // 3,
                slow=self.params.btc_trend_period
            )
            return btc_trend.reindex(candles.index, method='ffill').fillna(0.0)
        else:
            # Fallback: use asset's own trend
            return ema_trend_series(
                candles,
                fast=self.params.btc_trend_period // 3,
                slow=self.params.btc_trend_period
            )

    def calculate_funding_rate_signal(
        self,
        funding_rates: Optional[pd.Series] = None
    ) -> pd.Series:
        """
        Contrarian funding rate signal.

        High positive funding = crowded long = bearish signal
        High negative funding = crowded short = bullish signal

        Args:
            funding_rates: Series of funding rates (optional)

        Returns:
            pd.Series: Contrarian signal (-1 to +1)
        """
        if funding_rates is None:
            # Return neutral if no funding data
            return pd.Series(dtype=float)

        threshold = self.params.funding_rate_threshold

        # Contrarian signal: high funding = go opposite
        signal = pd.Series(0.0, index=funding_rates.index)
        signal = signal.where(~(funding_rates > threshold), -1.0)   # High positive = bearish
        signal = signal.where(~(funding_rates < -threshold), 1.0)   # High negative = bullish

        return signal

    def calculate_btc_dominance_signal(
        self,
        btc_dominance: Optional[pd.Series] = None
    ) -> pd.Series:
        """
        BTC dominance trend for altcoin timing.

        Rising BTC.D = money flowing to BTC = bearish for alts
        Falling BTC.D = money flowing to alts = bullish for alts

        Args:
            btc_dominance: Series of BTC dominance values (optional)

        Returns:
            pd.Series: Signal for altcoin timing (-1 to +1)
        """
        if btc_dominance is None:
            return pd.Series(dtype=float)

        # Calculate trend of BTC dominance
        fast_ema = btc_dominance.ewm(span=self.params.btc_dominance_period // 3).mean()
        slow_ema = btc_dominance.ewm(span=self.params.btc_dominance_period).mean()

        # Contrarian for alts: rising BTC.D = bearish for alts
        signal = pd.Series(
            np.where(fast_ema < slow_ema, 1.0, -1.0),  # Falling BTC.D = bullish for alts
            index=btc_dominance.index
        )

        return signal

    # === EXTENDED COMPOSITE ===

    def calculate_composite_signal_extended(
        self,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame] = None,
        funding_rates: Optional[pd.Series] = None,
        btc_dominance: Optional[pd.Series] = None,
    ) -> pd.Series:
        """
        Extended composite including crypto-specific signals.

        Args:
            candles: Asset OHLCV DataFrame
            btc_candles: Optional BTC OHLCV DataFrame
            funding_rates: Optional funding rate series
            btc_dominance: Optional BTC dominance series

        Returns:
            pd.Series: Composite signal (-1 to +1)
        """
        # Get base composite
        base_composite = super().calculate_composite_signal(candles)

        # Calculate base weight (sum of active weights)
        is_regime_b = self.calculate_regime_indicator(candles)
        weights_a = self.params.weights_A
        weights_b = self.params.weights_B

        # Get active weights for each bar
        base_weight = pd.Series(0.0, index=candles.index)
        for field in ['trend', 'momentum', 'mean_reversion', 'volatility', 'volume']:
            w_a = abs(getattr(weights_a, field))
            w_b = abs(getattr(weights_b, field))
            bar_weight = pd.Series(
                np.where(is_regime_b, w_b, w_a),
                index=candles.index
            )
            base_weight = base_weight + bar_weight.where(bar_weight > 0.01, 0.0)

        # Collect extra signals and weights
        extra_signals = []
        extra_weights = []

        # BTC correlation
        if abs(self.params.weight_btc_correlation) > 0.01:
            btc_signal = self.calculate_btc_correlation_signal(candles, btc_candles)
            if len(btc_signal) > 0:
                btc_signal = btc_signal.reindex(candles.index, method='ffill').fillna(0.0)
                extra_signals.append(btc_signal)
                extra_weights.append(self.params.weight_btc_correlation)

        # Funding rate
        if abs(self.params.weight_funding_rate) > 0.01 and funding_rates is not None:
            funding_signal = self.calculate_funding_rate_signal(funding_rates)
            if len(funding_signal) > 0:
                funding_signal = funding_signal.reindex(candles.index, method='ffill').fillna(0.0)
                extra_signals.append(funding_signal)
                extra_weights.append(self.params.weight_funding_rate)

        # BTC dominance
        if abs(self.params.weight_btc_dominance) > 0.01 and btc_dominance is not None:
            dom_signal = self.calculate_btc_dominance_signal(btc_dominance)
            if len(dom_signal) > 0:
                dom_signal = dom_signal.reindex(candles.index, method='ffill').fillna(0.0)
                extra_signals.append(dom_signal)
                extra_weights.append(self.params.weight_btc_dominance)

        # If no extra signals, return base composite
        if not extra_signals:
            return base_composite

        # Combine base and crypto-specific signals
        # Weight base by its total weight, extra signals by their individual weights
        all_signals = [base_composite * base_weight] + [
            s * w for s, w in zip(extra_signals, extra_weights)
        ]
        all_weights = [base_weight] + [
            pd.Series(abs(w), index=candles.index) for w in extra_weights
        ]

        # Sum weighted signals
        total_signal = sum(all_signals)
        total_weight = sum(all_weights)

        # Normalize
        total_weight = total_weight.replace(0.0, 1.0)
        composite = total_signal / total_weight

        return composite.clip(-1.0, 1.0)

    def generate_signals_extended(
        self,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame] = None,
        funding_rates: Optional[pd.Series] = None,
        btc_dominance: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """
        Generate signals with crypto-specific data.

        Args:
            candles: Asset OHLCV DataFrame
            btc_candles: Optional BTC OHLCV DataFrame
            funding_rates: Optional funding rate series
            btc_dominance: Optional BTC dominance series

        Returns:
            DataFrame with all signal columns
        """
        if btc_candles is not None:
            market_filter = self.calculate_market_filter_with_btc(candles, btc_candles)
        else:
            market_filter = self.calculate_market_filter(candles)

        composite = self.calculate_composite_signal_extended(
            candles, btc_candles, funding_rates, btc_dominance
        )
        is_regime_b = self.calculate_regime_indicator(candles)

        signals = pd.DataFrame(index=candles.index)
        signals['composite'] = composite
        signals['market_filter'] = market_filter
        signals['is_regime_b'] = is_regime_b

        # Market filter must pass
        market_ok = market_filter >= self.params.market_filter_threshold

        # Long signals
        if self.params.allow_long:
            signals['entry_long'] = market_ok & (composite > self.params.entry_threshold_long)
            signals['exit_long'] = composite < self.params.exit_threshold_long
        else:
            signals['entry_long'] = False
            signals['exit_long'] = False

        # Short signals
        if self.params.allow_short:
            signals['entry_short'] = market_ok & (composite < self.params.entry_threshold_short)
            signals['exit_short'] = composite > self.params.exit_threshold_short
        else:
            signals['entry_short'] = False
            signals['exit_short'] = False

        return signals
