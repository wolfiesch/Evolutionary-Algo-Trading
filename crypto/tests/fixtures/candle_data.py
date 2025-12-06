"""Mock candle data generators for testing."""
import random
from datetime import datetime, timedelta
from typing import Literal

from data.storage.models import Candle


def generate_candles(
    symbol: str,
    count: int,
    start_price: float = 100.0,
    trend: Literal["bull", "bear", "sideways"] = "sideways",
    volatility: float = 0.02,
    start_time: datetime | None = None,
    interval_minutes: int = 1,
) -> list[Candle]:
    """
    Generate realistic candle data with controlled trend.

    Args:
        symbol: Trading pair symbol
        count: Number of candles to generate
        start_price: Initial price
        trend: Market direction
        volatility: Price volatility (0.02 = 2%)
        start_time: Starting timestamp
        interval_minutes: Candle interval

    Returns:
        List of Candle objects in chronological order
    """
    if start_time is None:
        start_time = datetime.now() - timedelta(minutes=count * interval_minutes)

    # Trend drift per candle
    # For 30 days (43,200 candles): bull ~+40%, bear ~-30%, sideways ~0%
    drift = {
        "bull": 0.000008,    # Positive drift: (1.000008)^43200 ≈ 1.40 (+40%)
        "bear": -0.000008,   # Negative drift: (0.999992)^43200 ≈ 0.70 (-30%)
        "sideways": 0.0,     # No drift
    }[trend]

    candles = []
    price = start_price

    for i in range(count):
        timestamp = start_time + timedelta(minutes=i * interval_minutes)

        # Random walk with drift
        change = random.gauss(drift, volatility)
        # Clamp extreme values to prevent price explosion/collapse
        change = max(-0.1, min(0.1, change))  # Max 10% move per candle
        price = price * (1 + change)

        # Generate OHLC with realistic intrabar movement
        open_price = price
        high_price = price * (1 + random.uniform(0, volatility / 2))
        low_price = price * (1 - random.uniform(0, volatility / 2))
        close_price = price * (1 + random.gauss(0, volatility / 4))

        # Ensure OHLC constraints
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        # Update price for next candle
        price = close_price

        # Random volume with some correlation to volatility
        base_volume = 1000000
        volume = base_volume * (1 + abs(change) * 10) * random.uniform(0.5, 1.5)

        candles.append(Candle(
            symbol=symbol,
            timestamp=int(timestamp.timestamp() * 1000),  # Convert to milliseconds
            open=round(open_price, 4),
            high=round(high_price, 4),
            low=round(low_price, 4),
            close=round(close_price, 4),
            volume=round(volume, 2),
            turnover=round(volume * close_price, 2),
        ))

    return candles


def generate_flash_crash(
    symbol: str,
    count: int = 100,
    crash_at: int = 50,
    crash_pct: float = 0.60,
) -> list[Candle]:
    """Generate data with a flash crash for testing data quality filters."""
    candles = generate_candles(symbol, count, trend="bull")

    # Insert flash crash
    if crash_at < len(candles):
        pre_crash = candles[crash_at - 1]
        crash_price = pre_crash.close * (1 - crash_pct)

        candles[crash_at] = Candle(
            symbol=symbol,
            timestamp=candles[crash_at].timestamp,
            open=pre_crash.close,
            high=pre_crash.close,
            low=crash_price,
            close=crash_price * 1.1,  # Partial recovery
            volume=candles[crash_at].volume * 10,  # Huge volume
            turnover=0,
        )

    return candles
