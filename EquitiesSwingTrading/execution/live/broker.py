"""
Broker abstraction layer for live trading.

Provides a broker-agnostic interface for order execution, position
management, and account information.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from datetime import datetime


class OrderSide(Enum):
    """Order direction."""
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class OrderStatus(Enum):
    """Order status."""
    PENDING = "pending"
    NEW = "new"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TimeInForce(Enum):
    """Order time in force."""
    DAY = "day"              # Cancel at end of day
    GTC = "gtc"              # Good till cancelled
    IOC = "ioc"              # Immediate or cancel
    FOK = "fok"              # Fill or kill
    OPG = "opg"              # Market on open
    CLS = "cls"              # Market on close


@dataclass
class Order:
    """
    Order representation.

    Designed to be broker-agnostic while supporting all common order types
    needed for swing trading.
    """
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Optional[Decimal] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    client_order_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    parent_order_id: Optional[str] = None  # For bracket orders
    legs: List["Order"] = field(default_factory=list)  # For bracket orders

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == OrderStatus.FILLED

    @property
    def is_open(self) -> bool:
        """Check if order is still open (pending execution)."""
        return self.status in (
            OrderStatus.PENDING,
            OrderStatus.NEW,
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
        )

    @property
    def is_closed(self) -> bool:
        """Check if order is closed (won't fill anymore)."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def remaining_quantity(self) -> Decimal:
        """Quantity remaining to be filled."""
        return self.quantity - self.filled_quantity


@dataclass
class BrokerPosition:
    """
    Position from broker.

    Represents an open position with real-time P&L.
    """
    symbol: str
    quantity: Decimal  # Positive for long, negative for short
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float
    side: str = "long"  # "long" or "short"

    @property
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.quantity < 0


@dataclass
class AccountInfo:
    """
    Account summary from broker.

    Provides key metrics for position sizing and risk management.
    """
    equity: Decimal                 # Total account value
    cash: Decimal                   # Available cash
    buying_power: Decimal           # Available for new positions
    portfolio_value: Decimal        # Current portfolio value
    day_trade_count: int = 0        # Trades in last 5 days
    pattern_day_trader: bool = False
    account_blocked: bool = False
    trading_blocked: bool = False
    last_updated: Optional[datetime] = None


@dataclass
class BracketOrderRequest:
    """
    Request for bracket order (entry + stop + optional target).

    Bracket orders ensure stop-loss is always attached to entry.
    """
    symbol: str
    side: OrderSide
    quantity: Decimal
    entry_type: OrderType = OrderType.MARKET
    entry_limit_price: Optional[Decimal] = None
    stop_loss_price: Decimal = Decimal("0")
    take_profit_price: Optional[Decimal] = None
    time_in_force: TimeInForce = TimeInForce.DAY


class BrokerAdapter(ABC):
    """
    Abstract broker interface.

    Implementations should handle broker-specific details while exposing
    a consistent interface. All methods are async to support non-blocking
    I/O with broker APIs.

    Implementations:
    - AlpacaAdapter: Alpaca Trading API
    - (Future) IBKRAdapter: Interactive Brokers
    """

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to broker.

        Returns:
            True if connection successful, False otherwise.

        Raises:
            BrokerConnectionError: If connection fails with details.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to broker."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if broker connection is active."""
        pass

    # === Account Methods ===

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """
        Get current account information.

        Returns:
            AccountInfo with equity, cash, buying power, etc.
        """
        pass

    # === Position Methods ===

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """
        Get all open positions.

        Returns:
            List of BrokerPosition objects.
        """
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """
        Get position for specific symbol.

        Args:
            symbol: Ticker symbol (e.g., "AAPL")

        Returns:
            BrokerPosition if position exists, None otherwise.
        """
        pass

    # === Order Methods ===

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """
        Submit order to broker.

        Args:
            order: Order to submit (market, limit, stop, stop-limit)

        Returns:
            Order with broker-assigned ID and status.

        Raises:
            OrderRejectedError: If broker rejects order.
        """
        pass

    @abstractmethod
    async def submit_bracket_order(
        self,
        request: BracketOrderRequest
    ) -> Order:
        """
        Submit bracket order (entry + stop-loss + optional take-profit).

        Bracket orders ensure stop-loss is always active once entry fills.

        Args:
            request: BracketOrderRequest with all legs

        Returns:
            Parent order with legs attached.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel pending order.

        Args:
            order_id: Broker order ID to cancel

        Returns:
            True if cancellation request accepted.
        """
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[Order]:
        """
        Get order status by ID.

        Args:
            order_id: Broker order ID

        Returns:
            Order with current status, None if not found.
        """
        pass

    @abstractmethod
    async def get_open_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Order]:
        """
        Get all open orders.

        Args:
            symbol: Optional filter by symbol

        Returns:
            List of open Order objects.
        """
        pass

    # === Position Management ===

    @abstractmethod
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
        pass

    @abstractmethod
    async def close_all_positions(self) -> List[Order]:
        """
        Close all positions (emergency).

        Used by kill switches for immediate position liquidation.

        Returns:
            List of exit orders submitted.
        """
        pass

    # === Market Data (Optional) ===

    async def get_last_price(self, symbol: str) -> Optional[Decimal]:
        """
        Get last traded price for symbol.

        Default implementation returns None (use external data source).
        Override if broker provides quotes.
        """
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
        return None


# === Custom Exceptions ===

class BrokerError(Exception):
    """Base exception for broker errors."""
    pass


class BrokerConnectionError(BrokerError):
    """Connection to broker failed."""
    pass


class OrderRejectedError(BrokerError):
    """Order was rejected by broker."""

    def __init__(self, message: str, order: Optional[Order] = None):
        super().__init__(message)
        self.order = order


class InsufficientFundsError(BrokerError):
    """Insufficient buying power for order."""
    pass


class PositionNotFoundError(BrokerError):
    """Position does not exist."""
    pass
