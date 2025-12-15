"""
Market Filter Primitives for Equities Swing Trading.

These primitives provide market regime awareness:
- SPY trend: Overall market direction filter
- VIX regime: Volatility regime classification
- Sector momentum: Sector rotation signals

All primitives return normalized values suitable for strategy expressions.
"""

import pandas as pd
import numpy as np


def spy_trend(spy_candles: pd.DataFrame, period: int) -> float:
    """
    SPY trend filter - checks overall market health.

    Equivalent to btc_trend for crypto. Uses dual EMA check:
    1. Price >= 98% of long EMA (price not collapsed)
    2. Short EMA > Long EMA (positive momentum)

    Args:
        spy_candles: OHLCV DataFrame for SPY (oldest first)
        period: EMA window for trend determination (e.g., 20, 50)

    Returns:
        +1.0 = Market in uptrend (safe to go long)
        -1.0 = Market in downtrend (defensive)

    Example usage:
        entry_long: spy_trend(20) >= 0 AND ...
    """
    if len(spy_candles) < period:
        return -1.0  # Conservative default

    close = spy_candles["close"]

    # Long EMA
    long_ema = close.ewm(span=period, adjust=False).mean()

    # Short EMA (period // 4, min 5)
    short_period = max(period // 4, 5)
    short_ema = close.ewm(span=short_period, adjust=False).mean()

    # Get current values
    current_price = close.iloc[-1]
    current_long_ema = long_ema.iloc[-1]
    current_short_ema = short_ema.iloc[-1]

    # Check for NaN
    if pd.isna(current_long_ema) or pd.isna(current_short_ema):
        return -1.0

    # Dual condition check
    price_above_ema = current_price >= current_long_ema * 0.98
    momentum_positive = current_short_ema > current_long_ema

    if price_above_ema and momentum_positive:
        return 1.0
    return -1.0


def vix_regime(vix_candles: pd.DataFrame, period: int) -> float:
    """
    VIX regime filter - classifies volatility environment.

    VIX is the "fear gauge" of the market:
    - Low VIX (<15): Complacency, risk-on environment
    - Normal VIX (15-25): Typical market conditions
    - High VIX (>25): Fear, risk-off environment

    Uses smoothed VIX (SMA) to avoid whipsaws.

    Args:
        vix_candles: OHLCV DataFrame for ^VIX (oldest first)
        period: SMA window for smoothing (e.g., 5, 10, 14)

    Returns:
        +1.0 = Low vol regime (VIX < 15) - risk on
        0.0 = Normal vol regime (VIX 15-25) - neutral
        -1.0 = High vol regime (VIX > 25) - risk off

    Example usage:
        entry_long: vix_regime(14) >= 0 AND ...
    """
    if len(vix_candles) < period:
        return 0.0  # Neutral default

    close = vix_candles["close"]

    # Smooth VIX with SMA
    vix_sma = close.rolling(window=period).mean()
    current_vix = vix_sma.iloc[-1]

    if pd.isna(current_vix):
        return 0.0

    # Classify regime
    if current_vix < 15:
        return 1.0   # Low vol - risk on
    elif current_vix > 25:
        return -1.0  # High vol - risk off
    else:
        return 0.0   # Normal - neutral


def vix_percentile(vix_candles: pd.DataFrame, period: int) -> float:
    """
    VIX percentile - current VIX relative to historical range.

    Provides more granular volatility signal than vix_regime.

    Args:
        vix_candles: OHLCV DataFrame for ^VIX (oldest first)
        period: Lookback period for percentile calculation

    Returns:
        0.0 to 1.0 (higher = higher volatility relative to history)
        0.5 if insufficient data

    Example usage:
        entry_long: vix_percentile(60) < 0.7 AND ...
    """
    if len(vix_candles) < period:
        return 0.5  # Neutral default

    close = vix_candles["close"]
    current_vix = close.iloc[-1]

    # Get historical range
    historical = close.iloc[-period:]

    if pd.isna(current_vix):
        return 0.5

    # Calculate percentile rank
    percentile = (historical < current_vix).sum() / len(historical)

    return float(percentile)


def spy_momentum(spy_candles: pd.DataFrame, period: int) -> float:
    """
    SPY momentum - rate of change over period.

    Measures how fast SPY is moving, not just direction.

    Args:
        spy_candles: OHLCV DataFrame for SPY (oldest first)
        period: Lookback period for momentum calculation

    Returns:
        -1.0 to +1.0 (positive = upward momentum)
        Clamped at ±1.0 to prevent extreme values

    Example usage:
        entry_long: spy_momentum(20) > 0.0 AND ...
    """
    if len(spy_candles) < period + 1:
        return 0.0

    close = spy_candles["close"]

    # Calculate returns over period
    current_price = close.iloc[-1]
    past_price = close.iloc[-period - 1]

    if past_price == 0 or pd.isna(current_price) or pd.isna(past_price):
        return 0.0

    # Return as percentage, scaled and clamped
    pct_change = (current_price - past_price) / past_price

    # Scale: 10% move = 1.0
    scaled = pct_change / 0.10

    return float(max(-1.0, min(1.0, scaled)))


def spy_above_sma(spy_candles: pd.DataFrame, period: int) -> float:
    """
    SPY above SMA - simple binary check.

    Classic trend-following filter: only long when price > SMA.

    Args:
        spy_candles: OHLCV DataFrame for SPY (oldest first)
        period: SMA period (e.g., 50, 100, 200)

    Returns:
        +1.0 if SPY > SMA (bullish)
        -1.0 if SPY < SMA (bearish)

    Example usage:
        entry_long: spy_above_sma(200) == 1.0 AND ...
    """
    if len(spy_candles) < period:
        return -1.0  # Conservative default

    close = spy_candles["close"]
    sma = close.rolling(window=period).mean()

    current_price = close.iloc[-1]
    current_sma = sma.iloc[-1]

    if pd.isna(current_sma):
        return -1.0

    if current_price > current_sma:
        return 1.0
    return -1.0


def market_breadth_proxy(spy_candles: pd.DataFrame, period: int) -> float:
    """
    Market breadth proxy using SPY price action.

    True market breadth requires advance/decline data.
    This proxy uses SPY's position in its range as estimate.

    Args:
        spy_candles: OHLCV DataFrame for SPY (oldest first)
        period: Lookback period for range calculation

    Returns:
        -1.0 to +1.0 (higher = price near highs = healthy breadth)

    Example usage:
        entry_long: market_breadth_proxy(20) > 0.0 AND ...
    """
    if len(spy_candles) < period:
        return 0.0

    close = spy_candles["close"]
    high = spy_candles["high"]
    low = spy_candles["low"]

    # Get period high and low
    period_high = high.iloc[-period:].max()
    period_low = low.iloc[-period:].min()
    current_price = close.iloc[-1]

    if period_high == period_low or pd.isna(current_price):
        return 0.0

    # Position in range: 0 = at low, 1 = at high
    position = (current_price - period_low) / (period_high - period_low)

    # Scale to -1.0 to +1.0
    return float(2 * position - 1)


# =============================================================================
# SECTOR FILTERS (for future use with sector ETFs)
# =============================================================================

def sector_trend(sector_candles: pd.DataFrame, period: int) -> float:
    """
    Sector ETF trend filter.

    Same logic as spy_trend but for sector ETFs (XLK, XLF, XLE, etc.)

    Args:
        sector_candles: OHLCV DataFrame for sector ETF (oldest first)
        period: EMA window for trend determination

    Returns:
        +1.0 = Sector in uptrend
        -1.0 = Sector in downtrend
    """
    # Same implementation as spy_trend
    return spy_trend(sector_candles, period)


def sector_vs_spy(
    sector_candles: pd.DataFrame,
    spy_candles: pd.DataFrame,
    period: int
) -> float:
    """
    Sector relative strength vs SPY.

    Measures if sector is outperforming or underperforming the market.

    Args:
        sector_candles: OHLCV DataFrame for sector ETF
        spy_candles: OHLCV DataFrame for SPY
        period: Lookback period for comparison

    Returns:
        -1.0 to +1.0 (positive = sector outperforming)
    """
    if len(sector_candles) < period + 1 or len(spy_candles) < period + 1:
        return 0.0

    # Calculate returns
    sector_return = (
        sector_candles["close"].iloc[-1] /
        sector_candles["close"].iloc[-period - 1] - 1
    )
    spy_return = (
        spy_candles["close"].iloc[-1] /
        spy_candles["close"].iloc[-period - 1] - 1
    )

    if pd.isna(sector_return) or pd.isna(spy_return):
        return 0.0

    # Relative strength (difference in returns)
    rs = sector_return - spy_return

    # Scale: 5% outperformance = 1.0
    scaled = rs / 0.05

    return float(max(-1.0, min(1.0, scaled)))


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test market filter primitives."""
    import sys
    sys.path.insert(0, "/Users/wolfgangschoenberger/Projects/Oil-Stonks/EquitiesSwingTrading")
    from data.ingestion.market_data import MarketDataClient

    client = MarketDataClient(provider="yahoo")

    # Get SPY and VIX data
    print("Fetching SPY and VIX data...")
    spy = client.fetch_spy_bars(days=100)
    vix = client.fetch_vix_bars(days=100)

    print(f"SPY: {len(spy)} bars, latest close: ${spy.iloc[-1]['close']:.2f}")
    print(f"VIX: {len(vix)} bars, latest close: {vix.iloc[-1]['close']:.2f}")

    # Test primitives
    print("\n=== Market Filter Tests ===")
    print(f"spy_trend(20): {spy_trend(spy, 20)}")
    print(f"spy_trend(50): {spy_trend(spy, 50)}")
    print(f"vix_regime(14): {vix_regime(vix, 14)}")
    print(f"vix_percentile(60): {vix_percentile(vix, 60):.2f}")
    print(f"spy_momentum(20): {spy_momentum(spy, 20):.2f}")
    print(f"spy_above_sma(50): {spy_above_sma(spy, 50)}")
    print(f"spy_above_sma(200): {spy_above_sma(spy, 200)}")
    print(f"market_breadth_proxy(20): {market_breadth_proxy(spy, 20):.2f}")


if __name__ == "__main__":
    quick_test()
