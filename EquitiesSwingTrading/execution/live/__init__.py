"""
Live trading module.

Provides broker integration, order management, and risk monitoring
for live equity trading.
"""
from execution.live.broker import (
    # Enums
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    # Data classes
    Order,
    BrokerPosition,
    AccountInfo,
    BracketOrderRequest,
    # Abstract base
    BrokerAdapter,
    # Exceptions
    BrokerError,
    BrokerConnectionError,
    OrderRejectedError,
    InsufficientFundsError,
    PositionNotFoundError,
)
from execution.live.alpaca_adapter import AlpacaAdapter
from execution.live.trader import (
    Signal,
    LiveTraderConfig,
    DailyStats,
    LivePosition,
    EquitiesLiveTrader,
)
from execution.live.watchdog import (
    KillSwitchTrigger,
    WatchdogState,
    KillSwitchConfig,
    KillSwitchEvent,
    WatchdogStats,
    RiskWatchdog,
)

__all__ = [
    # Enums
    "OrderSide",
    "OrderType",
    "OrderStatus",
    "TimeInForce",
    "KillSwitchTrigger",
    "WatchdogState",
    # Broker data classes
    "Order",
    "BrokerPosition",
    "AccountInfo",
    "BracketOrderRequest",
    # Trader data classes
    "Signal",
    "LiveTraderConfig",
    "DailyStats",
    "LivePosition",
    # Watchdog data classes
    "KillSwitchConfig",
    "KillSwitchEvent",
    "WatchdogStats",
    # Abstract base
    "BrokerAdapter",
    # Implementations
    "AlpacaAdapter",
    "EquitiesLiveTrader",
    "RiskWatchdog",
    # Exceptions
    "BrokerError",
    "BrokerConnectionError",
    "OrderRejectedError",
    "InsufficientFundsError",
    "PositionNotFoundError",
]
