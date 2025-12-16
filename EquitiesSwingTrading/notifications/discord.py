"""
Discord webhook notifications for equities shadow trading.

Sends rich embeds for trade entries, exits, and daily summaries.
"""
import logging
import time
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from pathlib import Path

import requests

from execution.shadow.models import TradeLog, DailySummary, PortfolioSnapshot


logger = logging.getLogger(__name__)


# Embed colors
COLOR_GREEN = 0x00FF00    # Profit, entry
COLOR_RED = 0xFF0000      # Loss, critical
COLOR_YELLOW = 0xFFFF00   # Warning
COLOR_BLUE = 0x0099FF     # Info
COLOR_PURPLE = 0x9B59B6   # Daily summary
COLOR_ORANGE = 0xFFA500   # Position warning


@dataclass
class RateLimiter:
    """Token bucket rate limiter for Discord API."""
    tokens: float = 25.0
    max_tokens: float = 25.0
    refill_rate: float = 25.0 / 60.0  # 25 per minute
    last_refill: float = 0.0
    lock: threading.Lock = None

    def __post_init__(self):
        self.last_refill = time.time()
        self.lock = threading.Lock()

    def acquire(self) -> bool:
        """Try to acquire a token. Returns True if successful."""
        with self.lock:
            now = time.time()
            # Refill tokens
            elapsed = now - self.last_refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

    def wait_for_token(self, timeout: float = 10.0) -> bool:
        """Wait until a token is available."""
        start = time.time()
        while time.time() - start < timeout:
            if self.acquire():
                return True
            time.sleep(0.1)
        return False


class DiscordNotifier:
    """
    Discord webhook notifier for equities trading signals.

    Features:
    - Trade entry/exit notifications
    - Daily summary reports
    - Kill switch alerts
    - Error notifications
    - Rate limiting to avoid 429s
    """

    def __init__(
        self,
        webhook_url: str,
        bot_name: str = "Equities Shadow Trader",
        rate_limiter: Optional[RateLimiter] = None,
    ):
        self.webhook_url = webhook_url
        self.bot_name = bot_name
        self.rate_limiter = rate_limiter or RateLimiter()
        self.session = requests.Session()

    def _send_webhook(
        self,
        embeds: list[dict],
        content: Optional[str] = None,
    ) -> bool:
        """Send webhook with rate limiting and retry."""
        if not self.rate_limiter.wait_for_token():
            logger.warning("Rate limit timeout, skipping notification")
            return False

        payload = {
            "username": self.bot_name,
            "embeds": embeds,
        }
        if content:
            payload["content"] = content

        for attempt in range(3):
            try:
                response = self.session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 204:
                    return True
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = response.json().get("retry_after", 1.0)
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                else:
                    logger.error(f"Discord webhook failed: {response.status_code} - {response.text}")
                    return False

            except Exception as e:
                logger.error(f"Discord webhook error: {e}")
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                    continue
                return False

        return False

    def send_trade_entry(self, trade: TradeLog) -> bool:
        """Send trade entry notification."""
        embed = {
            "title": f"📈 ENTRY: {trade.symbol}",
            "color": COLOR_GREEN,
            "fields": [
                {"name": "Strategy", "value": trade.strategy_id, "inline": True},
                {"name": "Price", "value": f"${trade.simulated_fill:.2f}", "inline": True},
                {"name": "Shares", "value": f"{trade.shares:.2f}", "inline": True},
                {"name": "Value", "value": f"${trade.notional_value:,.2f}", "inline": True},
                {"name": "Market", "value": trade.market_regime, "inline": True},
                {"name": "SPY Trend", "value": f"{trade.spy_trend:+.1f}", "inline": True},
            ],
            "footer": {"text": f"Date: {trade.trade_date}"},
            "timestamp": trade.timestamp,
        }

        # Add fundamental context if available
        if trade.insider_intensity is not None:
            embed["fields"].append({
                "name": "Insider", "value": f"{trade.insider_intensity:+.2f}", "inline": True
            })
        if trade.revenue_cagr is not None:
            embed["fields"].append({
                "name": "Rev CAGR", "value": f"{trade.revenue_cagr:+.1%}", "inline": True
            })

        return self._send_webhook([embed])

    def send_trade_exit(self, trade: TradeLog) -> bool:
        """Send trade exit notification."""
        pnl = trade.pnl or 0.0
        pnl_pct = trade.pnl_pct or 0.0

        # Color based on P&L
        color = COLOR_GREEN if pnl >= 0 else COLOR_RED

        # Emoji based on exit reason
        emoji = "🔴" if trade.exit_reason == "stop_loss" else "📉"

        embed = {
            "title": f"{emoji} EXIT: {trade.symbol}",
            "color": color,
            "fields": [
                {"name": "Strategy", "value": trade.strategy_id, "inline": True},
                {"name": "Exit Price", "value": f"${trade.simulated_fill:.2f}", "inline": True},
                {"name": "P&L", "value": f"${pnl:+,.2f} ({pnl_pct:+.1f}%)", "inline": True},
                {"name": "Days Held", "value": str(trade.days_held or 0), "inline": True},
                {"name": "Exit Reason", "value": trade.exit_reason or "signal", "inline": True},
                {"name": "Market", "value": trade.market_regime, "inline": True},
            ],
            "footer": {"text": f"Date: {trade.trade_date}"},
            "timestamp": trade.timestamp,
        }

        return self._send_webhook([embed])

    def send_daily_summary(self, summary: DailySummary) -> bool:
        """Send end-of-day summary."""
        # Determine emoji based on performance
        if summary.daily_pnl >= 0:
            emoji = "📊"
            color = COLOR_PURPLE
        else:
            emoji = "📉"
            color = COLOR_ORANGE

        # Build position list
        position_text = f"{summary.open_positions} open ({summary.exposure_pct:.0f}% exposure)"

        # Build activity summary
        activity = []
        if summary.entries > 0:
            activity.append(f"+{summary.entries} entries")
        if summary.exits > 0:
            activity.append(f"-{summary.exits} exits")
        if summary.stop_losses > 0:
            activity.append(f"🔴 {summary.stop_losses} stops")
        activity_text = ", ".join(activity) if activity else "No activity"

        embed = {
            "title": f"{emoji} Daily Summary: {summary.date}",
            "color": color,
            "fields": [
                {"name": "Daily P&L", "value": f"${summary.daily_pnl:+,.2f} ({summary.daily_pnl_pct:+.1f}%)", "inline": True},
                {"name": "Equity", "value": f"${summary.ending_equity:,.2f}", "inline": True},
                {"name": "Positions", "value": position_text, "inline": True},
                {"name": "Activity", "value": activity_text, "inline": False},
                {"name": "Market", "value": f"{summary.market_regime} | SPY {summary.spy_change_pct:+.1f}% | VIX {summary.vix_level:.1f}", "inline": False},
            ],
        }

        # Add best/worst trades if any
        if summary.best_trade:
            embed["fields"].append({
                "name": "Best Trade",
                "value": f"{summary.best_trade['symbol']}: ${summary.best_trade['pnl']:+,.2f}",
                "inline": True,
            })
        if summary.worst_trade:
            embed["fields"].append({
                "name": "Worst Trade",
                "value": f"{summary.worst_trade['symbol']}: ${summary.worst_trade['pnl']:+,.2f}",
                "inline": True,
            })

        return self._send_webhook([embed])

    def send_kill_switch(
        self,
        trigger: str,
        drawdown_pct: float,
        equity: float,
        positions_closed: int,
    ) -> bool:
        """Send kill switch activation alert."""
        embed = {
            "title": "🚨 KILL SWITCH ACTIVATED",
            "color": COLOR_RED,
            "description": f"**Trigger:** {trigger}\n**Action:** All positions closed, trading paused",
            "fields": [
                {"name": "Drawdown", "value": f"{drawdown_pct:.1f}%", "inline": True},
                {"name": "Equity", "value": f"${equity:,.2f}", "inline": True},
                {"name": "Positions Closed", "value": str(positions_closed), "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed], content="@here Kill switch triggered!")

    def send_drawdown_warning(
        self,
        level: str,  # "warning", "elevated", "critical"
        drawdown_pct: float,
        equity: float,
    ) -> bool:
        """Send drawdown warning."""
        colors = {
            "warning": COLOR_YELLOW,
            "elevated": COLOR_ORANGE,
            "critical": COLOR_RED,
        }
        emojis = {
            "warning": "⚠️",
            "elevated": "🔶",
            "critical": "🔴",
        }

        embed = {
            "title": f"{emojis.get(level, '⚠️')} Drawdown {level.upper()}",
            "color": colors.get(level, COLOR_YELLOW),
            "fields": [
                {"name": "Drawdown", "value": f"{drawdown_pct:.1f}%", "inline": True},
                {"name": "Equity", "value": f"${equity:,.2f}", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed])

    def send_position_warning(
        self,
        symbol: str,
        unrealized_pnl_pct: float,
        stop_loss_pct: float,
    ) -> bool:
        """Send warning when position is approaching stop loss."""
        embed = {
            "title": f"⚠️ Position Warning: {symbol}",
            "color": COLOR_ORANGE,
            "fields": [
                {"name": "Unrealized P&L", "value": f"{unrealized_pnl_pct:+.1f}%", "inline": True},
                {"name": "Stop Loss", "value": f"-{stop_loss_pct:.1f}%", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed])

    def send_startup(
        self,
        strategies: list[str],
        equity: float,
        open_positions: int,
    ) -> bool:
        """Send startup notification."""
        embed = {
            "title": "🚀 Equities Shadow Trader Started",
            "color": COLOR_BLUE,
            "fields": [
                {"name": "Strategies", "value": ", ".join(strategies) or "None", "inline": False},
                {"name": "Starting Equity", "value": f"${equity:,.2f}", "inline": True},
                {"name": "Open Positions", "value": str(open_positions), "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed])

    def send_shutdown(
        self,
        reason: str,
        equity: float,
        total_pnl: float,
    ) -> bool:
        """Send shutdown notification."""
        embed = {
            "title": "🛑 Equities Shadow Trader Stopped",
            "color": COLOR_BLUE,
            "fields": [
                {"name": "Reason", "value": reason, "inline": False},
                {"name": "Final Equity", "value": f"${equity:,.2f}", "inline": True},
                {"name": "Total P&L", "value": f"${total_pnl:+,.2f}", "inline": True},
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed])

    def send_error(self, error: str, context: Optional[str] = None) -> bool:
        """Send error notification."""
        description = f"```\n{error}\n```"
        if context:
            description = f"**Context:** {context}\n{description}"

        embed = {
            "title": "❌ Error",
            "color": COLOR_RED,
            "description": description[:2000],  # Discord limit
            "timestamp": datetime.utcnow().isoformat(),
        }

        return self._send_webhook([embed])

    def send_portfolio_snapshot(self, snapshot: PortfolioSnapshot) -> bool:
        """Send portfolio status snapshot."""
        embed = {
            "title": f"📊 Portfolio Snapshot",
            "color": COLOR_BLUE,
            "fields": [
                {"name": "Equity", "value": f"${snapshot.equity:,.2f}", "inline": True},
                {"name": "Daily P&L", "value": f"${snapshot.daily_pnl:+,.2f} ({snapshot.daily_pnl_pct:+.1f}%)", "inline": True},
                {"name": "Total P&L", "value": f"${snapshot.total_pnl:+,.2f} ({snapshot.total_pnl_pct:+.1f}%)", "inline": True},
                {"name": "Positions", "value": str(snapshot.open_positions), "inline": True},
                {"name": "Exposure", "value": f"{snapshot.exposure_pct:.0f}%", "inline": True},
                {"name": "Max DD", "value": f"{snapshot.max_drawdown_pct:.1f}%", "inline": True},
                {"name": "Trades", "value": str(snapshot.total_trades), "inline": True},
                {"name": "Win Rate", "value": f"{snapshot.win_rate:.0%}", "inline": True},
                {"name": "Market", "value": snapshot.market_regime, "inline": True},
            ],
            "footer": {"text": f"Date: {snapshot.trade_date}"},
            "timestamp": snapshot.timestamp,
        }

        return self._send_webhook([embed])
