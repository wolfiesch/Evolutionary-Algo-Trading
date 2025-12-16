"""Trend primitives for gene pool."""
import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange


# === VECTORIZED VERSIONS (Return pd.Series) ===

def ema_trend_series(candles: pd.DataFrame, fast: int, slow: int) -> pd.Series:
    """
    Vectorized EMA crossover signal.

    Args:
        candles: OHLCV DataFrame with columns [open, high, low, close, volume]
        fast: Fast EMA period (e.g., 9)
        slow: Slow EMA period (e.g., 21)

    Returns:
        pd.Series: +1.0 where fast > slow (uptrend), -1.0 where fast < slow (downtrend)
    """
    # Calculate EMAs using ta library
    fast_ema = EMAIndicator(candles['close'], window=fast).ema_indicator()
    slow_ema = EMAIndicator(candles['close'], window=slow).ema_indicator()

    # Vectorized comparison: +1 if fast > slow, -1 otherwise
    signal = pd.Series(
        np.where(fast_ema > slow_ema, 1.0, -1.0),
        index=candles.index
    )

    # Set NaN where EMAs are NaN
    signal = signal.where(fast_ema.notna() & slow_ema.notna(), 0.0)

    return signal


def price_position_series(candles: pd.DataFrame, period: int) -> pd.Series:
    """
    Vectorized price position relative to EMA, normalized by ATR.

    Args:
        candles: OHLCV DataFrame
        period: EMA and ATR period

    Returns:
        pd.Series: (Price - EMA) / ATR, capped at ±3.0
    """
    # Calculate EMA and ATR using ta library
    ema = EMAIndicator(candles['close'], window=period).ema_indicator()
    atr = AverageTrueRange(
        candles['high'], candles['low'], candles['close'], window=period
    ).average_true_range()

    # Calculate position: (close - ema) / atr
    # Guard against zero ATR
    safe_atr = atr.replace(0, np.nan)
    position = (candles['close'] - ema) / safe_atr

    # Cap at ±3.0
    position = position.clip(-3.0, 3.0)

    # Fill NaN with 0.0
    position = position.fillna(0.0)

    return position


# === SCALAR VERSIONS (Return single float for last bar) ===

def ema_trend(candles: pd.DataFrame, fast: int, slow: int) -> float:
    """
    Determine trend direction from EMA crossover state.

    Args:
        candles: OHLCV DataFrame with columns [open, high, low, close, volume]
                 Must be sorted oldest-first (chronological)
        fast: Fast EMA period (e.g., 9)
        slow: Slow EMA period (e.g., 21)

    Returns:
        +1.0 if fast EMA > slow EMA (uptrend)
        -1.0 if fast EMA < slow EMA (downtrend)
        0.0 if insufficient data
    """
    # Check sufficient data for slow EMA
    if len(candles) < slow:
        return 0.0

    # Calculate EMAs using ta library
    fast_ema = EMAIndicator(candles['close'], window=fast).ema_indicator()
    slow_ema = EMAIndicator(candles['close'], window=slow).ema_indicator()

    # Get the most recent values
    current_fast = fast_ema.iloc[-1]
    current_slow = slow_ema.iloc[-1]

    # Check for NaN values
    if pd.isna(current_fast) or pd.isna(current_slow):
        return 0.0

    # Determine trend
    if current_fast > current_slow:
        return 1.0
    else:
        return -1.0


def price_position(candles: pd.DataFrame, period: int) -> float:
    """
    Price position relative to EMA, normalized by ATR.

    Args:
        candles: OHLCV DataFrame
        period: EMA and ATR period

    Returns:
        (Price - EMA) / ATR, capped at ±3.0
        Positive = price above EMA, negative = below
        0.0 if insufficient data or zero ATR
    """
    # Check sufficient data
    if len(candles) < period:
        return 0.0

    # Calculate EMA and ATR using ta library
    ema = EMAIndicator(candles['close'], window=period).ema_indicator()
    atr = AverageTrueRange(
        candles['high'], candles['low'], candles['close'], window=period
    ).average_true_range()

    # Get the most recent values
    current_price = candles['close'].iloc[-1]
    current_ema = ema.iloc[-1]
    current_atr = atr.iloc[-1]

    # Check for NaN values
    if pd.isna(current_ema) or pd.isna(current_atr):
        return 0.0

    # Guard against zero ATR
    if current_atr == 0.0:
        return 0.0

    # Calculate normalized position
    position = (current_price - current_ema) / current_atr

    # Cap at ±3.0
    position = max(-3.0, min(3.0, position))

    return position
