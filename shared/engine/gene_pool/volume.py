"""Volume primitives for gene pool."""
import pandas as pd
import numpy as np


# === VECTORIZED VERSIONS (Return pd.Series) ===

def volume_intensity_series(candles: pd.DataFrame, period: int, threshold: float) -> pd.Series:
    """
    Vectorized volume spike detector.

    Args:
        candles: OHLCV DataFrame with 'volume' column
        period: Lookback for average volume calculation
        threshold: Multiplier (e.g., 2.0 = 2x average volume)

    Returns:
        pd.Series: 1.0 where current volume > threshold * average, 0.0 otherwise
    """
    if 'volume' not in candles.columns:
        return pd.Series(0.0, index=candles.index)

    # Calculate rolling average volume (shifted by 1 to exclude current)
    avg_volume = candles['volume'].shift(1).rolling(period).mean()

    # Compare current volume to threshold * average
    signal = pd.Series(
        np.where(candles['volume'] > threshold * avg_volume, 1.0, 0.0),
        index=candles.index
    )

    # Fill NaN with 0.0
    signal = signal.fillna(0.0)

    return signal


def vwap_distance_series(candles: pd.DataFrame, period: int = 20) -> pd.Series:
    """
    Vectorized Z-score of price vs rolling VWAP.

    Args:
        candles: OHLCV DataFrame
        period: Lookback period for VWAP and std calculation

    Returns:
        pd.Series: Z-score capped at ±3.0
    """
    # Check required columns
    required_cols = ['high', 'low', 'close', 'volume']
    if not all(col in candles.columns for col in required_cols):
        return pd.Series(0.0, index=candles.index)

    # Calculate typical price (HLC/3)
    typical_price = (candles['high'] + candles['low'] + candles['close']) / 3

    # Calculate rolling VWAP
    tp_vol = typical_price * candles['volume']
    rolling_vwap = tp_vol.rolling(period).sum() / candles['volume'].rolling(period).sum()

    # Calculate rolling std of typical price
    rolling_std = typical_price.rolling(period).std()

    # Guard against zero std
    safe_std = rolling_std.replace(0, np.nan)

    # Calculate z-score
    z_score = (candles['close'] - rolling_vwap) / safe_std

    # Clip to ±3.0 and fill NaN with 0.0
    z_score = z_score.clip(-3.0, 3.0).fillna(0.0)

    return z_score


# === SCALAR VERSIONS (Return single float for last bar) ===

def volume_intensity(candles: pd.DataFrame, period: int, threshold: float) -> float:
    """
    Binary volume spike detector.

    Args:
        candles: OHLCV DataFrame with 'volume' column
        period: Lookback for average volume calculation
        threshold: Multiplier (e.g., 2.0 = 2x average volume)

    Returns:
        1.0 if current volume > threshold * average volume
        0.0 otherwise or if insufficient data
    """
    # Check sufficient data
    if len(candles) < period + 1:
        return 0.0

    # Check if volume column exists
    if 'volume' not in candles.columns:
        return 0.0

    # Get current volume
    current_volume = candles['volume'].iloc[-1]

    # Calculate average volume over the period (excluding current candle)
    avg_volume = candles['volume'].iloc[-(period + 1):-1].mean()

    # Guard against zero average volume
    if avg_volume == 0 or pd.isna(avg_volume):
        return 0.0

    # Check if current volume exceeds threshold
    if current_volume > threshold * avg_volume:
        return 1.0
    else:
        return 0.0


def vwap_distance(candles: pd.DataFrame, period: int = 20) -> float:
    """
    Z-score of price vs session VWAP.

    Args:
        candles: OHLCV DataFrame
        period: Lookback period for VWAP and std calculation

    Returns:
        Z-score capped at ±3.0
        Positive = price above VWAP
        Negative = price below VWAP
        0.0 if insufficient data or zero std
    """
    # Check sufficient data
    if len(candles) < period:
        return 0.0

    # Check required columns exist
    required_cols = ['high', 'low', 'close', 'volume']
    if not all(col in candles.columns for col in required_cols):
        return 0.0

    # Get the last 'period' candles
    recent_candles = candles.iloc[-period:]

    # Calculate typical price (HLC/3)
    typical_price = (recent_candles['high'] + recent_candles['low'] + recent_candles['close']) / 3

    # Calculate VWAP
    vwap = (typical_price * recent_candles['volume']).sum() / recent_candles['volume'].sum()

    # Guard against zero volume sum
    if recent_candles['volume'].sum() == 0 or pd.isna(vwap):
        return 0.0

    # Calculate standard deviation of typical price
    std = typical_price.std()

    # Guard against zero std
    if std == 0 or pd.isna(std):
        return 0.0

    # Get current price (close)
    current_price = candles['close'].iloc[-1]

    # Calculate z-score
    z_score = (current_price - vwap) / std

    # Cap at ±3.0
    z_score = np.clip(z_score, -3.0, 3.0)

    return float(z_score)
