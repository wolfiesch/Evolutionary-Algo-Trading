"""Bybit WebSocket client for real-time candle data."""
import asyncio
import json
import logging
from typing import Callable, Awaitable, TYPE_CHECKING

import aiohttp
import websockets

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

from data.storage.models import Candle
from config import settings

logger = logging.getLogger(__name__)


class BybitWebSocketClient:
    """WebSocket client for Bybit kline (candlestick) data."""

    def __init__(
        self,
        symbols: list[str],
        on_candle: Callable[[Candle], Awaitable[None]],
        interval: str = "1",
    ):
        """
        Initialize Bybit WebSocket client.

        Args:
            symbols: List of trading symbols (e.g., ["BTCUSDT", "ETHUSDT"])
            on_candle: Async callback to handle incoming candles
            interval: Kline interval in minutes (default: "1")
        """
        self.symbols = symbols
        self.on_candle = on_candle
        self.interval = interval
        self._running = False
        self._reconnect_delay = settings.reconnect_delay_seconds
        self._max_reconnect_delay = 60

    async def run(self) -> None:
        """
        Main loop with auto-reconnect and exponential backoff.

        Continuously connects to WebSocket, handles disconnections,
        and implements exponential backoff for reconnection attempts.
        """
        self._running = True
        current_delay = self._reconnect_delay

        while self._running:
            try:
                await self._connect_and_stream()
                # Reset delay on successful connection
                current_delay = self._reconnect_delay
            except Exception as e:
                logger.error(f"WebSocket error: {e}", exc_info=True)

                if self._running:
                    logger.info(f"Reconnecting in {current_delay}s...")
                    await asyncio.sleep(current_delay)

                    # Exponential backoff
                    current_delay = min(current_delay * 2, self._max_reconnect_delay)

    async def _connect_and_stream(self) -> None:
        """
        Connect to WebSocket and process messages.

        Establishes connection, performs warmup, subscribes to topics,
        and processes incoming messages.
        """
        logger.info(f"Connecting to {settings.bybit_ws_url}")

        async with websockets.connect(settings.bybit_ws_url) as ws:
            logger.info("WebSocket connected")

            # Perform warmup: fetch historical candles via REST
            await self._warmup()

            # Subscribe to kline topics
            await self._subscribe(ws)

            # Process incoming messages
            async for message in ws:
                try:
                    await self._handle_message(message)
                except Exception as e:
                    logger.error(f"Error handling message: {e}", exc_info=True)

    async def _subscribe(self, ws) -> None:
        """
        Subscribe to kline topics for all symbols.

        Args:
            ws: WebSocket connection
        """
        # Build subscription arguments: ["kline.1.BTCUSDT", "kline.1.ETHUSDT", ...]
        args = [f"kline.{self.interval}.{symbol}" for symbol in self.symbols]

        subscription = {"op": "subscribe", "args": args}

        await ws.send(json.dumps(subscription))
        logger.info(f"Subscribed to {len(args)} kline topics")

    async def _handle_message(self, message: str) -> None:
        """
        Parse kline messages and emit Candle via callback.

        Args:
            message: Raw WebSocket message string

        Expected message format:
        {
            "topic": "kline.1.BTCUSDT",
            "data": [{
                "start": 1234567890000,  # milliseconds
                "open": "50000.0",
                "high": "50100.0",
                "low": "49900.0",
                "close": "50050.0",
                "volume": "123.456",
                "turnover": "6172800.0"
            }]
        }
        """
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {message}")
            return

        # Skip non-kline messages (e.g., subscription confirmations)
        if "topic" not in data or not data["topic"].startswith("kline."):
            return

        # Extract symbol from topic: "kline.1.BTCUSDT" -> "BTCUSDT"
        topic = data["topic"]
        symbol = topic.split(".")[-1]

        # Process each candle in the data array
        candle_data_list = data.get("data", [])
        for candle_data in candle_data_list:
            try:
                candle = self._parse_candle(symbol, candle_data)
                await self.on_candle(candle)
            except Exception as e:
                logger.error(f"Error parsing candle for {symbol}: {e}", exc_info=True)

    def _parse_candle(self, symbol: str, candle_data: dict) -> Candle:
        """
        Parse raw candle data into Candle object.

        Args:
            symbol: Trading symbol
            candle_data: Raw candle data from WebSocket

        Returns:
            Candle object
        """
        return Candle(
            symbol=symbol,
            timestamp=int(candle_data["start"]),  # milliseconds
            open=float(candle_data["open"]),
            high=float(candle_data["high"]),
            low=float(candle_data["low"]),
            close=float(candle_data["close"]),
            volume=float(candle_data["volume"]),
            turnover=float(candle_data["turnover"]),
        )

    async def _warmup(self) -> None:
        """
        Fetch historical candles via REST on reconnect.

        This ensures we have recent data when reconnecting after
        a disconnection.
        """
        logger.info("Warming up: fetching historical candles...")

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_historical(session, symbol) for symbol in self.symbols
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for symbol, result in zip(self.symbols, results):
                if isinstance(result, Exception):
                    logger.error(f"Error fetching historical for {symbol}: {result}")
                else:
                    logger.info(f"Fetched {len(result)} historical candles for {symbol}")
                    # Bybit REST returns candles newest-first, but callbacks expect
                    # chronological order (oldest-first) so validator state is seeded
                    # with the most recent timestamp, not the oldest
                    sorted_candles = sorted(result, key=lambda c: c.timestamp)
                    for candle in sorted_candles:
                        try:
                            await self.on_candle(candle)
                        except Exception as e:
                            logger.error(f"Error emitting historical candle: {e}")

    async def _fetch_historical(
        self, session: aiohttp.ClientSession, symbol: str
    ) -> list[Candle]:
        """
        REST API call to get last 100 candles.

        Args:
            session: aiohttp session
            symbol: Trading symbol

        Returns:
            List of historical Candle objects
        """
        url = f"{settings.bybit_rest_url}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": self.interval,
            "limit": settings.warmup_candles,
        }

        async with session.get(url, params=params) as response:
            response.raise_for_status()
            data = await response.json()

            # Parse response
            # Expected format: {"retCode": 0, "result": {"list": [[start, open, high, low, close, volume, turnover], ...]}}
            if data.get("retCode") != 0:
                raise ValueError(f"API error: {data.get('retMsg', 'Unknown error')}")

            result = data.get("result", {})
            candle_list = result.get("list", [])

            candles = []
            for candle_data in candle_list:
                try:
                    # Bybit REST API returns candles as arrays
                    candle = Candle(
                        symbol=symbol,
                        timestamp=int(candle_data[0]),  # milliseconds
                        open=float(candle_data[1]),
                        high=float(candle_data[2]),
                        low=float(candle_data[3]),
                        close=float(candle_data[4]),
                        volume=float(candle_data[5]),
                        turnover=float(candle_data[6]),
                    )
                    candles.append(candle)
                except Exception as e:
                    logger.error(f"Error parsing historical candle: {e}")

            return candles

    def stop(self) -> None:
        """Signal to stop the client."""
        logger.info("Stopping WebSocket client...")
        self._running = False
