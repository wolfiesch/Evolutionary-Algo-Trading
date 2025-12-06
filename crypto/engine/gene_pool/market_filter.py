"""Market filter primitives for gene pool."""
import pandas as pd
from ta.trend import EMAIndicator


def btc_trend(btc_candles: pd.DataFrame, window: int) -> float:
    """
    BTC trend filter - MANDATORY for all altcoin long entries.

    "Don't buy alts when BTC is dumping."

    Args:
        btc_candles: OHLCV DataFrame for BTCUSDT (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = BTC stable or rising (safe to long alts)
        -1.0 = BTC dumping (avoid new longs)
        -1.0 if insufficient data (conservative default)

    Rule: All entry_long conditions MUST include btc_trend(window) >= 0

    Implementation:
        1. Calculate long EMA (specified window)
        2. Calculate short EMA (window // 4, min 5)
        3. BTC is "safe" if:
           - Price >= long EMA * 0.98 (2% tolerance for noise)
           - Short EMA > long EMA (positive momentum)
        4. Return +1.0 if safe, -1.0 otherwise
    """
    # Check sufficient data
    if len(btc_candles) < window:
        return -1.0  # Conservative default

    # Calculate long EMA using ta library
    long_ema = EMAIndicator(btc_candles['close'], window=window).ema_indicator()

    # Calculate short EMA (window // 4, min 5)
    short_window = max(window // 4, 5)
    short_ema = EMAIndicator(btc_candles['close'], window=short_window).ema_indicator()

    # Get the most recent values
    current_price = btc_candles['close'].iloc[-1]
    current_long_ema = long_ema.iloc[-1]
    current_short_ema = short_ema.iloc[-1]

    # Check for NaN values
    if pd.isna(current_long_ema) or pd.isna(current_short_ema):
        return -1.0

    # BTC is "safe" if:
    # 1. Price >= EMA * 0.98 (2% tolerance for noise)
    # 2. Short EMA > Long EMA (positive momentum)
    price_above_ema = current_price >= current_long_ema * 0.98
    momentum_positive = current_short_ema > current_long_ema

    if price_above_ema and momentum_positive:
        return 1.0
    else:
        return -1.0
