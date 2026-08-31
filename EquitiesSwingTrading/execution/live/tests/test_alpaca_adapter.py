"""
Tests for AlpacaAdapter.

Tests cover:
- Connection management
- Account retrieval
- Position management
- Order submission (all types)
- Bracket orders
- Error handling
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

from alpaca.common.exceptions import APIError

from execution.live.alpaca_adapter import AlpacaAdapter
from execution.live.broker import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    BrokerPosition,
    AccountInfo,
    BracketOrderRequest,
    BrokerConnectionError,
    OrderRejectedError,
    InsufficientFundsError,
    PositionNotFoundError,
)
from execution.live.tests.conftest import (
    MockAlpacaAccount,
    MockAlpacaPosition,
    MockAlpacaOrder,
)


class TestAlpacaAdapterInit:
    """Test AlpacaAdapter initialization."""

    def test_init_with_credentials(self):
        """Should initialize with provided credentials."""
        adapter = AlpacaAdapter(
            api_key="test-key",
            secret_key="test-secret",
            paper=True,
        )

        assert adapter.api_key == "test-key"
        assert adapter.secret_key == "test-secret"
        assert adapter.paper is True
        assert adapter._client is None
        assert adapter._connected is False

    def test_init_from_env(self):
        """Should read credentials from environment."""
        with patch.dict("os.environ", {
            "ALPACA_API_KEY": "env-key",
            "ALPACA_SECRET_KEY": "env-secret",
        }):
            adapter = AlpacaAdapter()
            assert adapter.api_key == "env-key"
            assert adapter.secret_key == "env-secret"

    def test_init_paper_default(self):
        """Should default to paper trading."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        assert adapter.paper is True


class TestAlpacaAdapterConnection:
    """Test connection management."""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_trading_client):
        """Should connect successfully."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            result = await adapter.connect()

        assert result is True
        assert adapter._connected is True
        assert adapter._client is not None

    @pytest.mark.asyncio
    async def test_connect_inactive_account(self, mock_trading_client):
        """Should raise error for inactive account."""
        mock_trading_client.get_account.return_value = MockAlpacaAccount(
            status="INACTIVE"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            with pytest.raises(BrokerConnectionError) as exc_info:
                await adapter.connect()

        assert "INACTIVE" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_missing_credentials(self):
        """Should raise error for missing credentials."""
        adapter = AlpacaAdapter()
        adapter.api_key = None

        with pytest.raises(BrokerConnectionError) as exc_info:
            await adapter.connect()

        assert "Missing API credentials" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connect_api_error(self):
        """Should raise error on API failure."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            side_effect=APIError("Invalid credentials")
        ):
            with pytest.raises(BrokerConnectionError):
                await adapter.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_trading_client):
        """Should disconnect cleanly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            await adapter.disconnect()

        assert adapter._client is None
        assert adapter._connected is False

    @pytest.mark.asyncio
    async def test_is_connected(self, mock_trading_client):
        """Should check connection status."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        # Not connected initially
        assert await adapter.is_connected() is False

        # Connected after connect()
        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            assert await adapter.is_connected() is True


class TestAlpacaAdapterAccount:
    """Test account operations."""

    @pytest.mark.asyncio
    async def test_get_account(self, mock_trading_client, mock_alpaca_account):
        """Should get account info."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            account = await adapter.get_account()

        assert isinstance(account, AccountInfo)
        assert account.equity == Decimal("100000.00")
        assert account.cash == Decimal("50000.00")
        assert account.buying_power == Decimal("200000.00")
        assert account.day_trade_count == 0
        assert account.pattern_day_trader is False

    @pytest.mark.asyncio
    async def test_get_account_not_connected(self):
        """Should raise error if not connected."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with pytest.raises(BrokerConnectionError):
            await adapter.get_account()


class TestAlpacaAdapterPositions:
    """Test position operations."""

    @pytest.mark.asyncio
    async def test_get_positions(self, mock_trading_client, mock_alpaca_position):
        """Should get all positions."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            positions = await adapter.get_positions()

        assert len(positions) == 1
        assert isinstance(positions[0], BrokerPosition)
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("100")
        assert positions[0].avg_entry_price == Decimal("150.00")
        assert positions[0].unrealized_pnl == Decimal("500.00")

    @pytest.mark.asyncio
    async def test_get_position(self, mock_trading_client, mock_alpaca_position):
        """Should get specific position."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            position = await adapter.get_position("AAPL")

        assert position is not None
        assert position.symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_get_position_not_found(self, mock_trading_client):
        """Should return None for non-existent position."""
        mock_trading_client.get_open_position.side_effect = APIError(
            "position does not exist"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            position = await adapter.get_position("XYZ")

        assert position is None


class TestAlpacaAdapterOrders:
    """Test order operations."""

    @pytest.mark.asyncio
    async def test_submit_market_order(
        self, mock_trading_client, sample_order, mock_alpaca_order
    ):
        """Should submit market order."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.submit_order(sample_order)

        assert isinstance(result, Order)
        assert result.order_id == "order-123"
        assert result.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_submit_limit_order(
        self, mock_trading_client, sample_limit_order, mock_alpaca_order
    ):
        """Should submit limit order."""
        mock_alpaca_order.order_type = "limit"
        mock_alpaca_order.limit_price = "150.00"
        mock_alpaca_order.status = "new"

        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.submit_order(sample_limit_order)

        assert result.order_type == OrderType.LIMIT
        mock_trading_client.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_stop_order(
        self, mock_trading_client, sample_stop_order, mock_alpaca_order
    ):
        """Should submit stop order."""
        mock_alpaca_order.order_type = "stop"
        mock_alpaca_order.stop_price = "145.00"
        mock_alpaca_order.side = "sell"

        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.submit_order(sample_stop_order)

        assert result.side == OrderSide.SELL
        mock_trading_client.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_submit_order_insufficient_funds(self, mock_trading_client, sample_order):
        """Should raise InsufficientFundsError."""
        mock_trading_client.submit_order.side_effect = APIError(
            "insufficient buying power"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            with pytest.raises(InsufficientFundsError):
                await adapter.submit_order(sample_order)

    @pytest.mark.asyncio
    async def test_submit_order_rejected(self, mock_trading_client, sample_order):
        """Should raise OrderRejectedError."""
        mock_trading_client.submit_order.side_effect = APIError(
            "order rejected"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            with pytest.raises(OrderRejectedError):
                await adapter.submit_order(sample_order)

    @pytest.mark.asyncio
    async def test_submit_bracket_order(
        self, mock_trading_client, sample_bracket_request, mock_alpaca_order
    ):
        """Should submit bracket order."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.submit_bracket_order(sample_bracket_request)

        assert isinstance(result, Order)
        mock_trading_client.submit_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_order(self, mock_trading_client):
        """Should cancel order."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.cancel_order("order-123")

        assert result is True
        mock_trading_client.cancel_order_by_id.assert_called_once_with("order-123")

    @pytest.mark.asyncio
    async def test_cancel_order_not_cancelable(self, mock_trading_client):
        """Should return False if order not cancelable."""
        mock_trading_client.cancel_order_by_id.side_effect = APIError(
            "order is not cancelable"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.cancel_order("order-123")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_order(self, mock_trading_client, mock_alpaca_order):
        """Should get order by ID."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.get_order("order-123")

        assert result is not None
        assert result.order_id == "order-123"

    @pytest.mark.asyncio
    async def test_get_order_not_found(self, mock_trading_client):
        """Should return None for non-existent order."""
        mock_trading_client.get_order_by_id.side_effect = APIError(
            "order not found"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.get_order("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_open_orders(self, mock_trading_client, mock_alpaca_order):
        """Should get all open orders."""
        mock_alpaca_order.status = "new"
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            orders = await adapter.get_open_orders()

        assert len(orders) == 1

    @pytest.mark.asyncio
    async def test_get_open_orders_filtered(self, mock_trading_client):
        """Should filter open orders by symbol."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            await adapter.get_open_orders(symbol="AAPL")

        # Verify GetOrdersRequest was called with symbol filter
        mock_trading_client.get_orders.assert_called_once()


class TestAlpacaAdapterPositionManagement:
    """Test position management operations."""

    @pytest.mark.asyncio
    async def test_close_position(self, mock_trading_client, mock_alpaca_order):
        """Should close position."""
        mock_alpaca_order.side = "sell"
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.close_position("AAPL")

        assert isinstance(result, Order)
        mock_trading_client.close_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_partial(self, mock_trading_client, mock_alpaca_order):
        """Should close partial position."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            await adapter.close_position("AAPL", quantity=Decimal("50"))

        mock_trading_client.close_position.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, mock_trading_client):
        """Should raise PositionNotFoundError."""
        mock_trading_client.close_position.side_effect = APIError(
            "position does not exist"
        )
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            with pytest.raises(PositionNotFoundError):
                await adapter.close_position("XYZ")

    @pytest.mark.asyncio
    async def test_close_all_positions(self, mock_trading_client):
        """Should close all positions."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        with patch(
            "execution.live.alpaca_adapter.TradingClient",
            return_value=mock_trading_client
        ):
            await adapter.connect()
            result = await adapter.close_all_positions()

        assert isinstance(result, list)
        mock_trading_client.close_all_positions.assert_called_once_with(
            cancel_orders=True
        )


class TestAlpacaAdapterConversions:
    """Test data conversion helpers."""

    def test_convert_order_market(self):
        """Should convert market order correctly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        mock_order = MockAlpacaOrder(
            order_type="market",
            side="buy",
            status="filled",
        )

        result = adapter._convert_order(mock_order)

        assert result.order_type == OrderType.MARKET
        assert result.side == OrderSide.BUY
        assert result.status == OrderStatus.FILLED

    def test_convert_order_limit(self):
        """Should convert limit order correctly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        mock_order = MockAlpacaOrder(
            order_type="limit",
            limit_price="150.00",
            status="new",
        )

        result = adapter._convert_order(mock_order)

        assert result.order_type == OrderType.LIMIT
        assert result.limit_price == Decimal("150.00")
        assert result.status == OrderStatus.NEW

    def test_convert_order_stop_limit(self):
        """Should convert stop-limit order correctly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        mock_order = MockAlpacaOrder(
            order_type="stop_limit",
            stop_price="145.00",
            limit_price="144.50",
            status="accepted",
        )

        result = adapter._convert_order(mock_order)

        assert result.order_type == OrderType.STOP_LIMIT
        assert result.stop_price == Decimal("145.00")
        assert result.limit_price == Decimal("144.50")

    def test_convert_position(self):
        """Should convert position correctly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        mock_pos = MockAlpacaPosition()

        result = adapter._convert_position(mock_pos)

        assert result.symbol == "AAPL"
        assert result.quantity == Decimal("100")
        assert result.avg_entry_price == Decimal("150.00")
        assert result.current_price == Decimal("155.00")
        assert result.unrealized_pnl == Decimal("500.00")
        assert result.side == "long"

    def test_convert_position_short(self):
        """Should identify short position correctly."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        mock_pos = MockAlpacaPosition(qty="-100")

        result = adapter._convert_position(mock_pos)

        assert result.quantity == Decimal("-100")
        assert result.side == "short"


class TestAlpacaAdapterOrderBuilding:
    """Test order request building."""

    def test_build_market_order_request(self, sample_order):
        """Should build market order request."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        request = adapter._build_order_request(sample_order)

        assert request.symbol == "AAPL"
        assert float(request.qty) == 10.0

    def test_build_limit_order_request(self, sample_limit_order):
        """Should build limit order request."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        request = adapter._build_order_request(sample_limit_order)

        assert request.symbol == "AAPL"
        assert float(request.limit_price) == 150.0

    def test_build_stop_order_request(self, sample_stop_order):
        """Should build stop order request."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")

        request = adapter._build_order_request(sample_stop_order)

        assert request.symbol == "AAPL"
        assert float(request.stop_price) == 145.0

    def test_build_stop_limit_order_request(self):
        """Should build stop-limit order request."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        order = Order(
            order_id="",
            symbol="AAPL",
            side=OrderSide.SELL,
            order_type=OrderType.STOP_LIMIT,
            quantity=Decimal("10"),
            stop_price=Decimal("145.00"),
            limit_price=Decimal("144.50"),
        )

        request = adapter._build_order_request(order)

        assert float(request.stop_price) == 145.0
        assert float(request.limit_price) == 144.5

    def test_build_limit_order_missing_price(self, sample_order):
        """Should raise error for limit order without price."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        sample_order.order_type = OrderType.LIMIT
        sample_order.limit_price = None

        with pytest.raises(ValueError) as exc_info:
            adapter._build_order_request(sample_order)

        assert "limit_price" in str(exc_info.value)

    def test_build_stop_order_missing_price(self, sample_order):
        """Should raise error for stop order without price."""
        adapter = AlpacaAdapter(api_key="k", secret_key="s")
        sample_order.order_type = OrderType.STOP
        sample_order.stop_price = None

        with pytest.raises(ValueError) as exc_info:
            adapter._build_order_request(sample_order)

        assert "stop_price" in str(exc_info.value)
