"""Market filter primitives for gene pool."""
import pandas as pd
from ta.trend import EMAIndicator


def _asset_trend(candles: pd.DataFrame, window: int) -> float:
    """
    Generic asset trend filter - checks if asset is in uptrend.

    Used by btc_trend, sol_trend, eth_trend - each passes its own candles.

    Args:
        candles: OHLCV DataFrame for the asset (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = Asset stable or rising (safe to trade)
        -1.0 = Asset dumping (avoid new longs)
        -1.0 if insufficient data (conservative default)
    """
    # Check sufficient data
    if len(candles) < window:
        return -1.0  # Conservative default

    # Calculate long EMA using ta library
    long_ema = EMAIndicator(candles['close'], window=window).ema_indicator()

    # Calculate short EMA (window // 4, min 5)
    short_window = max(window // 4, 5)
    short_ema = EMAIndicator(candles['close'], window=short_window).ema_indicator()

    # Get the most recent values
    current_price = candles['close'].iloc[-1]
    current_long_ema = long_ema.iloc[-1]
    current_short_ema = short_ema.iloc[-1]

    # Check for NaN values
    if pd.isna(current_long_ema) or pd.isna(current_short_ema):
        return -1.0

    # Asset is "safe" if:
    # 1. Price >= EMA * 0.98 (2% tolerance for noise)
    # 2. Short EMA > Long EMA (positive momentum)
    price_above_ema = current_price >= current_long_ema * 0.98
    momentum_positive = current_short_ema > current_long_ema

    if price_above_ema and momentum_positive:
        return 1.0
    else:
        return -1.0


def btc_trend(btc_candles: pd.DataFrame, window: int) -> float:
    """
    BTC trend filter - checks BTC market health.

    For BTC trading: Self-referential (uses BTC's own data)
    For altcoin trading: Cross-asset filter (may not correlate well)

    Args:
        btc_candles: OHLCV DataFrame for BTCUSDT (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = BTC stable or rising
        -1.0 = BTC dumping
    """
    return _asset_trend(btc_candles, window)


def sol_trend(candles: pd.DataFrame, window: int) -> float:
    """
    SOL trend filter - checks if SOL is in uptrend.

    Self-referential filter for SOLUSDT trading.
    Use this instead of btc_trend when trading SOL.

    Args:
        candles: OHLCV DataFrame for SOLUSDT (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = SOL stable or rising (safe to long)
        -1.0 = SOL dumping (avoid new longs)
    """
    return _asset_trend(candles, window)


def eth_trend(candles: pd.DataFrame, window: int) -> float:
    """
    ETH trend filter - checks if ETH is in uptrend.

    Self-referential filter for ETHUSDT trading.
    Use this instead of btc_trend when trading ETH.

    Args:
        candles: OHLCV DataFrame for ETHUSDT (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = ETH stable or rising (safe to long)
        -1.0 = ETH dumping (avoid new longs)
    """
    return _asset_trend(candles, window)


def asset_trend(candles: pd.DataFrame, window: int) -> float:
    """
    Generic asset trend filter - checks if current asset is in uptrend.

    Self-referential filter that works for any asset.
    The parser passes the trading symbol's candles automatically.

    Args:
        candles: OHLCV DataFrame for the trading asset (oldest first)
        window: EMA window for trend determination

    Returns:
        +1.0 = Asset stable or rising (safe to long)
        -1.0 = Asset dumping (avoid new longs)
    """
    return _asset_trend(candles, window)
