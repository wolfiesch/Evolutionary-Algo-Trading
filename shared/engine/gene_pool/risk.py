"""
Risk management primitives for gene pool.

These primitives help strategies filter out high-risk conditions
and adapt to market volatility. They work within the existing
architecture by providing signals that strategies can use in
entry/exit conditions.

Usage in strategy expressions:
    "volatility_spike(14, 2.0) == 0 AND ..."  # Only enter when volatility is normal
    "trend_strength(20) > 0.5 AND ..."        # Only enter in strong trends
    "atr_stop_distance(14, 2) > 0.02 AND ..." # Only enter if stop isn't too tight
"""
import pandas as pd
import numpy as np
from ta.volatility import AverageTrueRange
from ta.trend import ADXIndicator


def volatility_spike(candles: pd.DataFrame, period: int, threshold: float = 2.0) -> float:
    """
    Detect sudden volatility increases (risk-off signal).

    Compares current ATR to recent average. High values indicate
    volatility spike - potentially risky for new entries.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        threshold: Multiple of avg ATR to consider a "spike" (default 2.0)

    Returns:
        1.0 = volatility spike detected (risk-off)
        0.0 = normal volatility (safe)
        0.0 if insufficient data
    """
    min_required = period * 3  # Need enough history for comparison
    if len(candles) < min_required:
        return 0.0

    atr = AverageTrueRange(
        high=candles["high"],
        low=candles["low"],
        close=candles["close"],
        window=period
    ).average_true_range()

    atr_values = atr.dropna()
    if len(atr_values) < period * 2:
        return 0.0

    current_atr = atr_values.iloc[-1]
    avg_atr = atr_values.iloc[-period*2:-period].mean()  # Recent but not current

    if avg_atr == 0:
        return 0.0

    ratio = current_atr / avg_atr
    return 1.0 if ratio >= threshold else 0.0


def trend_strength(candles: pd.DataFrame, period: int) -> float:
    """
    Measure current trend strength using ADX.

    Higher values indicate stronger trends - better for trend-following,
    lower values indicate ranging markets - better for mean reversion.

    Args:
        candles: OHLCV DataFrame
        period: ADX period (typically 14)

    Returns:
        0.0 to 1.0 (normalized ADX, where 1.0 = very strong trend)
        0.5 if insufficient data
    """
    min_required = period * 2
    if len(candles) < min_required:
        return 0.5

    try:
        adx = ADXIndicator(
            high=candles["high"],
            low=candles["low"],
            close=candles["close"],
            window=period
        ).adx()

        current_adx = adx.dropna().iloc[-1] if not adx.dropna().empty else 25.0

        # Normalize: ADX typically ranges 0-50+ but most values are 15-40
        # Map to 0-1 range with 50 as "maximum"
        normalized = min(1.0, current_adx / 50.0)
        return normalized
    except Exception:
        return 0.5


def atr_stop_distance(candles: pd.DataFrame, period: int, multiplier: float = 2.0) -> float:
    """
    Calculate ATR-based stop distance as percentage of price.

    Useful for filtering entries where the stop would be too tight
    (high volatility) or too wide (low volatility).

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        multiplier: ATR multiplier for stop distance (default 2.0)

    Returns:
        Stop distance as percentage (0.02 = 2% stop)
        0.03 if insufficient data
    """
    min_required = period + 1
    if len(candles) < min_required:
        return 0.03  # Default 3%

    atr = AverageTrueRange(
        high=candles["high"],
        low=candles["low"],
        close=candles["close"],
        window=period
    ).average_true_range()

    atr_values = atr.dropna()
    if atr_values.empty:
        return 0.03

    current_atr = atr_values.iloc[-1]
    current_price = candles["close"].iloc[-1]

    if current_price == 0:
        return 0.03

    stop_distance = (current_atr * multiplier) / current_price
    return stop_distance


def recent_range_position(candles: pd.DataFrame, lookback: int) -> float:
    """
    Position of current price within recent high-low range.

    Useful for identifying overbought/oversold conditions relative
    to recent price action, independent of indicators.

    Args:
        candles: OHLCV DataFrame
        lookback: Number of bars for range calculation

    Returns:
        0.0 = at recent low (potentially oversold)
        1.0 = at recent high (potentially overbought)
        0.5 if insufficient data
    """
    if len(candles) < lookback:
        return 0.5

    recent = candles.tail(lookback)
    high = recent["high"].max()
    low = recent["low"].min()
    current = candles["close"].iloc[-1]

    if high == low:
        return 0.5

    position = (current - low) / (high - low)
    return max(0.0, min(1.0, position))


def momentum_divergence(candles: pd.DataFrame, price_period: int, mom_period: int) -> float:
    """
    Detect price/momentum divergence (risk signal).

    Returns positive when price makes new highs but momentum doesn't
    (bearish divergence) or negative when price makes new lows but
    momentum doesn't (bullish divergence).

    Args:
        candles: OHLCV DataFrame
        price_period: Lookback for price highs/lows
        mom_period: Momentum calculation period

    Returns:
        +1.0 = bearish divergence (price high, momentum not)
        -1.0 = bullish divergence (price low, momentum not)
        0.0 = no divergence
        0.0 if insufficient data
    """
    min_required = max(price_period, mom_period) + 5
    if len(candles) < min_required:
        return 0.0

    closes = candles["close"]

    # Calculate momentum (rate of change)
    momentum = closes.pct_change(mom_period)

    # Get recent data
    recent_prices = closes.tail(price_period)
    recent_momentum = momentum.tail(price_period).dropna()

    if len(recent_momentum) < price_period - mom_period:
        return 0.0

    current_price = closes.iloc[-1]
    current_momentum = momentum.iloc[-1] if not pd.isna(momentum.iloc[-1]) else 0.0

    price_high = recent_prices.max()
    price_low = recent_prices.min()
    mom_high = recent_momentum.max()
    mom_low = recent_momentum.min()

    # Bearish divergence: price at high but momentum isn't
    if current_price >= price_high * 0.99 and current_momentum < mom_high * 0.7:
        return 1.0

    # Bullish divergence: price at low but momentum isn't
    if current_price <= price_low * 1.01 and current_momentum > mom_low * 0.7:
        return -1.0

    return 0.0


def volatility_contraction(candles: pd.DataFrame, period: int, lookback: int = 50) -> float:
    """
    Detect volatility contraction (potential breakout setup).

    Returns value indicating how much current volatility has contracted
    relative to recent history. High values suggest potential breakout.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        lookback: Historical comparison period

    Returns:
        0.0 = current volatility at historical average
        1.0 = volatility highly contracted (breakout potential)
        -1.0 = volatility expanded
        0.0 if insufficient data
    """
    min_required = period + lookback
    if len(candles) < min_required:
        return 0.0

    atr = AverageTrueRange(
        high=candles["high"],
        low=candles["low"],
        close=candles["close"],
        window=period
    ).average_true_range()

    atr_values = atr.dropna()
    if len(atr_values) < lookback:
        return 0.0

    current_atr = atr_values.iloc[-1]
    historical_atr = atr_values.iloc[-lookback:-1]

    avg_atr = historical_atr.mean()
    std_atr = historical_atr.std()

    if std_atr == 0 or avg_atr == 0:
        return 0.0

    # Z-score of current ATR (negative = contracted, positive = expanded)
    z_score = (current_atr - avg_atr) / std_atr

    # Normalize to -1 to 1 range, inverted so contraction = positive
    contraction = -np.clip(z_score / 2.0, -1.0, 1.0)

    return contraction
