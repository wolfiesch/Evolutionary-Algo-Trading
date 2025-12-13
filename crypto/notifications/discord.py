"""Discord webhook notifications for crypto trading system."""
import asyncio
import logging
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
import aiohttp
import certifi

logger = logging.getLogger("notifications")


# Discord embed colors
COLOR_GREEN = 0x00FF00    # Profit / Entry
COLOR_RED = 0xFF0000      # Loss / Critical
COLOR_YELLOW = 0xFFFF00   # Warning
COLOR_BLUE = 0x0099FF     # Info / Hourly
COLOR_PURPLE = 0x9B59B6   # Daily summary


@dataclass
class RateLimiter:
    """Token bucket rate limiter for Discord webhooks."""
    max_tokens: float = 25.0  # ~25 requests per minute
    refill_rate: float = 0.4  # tokens per second (24/min)
    tokens: float = 25.0
    last_refill: float = 0.0

    def __post_init__(self):
        self.last_refill = time.monotonic()

    def acquire(self) -> float:
        """
        Try to acquire a token. Returns wait time if rate limited.

        Returns:
            0.0 if token acquired, otherwise seconds to wait
        """
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

    async def send_trade_entry(self, trade: Any) -> None:
        """
        Send trade entry notification.

        Args:
            trade: TradeLog object with entry details
        """
        try:
            embed = {
                "title": f"ENTRY LONG - {trade.coin}",
                "color": COLOR_GREEN,
                "fields": [
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
                ],
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
