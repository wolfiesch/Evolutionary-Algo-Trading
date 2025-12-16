# Phase 5: Live Broker Integration

**Created:** 12/16/2025 01:30 AM PST (via pst-timestamp)
**Status:** Planning
**Priority:** T3 - Operational (required for production)

---

## Overview

This plan implements live broker integration for the equities swing trading system. After successful shadow trading validation (Phase 4), strategies can be promoted to live trading.

## Broker Selection

### Recommended: Alpaca

| Feature | Alpaca | IBKR | Schwab/TD |
|---------|--------|------|-----------|
| Commission | $0 | $0 (IBKR Lite) | $0 |
| API Quality | Excellent | Good (complex) | Limited |
| Paper Trading | Built-in | Separate account | Limited |
| Fractional Shares | Yes | No | Yes |
| Pattern Day Trading | Enforced | Enforced | Enforced |
| Setup Complexity | Low | High | Medium |
| Market Data | Free (IEX) | Paid | Paid |

**Decision:** Alpaca (easy API, free market data, built-in paper trading)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      LIVE TRADING FLOW                           │
│                                                                  │
│  Shadow Trader                    Live Trader                    │
│  ┌──────────────┐                ┌──────────────┐               │
│  │ Generates    │   Promotion    │ Executes     │               │
│  │ Signals      │───────────────>│ Orders       │               │
│  │ (Paper)      │                │ (Real $)     │               │
│  └──────────────┘                └──────┬───────┘               │
│                                         │                        │
│                                         ▼                        │
│                              ┌──────────────────┐               │
│                              │ Broker Adapter   │               │
│                              │ (Alpaca API)     │               │
│                              └──────────────────┘               │
│                                         │                        │
│                              ┌──────────────────┐               │
│                              │ Position Manager │               │
│                              │ - Open/Close     │               │
│                              │ - Stop-Loss      │               │
│                              │ - Take-Profit    │               │
│                              └──────────────────┘               │
│                                         │                        │
│                              ┌──────────────────┐               │
│                              │ Risk Watchdog    │               │
│                              │ - Kill Switches  │               │
│                              │ - Drawdown       │               │
│                              └──────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Tasks

### 5.1 Broker Abstraction Layer
**Priority:** T0 | **Effort:** Medium

Create a broker-agnostic interface:

```python
# execution/live/broker.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
from decimal import Decimal

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    """Order representation."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: Decimal = Decimal("0")
    filled_avg_price: Optional[Decimal] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class BrokerPosition:
    """Position from broker."""
    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: float

@dataclass
class AccountInfo:
    """Account summary."""
    equity: Decimal
    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    day_trade_count: int
    pattern_day_trader: bool


class BrokerAdapter(ABC):
    """Abstract broker interface."""

    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to broker."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        """Get account information."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """Get all open positions."""
        pass

    @abstractmethod
    async def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        """Get position for specific symbol."""
        pass

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """Submit order to broker."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel pending order."""
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order status."""
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """Get all open orders."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str) -> Order:
        """Close entire position (market order)."""
        pass

    @abstractmethod
    async def close_all_positions(self) -> List[Order]:
        """Close all positions (emergency)."""
        pass
```

**Tasks:**
- [ ] Create `broker.py` with abstract interface
- [ ] Define order, position, and account dataclasses
- [ ] Add comprehensive docstrings
- [ ] Write interface tests

### 5.2 Alpaca Implementation
**Priority:** T0 | **Effort:** Medium

```python
# execution/live/alpaca_adapter.py

import os
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
from alpaca.common.exceptions import APIError

class AlpacaAdapter(BrokerAdapter):
    """Alpaca broker implementation."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True
    ):
        self.api_key = api_key or os.environ.get("ALPACA_API_KEY")
        self.secret_key = secret_key or os.environ.get("ALPACA_SECRET_KEY")
        self.paper = paper
        self.client: Optional[TradingClient] = None

    async def connect(self) -> bool:
        """Initialize Alpaca client."""
        try:
            self.client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper
            )
            # Verify connection
            account = self.client.get_account()
            return account.status == "ACTIVE"
        except APIError as e:
            logger.error(f"Alpaca connection failed: {e}")
            return False

    async def submit_order(self, order: Order) -> Order:
        """Submit order to Alpaca."""
        try:
            if order.order_type == OrderType.MARKET:
                request = MarketOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL,
                    time_in_force=TimeInForce.DAY
                )
            elif order.order_type == OrderType.LIMIT:
                request = LimitOrderRequest(
                    symbol=order.symbol,
                    qty=float(order.quantity),
                    side=AlpacaSide.BUY if order.side == OrderSide.BUY else AlpacaSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=float(order.limit_price)
                )
            # Add stop, stop-limit handling...

            alpaca_order = self.client.submit_order(request)
            return self._convert_order(alpaca_order)
        except APIError as e:
            logger.error(f"Order submission failed: {e}")
            order.status = OrderStatus.REJECTED
            return order

    # ... implement remaining methods
```

**Tasks:**
- [ ] Install `alpaca-py` package
- [ ] Implement `AlpacaAdapter` class
- [ ] Handle all order types (market, limit, stop, stop-limit)
- [ ] Add bracket orders for stop-loss + take-profit
- [ ] Write integration tests (paper trading)
- [ ] Handle API errors gracefully

### 5.3 Live Trader Engine
**Priority:** T0 | **Effort:** High

```python
# execution/live/trader.py

class EquitiesLiveTrader:
    """
    Live trading engine.

    Consumes signals from shadow trader and executes real orders.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        notifier: DiscordNotifier,
        config: LiveTraderConfig,
    ):
        self.broker = broker
        self.notifier = notifier
        self.config = config
        self.positions: Dict[str, LivePosition] = {}
        self.daily_stats = DailyStats()

    async def process_signal(self, signal: Signal) -> Optional[Order]:
        """
        Process trading signal from shadow trader.

        Steps:
        1. Validate signal (not stale, passes risk checks)
        2. Check kill switches
        3. Calculate position size
        4. Submit order with stop-loss
        5. Log and notify
        """
        # Validate
        if not self._validate_signal(signal):
            return None

        # Risk checks
        if self._check_kill_switches():
            await self._emergency_close_all()
            return None

        # Calculate position size
        account = await self.broker.get_account()
        position_size = self._calculate_position_size(
            signal=signal,
            account=account
        )

        if position_size <= 0:
            return None

        # Submit order
        order = await self._submit_entry_order(signal, position_size)

        if order.status == OrderStatus.FILLED:
            # Submit stop-loss order
            await self._submit_stop_loss(signal, order)

            # Notify
            await self.notifier.send_trade_entry(
                symbol=signal.symbol,
                side="LONG" if signal.signal_type == "entry_long" else "SHORT",
                price=float(order.filled_avg_price),
                quantity=float(order.filled_quantity),
                strategy=signal.strategy_id,
            )

        return order

    def _calculate_position_size(
        self,
        signal: Signal,
        account: AccountInfo
    ) -> Decimal:
        """
        Calculate position size based on:
        1. Max position % of portfolio
        2. Risk per trade (ATR-based)
        3. Available buying power
        4. Sector limits
        """
        max_position_value = account.equity * self.config.max_position_pct

        # ATR-based sizing: risk_amount / stop_distance
        risk_amount = account.equity * self.config.risk_per_trade
        stop_distance = signal.entry_price * self.config.stop_loss_pct
        atr_based_size = risk_amount / stop_distance

        # Take minimum
        position_value = min(max_position_value, atr_based_size * signal.entry_price)

        # Check buying power
        position_value = min(position_value, float(account.buying_power))

        # Check sector limits
        sector_exposure = self._get_sector_exposure(signal.symbol)
        if sector_exposure > self.config.max_sector_pct:
            return Decimal("0")

        shares = int(position_value / signal.entry_price)
        return Decimal(str(shares))
```

**Tasks:**
- [ ] Create `trader.py` with live trading logic
- [ ] Implement signal validation
- [ ] Implement position sizing (ATR-based, sector limits)
- [ ] Implement stop-loss order submission
- [ ] Add bracket orders (entry + stop + target)
- [ ] Write unit tests

### 5.4 Risk Watchdog
**Priority:** T0 | **Effort:** Medium

```python
# execution/live/watchdog.py

@dataclass
class KillSwitchConfig:
    """Kill switch thresholds."""
    daily_drawdown_pct: float = 0.03      # 3% daily max
    weekly_drawdown_pct: float = 0.07     # 7% weekly max
    peak_drawdown_pct: float = 0.15       # 15% from peak
    single_position_loss_pct: float = 0.05  # 5% per position
    max_daily_trades: int = 10            # Prevent runaway
    max_daily_loss_usd: float = 1000.0    # Absolute limit


class RiskWatchdog:
    """
    Monitors portfolio risk and triggers kill switches.

    Kill Switch Triggers:
    1. Daily drawdown > 3%: Pause new trades for rest of day
    2. Weekly drawdown > 7%: Pause for 24 hours
    3. Peak drawdown > 15%: FULL SHUTDOWN (manual restart required)
    4. Single position > 5% loss: Force close that position
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        notifier: DiscordNotifier,
        config: KillSwitchConfig,
    ):
        self.broker = broker
        self.notifier = notifier
        self.config = config
        self.daily_high_water = Decimal("0")
        self.weekly_high_water = Decimal("0")
        self.peak_equity = Decimal("0")
        self.paused_until: Optional[datetime] = None
        self.shutdown = False

    async def check(self) -> bool:
        """
        Run all risk checks.

        Returns True if trading should continue, False if paused/shutdown.
        """
        if self.shutdown:
            return False

        if self.paused_until and datetime.utcnow() < self.paused_until:
            return False

        account = await self.broker.get_account()
        positions = await self.broker.get_positions()

        # Update high water marks
        self._update_high_water(account.equity)

        # Check kill switches
        if self._check_daily_drawdown(account.equity):
            await self._trigger_daily_pause()
            return False

        if self._check_weekly_drawdown(account.equity):
            await self._trigger_weekly_pause()
            return False

        if self._check_peak_drawdown(account.equity):
            await self._trigger_full_shutdown()
            return False

        # Check individual positions
        for pos in positions:
            if self._check_position_loss(pos):
                await self._force_close_position(pos)

        return True
```

**Tasks:**
- [ ] Create `watchdog.py` with risk monitoring
- [ ] Implement daily/weekly/peak drawdown checks
- [ ] Implement position-level stop enforcement
- [ ] Add pause and shutdown mechanisms
- [ ] Write unit tests

### 5.5 Order Manager
**Priority:** T1 | **Effort:** Medium

```python
# execution/live/order_manager.py

class OrderManager:
    """
    Manages order lifecycle:
    - Submit orders
    - Track pending orders
    - Handle fills/rejects
    - Sync with broker state
    """

    def __init__(self, broker: BrokerAdapter, repository: OrderRepository):
        self.broker = broker
        self.repository = repository
        self.pending_orders: Dict[str, Order] = {}

    async def submit_bracket_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        stop_loss_price: Decimal,
        take_profit_price: Optional[Decimal] = None,
    ) -> Tuple[Order, Order, Optional[Order]]:
        """
        Submit entry with attached stop-loss and optional take-profit.

        Alpaca supports bracket orders natively.
        """
        pass

    async def sync_with_broker(self) -> None:
        """
        Sync local state with broker state.

        Called on startup and periodically to ensure consistency.
        """
        pass
```

**Tasks:**
- [ ] Create `order_manager.py`
- [ ] Implement bracket order submission
- [ ] Add order tracking and persistence
- [ ] Implement state synchronization
- [ ] Handle partial fills

### 5.6 Position Synchronization
**Priority:** T1 | **Effort:** Low

```python
# execution/live/sync.py

class PositionSync:
    """
    Ensures local position state matches broker state.

    Handles:
    - Startup sync (recover from crashes)
    - Periodic reconciliation
    - Manual intervention detection
    """

    async def sync_on_startup(self) -> SyncReport:
        """
        Called on trader startup to recover state.
        """
        pass

    async def reconcile(self) -> List[Discrepancy]:
        """
        Compare local vs broker positions.
        """
        pass
```

**Tasks:**
- [ ] Create `sync.py`
- [ ] Implement startup recovery
- [ ] Add periodic reconciliation
- [ ] Handle manual trades (positions not from our system)

---

## Configuration

```python
# config.py additions

@dataclass
class LiveTraderConfig:
    """Live trading configuration."""

    # Position sizing
    max_position_pct: float = 0.05      # 5% max per position
    max_sector_pct: float = 0.20        # 20% max per sector
    max_total_exposure: float = 0.80    # 80% max invested
    risk_per_trade: float = 0.01        # 1% risk per trade

    # Order execution
    use_limit_orders: bool = True       # vs market orders
    limit_offset_pct: float = 0.001     # 0.1% better than market
    max_slippage_pct: float = 0.005     # 0.5% max acceptable

    # Timing
    entry_window_start: str = "09:35"   # ET - avoid open
    entry_window_end: str = "15:55"     # ET - avoid close

    # Kill switches
    kill_switch: KillSwitchConfig = field(default_factory=KillSwitchConfig)
```

---

## Testing Strategy

### Unit Tests
- [ ] Broker adapter interface tests
- [ ] Order type conversion tests
- [ ] Position sizing calculation tests
- [ ] Kill switch trigger tests

### Integration Tests (Paper Trading)
- [ ] Submit and cancel orders
- [ ] Full trade lifecycle (entry → stop → exit)
- [ ] Bracket order execution
- [ ] Account info retrieval

### Simulation Tests
- [ ] Slippage modeling
- [ ] Partial fill handling
- [ ] Network failure recovery

---

## Dependencies

```
# requirements.txt additions
alpaca-py>=0.15.0
```

---

## File Structure

```
execution/live/
├── __init__.py
├── broker.py           # Abstract broker interface
├── alpaca_adapter.py   # Alpaca implementation
├── trader.py           # Live trading engine
├── watchdog.py         # Risk monitoring / kill switches
├── order_manager.py    # Order lifecycle management
├── sync.py             # Position synchronization
├── models.py           # Data models
└── tests/
    ├── test_broker.py
    ├── test_alpaca.py
    ├── test_trader.py
    ├── test_watchdog.py
    └── conftest.py     # Alpaca mock fixtures
```

---

## Success Criteria

### Phase 5 Complete When:
- [ ] Broker adapter connects to Alpaca paper trading
- [ ] Orders submit and fill correctly
- [ ] Stop-loss orders trigger as expected
- [ ] Kill switches tested and working
- [ ] Position sync recovers from restart
- [ ] 7 days successful paper trading via live engine
- [ ] All tests passing (target: 50+ new tests)

---

## Estimated Effort

| Task | Effort | Dependencies |
|------|--------|--------------|
| 5.1 Broker Abstraction | 4 hours | None |
| 5.2 Alpaca Implementation | 6 hours | 5.1 |
| 5.3 Live Trader Engine | 8 hours | 5.1, 5.2 |
| 5.4 Risk Watchdog | 4 hours | 5.1 |
| 5.5 Order Manager | 4 hours | 5.1, 5.2 |
| 5.6 Position Sync | 2 hours | 5.1, 5.2 |
| Testing | 6 hours | All |
| **Total** | **~34 hours** | |

---

## Changelog

| Timestamp | Change | Author |
|-----------|--------|--------|
| 12/16/2025 01:30 AM PST | Initial Phase 5 plan created | Claude |
| 12/16/2025 02:39 PM PST | Completed 5.1 (broker abstraction) + 5.2 (AlpacaAdapter) with 41 tests | Claude |
| 12/16/2025 02:46 PM PST | Completed 5.3 (LiveTrader) + 5.4 (RiskWatchdog) - total 107 tests passing | Claude |

