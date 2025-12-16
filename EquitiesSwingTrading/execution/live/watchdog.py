"""
Risk watchdog with kill switches for live trading.

Monitors portfolio risk and triggers protective actions when
thresholds are breached.
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Callable

from .broker import (
    BrokerAdapter,
    BrokerPosition,
    AccountInfo,
    BrokerError,
)

logger = logging.getLogger(__name__)


class KillSwitchTrigger(Enum):
    """Kill switch trigger types."""
    DAILY_DRAWDOWN = "daily_drawdown"
    WEEKLY_DRAWDOWN = "weekly_drawdown"
    PEAK_DRAWDOWN = "peak_drawdown"
    SINGLE_POSITION_LOSS = "single_position_loss"
    MAX_DAILY_TRADES = "max_daily_trades"
    MAX_DAILY_LOSS = "max_daily_loss"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    MANUAL = "manual"


class WatchdogState(Enum):
    """Watchdog state."""
    ACTIVE = "active"           # Normal operation
    PAUSED = "paused"           # Temporarily paused
    SHUTDOWN = "shutdown"       # Full shutdown, manual restart required


@dataclass
class KillSwitchConfig:
    """Kill switch thresholds."""
    # Drawdown thresholds
    daily_drawdown_pct: float = 0.03      # 3% daily max loss
    weekly_drawdown_pct: float = 0.07     # 7% weekly max loss
    peak_drawdown_pct: float = 0.15       # 15% from all-time peak

    # Position-level
    single_position_loss_pct: float = 0.05  # 5% loss per position

    # Trade limits
    max_daily_trades: int = 20            # Max trades per day
    max_daily_loss_usd: float = 1000.0    # Absolute daily loss limit
    max_consecutive_losses: int = 5       # Consecutive losing trades

    # Pause durations
    daily_pause_hours: int = 4            # Pause duration for daily trigger
    weekly_pause_hours: int = 24          # Pause duration for weekly trigger


@dataclass
class KillSwitchEvent:
    """Record of a kill switch trigger."""
    timestamp: datetime
    trigger_type: KillSwitchTrigger
    threshold_value: float
    actual_value: float
    action_taken: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WatchdogStats:
    """Risk monitoring statistics."""
    # High water marks
    daily_high_water: Decimal = Decimal("0")
    weekly_high_water: Decimal = Decimal("0")
    peak_equity: Decimal = Decimal("0")

    # Current metrics
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    daily_drawdown_pct: float = 0.0
    weekly_drawdown_pct: float = 0.0
    peak_drawdown_pct: float = 0.0

    # Trade tracking
    daily_trades: int = 0
    consecutive_losses: int = 0
    last_reset_date: str = ""
    last_week_reset_date: str = ""


class RiskWatchdog:
    """
    Monitors portfolio risk and triggers kill switches.

    Kill Switch Triggers:
    1. Daily drawdown > 3%: Pause new trades for 4 hours
    2. Weekly drawdown > 7%: Pause for 24 hours
    3. Peak drawdown > 15%: FULL SHUTDOWN (manual restart required)
    4. Single position > 5% loss: Force close that position

    Example:
        watchdog = RiskWatchdog(
            broker=adapter,
            config=KillSwitchConfig(daily_drawdown_pct=0.03),
        )

        # In trading loop
        if watchdog.is_trading_allowed():
            # Process signals...
            pass

        # Check and handle risk events
        await watchdog.check()
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        config: Optional[KillSwitchConfig] = None,
        notifier: Optional[Any] = None,
        on_shutdown: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize risk watchdog.

        Args:
            broker: Broker adapter for position/account access
            config: Kill switch configuration
            notifier: Optional notifier for alerts
            on_shutdown: Callback when full shutdown triggered
        """
        self.broker = broker
        self.config = config or KillSwitchConfig()
        self.notifier = notifier
        self.on_shutdown = on_shutdown

        # State
        self.state = WatchdogState.ACTIVE
        self.paused_until: Optional[datetime] = None
        self.stats = WatchdogStats()

        # Event history
        self.events: List[KillSwitchEvent] = []
        self._max_events = 100  # Keep last N events

    async def check(self) -> bool:
        """
        Run all risk checks.

        Returns True if trading should continue, False if paused/shutdown.
        """
        if self.state == WatchdogState.SHUTDOWN:
            return False

        if self.state == WatchdogState.PAUSED:
            if self._is_pause_expired():
                self.state = WatchdogState.ACTIVE
                logger.info("Risk watchdog pause expired, resuming trading")
            else:
                return False

        try:
            account = await self.broker.get_account()
            positions = await self.broker.get_positions()
        except BrokerError as e:
            logger.error(f"Failed to fetch account/positions: {e}")
            return True  # Don't block trading on data fetch error

        # Reset daily/weekly stats if needed
        self._maybe_reset_stats(account.equity)

        # Update high water marks
        self._update_high_water(account.equity)

        # Calculate current drawdowns
        self._calculate_drawdowns(account.equity)

        # Run kill switch checks
        triggered = await self._run_kill_switch_checks(account, positions)

        return not triggered

    def is_trading_allowed(self) -> bool:
        """
        Quick check if trading is currently allowed.

        Use this before processing signals.
        """
        if self.state == WatchdogState.SHUTDOWN:
            return False

        if self.state == WatchdogState.PAUSED:
            if self._is_pause_expired():
                self.state = WatchdogState.ACTIVE
                return True
            return False

        return True

    def record_trade(self, is_winner: bool, pnl: Decimal) -> None:
        """
        Record a completed trade for tracking.

        Args:
            is_winner: Whether trade was profitable
            pnl: P&L amount
        """
        self.stats.daily_trades += 1
        self.stats.daily_pnl += pnl
        self.stats.weekly_pnl += pnl

        if is_winner:
            self.stats.consecutive_losses = 0
        else:
            self.stats.consecutive_losses += 1

    def manual_pause(self, hours: int = 1) -> None:
        """Manually pause trading."""
        self.state = WatchdogState.PAUSED
        self.paused_until = datetime.now(timezone.utc) + timedelta(hours=hours)
        self._record_event(
            KillSwitchTrigger.MANUAL,
            threshold_value=0,
            actual_value=0,
            action_taken=f"Manual pause for {hours} hours",
        )
        logger.info(f"Manual pause activated for {hours} hours")

    def manual_resume(self) -> None:
        """Manually resume trading from pause (not from shutdown)."""
        if self.state == WatchdogState.PAUSED:
            self.state = WatchdogState.ACTIVE
            self.paused_until = None
            logger.info("Manual resume from pause")

    def manual_shutdown(self) -> None:
        """Manually trigger full shutdown."""
        self.state = WatchdogState.SHUTDOWN
        self._record_event(
            KillSwitchTrigger.MANUAL,
            threshold_value=0,
            actual_value=0,
            action_taken="Manual full shutdown",
        )
        logger.warning("MANUAL SHUTDOWN triggered")
        if self.on_shutdown:
            self.on_shutdown()

    def reset_shutdown(self, new_peak_equity: Decimal) -> None:
        """
        Reset from shutdown state (requires manual confirmation).

        Args:
            new_peak_equity: New peak equity to track from
        """
        if self.state == WatchdogState.SHUTDOWN:
            self.state = WatchdogState.ACTIVE
            self.stats.peak_equity = new_peak_equity
            self.stats.daily_high_water = new_peak_equity
            self.stats.weekly_high_water = new_peak_equity
            self.stats.consecutive_losses = 0
            logger.info(f"Reset from shutdown with new peak equity: ${new_peak_equity}")

    # === Private Methods ===

    async def _run_kill_switch_checks(
        self,
        account: AccountInfo,
        positions: List[BrokerPosition]
    ) -> bool:
        """
        Run all kill switch checks.

        Returns True if any kill switch triggered.
        """
        triggered = False

        # 1. Check daily drawdown
        if self.stats.daily_drawdown_pct >= self.config.daily_drawdown_pct:
            await self._trigger_daily_pause()
            triggered = True

        # 2. Check weekly drawdown
        elif self.stats.weekly_drawdown_pct >= self.config.weekly_drawdown_pct:
            await self._trigger_weekly_pause()
            triggered = True

        # 3. Check peak drawdown
        elif self.stats.peak_drawdown_pct >= self.config.peak_drawdown_pct:
            await self._trigger_full_shutdown()
            triggered = True

        # 4. Check daily trade limit
        elif self.stats.daily_trades >= self.config.max_daily_trades:
            await self._trigger_daily_pause()
            self._record_event(
                KillSwitchTrigger.MAX_DAILY_TRADES,
                threshold_value=self.config.max_daily_trades,
                actual_value=self.stats.daily_trades,
                action_taken="Paused for rest of day",
            )
            triggered = True

        # 5. Check daily loss limit
        elif abs(float(self.stats.daily_pnl)) >= self.config.max_daily_loss_usd and self.stats.daily_pnl < 0:
            await self._trigger_daily_pause()
            self._record_event(
                KillSwitchTrigger.MAX_DAILY_LOSS,
                threshold_value=self.config.max_daily_loss_usd,
                actual_value=abs(float(self.stats.daily_pnl)),
                action_taken="Paused for rest of day",
            )
            triggered = True

        # 6. Check consecutive losses
        elif self.stats.consecutive_losses >= self.config.max_consecutive_losses:
            await self._trigger_daily_pause()
            self._record_event(
                KillSwitchTrigger.CONSECUTIVE_LOSSES,
                threshold_value=self.config.max_consecutive_losses,
                actual_value=self.stats.consecutive_losses,
                action_taken="Paused for 4 hours",
            )
            triggered = True

        # 7. Check individual positions
        for pos in positions:
            if self._check_position_loss(pos):
                await self._force_close_position(pos)
                triggered = True

        return triggered

    async def _trigger_daily_pause(self) -> None:
        """Trigger daily drawdown pause."""
        self.state = WatchdogState.PAUSED
        self.paused_until = datetime.now(timezone.utc) + timedelta(
            hours=self.config.daily_pause_hours
        )

        self._record_event(
            KillSwitchTrigger.DAILY_DRAWDOWN,
            threshold_value=self.config.daily_drawdown_pct,
            actual_value=self.stats.daily_drawdown_pct,
            action_taken=f"Paused for {self.config.daily_pause_hours} hours",
        )

        logger.warning(
            f"DAILY DRAWDOWN TRIGGER: {self.stats.daily_drawdown_pct:.1%} >= "
            f"{self.config.daily_drawdown_pct:.1%}. Paused until {self.paused_until}"
        )

        await self._notify_pause("Daily drawdown limit reached")

    async def _trigger_weekly_pause(self) -> None:
        """Trigger weekly drawdown pause."""
        self.state = WatchdogState.PAUSED
        self.paused_until = datetime.now(timezone.utc) + timedelta(
            hours=self.config.weekly_pause_hours
        )

        self._record_event(
            KillSwitchTrigger.WEEKLY_DRAWDOWN,
            threshold_value=self.config.weekly_drawdown_pct,
            actual_value=self.stats.weekly_drawdown_pct,
            action_taken=f"Paused for {self.config.weekly_pause_hours} hours",
        )

        logger.warning(
            f"WEEKLY DRAWDOWN TRIGGER: {self.stats.weekly_drawdown_pct:.1%} >= "
            f"{self.config.weekly_drawdown_pct:.1%}. Paused until {self.paused_until}"
        )

        await self._notify_pause("Weekly drawdown limit reached")

    async def _trigger_full_shutdown(self) -> None:
        """Trigger full shutdown - requires manual restart."""
        self.state = WatchdogState.SHUTDOWN

        self._record_event(
            KillSwitchTrigger.PEAK_DRAWDOWN,
            threshold_value=self.config.peak_drawdown_pct,
            actual_value=self.stats.peak_drawdown_pct,
            action_taken="FULL SHUTDOWN - manual restart required",
        )

        logger.critical(
            f"🚨 FULL SHUTDOWN: Peak drawdown {self.stats.peak_drawdown_pct:.1%} >= "
            f"{self.config.peak_drawdown_pct:.1%}. MANUAL RESTART REQUIRED."
        )

        # Close all positions
        try:
            await self.broker.close_all_positions()
        except BrokerError as e:
            logger.error(f"Failed to close positions on shutdown: {e}")

        await self._notify_shutdown()

        if self.on_shutdown:
            self.on_shutdown()

    def _check_position_loss(self, position: BrokerPosition) -> bool:
        """Check if position exceeds loss threshold."""
        if position.unrealized_pnl >= 0:
            return False

        # Calculate loss percentage
        loss_pct = abs(float(position.unrealized_pnl_pct)) / 100

        return loss_pct >= self.config.single_position_loss_pct

    async def _force_close_position(self, position: BrokerPosition) -> None:
        """Force close a position that exceeded loss threshold."""
        logger.warning(
            f"FORCE CLOSE: {position.symbol} - Loss: {position.unrealized_pnl_pct:.1f}% "
            f"exceeds {self.config.single_position_loss_pct:.1%} threshold"
        )

        self._record_event(
            KillSwitchTrigger.SINGLE_POSITION_LOSS,
            threshold_value=self.config.single_position_loss_pct,
            actual_value=abs(float(position.unrealized_pnl_pct)) / 100,
            action_taken=f"Force closed {position.symbol}",
            details={
                "symbol": position.symbol,
                "quantity": str(position.quantity),
                "unrealized_pnl": str(position.unrealized_pnl),
            }
        )

        try:
            await self.broker.close_position(position.symbol)
            await self._notify_force_close(position)
        except BrokerError as e:
            logger.error(f"Failed to force close {position.symbol}: {e}")

    def _update_high_water(self, current_equity: Decimal) -> None:
        """Update high water marks."""
        if current_equity > self.stats.daily_high_water:
            self.stats.daily_high_water = current_equity

        if current_equity > self.stats.weekly_high_water:
            self.stats.weekly_high_water = current_equity

        if current_equity > self.stats.peak_equity:
            self.stats.peak_equity = current_equity

    def _calculate_drawdowns(self, current_equity: Decimal) -> None:
        """Calculate current drawdown percentages."""
        # Daily drawdown
        if self.stats.daily_high_water > 0:
            daily_dd = (self.stats.daily_high_water - current_equity) / self.stats.daily_high_water
            self.stats.daily_drawdown_pct = max(0, float(daily_dd))
        else:
            self.stats.daily_drawdown_pct = 0

        # Weekly drawdown
        if self.stats.weekly_high_water > 0:
            weekly_dd = (self.stats.weekly_high_water - current_equity) / self.stats.weekly_high_water
            self.stats.weekly_drawdown_pct = max(0, float(weekly_dd))
        else:
            self.stats.weekly_drawdown_pct = 0

        # Peak drawdown
        if self.stats.peak_equity > 0:
            peak_dd = (self.stats.peak_equity - current_equity) / self.stats.peak_equity
            self.stats.peak_drawdown_pct = max(0, float(peak_dd))
        else:
            self.stats.peak_drawdown_pct = 0

    def _maybe_reset_stats(self, current_equity: Decimal) -> None:
        """Reset daily/weekly stats if needed."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        week_start = (datetime.now(timezone.utc) - timedelta(
            days=datetime.now(timezone.utc).weekday()
        )).strftime("%Y-%m-%d")

        # Daily reset
        if self.stats.last_reset_date != today:
            self.stats.last_reset_date = today
            self.stats.daily_high_water = current_equity
            self.stats.daily_pnl = Decimal("0")
            self.stats.daily_trades = 0
            logger.info(f"Daily stats reset for {today}")

        # Weekly reset (Monday)
        if self.stats.last_week_reset_date != week_start:
            self.stats.last_week_reset_date = week_start
            self.stats.weekly_high_water = current_equity
            self.stats.weekly_pnl = Decimal("0")
            logger.info(f"Weekly stats reset for week of {week_start}")

    def _is_pause_expired(self) -> bool:
        """Check if pause has expired."""
        if self.paused_until is None:
            return True
        return datetime.now(timezone.utc) >= self.paused_until

    def _record_event(
        self,
        trigger_type: KillSwitchTrigger,
        threshold_value: float,
        actual_value: float,
        action_taken: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a kill switch event."""
        event = KillSwitchEvent(
            timestamp=datetime.now(timezone.utc),
            trigger_type=trigger_type,
            threshold_value=threshold_value,
            actual_value=actual_value,
            action_taken=action_taken,
            details=details or {},
        )
        self.events.append(event)

        # Trim old events
        if len(self.events) > self._max_events:
            self.events = self.events[-self._max_events:]

    # === Notification Methods ===

    async def _notify_pause(self, reason: str) -> None:
        """Send pause notification."""
        if not self.notifier:
            return

        try:
            if hasattr(self.notifier, 'send_alert'):
                await self.notifier.send_alert(
                    f"⚠️ Trading PAUSED: {reason}\n"
                    f"Resume at: {self.paused_until}"
                )
        except Exception as e:
            logger.error(f"Failed to send pause notification: {e}")

    async def _notify_shutdown(self) -> None:
        """Send shutdown notification."""
        if not self.notifier:
            return

        try:
            if hasattr(self.notifier, 'send_alert'):
                await self.notifier.send_alert(
                    f"🚨 FULL SHUTDOWN TRIGGERED 🚨\n"
                    f"Peak drawdown: {self.stats.peak_drawdown_pct:.1%}\n"
                    f"Threshold: {self.config.peak_drawdown_pct:.1%}\n"
                    f"All positions closed. Manual restart required."
                )
        except Exception as e:
            logger.error(f"Failed to send shutdown notification: {e}")

    async def _notify_force_close(self, position: BrokerPosition) -> None:
        """Send force close notification."""
        if not self.notifier:
            return

        try:
            if hasattr(self.notifier, 'send_alert'):
                await self.notifier.send_alert(
                    f"⚠️ Position Force Closed: {position.symbol}\n"
                    f"Loss: {position.unrealized_pnl_pct:.1f}%\n"
                    f"P&L: ${position.unrealized_pnl}"
                )
        except Exception as e:
            logger.error(f"Failed to send force close notification: {e}")

    # === Status Methods ===

    def get_status(self) -> Dict[str, Any]:
        """Get current watchdog status."""
        return {
            "state": self.state.value,
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
            "stats": {
                "daily_high_water": str(self.stats.daily_high_water),
                "weekly_high_water": str(self.stats.weekly_high_water),
                "peak_equity": str(self.stats.peak_equity),
                "daily_drawdown_pct": f"{self.stats.daily_drawdown_pct:.2%}",
                "weekly_drawdown_pct": f"{self.stats.weekly_drawdown_pct:.2%}",
                "peak_drawdown_pct": f"{self.stats.peak_drawdown_pct:.2%}",
                "daily_trades": self.stats.daily_trades,
                "consecutive_losses": self.stats.consecutive_losses,
            },
            "config": {
                "daily_drawdown_pct": f"{self.config.daily_drawdown_pct:.1%}",
                "weekly_drawdown_pct": f"{self.config.weekly_drawdown_pct:.1%}",
                "peak_drawdown_pct": f"{self.config.peak_drawdown_pct:.1%}",
                "max_daily_trades": self.config.max_daily_trades,
                "max_daily_loss_usd": f"${self.config.max_daily_loss_usd:.2f}",
            },
            "recent_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "trigger": e.trigger_type.value,
                    "action": e.action_taken,
                }
                for e in self.events[-5:]
            ],
        }
