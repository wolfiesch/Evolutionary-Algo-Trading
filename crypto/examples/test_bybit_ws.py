#!/usr/bin/env python3
"""Example script to test Bybit WebSocket client (for manual testing only)."""
import asyncio
import logging
from data.ingestion.bybit_ws import BybitWebSocketClient
from data.storage.models import Candle

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Simple counter for testing
candle_count = 0


async def on_candle(candle: Candle) -> None:
    """Handle incoming candles."""
    global candle_count
    candle_count += 1
    print(f"[{candle_count}] {candle.symbol} @ {candle.datetime}: "
          f"O={candle.open} H={candle.high} L={candle.low} C={candle.close} V={candle.volume}")


async def main():
    """Run the WebSocket client for testing."""
    # Test with a few symbols
    symbols = ["BTCUSDT", "ETHUSDT"]

    client = BybitWebSocketClient(
        symbols=symbols,
        on_candle=on_candle,
        interval="1"  # 1-minute candles
    )

    print(f"Starting Bybit WebSocket client for {symbols}...")
    print("Press Ctrl+C to stop\n")

    try:
        await client.run()
    except KeyboardInterrupt:
        print("\nStopping client...")
        client.stop()
        print("Client stopped.")


if __name__ == "__main__":
    # Note: This is for manual testing only.
    # In production, this would run continuously in the background.
    asyncio.run(main())
