"""
Alpaca broker adapter for live trading.

Implements BrokerAdapter interface using Alpaca Markets API.
Supports both paper and live trading environments.
"""
import logging
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    GetOrdersRequest,
    ClosePositionRequest,
)
from alpaca.trading.enums import (
    OrderSide as AlpacaOrderSide,
    OrderType as AlpacaOrderType,
    OrderStatus as AlpacaOrderStatus,
    TimeInForce as AlpacaTimeInForce,
    QueryOrderStatus,
)
from alpaca.common.exceptions import APIError

from .broker import (
    BrokerAdapter,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    BrokerPosition,
    AccountInfo,
    BracketOrderRequest,
    BrokerError,
    BrokerConnectionError,
    OrderRejectedError,
    InsufficientFundsError,
    PositionNotFoundError,
)

logger = logging.getLogger(__name__)


class AlpacaAdapter(BrokerAdapter):
    """
    Alpaca Markets broker implementation.

    Features:
    - Supports both paper and live trading
    - All order types: market, limit, stop, stop-limit, bracket
    - Fractional shares supported
    - Real-time position and account data
    - WebSocket streaming (via separate data client)

    Example:
        adapter = AlpacaAdapter(paper=True)
        await adapter.connect()

        account = await adapter.get_account()
        print(f"Buying power: ${account.buying_power}")

        order = Order(
            order_id="",
            symbol="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("10"),
        )
        submitted = await adapter.submit_order(order)
    """

    # Mapping from our enums to Alpaca enums
    _SIDE_MAP: Dict[OrderSide, AlpacaOrderSide] = {
        OrderSide.BUY: AlpacaOrderSide.BUY,
        OrderSide.SELL: AlpacaOrderSide.SELL,
    }

    _ORDER_TYPE_MAP: Dict[OrderType, AlpacaOrderType] = {
        OrderType.MARKET: AlpacaOrderType.MARKET,
        OrderType.LIMIT: AlpacaOrderType.LIMIT,
        OrderType.STOP: AlpacaOrderType.STOP,
        OrderType.STOP_LIMIT: AlpacaOrderType.STOP_LIMIT,
    }

    _TIF_MAP: Dict[TimeInForce, AlpacaTimeInForce] = {
        TimeInForce.DAY: AlpacaTimeInForce.DAY,
        TimeInForce.GTC: AlpacaTimeInForce.GTC,
        TimeInForce.IOC: AlpacaTimeInForce.IOC,
        TimeInForce.FOK: AlpacaTimeInForce.FOK,
        TimeInForce.OPG: AlpacaTimeInForce.OPG,
        TimeInForce.CLS: AlpacaTimeInForce.CLS,
    }

    # Reverse mapping for status conversion
    _STATUS_MAP: Dict[str, OrderStatus] = {
        "new": OrderStatus.NEW,
        "accepted": OrderStatus.ACCEPTED,
        "pending_new": OrderStatus.PENDING,
        "accepted_for_bidding": OrderStatus.ACCEPTED,
        "stopped": OrderStatus.ACCEPTED,
        "rejected": OrderStatus.REJECTED,
        "suspended": OrderStatus.PENDING,
        "calculated": OrderStatus.PENDING,
        "filled": OrderStatus.FILLED,
        "partially_filled": OrderStatus.PARTIALLY_FILLED,
        "canceled": OrderStatus.CANCELLED,
        "expired": OrderStatus.EXPIRED,
        "replaced": OrderStatus.CANCELLED,
        "pending_cancel": OrderStatus.PENDING,
        "pending_replace": OrderStatus.PENDING,
        "done_for_day": OrderStatus.CANCELLED,
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
    ):
        """
        Initialize Alpaca adapter.

        Args:
            api_key: Alpaca API key (or use ALPACA_API_KEY env var)
            secret_key: Alpaca secret key (or use ALPACA_SECRET_KEY env var)
            paper: Use paper trading environment (default True for safety)
        """
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        self.paper = paper
        self._client: Optional[TradingClient] = None
        self._connected = False

        if not self.api_key or not self.secret_key:
            logger.warning(
                "Alpaca API credentials not provided. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables."
            )

    async def connect(self) -> bool:
        """
        Establish connection to Alpaca.

        Creates TradingClient and verifies account access.

        Returns:
            True if connection successful.

        Raises:
            BrokerConnectionError: If connection fails.
        """
        if not self.api_key or not self.secret_key:
            raise BrokerConnectionError(
                "Missing API credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY."
            )

        try:
            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )

            # Verify connection by fetching account
            account = self._client.get_account()

            if account.status != "ACTIVE":
                raise BrokerConnectionError(
                    f"Account status is {account.status}, expected ACTIVE"
                )

            self._connected = True
            logger.info(
                f"Connected to Alpaca {'paper' if self.paper else 'LIVE'} trading. "
                f"Account: {account.account_number}"
            )
            return True

        except APIError as e:
            self._connected = False
            raise BrokerConnectionError(f"Alpaca API error: {e}") from e
        except Exception as e:
            self._connected = False
            raise BrokerConnectionError(f"Connection failed: {e}") from e

    async def disconnect(self) -> None:
        """Close connection to Alpaca."""
        self._client = None
        self._connected = False
        logger.info("Disconnected from Alpaca")

    async def is_connected(self) -> bool:
        """Check if broker connection is active."""
        if not self._client or not self._connected:
            return False

        try:
            # Lightweight check - get account status
            account = self._client.get_account()
            return account.status == "ACTIVE"
        except Exception:
            self._connected = False
            return False

    # === Account Methods ===

    async def get_account(self) -> AccountInfo:
        """
        Get current account information.

        Returns:
            AccountInfo with equity, cash, buying power, etc.
        """
        self._ensure_connected()

        try:
            account = self._client.get_account()

            return AccountInfo(
                equity=Decimal(str(account.equity)),
                cash=Decimal(str(account.cash)),
                buying_power=Decimal(str(account.buying_power)),
                portfolio_value=Decimal(str(account.portfolio_value)),
                day_trade_count=int(account.daytrade_count) if account.daytrade_count else 0,
                pattern_day_trader=account.pattern_day_trader,
                account_blocked=account.account_blocked,
                trading_blocked=account.trading_blocked,
                last_updated=datetime.now(timezone.utc),
            )
        except APIError as e:
            raise BrokerError(f"Failed to get account: {e}") from e

    # === Position Methods ===

    async def get_positions(self) -> List[BrokerPosition]:
        """
        Get all open positions.

        Returns:
            List of BrokerPosition objects.
        """
        self._ensure_connected()

        try:
            positions = self._client.get_all_positions()
            return [self._convert_position(pos) for pos in positions]
        except APIError as e:
            raise BrokerError(f"Failed to get positions: {e}") from e

    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for specific symbol.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")

        Returns:
            BrokerPosition if position exists, None otherwise.
        """
        self._ensure_connected()

        try:
            position = self._client.get_open_position(symbol)
            return self._convert_position(position)
        except APIError as e:
            if "position does not exist" in str(e).lower():
                return None
            raise BrokerError(f"Failed to get position for {symbol}: {e}") from e

    # === Order Methods ===

    async def submit_order(self, order: Order) -> Order:
        """
        Submit order to Alpaca.

        Args:
            order: Order to submit (market, limit, stop, stop-limit)

        Returns:
            Order with Alpaca-assigned ID and status.

        Raises:
            OrderRejectedError: If broker rejects order.
            InsufficientFundsError: If not enough buying power.
        """
        self._ensure_connected()

        try:
            request = self._build_order_request(order)
            alpaca_order = self._client.submit_order(request)
            return self._convert_order(alpaca_order)

        except APIError as e:
            error_msg = str(e).lower()

            if "insufficient" in error_msg or "buying power" in error_msg:
                raise InsufficientFundsError(f"Insufficient funds: {e}") from e

            order.status = OrderStatus.REJECTED
            raise OrderRejectedError(f"Order rejected: {e}", order=order) from e

    async def submit_bracket_order(self, request: BracketOrderRequest) -> Order:
        """
        Submit bracket order (entry + stop-loss + optional take-profit).

        Alpaca supports bracket orders natively via order class.

        Args:
            request: BracketOrderRequest with all legs

        Returns:
            Parent order with legs attached.
        """
        self._ensure_connected()

        try:
            # Build base order request
            if request.entry_type == OrderType.MARKET:
                base_request = MarketOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._SIDE_MAP[request.side],
                    time_in_force=self._TIF_MAP[request.time_in_force],
                    order_class="bracket",
                    stop_loss={"stop_price": float(request.stop_loss_price)},
                )
            else:
                base_request = LimitOrderRequest(
                    symbol=request.symbol,
                    qty=float(request.quantity),
                    side=self._SIDE_MAP[request.side],
                    time_in_force=self._TIF_MAP[request.time_in_force],
                    limit_price=float(request.entry_limit_price),
                    order_class="bracket",
                    stop_loss={"stop_price": float(request.stop_loss_price)},
                )

            # Add take profit if specified
            if request.take_profit_price:
                base_request.take_profit = {
                    "limit_price": float(request.take_profit_price)
                }

            alpaca_order = self._client.submit_order(base_request)
            return self._convert_order(alpaca_order)

        except APIError as e:
            error_msg = str(e).lower()

            if "insufficient" in error_msg:
                raise InsufficientFundsError(f"Insufficient funds: {e}") from e

            raise OrderRejectedError(f"Bracket order rejected: {e}") from e

    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.

        Args:
            order_id: Alpaca order ID to cancel

        Returns:
            True if cancellation request accepted.
        """
        self._ensure_connected()

        try:
            self._client.cancel_order_by_id(order_id)
            logger.info(f"Cancel request submitted for order {order_id}")
            return True
        except APIError as e:
            if "order is not cancelable" in str(e).lower():
                logger.warning(f"Order {order_id} is not cancelable: {e}")
                return False
            raise BrokerError(f"Failed to cancel order {order_id}: {e}") from e

    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order status by ID.

        Args:
            order_id: Alpaca order ID

        Returns:
            Order with current status, None if not found.
        """
        self._ensure_connected()

        try:
            alpaca_order = self._client.get_order_by_id(order_id)
            return self._convert_order(alpaca_order)
        except APIError as e:
            if "order not found" in str(e).lower():
                return None
            raise BrokerError(f"Failed to get order {order_id}: {e}") from e

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Optional filter by symbol

        Returns:
            List of open Order objects.
        """
        self._ensure_connected()

        try:
            request = GetOrdersRequest(
                status=QueryOrderStatus.OPEN,
                symbols=[symbol] if symbol else None,
            )
            orders = self._client.get_orders(request)
            return [self._convert_order(o) for o in orders]
        except APIError as e:
            raise BrokerError(f"Failed to get open orders: {e}") from e

    # === Position Management ===

    async def close_position(
        self,
        symbol: str,
        quantity: Optional[Decimal] = None
    ) -> Order:
        """
        Close position (market order).

        Args:
            symbol: Symbol to close
            quantity: Optional partial close quantity (None = full close)

        Returns:
            Exit order.
        """
        self._ensure_connected()

        try:
            if quantity:
                # Partial close by quantity
                request = ClosePositionRequest(qty=str(quantity))
                alpaca_order = self._client.close_position(symbol, request)
            else:
                # Full close - use percentage=100
                request = ClosePositionRequest(percentage="100")
                alpaca_order = self._client.close_position(symbol, request)

            logger.info(f"Position close submitted for {symbol}")
            return self._convert_order(alpaca_order)

        except APIError as e:
            if "position does not exist" in str(e).lower():
                raise PositionNotFoundError(f"No position for {symbol}") from e
            raise BrokerError(f"Failed to close position {symbol}: {e}") from e

    async def close_all_positions(self) -> List[Order]:
        """
        Close all positions (emergency).

        Used by kill switches for immediate position liquidation.

        Returns:
            List of exit orders submitted.
        """
        self._ensure_connected()

        try:
            # Alpaca has a built-in close all positions endpoint
            responses = self._client.close_all_positions(cancel_orders=True)

            orders = []
            for response in responses:
                if hasattr(response, 'body') and response.body:
                    orders.append(self._convert_order(response.body))

            logger.warning(f"Emergency close all: {len(orders)} positions closed")
            return orders

        except APIError as e:
            raise BrokerError(f"Failed to close all positions: {e}") from e

    # === Market Data (Optional) ===

    async def get_last_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get last traded price for symbol.

        Note: For real-time data, use Alpaca's data client separately.
        This uses the trading client's limited snapshot capability.
        """
        # Trading client doesn't have direct quote access
        # Would need to use alpaca.data.StockHistoricalDataClient
        # For now, return None and let caller use external data source
        return None

    async def get_last_quote(
        self,
        symbol: str
    ) -> Optional[tuple[Decimal, Decimal]]:
        """
        Get bid/ask quote for symbol.

        Returns:
            Tuple of (bid, ask) or None if not available.
        """
        # Same as above - would need data client
        return None

    # === Private Helper Methods ===

    def _ensure_connected(self) -> None:
        """Raise error if not connected."""
        if not self._client or not self._connected:
            raise BrokerConnectionError("Not connected to Alpaca")

    def _build_order_request(self, order: Order) -> Any:
        """Build Alpaca order request from our Order dataclass."""
        side = self._SIDE_MAP[order.side]
        tif = self._TIF_MAP[order.time_in_force]

        if order.order_type == OrderType.MARKET:
            return MarketOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=tif,
                client_order_id=order.client_order_id,
            )

        elif order.order_type == OrderType.LIMIT:
            if not order.limit_price:
                raise ValueError("Limit order requires limit_price")
            return LimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=tif,
                limit_price=float(order.limit_price),
                client_order_id=order.client_order_id,
            )

        elif order.order_type == OrderType.STOP:
            if not order.stop_price:
                raise ValueError("Stop order requires stop_price")
            return StopOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=tif,
                stop_price=float(order.stop_price),
                client_order_id=order.client_order_id,
            )

        elif order.order_type == OrderType.STOP_LIMIT:
            if not order.stop_price or not order.limit_price:
                raise ValueError("Stop-limit order requires stop_price and limit_price")
            return StopLimitOrderRequest(
                symbol=order.symbol,
                qty=float(order.quantity),
                side=side,
                time_in_force=tif,
                stop_price=float(order.stop_price),
                limit_price=float(order.limit_price),
                client_order_id=order.client_order_id,
            )

        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

    def _convert_order(self, alpaca_order: Any) -> Order:
        """Convert Alpaca order to our Order dataclass."""
        # Determine order type
        order_type_str = str(alpaca_order.order_type).lower()
        if "market" in order_type_str:
            order_type = OrderType.MARKET
        elif "stop_limit" in order_type_str:
            order_type = OrderType.STOP_LIMIT
        elif "stop" in order_type_str:
            order_type = OrderType.STOP
        elif "limit" in order_type_str:
            order_type = OrderType.LIMIT
        else:
            order_type = OrderType.MARKET

        # Determine side
        side_str = str(alpaca_order.side).lower()
        side = OrderSide.BUY if "buy" in side_str else OrderSide.SELL

        # Determine status
        status_str = str(alpaca_order.status).lower()
        status = self._STATUS_MAP.get(status_str, OrderStatus.PENDING)

        # Determine time in force
        tif_str = str(alpaca_order.time_in_force).lower()
        tif_map = {v.value: k for k, v in self._TIF_MAP.items()}
        time_in_force = tif_map.get(tif_str, TimeInForce.DAY)

        return Order(
            order_id=str(alpaca_order.id),
            symbol=alpaca_order.symbol,
            side=side,
            order_type=order_type,
            quantity=Decimal(str(alpaca_order.qty)) if alpaca_order.qty else Decimal("0"),
            limit_price=Decimal(str(alpaca_order.limit_price)) if alpaca_order.limit_price else None,
            stop_price=Decimal(str(alpaca_order.stop_price)) if alpaca_order.stop_price else None,
            time_in_force=time_in_force,
            status=status,
            filled_quantity=Decimal(str(alpaca_order.filled_qty)) if alpaca_order.filled_qty else Decimal("0"),
            filled_avg_price=Decimal(str(alpaca_order.filled_avg_price)) if alpaca_order.filled_avg_price else None,
            created_at=alpaca_order.created_at,
            updated_at=alpaca_order.updated_at,
            client_order_id=alpaca_order.client_order_id,
            broker_order_id=str(alpaca_order.id),
        )

    def _convert_position(self, alpaca_position: Any) -> BrokerPosition:
        """Convert Alpaca position to our BrokerPosition dataclass."""
        qty = Decimal(str(alpaca_position.qty))

        return BrokerPosition(
            symbol=alpaca_position.symbol,
            quantity=qty,
            avg_entry_price=Decimal(str(alpaca_position.avg_entry_price)),
            current_price=Decimal(str(alpaca_position.current_price)),
            market_value=Decimal(str(alpaca_position.market_value)),
            cost_basis=Decimal(str(alpaca_position.cost_basis)),
            unrealized_pnl=Decimal(str(alpaca_position.unrealized_pl)),
            unrealized_pnl_pct=float(alpaca_position.unrealized_plpc) * 100,
            side="long" if qty > 0 else "short",
        )
