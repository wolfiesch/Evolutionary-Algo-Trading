"""
Live trading engine for equities swing trading.

Consumes signals from shadow trader and executes real orders
through the broker adapter.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, time as dt_time
from decimal import Decimal
from typing import Optional, Dict, List, Any, Callable

from .broker import (
    BrokerAdapter,
    Order,
    OrderSide,
    OrderType,
    OrderStatus,
    TimeInForce,
    BracketOrderRequest,
    AccountInfo,
    BrokerPosition,
    BrokerError,
    OrderRejectedError,
    InsufficientFundsError,
)

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """
    Trading signal from shadow trader.

    Represents a validated trading opportunity ready for execution.
    """
    signal_id: str
    strategy_id: str
    symbol: str
    signal_type: str  # "entry_long", "entry_short", "exit_long", "exit_short"
    entry_price: Decimal
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_entry(self) -> bool:
        """Check if this is an entry signal."""
        return self.signal_type.startswith("entry")

    @property
    def is_exit(self) -> bool:
        """Check if this is an exit signal."""
        return self.signal_type.startswith("exit")

    @property
    def is_long(self) -> bool:
        """Check if this is a long signal."""
        return "long" in self.signal_type

    @property
    def is_short(self) -> bool:
        """Check if this is a short signal."""
        return "short" in self.signal_type


@dataclass
class LiveTraderConfig:
    """Live trading configuration."""

    # Position sizing
    max_position_pct: float = 0.05          # 5% max per position
    max_sector_pct: float = 0.20            # 20% max per sector
    max_total_exposure: float = 0.80        # 80% max invested
    risk_per_trade: float = 0.01            # 1% risk per trade
    max_positions: int = 10                 # Maximum concurrent positions

    # Order execution
    use_limit_orders: bool = False          # Use market orders for speed
    limit_offset_pct: float = 0.001         # 0.1% better than market
    max_slippage_pct: float = 0.005         # 0.5% max acceptable

    # Stop-loss
    default_stop_loss_pct: float = 0.02     # 2% default stop
    use_bracket_orders: bool = True         # Always attach stop-loss

    # Timing (Eastern Time)
    entry_window_start: dt_time = dt_time(9, 35)   # After market open
    entry_window_end: dt_time = dt_time(15, 55)    # Before market close

    # Signal validation
    max_signal_age_seconds: int = 60        # Reject stale signals
    require_stop_loss: bool = True          # Require stop-loss on entries

    # Throttling
    min_entry_interval_seconds: int = 300   # 5 min between entries
    max_daily_trades: int = 20              # Max trades per day


@dataclass
class DailyStats:
    """Daily trading statistics."""
    date: str = ""
    trades_count: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    gross_loss: Decimal = Decimal("0")
    max_drawdown: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")

    def reset(self, date: str, equity: Decimal) -> None:
        """Reset stats for new day."""
        self.date = date
        self.trades_count = 0
        self.wins = 0
        self.losses = 0
        self.total_pnl = Decimal("0")
        self.gross_profit = Decimal("0")
        self.gross_loss = Decimal("0")
        self.max_drawdown = Decimal("0")
        self.peak_equity = equity


@dataclass
class LivePosition:
    """
    Internal position tracking.

    Augments broker position with strategy metadata.
    """
    symbol: str
    strategy_id: str
    entry_order_id: str
    entry_price: Decimal
    quantity: Decimal
    stop_loss_order_id: Optional[str] = None
    take_profit_order_id: Optional[str] = None
    stop_loss_price: Optional[Decimal] = None
    take_profit_price: Optional[Decimal] = None
    entry_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    signal_id: Optional[str] = None


class EquitiesLiveTrader:
    """
    Live trading engine.

    Consumes signals from shadow trader and executes real orders.
    Implements position sizing, risk management, and order lifecycle.

    Example:
        adapter = AlpacaAdapter(paper=True)
        await adapter.connect()

        trader = EquitiesLiveTrader(
            broker=adapter,
            config=LiveTraderConfig(max_positions=5),
        )

        signal = Signal(
            signal_id="sig-1",
            strategy_id="momentum_v1",
            symbol="AAPL",
            signal_type="entry_long",
            entry_price=Decimal("150.00"),
            stop_loss_price=Decimal("147.00"),
        )

        order = await trader.process_signal(signal)
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        config: Optional[LiveTraderConfig] = None,
        notifier: Optional[Any] = None,
        risk_callback: Optional[Callable[[], bool]] = None,
    ):
        """
        Initialize live trader.

        Args:
            broker: Broker adapter for order execution
            config: Trading configuration
            notifier: Optional notifier for alerts (Discord, etc.)
            risk_callback: Optional callback to check kill switches
        """
        self.broker = broker
        self.config = config or LiveTraderConfig()
        self.notifier = notifier
        self.risk_callback = risk_callback

        # Position tracking
        self.positions: Dict[str, LivePosition] = {}
        self.daily_stats = DailyStats()

        # Throttling
        self._last_entry_time: Optional[datetime] = None

        # State
        self._running = False
        self._paused = False

    async def process_signal(self, signal: Signal) -> Optional[Order]:
        """
        Process trading signal.

        Steps:
        1. Validate signal (not stale, has required fields)
        2. Check kill switches via callback
        3. Check if within trading window
        4. Check position limits
        5. Calculate position size
        6. Submit order with stop-loss

        Args:
            signal: Trading signal to process

        Returns:
            Submitted order if successful, None if rejected.
        """
        logger.info(f"Processing signal: {signal.signal_id} - {signal.signal_type} {signal.symbol}")

        # 1. Validate signal
        validation_error = self._validate_signal(signal)
        if validation_error:
            logger.warning(f"Signal rejected: {validation_error}")
            return None

        # 2. Check kill switches
        if self.risk_callback and not self.risk_callback():
            logger.warning("Signal rejected: kill switch triggered")
            return None

        # 3. Check trading window
        if not self._in_trading_window():
            logger.info("Signal rejected: outside trading window")
            return None

        # 4. Handle entry vs exit
        if signal.is_entry:
            return await self._process_entry_signal(signal)
        else:
            return await self._process_exit_signal(signal)

    async def _process_entry_signal(self, signal: Signal) -> Optional[Order]:
        """Process entry signal."""
        # Check position limits
        if len(self.positions) >= self.config.max_positions:
            logger.warning(f"Signal rejected: max positions ({self.config.max_positions}) reached")
            return None

        # Check if already have position in this symbol
        if signal.symbol in self.positions:
            logger.warning(f"Signal rejected: already have position in {signal.symbol}")
            return None

        # Check throttling
        if not self._check_entry_throttle():
            logger.info("Signal rejected: entry throttled")
            return None

        # Check daily trade limit
        if self.daily_stats.trades_count >= self.config.max_daily_trades:
            logger.warning("Signal rejected: daily trade limit reached")
            return None

        # Get account info for position sizing
        try:
            account = await self.broker.get_account()
        except BrokerError as e:
            logger.error(f"Failed to get account info: {e}")
            return None

        # Calculate position size
        position_size = self._calculate_position_size(signal, account)
        if position_size <= 0:
            logger.warning("Signal rejected: position size calculated as 0")
            return None

        # Check total exposure
        current_exposure = await self._get_current_exposure(account)
        new_exposure = current_exposure + (position_size * signal.entry_price)
        max_exposure = account.equity * Decimal(str(self.config.max_total_exposure))

        if new_exposure > max_exposure:
            logger.warning(f"Signal rejected: would exceed max exposure ({new_exposure} > {max_exposure})")
            return None

        # Submit order
        try:
            if self.config.use_bracket_orders and signal.stop_loss_price:
                order = await self._submit_bracket_entry(signal, position_size)
            else:
                order = await self._submit_simple_entry(signal, position_size)

            if order and order.status in (OrderStatus.FILLED, OrderStatus.NEW, OrderStatus.ACCEPTED):
                # Track position
                self.positions[signal.symbol] = LivePosition(
                    symbol=signal.symbol,
                    strategy_id=signal.strategy_id,
                    entry_order_id=order.order_id,
                    entry_price=order.filled_avg_price or signal.entry_price,
                    quantity=order.filled_quantity or position_size,
                    stop_loss_price=signal.stop_loss_price,
                    take_profit_price=signal.take_profit_price,
                    signal_id=signal.signal_id,
                )

                # Update stats
                self.daily_stats.trades_count += 1
                self._last_entry_time = datetime.now(timezone.utc)

                logger.info(
                    f"Entry order submitted: {signal.symbol} {order.side.value} "
                    f"{order.filled_quantity or position_size} @ {order.filled_avg_price or signal.entry_price}"
                )

                # Notify
                if self.notifier:
                    await self._notify_entry(signal, order)

            return order

        except (OrderRejectedError, InsufficientFundsError) as e:
            logger.error(f"Entry order rejected: {e}")
            return None
        except BrokerError as e:
            logger.error(f"Entry order failed: {e}")
            return None

    async def _process_exit_signal(self, signal: Signal) -> Optional[Order]:
        """Process exit signal."""
        if signal.symbol not in self.positions:
            logger.warning(f"Exit signal rejected: no position in {signal.symbol}")
            return None

        position = self.positions[signal.symbol]

        try:
            # Close position via broker
            order = await self.broker.close_position(signal.symbol)

            if order and order.status in (OrderStatus.FILLED, OrderStatus.NEW, OrderStatus.ACCEPTED):
                # Calculate P&L
                exit_price = order.filled_avg_price or signal.entry_price
                pnl = (exit_price - position.entry_price) * position.quantity
                if signal.is_short:
                    pnl = -pnl

                # Update stats
                self.daily_stats.total_pnl += pnl
                if pnl > 0:
                    self.daily_stats.wins += 1
                    self.daily_stats.gross_profit += pnl
                else:
                    self.daily_stats.losses += 1
                    self.daily_stats.gross_loss += abs(pnl)

                # Remove from tracking
                del self.positions[signal.symbol]

                logger.info(
                    f"Exit order submitted: {signal.symbol} - P&L: ${pnl:.2f}"
                )

                # Notify
                if self.notifier:
                    await self._notify_exit(signal, order, pnl)

            return order

        except BrokerError as e:
            logger.error(f"Exit order failed: {e}")
            return None

    async def _submit_bracket_entry(
        self,
        signal: Signal,
        quantity: Decimal
    ) -> Order:
        """Submit bracket order (entry + stop-loss + optional take-profit)."""
        side = OrderSide.BUY if signal.is_long else OrderSide.SELL

        request = BracketOrderRequest(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            entry_type=OrderType.MARKET if not self.config.use_limit_orders else OrderType.LIMIT,
            entry_limit_price=signal.entry_price if self.config.use_limit_orders else None,
            stop_loss_price=signal.stop_loss_price or self._calculate_default_stop(signal),
            take_profit_price=signal.take_profit_price,
            time_in_force=TimeInForce.DAY,
        )

        return await self.broker.submit_bracket_order(request)

    async def _submit_simple_entry(
        self,
        signal: Signal,
        quantity: Decimal
    ) -> Order:
        """Submit simple market/limit entry order."""
        side = OrderSide.BUY if signal.is_long else OrderSide.SELL

        order = Order(
            order_id="",
            symbol=signal.symbol,
            side=side,
            order_type=OrderType.MARKET if not self.config.use_limit_orders else OrderType.LIMIT,
            quantity=quantity,
            limit_price=signal.entry_price if self.config.use_limit_orders else None,
            time_in_force=TimeInForce.DAY,
            client_order_id=signal.signal_id,
        )

        return await self.broker.submit_order(order)

    def _validate_signal(self, signal: Signal) -> Optional[str]:
        """
        Validate signal.

        Returns error message if invalid, None if valid.
        """
        # Check signal age
        age = (datetime.now(timezone.utc) - signal.timestamp).total_seconds()
        if age > self.config.max_signal_age_seconds:
            return f"Signal too old ({age:.1f}s > {self.config.max_signal_age_seconds}s)"

        # Check required fields
        if not signal.symbol:
            return "Missing symbol"
        if not signal.signal_type:
            return "Missing signal type"
        if signal.entry_price <= 0:
            return "Invalid entry price"

        # Check stop-loss for entries
        if signal.is_entry and self.config.require_stop_loss and not signal.stop_loss_price:
            return "Missing stop-loss price"

        # Validate stop-loss direction
        if signal.is_entry and signal.stop_loss_price:
            if signal.is_long and signal.stop_loss_price >= signal.entry_price:
                return "Long stop-loss must be below entry"
            if signal.is_short and signal.stop_loss_price <= signal.entry_price:
                return "Short stop-loss must be above entry"

        return None

    def _calculate_position_size(
        self,
        signal: Signal,
        account: AccountInfo
    ) -> Decimal:
        """
        Calculate position size based on risk parameters.

        Uses the smaller of:
        1. Max position % of portfolio
        2. Risk-based sizing (risk_amount / stop_distance)
        3. Available buying power
        """
        equity = account.equity

        # Max position by portfolio %
        max_position_value = equity * Decimal(str(self.config.max_position_pct))

        # Risk-based sizing
        if signal.stop_loss_price:
            stop_distance = abs(signal.entry_price - signal.stop_loss_price)
            if stop_distance > 0:
                risk_amount = equity * Decimal(str(self.config.risk_per_trade))
                risk_based_shares = risk_amount / stop_distance
                risk_based_value = risk_based_shares * signal.entry_price
            else:
                risk_based_value = max_position_value
        else:
            # Use default stop distance for sizing
            stop_distance = signal.entry_price * Decimal(str(self.config.default_stop_loss_pct))
            risk_amount = equity * Decimal(str(self.config.risk_per_trade))
            risk_based_shares = risk_amount / stop_distance
            risk_based_value = risk_based_shares * signal.entry_price

        # Take minimum of position limits
        position_value = min(max_position_value, risk_based_value)

        # Check buying power
        position_value = min(position_value, account.buying_power)

        # Convert to shares (round down)
        shares = int(position_value / signal.entry_price)

        return Decimal(str(shares)) if shares > 0 else Decimal("0")

    def _calculate_default_stop(self, signal: Signal) -> Decimal:
        """Calculate default stop-loss price."""
        stop_pct = Decimal(str(self.config.default_stop_loss_pct))

        if signal.is_long:
            return signal.entry_price * (1 - stop_pct)
        else:
            return signal.entry_price * (1 + stop_pct)

    def _in_trading_window(self) -> bool:
        """Check if current time is within trading window."""
        # For MVP, always return True
        # [*TO-DO*] - Implement proper market hours check with timezone conversion
        return True

    def _check_entry_throttle(self) -> bool:
        """Check if enough time has passed since last entry."""
        if self._last_entry_time is None:
            return True

        elapsed = (datetime.now(timezone.utc) - self._last_entry_time).total_seconds()
        return elapsed >= self.config.min_entry_interval_seconds

    async def _get_current_exposure(self, account: AccountInfo) -> Decimal:
        """Get current total position value."""
        try:
            positions = await self.broker.get_positions()
            return sum(pos.market_value for pos in positions)
        except BrokerError:
            return Decimal("0")

    async def _notify_entry(self, signal: Signal, order: Order) -> None:
        """Send entry notification."""
        if not self.notifier:
            return

        try:
            # Generic notification interface
            if hasattr(self.notifier, 'send_trade_entry'):
                await self.notifier.send_trade_entry(
                    symbol=signal.symbol,
                    side="LONG" if signal.is_long else "SHORT",
                    price=float(order.filled_avg_price or signal.entry_price),
                    quantity=float(order.filled_quantity or order.quantity),
                    strategy=signal.strategy_id,
                )
        except Exception as e:
            logger.error(f"Failed to send entry notification: {e}")

    async def _notify_exit(
        self,
        signal: Signal,
        order: Order,
        pnl: Decimal
    ) -> None:
        """Send exit notification."""
        if not self.notifier:
            return

        try:
            if hasattr(self.notifier, 'send_trade_exit'):
                await self.notifier.send_trade_exit(
                    symbol=signal.symbol,
                    price=float(order.filled_avg_price or signal.entry_price),
                    quantity=float(order.filled_quantity or order.quantity),
                    pnl=float(pnl),
                    strategy=signal.strategy_id,
                )
        except Exception as e:
            logger.error(f"Failed to send exit notification: {e}")

    # === Position Management ===

    async def sync_positions(self) -> None:
        """
        Sync internal position state with broker.

        Called on startup and periodically to ensure consistency.
        """
        try:
            broker_positions = await self.broker.get_positions()
            broker_symbols = {pos.symbol for pos in broker_positions}

            # Log discrepancies
            tracked_symbols = set(self.positions.keys())

            # Positions in broker but not tracked
            untracked = broker_symbols - tracked_symbols
            if untracked:
                logger.warning(f"Untracked positions found: {untracked}")

            # Positions tracked but not in broker
            missing = tracked_symbols - broker_symbols
            if missing:
                logger.warning(f"Tracked positions missing from broker: {missing}")
                for symbol in missing:
                    del self.positions[symbol]

        except BrokerError as e:
            logger.error(f"Failed to sync positions: {e}")

    async def close_all_positions(self) -> List[Order]:
        """
        Emergency close all positions.

        Used by kill switches.
        """
        logger.warning("EMERGENCY: Closing all positions")

        try:
            orders = await self.broker.close_all_positions()
            self.positions.clear()

            if self.notifier and hasattr(self.notifier, 'send_alert'):
                await self.notifier.send_alert(
                    "🚨 EMERGENCY: All positions closed"
                )

            return orders

        except BrokerError as e:
            logger.error(f"Failed to close all positions: {e}")
            return []

    def get_daily_stats(self) -> DailyStats:
        """Get current daily statistics."""
        return self.daily_stats

    def reset_daily_stats(self, equity: Decimal) -> None:
        """Reset daily statistics (call at market open)."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.daily_stats.reset(today, equity)
