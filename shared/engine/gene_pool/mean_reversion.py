"""Mean reversion primitives for gene pool."""
import pandas as pd
import numpy as np
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands


# === VECTORIZED VERSIONS (Return pd.Series) ===

def norm_rsi_series(candles: pd.DataFrame, period: int) -> pd.Series:
    """
    Vectorized normalized RSI: (RSI - 50) / 50

    Args:
        candles: OHLCV DataFrame (oldest first)
        period: RSI period (typically 14)

    Returns:
        pd.Series: -1.0 (oversold, RSI=0) to +1.0 (overbought, RSI=100)
    """
    # Calculate RSI using ta library
    rsi_series = RSIIndicator(candles['close'], window=period).rsi()

    # Normalize: (RSI - 50) / 50
    normalized = (rsi_series - 50.0) / 50.0

    # Clamp to [-1.0, 1.0] and fill NaN with 0.0
    normalized = normalized.clip(-1.0, 1.0).fillna(0.0)

    return normalized


def bb_position_series(candles: pd.DataFrame, period: int, std: float) -> pd.Series:
    """
    Vectorized position within Bollinger Bands.

    Args:
        candles: OHLCV DataFrame
        period: BB period (typically 20)
        std: Standard deviation multiplier (typically 2.0)

    Returns:
        pd.Series: -1.0 (lower band) to +1.0 (upper band)
    """
    # Calculate Bollinger Bands using ta library
    bb = BollingerBands(candles['close'], window=period, window_dev=std)

    lower = bb.bollinger_lband()
    middle = bb.bollinger_mavg()
    upper = bb.bollinger_hband()

    # Calculate half-width (upper - middle)
    half_width = upper - middle

    # Guard against zero width
    safe_half_width = half_width.replace(0, np.nan)

    # Calculate position: (close - middle) / half_width
    position = (candles['close'] - middle) / safe_half_width

    # Clamp to [-1.0, 1.0] and fill NaN with 0.0
    position = position.clip(-1.0, 1.0).fillna(0.0)

    return position


def bb_width_percentile_series(candles: pd.DataFrame, period: int, lookback: int = 100) -> pd.Series:
    """
    Vectorized Bollinger Band width percentile vs rolling history.

    Args:
        candles: OHLCV DataFrame
        period: BB period
        lookback: Historical lookback for percentile calculation

    Returns:
        pd.Series: 0.0 (narrowest) to 1.0 (widest) in lookback window
    """
    # Calculate Bollinger Bands
    bb = BollingerBands(candles['close'], window=period, window_dev=2.0)

    # Calculate band width series
    band_width = bb.bollinger_hband() - bb.bollinger_lband()

    # Calculate rolling percentile rank
    def rolling_percentile_rank(s: pd.Series) -> pd.Series:
        """Calculate percentile rank of last value in each rolling window."""
        result = pd.Series(index=s.index, dtype=float)
        for i in range(len(s)):
            if i < lookback - 1:
                result.iloc[i] = 0.5  # Default for insufficient data
            else:
                window = s.iloc[i - lookback + 1:i + 1]
                current = s.iloc[i]
                if pd.isna(current) or window.isna().all():
                    result.iloc[i] = 0.5
                else:
                    rank = (window < current).sum() / len(window.dropna())
                    result.iloc[i] = rank
        return result

    # Use rolling rank (more efficient)
    percentile = band_width.rolling(lookback).apply(
        lambda x: (x < x.iloc[-1]).sum() / (len(x) - 1) if len(x) > 1 else 0.5,
        raw=False
    )

    # Clamp to [0.0, 1.0] and fill NaN with 0.5
    percentile = percentile.clip(0.0, 1.0).fillna(0.5)

    return percentile


# === SCALAR VERSIONS (Return single float for last bar) ===

def norm_rsi(candles: pd.DataFrame, period: int) -> float:
    """
    Normalized RSI: (RSI - 50) / 50

    Args:
        candles: OHLCV DataFrame (oldest first)
        period: RSI period (typically 14)

    Returns:
        -1.0 (oversold, RSI=0) to +1.0 (overbought, RSI=100)
        0.0 = neutral (RSI=50) or insufficient data
    """
    if len(candles) < period:
        return 0.0

    # Calculate RSI using ta library
    rsi_series = RSIIndicator(candles['close'], window=period).rsi()

    # Get the last RSI value
    if rsi_series is None or len(rsi_series) == 0:
        return 0.0

    last_rsi = rsi_series.iloc[-1]

    # Handle NaN values
    if pd.isna(last_rsi):
        return 0.0

    # Normalize: (RSI - 50) / 50
    # RSI = 0 -> -1.0 (oversold)
    # RSI = 50 -> 0.0 (neutral)
    # RSI = 100 -> +1.0 (overbought)
    normalized = (last_rsi - 50.0) / 50.0

    # Clamp to [-1.0, 1.0] range (though RSI should already be [0, 100])
    return max(-1.0, min(1.0, normalized))


def bb_position(candles: pd.DataFrame, period: int, std: float) -> float:
    """
    Position within Bollinger Bands.

    Args:
        candles: OHLCV DataFrame
        period: BB period (typically 20)
        std: Standard deviation multiplier (typically 2.0)

    Returns:
        -1.0 = at lower band
        0.0 = at middle band
        +1.0 = at upper band
        Capped at ±1.0 even if price outside bands
        0.0 if insufficient data or zero width
    """
    if len(candles) < period:
        return 0.0

    # Calculate Bollinger Bands using ta library
    bb = BollingerBands(candles['close'], window=period, window_dev=std)

    # Get the last values
    lower = bb.bollinger_lband().iloc[-1]
    middle = bb.bollinger_mavg().iloc[-1]
    upper = bb.bollinger_hband().iloc[-1]
    current_price = candles['close'].iloc[-1]

    # Handle NaN values
    if pd.isna(lower) or pd.isna(middle) or pd.isna(upper):
        return 0.0

    # Calculate band width
    band_width = upper - lower

    # Guard against zero width
    if band_width <= 0:
        return 0.0

    # Calculate position within bands
    # Position = (price - middle) / (half_width)
    half_width = (upper - middle)

    if half_width <= 0:
        return 0.0

    position = (current_price - middle) / half_width

    # Clamp to [-1.0, 1.0]
    return max(-1.0, min(1.0, position))


def bb_width_percentile(candles: pd.DataFrame, period: int, lookback: int = 100) -> float:
    """
    Bollinger Band width percentile vs recent history.

    Args:
        candles: OHLCV DataFrame
        period: BB period
        lookback: Historical lookback for percentile calculation

    Returns:
        0.0 = narrowest bands in lookback
        1.0 = widest bands in lookback
        0.5 if insufficient data
    """
    # Need at least period + lookback candles for meaningful calculation
    required_candles = period + lookback
    if len(candles) < required_candles:
        return 0.5

    # Calculate Bollinger Bands
    bb = BollingerBands(candles['close'], window=period, window_dev=2.0)

    # Calculate band width series
    band_width = bb.bollinger_hband() - bb.bollinger_lband()

    # Get the last lookback values
    recent_widths = band_width.iloc[-lookback:]

    # Remove NaN values
    recent_widths = recent_widths.dropna()

    if len(recent_widths) == 0:
        return 0.5

    # Get current width
    current_width = band_width.iloc[-1]

    if pd.isna(current_width):
        return 0.5

    # Calculate percentile
    # Count how many historical widths are less than current width
    percentile = (recent_widths < current_width).sum() / len(recent_widths)

    # Clamp to [0.0, 1.0] (should already be in range)
    return max(0.0, min(1.0, percentile))
