"""
Equities Market Regime Classifier.

Classifies market conditions using SPY (trend) and VIX (volatility):
- bull_calm: SPY uptrend, VIX < 20
- bull_volatile: SPY uptrend, VIX >= 20
- bear_calm: SPY downtrend, VIX < 25
- bear_volatile: SPY downtrend, VIX >= 25
- sideways: SPY range-bound

Used for regime-aware fitness calculation (strategies must perform
across multiple regimes to avoid overfitting).
"""

import logging
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classification."""
    BULL_CALM = "bull_calm"
    BULL_VOLATILE = "bull_volatile"
    BEAR_CALM = "bear_calm"
    BEAR_VOLATILE = "bear_volatile"
    SIDEWAYS = "sideways"


@dataclass
class RegimeConfig:
    """Configuration for regime classification."""
    # Trend determination
    trend_window: int = 20           # Days for trend calculation
    trend_threshold: float = 0.02    # 2% move = trend vs sideways

    # VIX thresholds
    vix_low: float = 20.0            # Below = calm
    vix_high: float = 25.0           # Above = volatile (bear)
    vix_neutral_high: float = 20.0   # Threshold for bull volatile

    # Smoothing
    vix_smoothing_window: int = 5    # SMA for VIX noise reduction


class EquitiesRegimeClassifier:
    """
    Classifies market regimes using SPY and VIX.

    Uses a combination of:
    - SPY momentum (20-day return)
    - VIX level (smoothed)
    """

    def __init__(self, config: Optional[RegimeConfig] = None):
        """
        Initialize classifier.

        Args:
            config: Regime classification configuration
        """
        self.config = config or RegimeConfig()

    def classify(
        self,
        spy_candles: pd.DataFrame,
        vix_candles: pd.DataFrame,
    ) -> MarketRegime:
        """
        Classify current market regime.

        Args:
            spy_candles: SPY OHLCV data (oldest first)
            vix_candles: VIX data (oldest first)

        Returns:
            MarketRegime enum value
        """
        if len(spy_candles) < self.config.trend_window:
            logger.warning("Insufficient SPY data for regime classification")
            return MarketRegime.SIDEWAYS

        if len(vix_candles) < self.config.vix_smoothing_window:
            logger.warning("Insufficient VIX data for regime classification")
            return MarketRegime.SIDEWAYS

        # Calculate SPY momentum
        spy_return = self._calculate_momentum(spy_candles)

        # Get smoothed VIX level
        vix_level = self._get_vix_level(vix_candles)

        return self._classify_regime(spy_return, vix_level)

    def _calculate_momentum(self, candles: pd.DataFrame) -> float:
        """Calculate momentum as percentage return over window."""
        close = candles["close"]
        window = self.config.trend_window

        if len(close) < window + 1:
            return 0.0

        current_price = close.iloc[-1]
        past_price = close.iloc[-window - 1]

        if past_price == 0 or pd.isna(past_price):
            return 0.0

        return (current_price - past_price) / past_price

    def _get_vix_level(self, vix_candles: pd.DataFrame) -> float:
        """Get smoothed VIX level."""
        close = vix_candles["close"]
        window = self.config.vix_smoothing_window

        if len(close) < window:
            return close.iloc[-1] if len(close) > 0 else 20.0

        # Simple moving average
        smoothed = close.rolling(window=window).mean()
        return float(smoothed.iloc[-1])

    def _classify_regime(
        self,
        spy_return: float,
        vix_level: float,
    ) -> MarketRegime:
        """
        Classify regime based on momentum and volatility.

        Matrix:
        |           | VIX < 20        | VIX 20-25       | VIX > 25        |
        |-----------|-----------------|-----------------|-----------------|
        | SPY > 2%  | bull_calm       | bull_volatile   | bull_volatile   |
        | SPY ±2%   | sideways        | sideways        | sideways        |
        | SPY < -2% | bear_calm       | bear_calm       | bear_volatile   |
        """
        threshold = self.config.trend_threshold

        # Determine trend direction
        if spy_return > threshold:
            # Bull market
            if vix_level < self.config.vix_neutral_high:
                return MarketRegime.BULL_CALM
            else:
                return MarketRegime.BULL_VOLATILE

        elif spy_return < -threshold:
            # Bear market
            if vix_level > self.config.vix_high:
                return MarketRegime.BEAR_VOLATILE
            else:
                return MarketRegime.BEAR_CALM

        else:
            # Sideways
            return MarketRegime.SIDEWAYS

    def label_series(
        self,
        spy_candles: pd.DataFrame,
        vix_candles: pd.DataFrame,
        window_size: int = 20,
        step_size: int = 5,
    ) -> pd.DataFrame:
        """
        Label a time series with regime classifications.

        Creates rolling windows and classifies each period.

        Args:
            spy_candles: SPY OHLCV data
            vix_candles: VIX data
            window_size: Window size for regime calculation
            step_size: Step between windows

        Returns:
            DataFrame with columns: start_date, end_date, regime, spy_return, vix_level
        """
        if len(spy_candles) < window_size or len(vix_candles) < window_size:
            return pd.DataFrame()

        # Align data by date
        spy_candles = spy_candles.copy()
        vix_candles = vix_candles.copy()

        if "date" not in spy_candles.columns:
            spy_candles["date"] = spy_candles.index

        if "date" not in vix_candles.columns:
            vix_candles["date"] = vix_candles.index

        results = []
        n_windows = (len(spy_candles) - window_size) // step_size + 1

        for i in range(n_windows):
            start_idx = i * step_size
            end_idx = start_idx + window_size

            if end_idx > len(spy_candles):
                break

            spy_window = spy_candles.iloc[start_idx:end_idx]
            vix_window = vix_candles.iloc[start_idx:end_idx]

            regime = self.classify(spy_window, vix_window)
            spy_return = self._calculate_momentum(spy_window)
            vix_level = self._get_vix_level(vix_window)

            results.append({
                "start_date": spy_window["date"].iloc[0],
                "end_date": spy_window["date"].iloc[-1],
                "regime": regime.value,
                "spy_return": spy_return,
                "vix_level": vix_level,
            })

        return pd.DataFrame(results)


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

_classifier: Optional[EquitiesRegimeClassifier] = None


def _get_classifier() -> EquitiesRegimeClassifier:
    """Get or create default classifier."""
    global _classifier
    if _classifier is None:
        _classifier = EquitiesRegimeClassifier()
    return _classifier


def classify_regime(
    spy_candles: pd.DataFrame,
    vix_candles: pd.DataFrame,
) -> str:
    """
    Classify current market regime.

    Convenience function for quick regime classification.

    Args:
        spy_candles: SPY OHLCV data
        vix_candles: VIX data

    Returns:
        Regime name as string
    """
    classifier = _get_classifier()
    regime = classifier.classify(spy_candles, vix_candles)
    return regime.value


def label_regimes(
    spy_candles: pd.DataFrame,
    vix_candles: pd.DataFrame,
    window_size: int = 20,
    step_size: int = 5,
) -> pd.DataFrame:
    """
    Label time series with regimes.

    Args:
        spy_candles: SPY OHLCV data
        vix_candles: VIX data
        window_size: Window size
        step_size: Step between windows

    Returns:
        DataFrame with regime labels
    """
    classifier = _get_classifier()
    return classifier.label_series(
        spy_candles, vix_candles, window_size, step_size
    )


def get_regime_distribution(labels_df: pd.DataFrame) -> dict[str, float]:
    """
    Calculate distribution of regimes.

    Args:
        labels_df: Output from label_regimes()

    Returns:
        Dict mapping regime name to percentage
    """
    if labels_df.empty:
        return {}

    counts = labels_df["regime"].value_counts()
    total = len(labels_df)

    return {regime: count / total for regime, count in counts.items()}


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test regime classifier."""
    import sys
    sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks/EquitiesSwingTrading")

    from data.ingestion.market_data import MarketDataClient

    print("Testing regime classifier...")

    client = MarketDataClient(provider="yahoo")

    # Fetch SPY and VIX
    spy = client.fetch_spy_bars(days=252)  # 1 year
    vix = client.fetch_vix_bars(days=252)

    print(f"SPY: {len(spy)} bars")
    print(f"VIX: {len(vix)} bars")

    # Current regime
    current = classify_regime(spy, vix)
    print(f"\nCurrent regime: {current}")

    # Label series
    labels = label_regimes(spy, vix, window_size=20, step_size=5)
    print(f"\nLabeled {len(labels)} periods")

    # Distribution
    dist = get_regime_distribution(labels)
    print("\nRegime distribution:")
    for regime, pct in sorted(dist.items()):
        print(f"  {regime}: {pct:.1%}")


if __name__ == "__main__":
    quick_test()
