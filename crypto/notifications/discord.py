"""Discord webhook notifications for crypto trading system."""
import asyncio
import logging
import ssl
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
import aiohttp
import certifi
import requests

logger = logging.getLogger("notifications")


# Discord embed colors
COLOR_GREEN = 0x00FF00    # Profit / Entry
COLOR_RED = 0xFF0000      # Loss / Critical
COLOR_YELLOW = 0xFFFF00   # Warning
COLOR_BLUE = 0x0099FF     # Info / Hourly
COLOR_PURPLE = 0x9B59B6   # Daily summary
COLOR_ORANGE = 0xFFA500   # Warning (position health)
COLOR_DARK_RED = 0x8B0000 # Critical errors


@dataclass
class RateLimiter:
    """Thread-safe token bucket rate limiter for Discord webhooks."""
    max_tokens: float = 25.0  # ~25 requests per minute
    refill_rate: float = 0.4  # tokens per second (24/min)
    tokens: float = 25.0
    last_refill: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        self.last_refill = time.monotonic()

    def acquire(self) -> float:
        """
        Try to acquire a token. Returns wait time if rate limited.
        Thread-safe implementation.

        Returns:
            0.0 if token acquired, otherwise seconds to wait
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return 0.0
            else:
                return (1.0 - self.tokens) / self.refill_rate


class DiscordNotifier:
    """
    Discord webhook notifier for trading events.

    Features:
    - Rich embeds with colors and formatting
    - Rate limiting to avoid 429 errors
    - Async non-blocking sends
    - Retry with exponential backoff
    - All exceptions caught (never crash trading)
    """

    def __init__(self, webhook_url: str, enabled: bool = True):
        """
        Initialize Discord notifier.

        Args:
            webhook_url: Discord webhook URL
            enabled: If False, all sends are no-ops
        """
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)
        self.rate_limiter = RateLimiter()
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session with proper SSL context."""
        if self._session is None or self._session.closed:
            # Create SSL context using certifi's certificate bundle
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _send(
        self,
        embeds: list[dict],
        content: Optional[str] = None,
        retries: int = 3,
    ) -> bool:
        """
        Send message to Discord webhook with rate limiting and retries.

        Args:
            embeds: List of Discord embed objects
            content: Optional plain text content
            retries: Number of retry attempts

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        # Rate limiting
        wait_time = self.rate_limiter.acquire()
        if wait_time > 0:
            await asyncio.sleep(wait_time)

        payload = {"embeds": embeds}
        if content:
            payload["content"] = content

        for attempt in range(retries):
            try:
                session = await self._get_session()
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 204:
                        return True
                    elif response.status == 429:
                        # Rate limited by Discord
                        retry_after = float(response.headers.get("Retry-After", 5))
                        logger.warning(f"Discord rate limited, waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        logger.warning(
                            f"Discord webhook failed: {response.status} - {await response.text()}"
                        )
            except asyncio.TimeoutError:
                logger.warning(f"Discord webhook timeout (attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Discord webhook error: {e}")

            # Exponential backoff
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)

        return False

    def _send_sync(
        self,
        embeds: list[dict],
        content: Optional[str] = None,
        retries: int = 3,
    ) -> bool:
        """
        Synchronous send for non-async contexts (evolution, monitoring).

        Uses requests library internally. Shares rate limiter with async sends.

        Args:
            embeds: List of Discord embed objects
            content: Optional plain text content
            retries: Number of retry attempts

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            return True

        # Rate limiting (shared with async)
        wait_time = self.rate_limiter.acquire()
        if wait_time > 0:
            time.sleep(wait_time)

        payload = {"embeds": embeds}
        if content:
            payload["content"] = content

        for attempt in range(retries):
            try:
                response = requests.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10,
                )
                if response.status_code == 204:
                    return True
                elif response.status_code == 429:
                    # Rate limited by Discord
                    retry_after = float(response.headers.get("Retry-After", 5))
                    logger.warning(f"Discord rate limited (sync), waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.warning(
                        f"Discord webhook failed (sync): {response.status_code} - {response.text[:200]}"
                    )
            except requests.Timeout:
                logger.warning(f"Discord webhook timeout (sync, attempt {attempt + 1})")
            except Exception as e:
                logger.warning(f"Discord webhook error (sync): {e}")

            # Exponential backoff
            if attempt < retries - 1:
                time.sleep(2 ** attempt)

        return False

    def _format_price(self, price: float) -> str:
        """Format price with appropriate precision."""
        if price >= 1000:
            return f"${price:,.2f}"
        elif price >= 1:
            return f"${price:.4f}"
        else:
            return f"${price:.6f}"

    def _format_pnl(self, pnl: float, pnl_pct: float) -> str:
        """Format P&L with sign and percentage."""
        sign = "+" if pnl >= 0 else ""
        return f"{sign}${pnl:.2f} ({sign}{pnl_pct:.2f}%)"

    def _format_hold_time(self, entry_time_ms: int, exit_time_ms: int) -> str:
        """Format hold time as human-readable string."""
        seconds = (exit_time_ms - entry_time_ms) / 1000
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            return f"{hours}h {mins}m"

    async def send_trade_entry(
        self,
        trade: Any,
        stop_loss_price: Optional[float] = None,
        stop_loss_pct: Optional[float] = None,
        risk_amount: Optional[float] = None,
        current_exposure_pct: Optional[float] = None,
        open_positions: Optional[int] = None,
    ) -> None:
        """
        Send trade entry notification with enriched context.

        Args:
            trade: TradeLog object with entry details
            stop_loss_price: Stop-loss price level
            stop_loss_pct: Stop-loss distance as percentage (e.g., 3.0 for 3%)
            risk_amount: Amount at risk in USD
            current_exposure_pct: Portfolio exposure after this trade
            open_positions: Number of open positions after this trade
        """
        try:
            fields = [
                {
                    "name": "Strategy",
                    "value": trade.strategy_id,
                    "inline": True,
                },
                {
                    "name": "Price",
                    "value": f"{self._format_price(trade.price_at_signal)} -> {self._format_price(trade.simulated_fill)}",
                    "inline": True,
                },
                {
                    "name": "Size",
                    "value": f"${trade.position_size_usdt:.2f}",
                    "inline": True,
                },
            ]

            # Add stop-loss info if provided
            if stop_loss_price is not None:
                sl_text = self._format_price(stop_loss_price)
                if stop_loss_pct is not None:
                    sl_text += f" (-{stop_loss_pct:.1f}%)"
                fields.append({
                    "name": "Stop Loss",
                    "value": sl_text,
                    "inline": True,
                })

            # Add risk amount if provided
            if risk_amount is not None:
                fields.append({
                    "name": "Risk",
                    "value": f"${risk_amount:.2f}",
                    "inline": True,
                })

            # Add exposure info if provided
            if current_exposure_pct is not None:
                fields.append({
                    "name": "Exposure",
                    "value": f"{current_exposure_pct:.0f}%",
                    "inline": True,
                })

            # Add position count if provided
            if open_positions is not None:
                fields.append({
                    "name": "Open Positions",
                    "value": str(open_positions),
                    "inline": True,
                })

            # Add market context
            fields.extend([
                {
                    "name": "Market",
                    "value": trade.market_regime.replace("_", " ").title(),
                    "inline": True,
                },
                {
                    "name": "BTC Trend",
                    "value": "Bullish" if trade.btc_trend >= 0 else "Bearish",
                    "inline": True,
                },
                {
                    "name": "Volatility",
                    "value": "High" if trade.atr_regime > 0 else ("Low" if trade.atr_regime < 0 else "Normal"),
                    "inline": True,
                },
            ])

            embed = {
                "title": f"ENTRY LONG - {trade.coin}",
                "color": COLOR_GREEN,
                "fields": fields,
                "footer": {"text": f"Entry: {trade.gene_expression[:80]}..."}
                    if len(trade.gene_expression) > 80
                    else {"text": f"Entry: {trade.gene_expression}"},
                "timestamp": datetime.utcfromtimestamp(trade.timestamp / 1000).isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send trade entry notification: {e}")

    async def send_trade_exit(
        self,
        trade: Any,
        entry_time_ms: Optional[int] = None,
    ) -> None:
        """
        Send trade exit notification.

        Args:
            trade: TradeLog object with exit details
            entry_time_ms: Original entry timestamp for hold time calculation
        """
        try:
            is_profit = trade.pnl is not None and trade.pnl >= 0
            color = COLOR_GREEN if is_profit else COLOR_RED

            # Determine exit type from signal
            exit_type = "EXIT LONG"
            if "STOP_LOSS" in trade.signal:
                exit_type = "STOP LOSS"
            elif "EMERGENCY" in trade.signal:
                exit_type = "EMERGENCY CLOSE"

            fields = [
                {
                    "name": "Strategy",
                    "value": trade.strategy_id,
                    "inline": True,
                },
                {
                    "name": "Exit Price",
                    "value": self._format_price(trade.simulated_fill),
                    "inline": True,
                },
            ]

            if trade.pnl is not None:
                fields.append({
                    "name": "P&L",
                    "value": self._format_pnl(trade.pnl, trade.pnl_pct),
                    "inline": True,
                })

            if entry_time_ms:
                fields.append({
                    "name": "Hold Time",
                    "value": self._format_hold_time(entry_time_ms, trade.timestamp),
                    "inline": True,
                })

            embed = {
                "title": f"{exit_type} - {trade.coin}",
                "color": color,
                "fields": fields,
                "timestamp": datetime.utcfromtimestamp(trade.timestamp / 1000).isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send trade exit notification: {e}")

    async def send_kill_switch(
        self,
        trigger: str,
        current_equity: float,
        initial_equity: float,
        drawdown_pct: float,
        positions_closed: int = 0,
        pause_duration: Optional[str] = None,
    ) -> None:
        """
        Send kill switch alert.

        Args:
            trigger: Description of what triggered the kill switch
            current_equity: Current portfolio equity
            initial_equity: Initial portfolio equity
            drawdown_pct: Current drawdown percentage
            positions_closed: Number of positions force-closed
            pause_duration: How long trading is paused (e.g., "1 hour", "INDEFINITE")
        """
        try:
            action = f"Trading paused for {pause_duration}" if pause_duration else "FULL STOP - Manual restart required"

            embed = {
                "title": "KILL SWITCH TRIGGERED",
                "description": f"**{trigger}**\n{action}",
                "color": COLOR_RED,
                "fields": [
                    {
                        "name": "Current Equity",
                        "value": f"${current_equity:,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Initial Equity",
                        "value": f"${initial_equity:,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Drawdown",
                        "value": f"-{drawdown_pct:.1f}%",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }

            if positions_closed > 0:
                embed["fields"].append({
                    "name": "Positions Closed",
                    "value": str(positions_closed),
                    "inline": True,
                })

            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send kill switch notification: {e}")

    async def send_connection_alert(
        self,
        state: str,
        details: Optional[str] = None,
    ) -> None:
        """
        Send connection state change alert.

        Args:
            state: New connection state
            details: Additional details about the state change
        """
        try:
            is_critical = state.lower() in ["disconnected", "error"]

            embed = {
                "title": f"Connection: {state.upper()}",
                "color": COLOR_RED if is_critical else COLOR_YELLOW,
                "timestamp": datetime.utcnow().isoformat(),
            }

            if details:
                embed["description"] = details

            if is_critical:
                embed["description"] = (embed.get("description", "") +
                    "\n\n**Trading paused until connection restored.**")

            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send connection alert: {e}")

    async def send_emergency_close(
        self,
        positions_closed: int,
        reason: str,
        total_pnl: float,
    ) -> None:
        """
        Send emergency position close notification.

        Args:
            positions_closed: Number of positions closed
            reason: Reason for emergency close
            total_pnl: Total P&L from closed positions
        """
        try:
            embed = {
                "title": "EMERGENCY CLOSE",
                "description": f"**{reason}**\n{positions_closed} position(s) closed",
                "color": COLOR_RED,
                "fields": [
                    {
                        "name": "Total P&L",
                        "value": f"${total_pnl:+,.2f}",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send emergency close notification: {e}")

    async def send_hourly_summary(self, stats: dict) -> None:
        """
        Send hourly portfolio summary.

        Args:
            stats: Portfolio statistics from pool_manager.get_stats()
        """
        try:
            pnl_pct = stats.get("total_pnl_pct", 0)
            pnl_sign = "+" if pnl_pct >= 0 else ""

            embed = {
                "title": f"Hourly Summary ({datetime.utcnow().strftime('%H:%M')} UTC)",
                "color": COLOR_BLUE,
                "fields": [
                    {
                        "name": "Equity",
                        "value": f"${stats.get('paper_equity', 0):,.2f} ({pnl_sign}{pnl_pct:.2f}%)",
                        "inline": True,
                    },
                    {
                        "name": "Open Positions",
                        "value": f"{stats.get('open_positions', 0)} ({stats.get('current_exposure', 0):.0%} exposure)",
                        "inline": True,
                    },
                    {
                        "name": "Total P&L",
                        "value": f"${stats.get('total_pnl', 0):+,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Strategies",
                        "value": str(stats.get("strategies_loaded", 0)),
                        "inline": True,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Add trading status
            if stats.get("trading_paused"):
                embed["fields"].append({
                    "name": "Status",
                    "value": "PAUSED",
                    "inline": True,
                })

            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send hourly summary: {e}")

    async def send_daily_summary(self, stats: dict, day_stats: Optional[dict] = None) -> None:
        """
        Send comprehensive daily summary.

        Args:
            stats: Current portfolio statistics
            day_stats: Optional day-specific stats (trades, wins, losses)
        """
        try:
            pnl_pct = stats.get("total_pnl_pct", 0)
            pnl_sign = "+" if pnl_pct >= 0 else ""

            fields = [
                {
                    "name": "Portfolio Value",
                    "value": f"${stats.get('paper_equity', 0):,.2f}",
                    "inline": True,
                },
                {
                    "name": "Total P&L",
                    "value": f"${stats.get('total_pnl', 0):+,.2f} ({pnl_sign}{pnl_pct:.2f}%)",
                    "inline": True,
                },
                {
                    "name": "Open Positions",
                    "value": str(stats.get("open_positions", 0)),
                    "inline": True,
                },
            ]

            # Add strategy performance
            strat_perf = stats.get("strategy_performance", {})
            if strat_perf:
                # Sort by P&L descending
                sorted_strats = sorted(
                    strat_perf.items(),
                    key=lambda x: x[1].get("total_pnl", 0),
                    reverse=True,
                )

                # Top performer
                if sorted_strats:
                    top_id, top_perf = sorted_strats[0]
                    fields.append({
                        "name": "Top Strategy",
                        "value": f"{top_perf.get('name', top_id)}: ${top_perf.get('total_pnl', 0):+,.2f} ({top_perf.get('trade_count', 0)} trades)",
                        "inline": False,
                    })

                # Total trades across all strategies
                total_trades = sum(p.get("trade_count", 0) for p in strat_perf.values())
                avg_win_rate = (
                    sum(p.get("win_rate", 0) * p.get("trade_count", 0) for p in strat_perf.values())
                    / total_trades if total_trades > 0 else 0
                )

                fields.append({
                    "name": "Total Trades",
                    "value": str(total_trades),
                    "inline": True,
                })
                fields.append({
                    "name": "Avg Win Rate",
                    "value": f"{avg_win_rate:.1%}",
                    "inline": True,
                })

            embed = {
                "title": f"Daily Summary ({datetime.utcnow().strftime('%b %d, %Y')})",
                "color": COLOR_PURPLE,
                "fields": fields,
                "timestamp": datetime.utcnow().isoformat(),
            }

            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send daily summary: {e}")

    async def send_startup(self, stats: Optional[dict] = None) -> None:
        """Send system startup notification."""
        try:
            fields = []
            if stats:
                fields = [
                    {
                        "name": "Equity",
                        "value": f"${stats.get('paper_equity', 0):,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Strategies",
                        "value": str(stats.get("strategies_loaded", 0)),
                        "inline": True,
                    },
                ]

            embed = {
                "title": "Crypto Alpha System Started",
                "color": COLOR_GREEN,
                "description": "Shadow trading system is now online.",
                "fields": fields,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send startup notification: {e}")

    async def send_shutdown(self, stats: Optional[dict] = None) -> None:
        """Send system shutdown notification."""
        try:
            fields = []
            if stats:
                pnl_pct = stats.get("total_pnl_pct", 0)
                pnl_sign = "+" if pnl_pct >= 0 else ""
                fields = [
                    {
                        "name": "Final Equity",
                        "value": f"${stats.get('paper_equity', 0):,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Total P&L",
                        "value": f"${stats.get('total_pnl', 0):+,.2f} ({pnl_sign}{pnl_pct:.2f}%)",
                        "inline": True,
                    },
                ]

            embed = {
                "title": "Crypto Alpha System Shutdown",
                "color": COLOR_YELLOW,
                "description": "Shadow trading system is shutting down.",
                "fields": fields,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send shutdown notification: {e}")

    # =========================================================================
    # T0.4: Error/Exception Notifications
    # =========================================================================

    async def send_error(
        self,
        error: Exception,
        context: str,
        severity: str = "error",
    ) -> None:
        """
        Send error notification with stack trace and context.

        Args:
            error: The exception that occurred
            context: Which component failed (e.g., "Evolution", "Data Pipeline")
            severity: "error" for recoverable, "critical" for system-halting
        """
        try:
            color = COLOR_DARK_RED if severity == "critical" else COLOR_RED
            title = f"CRITICAL ERROR - {context}" if severity == "critical" else f"ERROR - {context}"

            # Get truncated stack trace
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tb_str = "".join(tb)
            if len(tb_str) > 500:
                tb_str = "..." + tb_str[-500:]

            embed = {
                "title": title,
                "color": color,
                "fields": [
                    {
                        "name": "Error Type",
                        "value": type(error).__name__,
                        "inline": True,
                    },
                    {
                        "name": "Message",
                        "value": str(error)[:200] or "No message",
                        "inline": True,
                    },
                    {
                        "name": "Stack Trace",
                        "value": f"```\n{tb_str}\n```",
                        "inline": False,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send error notification: {e}")

    def send_error_sync(
        self,
        error: Exception,
        context: str,
        severity: str = "error",
    ) -> None:
        """Synchronous version of send_error for non-async contexts."""
        try:
            color = COLOR_DARK_RED if severity == "critical" else COLOR_RED
            title = f"CRITICAL ERROR - {context}" if severity == "critical" else f"ERROR - {context}"

            # Get truncated stack trace
            tb = traceback.format_exception(type(error), error, error.__traceback__)
            tb_str = "".join(tb)
            if len(tb_str) > 500:
                tb_str = "..." + tb_str[-500:]

            embed = {
                "title": title,
                "color": color,
                "fields": [
                    {
                        "name": "Error Type",
                        "value": type(error).__name__,
                        "inline": True,
                    },
                    {
                        "name": "Message",
                        "value": str(error)[:200] or "No message",
                        "inline": True,
                    },
                    {
                        "name": "Stack Trace",
                        "value": f"```\n{tb_str}\n```",
                        "inline": False,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._send_sync([embed])
        except Exception as e:
            logger.error(f"Failed to send error notification (sync): {e}")

    # =========================================================================
    # T0.6: Position Health Warning Alerts
    # =========================================================================

    async def send_drawdown_warning(
        self,
        current_dd_pct: float,
        threshold: str,
        equity: float,
        peak_equity: float,
    ) -> None:
        """
        Send drawdown warning notification (before kill switch triggers).

        Args:
            current_dd_pct: Current drawdown as percentage (e.g., 3.5 for 3.5%)
            threshold: "warning" (3%), "elevated" (5%), "critical" (10%)
            equity: Current portfolio equity
            peak_equity: Peak portfolio equity
        """
        try:
            colors = {
                "warning": COLOR_YELLOW,
                "elevated": COLOR_ORANGE,
                "critical": COLOR_RED,
            }
            color = colors.get(threshold, COLOR_YELLOW)

            embed = {
                "title": f"DRAWDOWN {threshold.upper()}",
                "color": color,
                "fields": [
                    {
                        "name": "Current Drawdown",
                        "value": f"-{current_dd_pct:.2f}%",
                        "inline": True,
                    },
                    {
                        "name": "Current Equity",
                        "value": f"${equity:,.2f}",
                        "inline": True,
                    },
                    {
                        "name": "Peak Equity",
                        "value": f"${peak_equity:,.2f}",
                        "inline": True,
                    },
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }

            # Add threshold context
            if threshold == "warning":
                embed["description"] = "Portfolio drawdown approaching warning level. Monitoring closely."
            elif threshold == "elevated":
                embed["description"] = "Portfolio drawdown elevated. Kill switch at 5% hourly will pause trading."
            elif threshold == "critical":
                embed["description"] = "Portfolio drawdown critical. Kill switch at 15% total will halt system."

            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send drawdown warning: {e}")

    async def send_position_warning(
        self,
        symbol: str,
        strategy_id: str,
        unrealized_pnl_pct: float,
        entry_price: float,
        current_price: float,
    ) -> None:
        """
        Send per-position warning when approaching stop-loss.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            strategy_id: Strategy identifier
            unrealized_pnl_pct: Current unrealized P&L percentage (negative)
            entry_price: Position entry price
            current_price: Current market price
        """
        try:
            embed = {
                "title": f"POSITION WARNING - {symbol}",
                "color": COLOR_ORANGE,
                "fields": [
                    {
                        "name": "Strategy",
                        "value": strategy_id,
                        "inline": True,
                    },
                    {
                        "name": "Unrealized P&L",
                        "value": f"{unrealized_pnl_pct:+.2f}%",
                        "inline": True,
                    },
                    {
                        "name": "Entry Price",
                        "value": self._format_price(entry_price),
                        "inline": True,
                    },
                    {
                        "name": "Current Price",
                        "value": self._format_price(current_price),
                        "inline": True,
                    },
                ],
                "description": "Position approaching stop-loss threshold (3%).",
                "timestamp": datetime.utcnow().isoformat(),
            }
            await self._send([embed])
        except Exception as e:
            logger.error(f"Failed to send position warning: {e}")

    # =========================================================================
    # Evolution-specific notifications (sync, for EvolutionScheduler)
    # =========================================================================

    def send_evolution_start_sync(
        self,
        symbol: str,
        generations: int,
        population: int,
    ) -> None:
        """Send notification when evolution starts (sync for scheduler)."""
        try:
            embed = {
                "title": "Evolution Started",
                "color": COLOR_BLUE,
                "fields": [
                    {"name": "Symbol", "value": symbol, "inline": True},
                    {"name": "Generations", "value": str(generations), "inline": True},
                    {"name": "Population", "value": str(population), "inline": True},
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._send_sync([embed])
        except Exception as e:
            logger.error(f"Failed to send evolution start notification: {e}")

    def send_strategy_evaluated_sync(
        self,
        strategy_name: str,
        score: float,
        progress_pct: float,
        phase: str,
        is_best: bool = False,
    ) -> None:
        """Send notification when a strategy is evaluated (sync for scheduler)."""
        try:
            # Color based on score
            if score >= 3.0:
                color = COLOR_GREEN
            elif score >= 1.0:
                color = COLOR_YELLOW
            elif score > 0:
                color = COLOR_ORANGE
            else:
                color = 0x808080  # Gray - disqualified

            title = "New Best Strategy!" if is_best else "Strategy Evaluated"
            if is_best:
                color = COLOR_GREEN

            embed = {
                "title": title,
                "color": color,
                "fields": [
                    {"name": "Strategy", "value": strategy_name, "inline": True},
                    {"name": "Score", "value": f"{score:.3f}", "inline": True},
                    {"name": "Progress", "value": f"{progress_pct:.0f}%", "inline": True},
                    {"name": "Phase", "value": phase, "inline": True},
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._send_sync([embed])
        except Exception as e:
            logger.error(f"Failed to send strategy evaluated notification: {e}")

    def send_evolution_complete_sync(
        self,
        success: bool,
        best_name: Optional[str] = None,
        best_score: Optional[float] = None,
        duration_min: float = 0,
        promoted: bool = False,
    ) -> None:
        """Send notification when evolution completes (sync for scheduler)."""
        try:
            if success and best_name:
                color = COLOR_GREEN if promoted else COLOR_YELLOW
                title = "Evolution Complete" if promoted else "Evolution Complete (Not Promoted)"
                fields = [
                    {"name": "Best Strategy", "value": best_name, "inline": True},
                    {"name": "Score", "value": f"{best_score:.3f}", "inline": True},
                    {"name": "Duration", "value": f"{duration_min:.1f} min", "inline": True},
                ]
                description = "Promoted to Shadow Pool" if promoted else "Did not meet promotion criteria"
            else:
                color = COLOR_RED
                title = "Evolution Failed"
                fields = [
                    {"name": "Duration", "value": f"{duration_min:.1f} min", "inline": True},
                    {"name": "Result", "value": "No viable strategy found", "inline": True},
                ]
                description = None

            embed = {
                "title": title,
                "color": color,
                "fields": fields,
                "timestamp": datetime.utcnow().isoformat(),
            }
            if description:
                embed["description"] = description

            self._send_sync([embed])
        except Exception as e:
            logger.error(f"Failed to send evolution complete notification: {e}")


class TradeBatcher:
    """
    Batches trade notifications over a configurable interval to reduce noise.

    Usage:
        batcher = TradeBatcher(notifier, batch_interval_seconds=300)
        await batcher.start()  # Start background task
        await batcher.queue_entry(trade, ...)  # Queue trades
        await batcher.stop()  # Stop and send final batch
    """

    def __init__(
        self,
        notifier: DiscordNotifier,
        batch_interval_seconds: int = 300,
        max_batch_size: int = 20,
    ):
        self.notifier = notifier
        self.batch_interval = batch_interval_seconds
        self.max_batch_size = max_batch_size

        self._pending_entries: list[dict] = []  # List of entry trade dicts
        self._pending_exits: list[dict] = []    # List of exit trade dicts
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the background batching task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._batch_loop())
        logger.info(f"TradeBatcher started (interval: {self.batch_interval}s)")

    async def stop(self) -> None:
        """Stop the batcher and flush remaining trades."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        # Flush remaining
        await self.flush()
        logger.info("TradeBatcher stopped")

    async def queue_entry(
        self,
        trade: Any,
        stop_loss_price: Optional[float] = None,
        risk_amount: Optional[float] = None,
    ) -> None:
        """Queue a trade entry for batched notification."""
        async with self._lock:
            self._pending_entries.append({
                "coin": trade.coin,
                "strategy_id": trade.strategy_id,
                "fill_price": trade.simulated_fill,
                "size_usdt": trade.position_size_usdt,
                "stop_loss_price": stop_loss_price,
                "risk_amount": risk_amount,
                "timestamp": trade.timestamp,
            })
            # If we hit max batch size, send immediately
            if len(self._pending_entries) >= self.max_batch_size:
                await self._send_entry_batch()

    async def queue_exit(
        self,
        trade: Any,
        pnl: float,
        pnl_pct: float,
    ) -> None:
        """Queue a trade exit for batched notification."""
        async with self._lock:
            self._pending_exits.append({
                "coin": trade.coin,
                "strategy_id": trade.strategy_id,
                "fill_price": trade.simulated_fill,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "timestamp": trade.timestamp,
            })
            # If we hit max batch size, send immediately
            if len(self._pending_exits) >= self.max_batch_size:
                await self._send_exit_batch()

    async def flush(self) -> None:
        """Flush all pending notifications immediately."""
        async with self._lock:
            if self._pending_entries:
                await self._send_entry_batch()
            if self._pending_exits:
                await self._send_exit_batch()

    async def _batch_loop(self) -> None:
        """Background task that sends batched notifications periodically."""
        while self._running:
            try:
                await asyncio.sleep(self.batch_interval)
                await self.flush()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"TradeBatcher error: {e}")

    async def _send_entry_batch(self) -> None:
        """Send batched entry notifications."""
        if not self._pending_entries:
            return

        entries = self._pending_entries
        self._pending_entries = []

        # Build summary embed
        total_size = sum(e["size_usdt"] for e in entries)
        total_risk = sum(e.get("risk_amount", 0) or 0 for e in entries)

        # Group by symbol for summary
        symbols = {}
        for e in entries:
            coin = e["coin"]
            if coin not in symbols:
                symbols[coin] = {"count": 0, "total_size": 0}
            symbols[coin]["count"] += 1
            symbols[coin]["total_size"] += e["size_usdt"]

        symbol_summary = ", ".join(
            f"{coin} ({data['count']}x ${data['total_size']:.0f})"
            for coin, data in sorted(symbols.items())
        )

        embed = {
            "title": f"BATCH: {len(entries)} Entry(s)",
            "color": COLOR_GREEN,
            "fields": [
                {
                    "name": "Total Size",
                    "value": f"${total_size:,.2f}",
                    "inline": True,
                },
                {
                    "name": "Total Risk",
                    "value": f"${total_risk:,.2f}",
                    "inline": True,
                },
                {
                    "name": "Trades",
                    "value": str(len(entries)),
                    "inline": True,
                },
                {
                    "name": "Symbols",
                    "value": symbol_summary[:200] or "N/A",
                    "inline": False,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.notifier._send([embed])
        logger.debug(f"Sent batch entry notification: {len(entries)} trades")

    async def _send_exit_batch(self) -> None:
        """Send batched exit notifications."""
        if not self._pending_exits:
            return

        exits = self._pending_exits
        self._pending_exits = []

        # Calculate totals
        total_pnl = sum(e["pnl"] for e in exits)
        winners = sum(1 for e in exits if e["pnl"] >= 0)
        losers = len(exits) - winners

        # Group by symbol
        symbols = {}
        for e in exits:
            coin = e["coin"]
            if coin not in symbols:
                symbols[coin] = {"count": 0, "pnl": 0}
            symbols[coin]["count"] += 1
            symbols[coin]["pnl"] += e["pnl"]

        symbol_summary = ", ".join(
            f"{coin} ({data['count']}x ${data['pnl']:+.2f})"
            for coin, data in sorted(symbols.items(), key=lambda x: x[1]["pnl"], reverse=True)
        )

        color = COLOR_GREEN if total_pnl >= 0 else COLOR_RED

        embed = {
            "title": f"BATCH: {len(exits)} Exit(s)",
            "color": color,
            "fields": [
                {
                    "name": "Total P&L",
                    "value": f"${total_pnl:+,.2f}",
                    "inline": True,
                },
                {
                    "name": "Win/Loss",
                    "value": f"{winners}W / {losers}L",
                    "inline": True,
                },
                {
                    "name": "Trades",
                    "value": str(len(exits)),
                    "inline": True,
                },
                {
                    "name": "Symbols",
                    "value": symbol_summary[:200] or "N/A",
                    "inline": False,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.notifier._send([embed])
        logger.debug(f"Sent batch exit notification: {len(exits)} trades")
