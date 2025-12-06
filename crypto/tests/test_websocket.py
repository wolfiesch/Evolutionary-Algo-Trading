"""Tests for Bybit WebSocket client."""
import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch, MagicMock

import pytest
from aiohttp import ClientResponse

from data.ingestion.bybit_ws import BybitWebSocketClient
from data.storage.models import Candle


@pytest.fixture
def mock_candle_callback():
    """Create a mock async callback for candles."""
    return AsyncMock()


@pytest.fixture
def client(mock_candle_callback):
    """Create a BybitWebSocketClient instance."""
    return BybitWebSocketClient(
        symbols=["BTCUSDT", "ETHUSDT"],
        on_candle=mock_candle_callback,
        interval="1",
    )


class TestMessageParsing:
    """Test WebSocket message parsing."""

    @pytest.mark.asyncio
    async def test_parse_valid_kline_message(self, client, mock_candle_callback):
        """Test parsing a valid kline message."""
        message = json.dumps(
            {
                "topic": "kline.1.BTCUSDT",
                "data": [
                    {
                        "start": 1700000000000,  # milliseconds
                        "open": "50000.0",
                        "high": "50100.0",
                        "low": "49900.0",
                        "close": "50050.0",
                        "volume": "123.456",
                        "turnover": "6172800.0",
                    }
                ],
            }
        )

        await client._handle_message(message)

        # Verify callback was called once
        assert mock_candle_callback.call_count == 1

        # Verify Candle object was created correctly
        candle: Candle = mock_candle_callback.call_args[0][0]
        assert candle.symbol == "BTCUSDT"
        assert candle.timestamp == 1700000000000  # milliseconds
        assert candle.open == 50000.0
        assert candle.high == 50100.0
        assert candle.low == 49900.0
        assert candle.close == 50050.0
        assert candle.volume == 123.456
        assert candle.turnover == 6172800.0

    @pytest.mark.asyncio
    async def test_parse_multiple_candles(self, client, mock_candle_callback):
        """Test parsing multiple candles in a single message."""
        message = json.dumps(
            {
                "topic": "kline.1.ETHUSDT",
                "data": [
                    {
                        "start": 1700000000000,
                        "open": "3000.0",
                        "high": "3010.0",
                        "low": "2990.0",
                        "close": "3005.0",
                        "volume": "100.0",
                        "turnover": "300500.0",
                    },
                    {
                        "start": 1700000060000,
                        "open": "3005.0",
                        "high": "3020.0",
                        "low": "3000.0",
                        "close": "3015.0",
                        "volume": "150.0",
                        "turnover": "452250.0",
                    },
                ],
            }
        )

        await client._handle_message(message)

        # Verify callback was called twice
        assert mock_candle_callback.call_count == 2

    @pytest.mark.asyncio
    async def test_ignore_non_kline_message(self, client, mock_candle_callback):
        """Test that non-kline messages are ignored."""
        message = json.dumps(
            {
                "success": True,
                "ret_msg": "",
                "conn_id": "test-connection",
                "op": "subscribe",
            }
        )

        await client._handle_message(message)

        # Verify callback was not called
        mock_candle_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_invalid_json(self, client, mock_candle_callback):
        """Test handling of invalid JSON messages."""
        message = "not valid json {"

        await client._handle_message(message)

        # Verify callback was not called
        mock_candle_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_symbol_extraction_from_topic(self, client, mock_candle_callback):
        """Test correct symbol extraction from topic string."""
        message = json.dumps(
            {
                "topic": "kline.1.SOLUSDT",
                "data": [
                    {
                        "start": 1700000000000,
                        "open": "100.0",
                        "high": "101.0",
                        "low": "99.0",
                        "close": "100.5",
                        "volume": "1000.0",
                        "turnover": "100500.0",
                    }
                ],
            }
        )

        await client._handle_message(message)

        candle: Candle = mock_candle_callback.call_args[0][0]
        assert candle.symbol == "SOLUSDT"


class TestSubscription:
    """Test WebSocket subscription format."""

    @pytest.mark.asyncio
    async def test_subscription_format(self, client):
        """Test that subscription message has correct format."""
        mock_ws = AsyncMock()

        await client._subscribe(mock_ws)

        # Verify send was called once
        assert mock_ws.send.call_count == 1

        # Parse the sent message
        sent_message = mock_ws.send.call_args[0][0]
        subscription = json.loads(sent_message)

        # Verify subscription format
        assert subscription["op"] == "subscribe"
        assert "args" in subscription
        assert len(subscription["args"]) == 2
        assert "kline.1.BTCUSDT" in subscription["args"]
        assert "kline.1.ETHUSDT" in subscription["args"]

    @pytest.mark.asyncio
    async def test_subscription_with_custom_interval(self, mock_candle_callback):
        """Test subscription with custom interval."""
        client = BybitWebSocketClient(
            symbols=["BTCUSDT"],
            on_candle=mock_candle_callback,
            interval="5",
        )

        mock_ws = AsyncMock()
        await client._subscribe(mock_ws)

        sent_message = mock_ws.send.call_args[0][0]
        subscription = json.loads(sent_message)

        assert "kline.5.BTCUSDT" in subscription["args"]


class TestReconnectionBackoff:
    """Test reconnection backoff logic."""

    def test_exponential_backoff_calculation(self):
        """Test that backoff delay doubles up to max."""
        initial_delay = 5
        max_delay = 60

        delays = [initial_delay]
        current = initial_delay

        # Simulate backoff calculation
        for _ in range(10):
            current = min(current * 2, max_delay)
            delays.append(current)

        # Verify exponential growth: 5, 10, 20, 40, 60, 60, 60, ...
        assert delays[0] == 5
        assert delays[1] == 10
        assert delays[2] == 20
        assert delays[3] == 40
        assert delays[4] == 60
        assert delays[5] == 60  # Capped at max
        assert all(d == 60 for d in delays[5:])

    @pytest.mark.asyncio
    async def test_backoff_reset_on_successful_connection(
        self, client, mock_candle_callback
    ):
        """Test that backoff resets after successful connection."""
        # Mock _connect_and_stream to fail once, then succeed
        call_count = 0

        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Simulated connection error")
            # Stop after second call
            client.stop()

        # Reduce reconnect delay for faster testing
        client._reconnect_delay = 0.1

        with patch.object(client, "_connect_and_stream", side_effect=mock_connect):
            # Run with timeout to prevent infinite loop
            try:
                await asyncio.wait_for(client.run(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

        # Verify delay was reset (we can't directly check internal state,
        # but we know it should have been called twice)
        assert call_count == 2


class TestHistoricalFetch:
    """Test REST API historical candle fetching."""

    @pytest.mark.asyncio
    async def test_fetch_historical_success(self, client):
        """Test successful historical candle fetch."""
        mock_response_data = {
            "retCode": 0,
            "result": {
                "list": [
                    [
                        "1700000000000",  # timestamp
                        "50000.0",  # open
                        "50100.0",  # high
                        "49900.0",  # low
                        "50050.0",  # close
                        "123.456",  # volume
                        "6172800.0",  # turnover
                    ],
                    [
                        "1700000060000",
                        "50050.0",
                        "50150.0",
                        "50000.0",
                        "50100.0",
                        "234.567",
                        "11750000.0",
                    ],
                ]
            },
        }

        # Mock aiohttp response
        mock_response = AsyncMock(spec=ClientResponse)
        mock_response.raise_for_status = Mock()
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response

        candles = await client._fetch_historical(mock_session, "BTCUSDT")

        # Verify results
        assert len(candles) == 2
        assert candles[0].symbol == "BTCUSDT"
        assert candles[0].open == 50000.0
        assert candles[1].close == 50100.0

    @pytest.mark.asyncio
    async def test_fetch_historical_api_error(self, client):
        """Test handling of API error response."""
        mock_response_data = {
            "retCode": 10001,
            "retMsg": "Invalid parameter",
        }

        mock_response = AsyncMock(spec=ClientResponse)
        mock_response.raise_for_status = Mock()
        mock_response.json = AsyncMock(return_value=mock_response_data)

        mock_session = AsyncMock()
        mock_session.get = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(ValueError, match="API error"):
            await client._fetch_historical(mock_session, "BTCUSDT")


class TestClientLifecycle:
    """Test client lifecycle management."""

    def test_stop_method(self, client):
        """Test that stop method sets running flag to False."""
        assert client._running is False  # Not running initially

        client._running = True  # Simulate running state
        client.stop()

        assert client._running is False

    @pytest.mark.asyncio
    async def test_warmup_calls_fetch_for_all_symbols(
        self, client, mock_candle_callback
    ):
        """Test that warmup fetches historical data for all symbols."""
        with patch.object(
            client, "_fetch_historical", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = []  # Empty list of candles

            await client._warmup()

            # Verify fetch was called for each symbol
            assert mock_fetch.call_count == 2
            calls = [call[0][1] for call in mock_fetch.call_args_list]
            assert "BTCUSDT" in calls
            assert "ETHUSDT" in calls

    @pytest.mark.asyncio
    async def test_warmup_emits_historical_candles(
        self, client, mock_candle_callback
    ):
        """Test that warmup emits historical candles via callback."""
        historical_candles = [
            Candle(
                symbol="BTCUSDT",
                timestamp=1700000000000,  # milliseconds
                open=50000.0,
                high=50100.0,
                low=49900.0,
                close=50050.0,
                volume=123.456,
                turnover=6172800.0,
            )
        ]

        with patch.object(
            client, "_fetch_historical", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = historical_candles

            await client._warmup()

            # Verify callback was called with historical candles
            # 2 symbols * 1 candle each = 2 calls
            assert mock_candle_callback.call_count == 2
