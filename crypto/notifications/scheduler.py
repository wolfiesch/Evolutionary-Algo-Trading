"""Notification scheduler for periodic summaries."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .discord import DiscordNotifier

logger = logging.getLogger("notifications")


class NotificationScheduler:
    """
    Scheduler for periodic Discord notifications.

    Runs hourly and daily summaries without external cron dependencies.
    Uses asyncio tasks that run in the same event loop as the trading system.
    """

    def __init__(
        self,
        notifier: "DiscordNotifier",
        get_stats: Callable[[], dict],
    ):
        """
        Initialize scheduler.

        Args:
            notifier: Discord notifier instance
            get_stats: Callable that returns current portfolio stats
        """
        self.notifier = notifier
        self.get_stats = get_stats
        self._running = False
        self._hourly_task: Optional[asyncio.Task] = None
        self._daily_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the scheduler tasks."""
        if self._running:
            return

        self._running = True
        self._hourly_task = asyncio.create_task(self._hourly_loop())
        self._daily_task = asyncio.create_task(self._daily_loop())
        logger.info("Notification scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler tasks gracefully."""
        self._running = False

        if self._hourly_task:
            self._hourly_task.cancel()
            try:
                await self._hourly_task
            except asyncio.CancelledError:
                pass

        if self._daily_task:
            self._daily_task.cancel()
            try:
                await self._daily_task
            except asyncio.CancelledError:
                pass

        logger.info("Notification scheduler stopped")

    def _seconds_until_next_hour(self) -> float:
        """Calculate seconds until the next hour."""
        now = datetime.utcnow()
        next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        return (next_hour - now).total_seconds()

    def _seconds_until_midnight_utc(self) -> float:
        """Calculate seconds until midnight UTC."""
        now = datetime.utcnow()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return (tomorrow - now).total_seconds()

    async def _hourly_loop(self) -> None:
        """Background task for hourly summaries."""
        try:
            # Wait until the next hour
            await asyncio.sleep(self._seconds_until_next_hour())

            while self._running:
                try:
                    stats = self.get_stats()
                    await self.notifier.send_hourly_summary(stats)
                    logger.debug("Sent hourly summary")
                except Exception as e:
                    logger.error(f"Failed to send hourly summary: {e}")

                # Wait for next hour
                await asyncio.sleep(3600)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Hourly loop crashed: {e}")

    async def _daily_loop(self) -> None:
        """Background task for daily summaries."""
        try:
            # Wait until midnight UTC
            await asyncio.sleep(self._seconds_until_midnight_utc())

            while self._running:
                try:
                    stats = self.get_stats()
                    await self.notifier.send_daily_summary(stats)
                    logger.debug("Sent daily summary")
                except Exception as e:
                    logger.error(f"Failed to send daily summary: {e}")

                # Wait for next midnight
                await asyncio.sleep(86400)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Daily loop crashed: {e}")

    async def send_immediate_summary(self) -> None:
        """Send an immediate summary (useful for testing or on-demand)."""
        try:
            stats = self.get_stats()
            await self.notifier.send_hourly_summary(stats)
        except Exception as e:
            logger.error(f"Failed to send immediate summary: {e}")
