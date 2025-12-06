"""Volatility primitives for gene pool."""
import pandas as pd
import pandas_ta as ta


def atr_regime(candles: pd.DataFrame, period: int, lookback: int = 100) -> float:
    """
    Classify current volatility regime.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        lookback: Historical lookback for percentile comparison

    Returns:
        +1.0 = high volatility (ATR > 75th percentile)
        0.0 = normal volatility (25th-75th percentile)
        -1.0 = low volatility (ATR < 25th percentile)
        0.0 if insufficient data
    """
    # Need at least period + lookback candles
    min_required = period + lookback
    if len(candles) < min_required:
        return 0.0

    # Calculate ATR
    atr = ta.atr(
        high=candles["high"],
        low=candles["low"],
        close=candles["close"],
        length=period
    )

    # Get the last lookback ATR values (excluding NaN from start)
    atr_history = atr.dropna().tail(lookback)

    if len(atr_history) < lookback:
        return 0.0

    # Current ATR is the most recent value
    current_atr = atr_history.iloc[-1]

    # Calculate percentile thresholds
    p25 = atr_history.quantile(0.25)
    p75 = atr_history.quantile(0.75)

    # Classify regime
    if current_atr > p75:
        return 1.0  # High volatility
    elif current_atr < p25:
        return -1.0  # Low volatility
    else:
        return 0.0  # Normal volatility


def atr_percentile(candles: pd.DataFrame, period: int, lookback: int = 100) -> float:
    """
    Current ATR percentile vs historical.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        lookback: Historical lookback for percentile

    Returns:
        0.0 = lowest ATR in lookback
        1.0 = highest ATR in lookback
        0.5 if insufficient data
    """
    # Need at least period + lookback candles
    min_required = period + lookback
    if len(candles) < min_required:
        return 0.5

    # Calculate ATR
    atr = ta.atr(
        high=candles["high"],
        low=candles["low"],
        close=candles["close"],
        length=period
    )

    # Get the last lookback ATR values (excluding NaN from start)
    atr_history = atr.dropna().tail(lookback)

    if len(atr_history) < lookback:
        return 0.5

    # Current ATR is the most recent value
    current_atr = atr_history.iloc[-1]

    # Calculate rank-based percentile
    # Count how many historical values are less than current
    rank = (atr_history < current_atr).sum()
    percentile = rank / (len(atr_history) - 1) if len(atr_history) > 1 else 0.5

    return percentile
