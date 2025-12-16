"""
Shared test fixtures for live trading tests.

Provides mocked Alpaca client and common test data.
"""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass
from typing import Optional, List

from execution.live.broker import (
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    BrokerPosition,
    AccountInfo,
    BracketOrderRequest,
)


# === Mock Alpaca Data Classes ===

@dataclass
class MockAlpacaAccount:
    """Mock Alpaca account response."""
    id: str = "account-123"
    account_number: str = "PA123456"
    status: str = "ACTIVE"
    equity: str = "100000.00"
    cash: str = "50000.00"
    buying_power: str = "200000.00"
    portfolio_value: str = "100000.00"
    daytrade_count: int = 0
    pattern_day_trader: bool = False
    account_blocked: bool = False
    trading_blocked: bool = False


@dataclass
class MockAlpacaPosition:
    """Mock Alpaca position response."""
    symbol: str = "AAPL"
    qty: str = "100"
    avg_entry_price: str = "150.00"
    current_price: str = "155.00"
    market_value: str = "15500.00"
    cost_basis: str = "15000.00"
    unrealized_pl: str = "500.00"
    unrealized_plpc: str = "0.0333"


@dataclass
class MockAlpacaOrder:
    """Mock Alpaca order response."""
    id: str = "order-123"
    symbol: str = "AAPL"
    side: str = "buy"
    order_type: str = "market"
    qty: str = "10"
    limit_price: Optional[str] = None
    stop_price: Optional[str] = None
    time_in_force: str = "day"
    status: str = "filled"
    filled_qty: str = "10"
    filled_avg_price: str = "150.00"
    created_at: datetime = None
    updated_at: datetime = None
    client_order_id: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
        if self.updated_at is None:
            self.updated_at = datetime.now(timezone.utc)


# === Fixtures ===

@pytest.fixture
def mock_alpaca_account():
    """Return a mock Alpaca account."""
    return MockAlpacaAccount()


@pytest.fixture
def mock_alpaca_position():
    """Return a mock Alpaca position."""
    return MockAlpacaPosition()


@pytest.fixture
def mock_alpaca_order():
    """Return a mock Alpaca order."""
    return MockAlpacaOrder()


@pytest.fixture
def mock_trading_client(mock_alpaca_account, mock_alpaca_position, mock_alpaca_order):
    """
    Create a mocked TradingClient.

    Returns a MagicMock that mimics Alpaca TradingClient behavior.
    """
    client = MagicMock()

    # Account methods
    client.get_account.return_value = mock_alpaca_account

    # Position methods
    client.get_all_positions.return_value = [mock_alpaca_position]
    client.get_open_position.return_value = mock_alpaca_position

    # Order methods
    client.submit_order.return_value = mock_alpaca_order
    client.get_order_by_id.return_value = mock_alpaca_order
    client.get_orders.return_value = [mock_alpaca_order]
    client.cancel_order_by_id.return_value = None

    # Position management
    client.close_position.return_value = mock_alpaca_order
    client.close_all_positions.return_value = []

    return client


@pytest.fixture
def sample_order():
    """Return a sample Order for testing."""
    return Order(
        order_id="",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        quantity=Decimal("10"),
        time_in_force=TimeInForce.DAY,
    )


@pytest.fixture
def sample_limit_order():
    """Return a sample limit Order for testing."""
    return Order(
        order_id="",
        symbol="AAPL",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("10"),
        limit_price=Decimal("150.00"),
        time_in_force=TimeInForce.GTC,
    )


@pytest.fixture
def sample_stop_order():
    """Return a sample stop Order for testing."""
    return Order(
        order_id="",
        symbol="AAPL",
        side=OrderSide.SELL,
        order_type=OrderType.STOP,
        quantity=Decimal("10"),
        stop_price=Decimal("145.00"),
        time_in_force=TimeInForce.GTC,
    )


@pytest.fixture
def sample_bracket_request():
    """Return a sample BracketOrderRequest for testing."""
    return BracketOrderRequest(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
        entry_type=OrderType.MARKET,
        stop_loss_price=Decimal("145.00"),
        take_profit_price=Decimal("160.00"),
        time_in_force=TimeInForce.GTC,
    )
