"""Pre-built market scenarios for comprehensive testing."""
from datetime import datetime, timedelta

from .candle_data import generate_candles
from data.storage.models import Candle


def get_bull_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of bull market data (1-minute candles)."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=1500.0,
        trend="bull",
        volatility=0.001,  # Small volatility for realistic prices over many candles
    )


def get_bear_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of bear market data."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=2000.0,
        trend="bear",
        volatility=0.001,  # Small volatility for realistic prices
    )


def get_sideways_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of sideways/ranging market."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=1800.0,
        trend="sideways",
        volatility=0.001,  # Small volatility
    )


def get_btc_reference(trend: str = "bull", days: int = 30) -> list[Candle]:
    """BTC data for market filter tests."""
    return generate_candles(
        symbol="BTCUSDT",
        count=days * 24 * 60,
        start_price=42000.0,
        trend=trend,
        volatility=0.001,  # Small volatility
    )


def get_multi_regime_data(symbol: str = "ETHUSDT") -> list[Candle]:
    """
    90 days of data with 3 distinct regimes:
    - Days 1-30: Bull
    - Days 31-60: Sideways
    - Days 61-90: Bear
    """
    base_time = datetime.now() - timedelta(days=90)

    bull = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=1500.0,
        trend="bull",
        start_time=base_time,
        volatility=0.001,
    )

    # Start sideways from bull's end price
    sideways_start = bull[-1].close
    sideways = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=sideways_start,
        trend="sideways",
        start_time=base_time + timedelta(days=30),
        volatility=0.001,
    )

    # Start bear from sideways end
    bear_start = sideways[-1].close
    bear = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=bear_start,
        trend="bear",
        start_time=base_time + timedelta(days=60),
        volatility=0.001,
    )

    return bull + sideways + bear
