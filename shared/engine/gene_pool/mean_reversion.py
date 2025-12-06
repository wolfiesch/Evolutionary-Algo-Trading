"""Mean reversion primitives for gene pool."""
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands


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
