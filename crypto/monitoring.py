"""
Monitoring and alerts for the evolution system.

Provides a CLI dashboard and alerting for:
- Evolution run status and history
- Shadow pool health
- Strategy performance tracking
- System health checks
- Paper equity and drawdown monitoring
- Webhook alerts (Slack/Discord)
- Daily performance reports

Usage:
    # Show dashboard
    python monitoring.py

    # Watch mode (refresh every 30s)
    python monitoring.py --watch

    # Check specific component
    python monitoring.py --check-shadow-pool
    python monitoring.py --check-evolution-health

    # Send webhook alert
    python monitoring.py --send-alert "Test message"

    # Generate daily report
    python monitoring.py --daily-report
"""
import argparse
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crypto.config import settings
from crypto.data.storage.repository import CandleRepository

from shared.evolution.persistence import (
    StrategyStore,
    list_strategies,
    get_shadow_pool_summary,
)

logger = logging.getLogger(__name__)


# Alert thresholds (from CLAUDE.md)
ALERT_THRESHOLDS = {
    "shadow_dd_warning": 0.05,      # 5% drawdown warning
    "shadow_dd_critical": 0.10,     # 10% drawdown critical
    "shadow_dd_emergency": 0.15,    # 15% drawdown emergency
    "no_trades_warning_hours": 24,  # No trades warning
    "data_stale_minutes": 60,       # Data staleness critical
}


class WebhookAlerter:
    """
    Send alerts via webhook (Slack/Discord compatible).

    Supports both Slack and Discord webhook formats.
    Set ALERT_WEBHOOK_URL environment variable.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.environ.get("ALERT_WEBHOOK_URL")
        self.is_discord = self.webhook_url and "discord" in self.webhook_url.lower() if self.webhook_url else False

    def send(self, message: str, level: str = "info") -> bool:
        """
        Send alert message via webhook.

        Args:
            message: Alert message
            level: Alert level (info, warning, critical)

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            logger.warning("No webhook URL configured (set ALERT_WEBHOOK_URL)")
            return False

        # Format for Discord vs Slack
        if self.is_discord:
            # Discord format
            payload = {
                "content": f"**[{level.upper()}]** {message}",
                "username": "Crypto Alpha Bot",
            }
        else:
            # Slack format
            emoji = {"info": ":information_source:", "warning": ":warning:", "critical": ":rotating_light:"}.get(level, ":robot_face:")
            payload = {
                "text": f"{emoji} *[{level.upper()}]* {message}",
                "username": "Crypto Alpha Bot",
            }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status == 200 or response.status == 204
        except urllib.error.URLError as e:
            logger.error(f"Failed to send webhook alert: {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook error: {e}")
            return False

    def send_daily_report(self, report: dict) -> bool:
        """
        Send formatted daily report via webhook.

        Args:
            report: Report dictionary with metrics

        Returns:
            True if sent successfully
        """
        if not self.webhook_url:
            return False

        # Format report message
        pnl_emoji = "📈" if report.get("daily_pnl", 0) >= 0 else "📉"

        message_lines = [
            f"*Daily Performance Report* - {report.get('date', 'N/A')}",
            "",
            f"{pnl_emoji} *Paper Equity:* ${report.get('paper_equity', 0):,.2f}",
            f"*Daily P&L:* ${report.get('daily_pnl', 0):,.2f} ({report.get('daily_pnl_pct', 0):.2f}%)",
            f"*Cumulative P&L:* ${report.get('total_pnl', 0):,.2f} ({report.get('total_pnl_pct', 0):.2f}%)",
            f"*Max Drawdown:* {report.get('max_drawdown', 0):.2f}%",
            "",
            f"*Trades Today:* {report.get('trades_today', 0)}",
            f"*Win Rate:* {report.get('win_rate', 0):.1%}",
            f"*Active Strategies:* {report.get('active_strategies', 0)}",
            "",
            f"*Data Status:* {report.get('data_status', 'Unknown')}",
            f"*System Uptime:* {report.get('uptime_hours', 0):.1f} hours",
        ]

        message = "\n".join(message_lines)
        return self.send(message, level="info")


class EvolutionMonitor:
    """
    Monitoring dashboard for evolution system.
    """

    def __init__(
        self,
        strategy_store_dir: Optional[Path] = None,
        shadow_pool_dir: Optional[Path] = None,
        logs_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        self.strategy_store_dir = strategy_store_dir or (settings.logs_dir / "strategies")
        self.shadow_pool_dir = shadow_pool_dir or (settings.logs_dir / "shadow_pool")
        self.logs_dir = logs_dir or settings.logs_dir
        self.db_path = db_path or settings.sqlite_path

        self.scheduler_history_path = self.logs_dir / "scheduler_history.jsonl"
        self.shadow_trades_path = self.logs_dir / "shadow_trades.jsonl"
        self.daily_reports_dir = self.logs_dir / "daily_reports"
        self.daily_reports_dir.mkdir(parents=True, exist_ok=True)

        # Alerter
        self.alerter = WebhookAlerter()

    def get_data_status(self) -> dict:
        """Get status of candle data."""
        try:
            repo = CandleRepository(self.db_path)
            symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

            symbol_stats = {}
            for symbol in symbols:
                count = repo.count(symbol)
                latest = repo.get_latest(symbol, limit=1)

                if latest:
                    last_ts = latest[0].timestamp
                    last_time = datetime.fromtimestamp(last_ts / 1000)
                    age_minutes = (datetime.now() - last_time).total_seconds() / 60
                else:
                    last_time = None
                    age_minutes = None

                symbol_stats[symbol] = {
                    "count": count,
                    "last_update": last_time.isoformat() if last_time else None,
                    "age_minutes": age_minutes,
                    "status": "OK" if age_minutes and age_minutes < 60 else "STALE" if age_minutes else "NO DATA",
                }

            return {
                "database": str(self.db_path),
                "symbols": symbol_stats,
                "total_candles": sum(s["count"] for s in symbol_stats.values()),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_evolution_status(self) -> dict:
        """Get status of recent evolution runs."""
        if not self.scheduler_history_path.exists():
            return {
                "total_runs": 0,
                "recent_runs": [],
                "status": "NO RUNS YET",
            }

        runs = []
        try:
            with open(self.scheduler_history_path, "r") as f:
                for line in f:
                    if line.strip():
                        runs.append(json.loads(line))
        except Exception as e:
            return {"error": str(e)}

        if not runs:
            return {
                "total_runs": 0,
                "recent_runs": [],
                "status": "NO RUNS YET",
            }

        # Get recent runs (last 10)
        recent = runs[-10:]
        recent.reverse()

        # Calculate success rate
        recent_success = sum(1 for r in runs[-10:] if r.get("success", False))
        success_rate = recent_success / min(10, len(runs))

        # Check last run
        last_run = runs[-1]
        last_time = datetime.fromisoformat(last_run["timestamp"])
        hours_since = (datetime.utcnow() - last_time).total_seconds() / 3600

        status = "OK"
        if hours_since > 48:
            status = "WARNING - No run in 48+ hours"
        elif not last_run.get("success", False):
            status = "WARNING - Last run failed"

        return {
            "total_runs": len(runs),
            "recent_runs": recent,
            "success_rate": success_rate,
            "last_run_time": last_run["timestamp"],
            "hours_since_last": hours_since,
            "status": status,
        }

    def get_strategy_pool_status(self) -> dict:
        """Get status of evolved strategy pool."""
        try:
            strategies = list_strategies(self.strategy_store_dir)

            if not strategies:
                return {
                    "total": 0,
                    "by_status": {},
                    "best_strategy": None,
                    "status": "EMPTY",
                }

            # Count by status
            by_status = {}
            for s in strategies:
                by_status[s.status] = by_status.get(s.status, 0) + 1

            # Get best non-retired strategy
            active = [s for s in strategies if s.status != "retired"]
            best = active[0] if active else None

            return {
                "total": len(strategies),
                "by_status": by_status,
                "best_strategy": {
                    "name": best.name,
                    "score": best.final_score,
                    "sharpe": best.sharpe_ratio,
                    "status": best.status,
                } if best else None,
                "status": "OK" if active else "NO ACTIVE STRATEGIES",
            }
        except Exception as e:
            return {"error": str(e)}

    def get_shadow_pool_status(self) -> dict:
        """Get status of shadow trading pool."""
        try:
            summary = get_shadow_pool_summary(self.shadow_pool_dir)

            if summary["count"] == 0:
                return {
                    "count": 0,
                    "strategies": [],
                    "status": "EMPTY - No strategies in shadow pool",
                }

            return {
                "count": summary["count"],
                "strategies": summary["strategies"],
                "avg_sharpe": summary.get("avg_sharpe", 0),
                "avg_max_dd": summary.get("avg_max_dd", 0),
                "status": "OK",
            }
        except Exception as e:
            return {"error": str(e)}

    def get_shadow_trading_status(self) -> dict:
        """Get status of shadow trading activity."""
        if not self.shadow_trades_path.exists():
            return {
                "total_trades": 0,
                "recent_trades": [],
                "status": "NO TRADES YET",
            }

        trades = []
        try:
            with open(self.shadow_trades_path, "r") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except Exception as e:
            return {"error": str(e)}

        if not trades:
            return {
                "total_trades": 0,
                "recent_trades": [],
                "status": "NO TRADES YET",
            }

        # Recent trades (last 10)
        recent = trades[-10:]
        recent.reverse()

        # Calculate stats
        exits = [t for t in trades if t.get("pnl") is not None]
        if exits:
            total_pnl = sum(t["pnl"] for t in exits)
            win_count = sum(1 for t in exits if t["pnl"] >= 0)
            win_rate = win_count / len(exits)
        else:
            total_pnl = 0
            win_rate = 0

        # Check recency
        last_time = datetime.fromtimestamp(trades[-1]["timestamp"] / 1000)
        hours_since = (datetime.now() - last_time).total_seconds() / 3600

        status = "OK"
        if hours_since > 24:
            status = "INFO - No trades in 24+ hours"

        return {
            "total_trades": len(trades),
            "completed_trades": len(exits),
            "total_pnl": total_pnl,
            "win_rate": win_rate,
            "recent_trades": recent[:5],  # Last 5 for display
            "last_trade_time": last_time.isoformat(),
            "hours_since_last": hours_since,
            "status": status,
        }

    def get_paper_equity_status(self) -> dict:
        """
        Get paper equity and drawdown status.

        Calculates current equity, P&L, and drawdown from trade history.
        """
        initial_equity = settings.initial_equity

        if not self.shadow_trades_path.exists():
            return {
                "paper_equity": initial_equity,
                "initial_equity": initial_equity,
                "total_pnl": 0.0,
                "total_pnl_pct": 0.0,
                "max_drawdown": 0.0,
                "current_drawdown": 0.0,
                "peak_equity": initial_equity,
                "status": "OK - No trades yet",
            }

        # Parse all trades
        trades = []
        try:
            with open(self.shadow_trades_path, "r") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except Exception as e:
            return {"error": str(e)}

        # Calculate equity curve
        equity = initial_equity
        peak_equity = initial_equity
        max_drawdown = 0.0

        for trade in trades:
            if trade.get("pnl") is not None:
                equity += trade["pnl"]

                if equity > peak_equity:
                    peak_equity = equity

                current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
                if current_dd > max_drawdown:
                    max_drawdown = current_dd

        total_pnl = equity - initial_equity
        total_pnl_pct = (total_pnl / initial_equity) * 100 if initial_equity > 0 else 0
        current_dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0

        # Determine status based on thresholds
        status = "OK"
        if current_dd >= ALERT_THRESHOLDS["shadow_dd_emergency"]:
            status = "EMERGENCY - Drawdown > 15%"
        elif current_dd >= ALERT_THRESHOLDS["shadow_dd_critical"]:
            status = "CRITICAL - Drawdown > 10%"
        elif current_dd >= ALERT_THRESHOLDS["shadow_dd_warning"]:
            status = "WARNING - Drawdown > 5%"

        return {
            "paper_equity": equity,
            "initial_equity": initial_equity,
            "total_pnl": total_pnl,
            "total_pnl_pct": total_pnl_pct,
            "max_drawdown": max_drawdown * 100,  # Convert to percentage
            "current_drawdown": current_dd * 100,
            "peak_equity": peak_equity,
            "status": status,
        }

    def get_daily_performance(self, date: Optional[datetime] = None) -> dict:
        """
        Get performance metrics for a specific day.

        Args:
            date: Date to get metrics for (defaults to today)

        Returns:
            Dictionary with daily metrics
        """
        target_date = date or datetime.utcnow()
        day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        if not self.shadow_trades_path.exists():
            return {
                "date": day_start.strftime("%Y-%m-%d"),
                "trades_today": 0,
                "daily_pnl": 0.0,
                "daily_pnl_pct": 0.0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
            }

        trades = []
        try:
            with open(self.shadow_trades_path, "r") as f:
                for line in f:
                    if line.strip():
                        trade = json.loads(line)
                        trade_time = datetime.fromtimestamp(trade["timestamp"] / 1000)
                        if day_start <= trade_time < day_end:
                            trades.append(trade)
        except Exception as e:
            return {"error": str(e)}

        # Calculate daily metrics
        exits = [t for t in trades if t.get("pnl") is not None]
        daily_pnl = sum(t["pnl"] for t in exits) if exits else 0
        wins = sum(1 for t in exits if t["pnl"] >= 0)
        losses = len(exits) - wins

        return {
            "date": day_start.strftime("%Y-%m-%d"),
            "trades_today": len(exits),
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": (daily_pnl / settings.initial_equity) * 100,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / len(exits) if exits else 0.0,
        }

    def get_slippage_analysis(self) -> dict:
        """
        Analyze realized slippage from shadow trades.

        Calculates slippage statistics per market regime and overall
        to help calibrate the backtest friction model.

        Returns:
            Dictionary with slippage statistics
        """
        if not self.shadow_trades_path.exists():
            return {
                "total_trades": 0,
                "avg_slippage_pct": 0.0,
                "by_regime": {},
                "status": "NO DATA",
            }

        trades = []
        try:
            with open(self.shadow_trades_path, "r") as f:
                for line in f:
                    if line.strip():
                        trades.append(json.loads(line))
        except Exception as e:
            return {"error": str(e)}

        if not trades:
            return {
                "total_trades": 0,
                "avg_slippage_pct": 0.0,
                "by_regime": {},
                "status": "NO DATA",
            }

        # Filter trades with slippage data
        trades_with_slippage = [
            t for t in trades
            if t.get("implied_slippage_pct") is not None
        ]

        if not trades_with_slippage:
            return {
                "total_trades": len(trades),
                "trades_with_slippage": 0,
                "avg_slippage_pct": 0.0,
                "by_regime": {},
                "status": "NO SLIPPAGE DATA (old trades)",
            }

        # Calculate overall slippage
        slippages = [abs(t["implied_slippage_pct"]) for t in trades_with_slippage]
        avg_slippage = sum(slippages) / len(slippages)
        max_slippage = max(slippages)
        min_slippage = min(slippages)

        # Calculate by regime
        by_regime = {}
        for trade in trades_with_slippage:
            regime = trade.get("market_regime", "unknown")
            if regime not in by_regime:
                by_regime[regime] = {"slippages": [], "count": 0}
            by_regime[regime]["slippages"].append(abs(trade["implied_slippage_pct"]))
            by_regime[regime]["count"] += 1

        # Calculate averages per regime
        regime_stats = {}
        for regime, data in by_regime.items():
            regime_stats[regime] = {
                "count": data["count"],
                "avg_slippage_pct": sum(data["slippages"]) / len(data["slippages"]),
                "max_slippage_pct": max(data["slippages"]),
            }

        # Calculate by signal type (entry vs exit)
        entries = [t for t in trades_with_slippage if "ENTRY" in t.get("signal", "")]
        exits = [t for t in trades_with_slippage if "EXIT" in t.get("signal", "")]

        entry_slippage = sum(abs(t["implied_slippage_pct"]) for t in entries) / len(entries) if entries else 0
        exit_slippage = sum(abs(t["implied_slippage_pct"]) for t in exits) / len(exits) if exits else 0

        # Compare to configured friction
        configured_friction = settings.friction_per_side * 100  # Convert to pct

        return {
            "total_trades": len(trades),
            "trades_with_slippage": len(trades_with_slippage),
            "avg_slippage_pct": avg_slippage,
            "max_slippage_pct": max_slippage,
            "min_slippage_pct": min_slippage,
            "entry_avg_slippage_pct": entry_slippage,
            "exit_avg_slippage_pct": exit_slippage,
            "configured_friction_pct": configured_friction,
            "friction_accurate": abs(avg_slippage - configured_friction) < 0.1,  # Within 0.1%
            "by_regime": regime_stats,
            "status": "OK",
        }

    def generate_daily_report(self, send_webhook: bool = True) -> dict:
        """
        Generate comprehensive daily performance report.

        Args:
            send_webhook: Whether to send report via webhook

        Returns:
            Report dictionary
        """
        equity_status = self.get_paper_equity_status()
        daily_perf = self.get_daily_performance()
        shadow_pool = self.get_shadow_pool_status()
        data_status = self.get_data_status()

        # Determine overall data status
        data_ok = all(
            s.get("status") == "OK"
            for s in data_status.get("symbols", {}).values()
        ) if "symbols" in data_status else False

        report = {
            "date": daily_perf.get("date"),
            "generated_at": datetime.utcnow().isoformat(),
            "paper_equity": equity_status.get("paper_equity", 0),
            "daily_pnl": daily_perf.get("daily_pnl", 0),
            "daily_pnl_pct": daily_perf.get("daily_pnl_pct", 0),
            "total_pnl": equity_status.get("total_pnl", 0),
            "total_pnl_pct": equity_status.get("total_pnl_pct", 0),
            "max_drawdown": equity_status.get("max_drawdown", 0),
            "current_drawdown": equity_status.get("current_drawdown", 0),
            "trades_today": daily_perf.get("trades_today", 0),
            "win_rate": daily_perf.get("win_rate", 0),
            "active_strategies": shadow_pool.get("count", 0),
            "data_status": "OK" if data_ok else "ISSUES",
            "uptime_hours": 0,  # [*TO-DO*] - Track actual uptime
        }

        # Save report to file
        report_filename = f"report_{daily_perf.get('date', 'unknown')}.json"
        report_path = self.daily_reports_dir / report_filename
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        # Send via webhook if configured
        if send_webhook and self.alerter.webhook_url:
            self.alerter.send_daily_report(report)

        return report

    def send_alert(self, message: str, level: str = "warning") -> bool:
        """
        Send an alert via webhook.

        Args:
            message: Alert message
            level: Alert level (info, warning, critical)

        Returns:
            True if sent successfully
        """
        return self.alerter.send(message, level)

    def print_dashboard(self):
        """Print the full monitoring dashboard."""
        print("\n" + "=" * 70)
        print("CRYPTO EVOLUTION SYSTEM MONITOR")
        print(f"Time: {datetime.utcnow().isoformat()} UTC")
        print("=" * 70)

        # Data Status
        print("\n📊 DATA STATUS")
        print("-" * 40)
        data = self.get_data_status()
        if "error" in data:
            print(f"  ERROR: {data['error']}")
        else:
            print(f"  Database: {data['database']}")
            print(f"  Total candles: {data['total_candles']:,}")
            for symbol, stats in data["symbols"].items():
                status_icon = "✅" if stats["status"] == "OK" else "⚠️" if stats["status"] == "STALE" else "❌"
                print(f"    {status_icon} {symbol}: {stats['count']:,} candles", end="")
                if stats["age_minutes"]:
                    print(f" (last update: {stats['age_minutes']:.0f} min ago)")
                else:
                    print(" (no data)")

        # Evolution Status
        print("\n🧬 EVOLUTION STATUS")
        print("-" * 40)
        evo = self.get_evolution_status()
        if "error" in evo:
            print(f"  ERROR: {evo['error']}")
        else:
            status_icon = "✅" if evo["status"] == "OK" else "⚠️"
            print(f"  {status_icon} Status: {evo['status']}")
            print(f"  Total runs: {evo['total_runs']}")
            if evo["total_runs"] > 0:
                print(f"  Success rate (last 10): {evo['success_rate']:.0%}")
                print(f"  Last run: {evo.get('last_run_time', 'N/A')}")
                print(f"  Hours since last: {evo.get('hours_since_last', 0):.1f}")

        # Strategy Pool Status
        print("\n📦 STRATEGY POOL")
        print("-" * 40)
        pool = self.get_strategy_pool_status()
        if "error" in pool:
            print(f"  ERROR: {pool['error']}")
        else:
            status_icon = "✅" if pool["status"] == "OK" else "⚠️" if pool["total"] > 0 else "❌"
            print(f"  {status_icon} Status: {pool['status']}")
            print(f"  Total strategies: {pool['total']}")
            if pool["by_status"]:
                for status, count in pool["by_status"].items():
                    print(f"    {status}: {count}")
            if pool["best_strategy"]:
                best = pool["best_strategy"]
                print(f"  Best: {best['name']} (Score: {best['score']:.3f}, Sharpe: {best['sharpe']:.2f})")

        # Shadow Pool Status
        print("\n🌑 SHADOW POOL")
        print("-" * 40)
        shadow = self.get_shadow_pool_status()
        if "error" in shadow:
            print(f"  ERROR: {shadow['error']}")
        else:
            status_icon = "✅" if shadow["status"] == "OK" else "⚠️"
            print(f"  {status_icon} Status: {shadow['status']}")
            print(f"  Active strategies: {shadow['count']}")
            if shadow["count"] > 0:
                print(f"  Avg Sharpe: {shadow.get('avg_sharpe', 0):.2f}")
                print(f"  Avg Max DD: {shadow.get('avg_max_dd', 0):.1%}")

        # Shadow Trading Status
        print("\n💹 SHADOW TRADING")
        print("-" * 40)
        trading = self.get_shadow_trading_status()
        if "error" in trading:
            print(f"  ERROR: {trading['error']}")
        else:
            status_icon = "✅" if trading["status"] == "OK" else "ℹ️"
            print(f"  {status_icon} Status: {trading['status']}")
            print(f"  Total trades: {trading['total_trades']}")
            if trading["completed_trades"] > 0:
                print(f"  Completed: {trading['completed_trades']}")
                print(f"  Total P&L: ${trading['total_pnl']:.2f}")
                print(f"  Win rate: {trading['win_rate']:.1%}")

        # Paper Equity & Drawdown Status
        print("\n💰 PAPER EQUITY")
        print("-" * 40)
        equity = self.get_paper_equity_status()
        if "error" in equity:
            print(f"  ERROR: {equity['error']}")
        else:
            pnl_icon = "📈" if equity["total_pnl"] >= 0 else "📉"
            dd_icon = "✅" if equity["current_drawdown"] < 5 else "⚠️" if equity["current_drawdown"] < 10 else "🚨"

            print(f"  {pnl_icon} Paper Equity: ${equity['paper_equity']:,.2f}")
            print(f"  Total P&L: ${equity['total_pnl']:,.2f} ({equity['total_pnl_pct']:.2f}%)")
            print(f"  {dd_icon} Current Drawdown: {equity['current_drawdown']:.2f}%")
            print(f"  Max Drawdown: {equity['max_drawdown']:.2f}%")
            print(f"  Peak Equity: ${equity['peak_equity']:,.2f}")
            if equity["status"] != "OK":
                print(f"  ⚠️ {equity['status']}")

        # Daily Performance
        print("\n📅 TODAY'S PERFORMANCE")
        print("-" * 40)
        daily = self.get_daily_performance()
        if "error" in daily:
            print(f"  ERROR: {daily['error']}")
        else:
            daily_icon = "📈" if daily["daily_pnl"] >= 0 else "📉"
            print(f"  {daily_icon} Daily P&L: ${daily['daily_pnl']:,.2f} ({daily['daily_pnl_pct']:.2f}%)")
            print(f"  Trades today: {daily['trades_today']}")
            if daily["trades_today"] > 0:
                print(f"  Win/Loss: {daily['wins']}/{daily['losses']}")
                print(f"  Win rate: {daily['win_rate']:.1%}")

        # Slippage Calibration
        print("\n📊 SLIPPAGE CALIBRATION")
        print("-" * 40)
        slippage = self.get_slippage_analysis()
        if "error" in slippage:
            print(f"  ERROR: {slippage['error']}")
        elif slippage.get("trades_with_slippage", 0) == 0:
            print(f"  Status: {slippage.get('status', 'NO DATA')}")
            print(f"  Total trades: {slippage.get('total_trades', 0)}")
        else:
            accuracy_icon = "✅" if slippage.get("friction_accurate", False) else "⚠️"
            print(f"  Trades with data: {slippage['trades_with_slippage']}")
            print(f"  Avg slippage: {slippage['avg_slippage_pct']:.3f}%")
            print(f"  Configured friction: {slippage['configured_friction_pct']:.3f}%")
            print(f"  {accuracy_icon} Friction accuracy: {'Within 0.1%' if slippage.get('friction_accurate') else 'CALIBRATION NEEDED'}")
            print(f"  Entry slippage: {slippage.get('entry_avg_slippage_pct', 0):.3f}%")
            print(f"  Exit slippage: {slippage.get('exit_avg_slippage_pct', 0):.3f}%")
            if slippage.get("by_regime"):
                print("  By regime:")
                for regime, stats in slippage["by_regime"].items():
                    print(f"    {regime}: {stats['avg_slippage_pct']:.3f}% ({stats['count']} trades)")

        print("\n" + "=" * 70)

    def check_alerts(self, send_webhooks: bool = False) -> list[str]:
        """
        Check for alert conditions.

        Args:
            send_webhooks: If True, send alerts via webhook

        Returns list of alert messages.
        """
        alerts = []

        # Check data staleness
        data = self.get_data_status()
        if "error" not in data:
            for symbol, stats in data["symbols"].items():
                if stats["status"] == "STALE":
                    alerts.append(("warning", f"DATA: {symbol} data is stale ({stats['age_minutes']:.0f} min old)"))
                elif stats["status"] == "NO DATA":
                    alerts.append(("critical", f"DATA: {symbol} has no data"))

        # Check evolution
        evo = self.get_evolution_status()
        if "error" not in evo:
            if evo.get("hours_since_last", 0) > 48:
                alerts.append(("warning", "EVOLUTION: No evolution run in 48+ hours"))
            if evo.get("success_rate", 1) < 0.5:
                alerts.append(("warning", "EVOLUTION: Success rate below 50%"))

        # Check shadow pool
        shadow = self.get_shadow_pool_status()
        if "error" not in shadow and shadow["count"] == 0:
            alerts.append(("info", "SHADOW: Shadow pool is empty - no strategies deployed"))

        # Check paper equity and drawdown
        equity = self.get_paper_equity_status()
        if "error" not in equity:
            current_dd = equity.get("current_drawdown", 0) / 100  # Convert back to decimal
            if current_dd >= ALERT_THRESHOLDS["shadow_dd_emergency"]:
                alerts.append(("critical", f"DRAWDOWN: Emergency >15% drawdown ({equity['current_drawdown']:.1f}%)"))
            elif current_dd >= ALERT_THRESHOLDS["shadow_dd_critical"]:
                alerts.append(("critical", f"DRAWDOWN: Critical >10% drawdown ({equity['current_drawdown']:.1f}%)"))
            elif current_dd >= ALERT_THRESHOLDS["shadow_dd_warning"]:
                alerts.append(("warning", f"DRAWDOWN: Warning >5% drawdown ({equity['current_drawdown']:.1f}%)"))

        # Check trading activity
        trading = self.get_shadow_trading_status()
        if "error" not in trading:
            if trading.get("hours_since_last", 0) > ALERT_THRESHOLDS["no_trades_warning_hours"]:
                alerts.append(("warning", f"TRADING: No trades in {trading['hours_since_last']:.0f} hours"))

        # Send webhooks if requested
        if send_webhooks and self.alerter.webhook_url:
            for level, message in alerts:
                if level in ("warning", "critical"):  # Only send warning and critical alerts
                    self.alerter.send(message, level=level)

        # Format alerts for return (backwards compatible)
        formatted = []
        for level, message in alerts:
            icon = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}.get(level, "❓")
            formatted.append(f"{icon} {message}")

        return formatted


def main():
    parser = argparse.ArgumentParser(
        description="Evolution system monitoring dashboard"
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Watch mode - refresh every 30 seconds",
    )
    parser.add_argument(
        "--check-alerts",
        action="store_true",
        help="Only check and print alerts",
    )
    parser.add_argument(
        "--send-alerts",
        action="store_true",
        help="Send alerts via webhook (requires ALERT_WEBHOOK_URL env var)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )
    parser.add_argument(
        "--daily-report",
        action="store_true",
        help="Generate and optionally send daily report",
    )
    parser.add_argument(
        "--send-alert",
        type=str,
        metavar="MESSAGE",
        help="Send a custom alert message via webhook",
    )
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Quick health check (exit code 0=healthy, 1=issues)",
    )

    args = parser.parse_args()

    monitor = EvolutionMonitor()

    if args.send_alert:
        # Send custom alert
        if monitor.send_alert(args.send_alert, level="warning"):
            print(f"✅ Alert sent: {args.send_alert}")
            sys.exit(0)
        else:
            print("❌ Failed to send alert (check ALERT_WEBHOOK_URL)")
            sys.exit(1)

    elif args.daily_report:
        # Generate daily report
        report = monitor.generate_daily_report(send_webhook=args.send_alerts)
        print("📊 Daily Report Generated")
        print("-" * 40)
        print(f"Date: {report['date']}")
        print(f"Paper Equity: ${report['paper_equity']:,.2f}")
        print(f"Daily P&L: ${report['daily_pnl']:,.2f} ({report['daily_pnl_pct']:.2f}%)")
        print(f"Total P&L: ${report['total_pnl']:,.2f} ({report['total_pnl_pct']:.2f}%)")
        print(f"Max Drawdown: {report['max_drawdown']:.2f}%")
        print(f"Trades Today: {report['trades_today']}")
        print(f"Active Strategies: {report['active_strategies']}")
        if args.send_alerts:
            print("\n✅ Report sent via webhook")

    elif args.health_check:
        # Quick health check for scripts/cron
        alerts = monitor.check_alerts()
        critical_alerts = [a for a in alerts if "🚨" in a]

        if critical_alerts:
            print("CRITICAL")
            for alert in critical_alerts:
                print(f"  {alert}")
            sys.exit(1)
        elif alerts:
            print("WARNING")
            for alert in alerts:
                print(f"  {alert}")
            sys.exit(0)  # Warnings don't fail health check
        else:
            print("OK")
            sys.exit(0)

    elif args.check_alerts:
        alerts = monitor.check_alerts(send_webhooks=args.send_alerts)
        if alerts:
            for alert in alerts:
                print(alert)
            sys.exit(1)
        else:
            print("✅ All systems OK")
            sys.exit(0)

    elif args.json:
        import json as json_lib
        output = {
            "timestamp": datetime.utcnow().isoformat(),
            "data": monitor.get_data_status(),
            "evolution": monitor.get_evolution_status(),
            "strategy_pool": monitor.get_strategy_pool_status(),
            "shadow_pool": monitor.get_shadow_pool_status(),
            "shadow_trading": monitor.get_shadow_trading_status(),
            "paper_equity": monitor.get_paper_equity_status(),
            "daily_performance": monitor.get_daily_performance(),
            "slippage_analysis": monitor.get_slippage_analysis(),
            "alerts": monitor.check_alerts(),
        }
        print(json_lib.dumps(output, indent=2))

    elif args.watch:
        try:
            while True:
                # Clear screen
                print("\033[2J\033[H", end="")
                monitor.print_dashboard()

                # Check and print alerts
                alerts = monitor.check_alerts()
                if alerts:
                    print("\n🚨 ALERTS:")
                    for alert in alerts:
                        print(f"  {alert}")

                print("\n(Press Ctrl+C to exit, refreshing in 30s...)")
                time.sleep(30)
        except KeyboardInterrupt:
            print("\nExiting...")

    else:
        monitor.print_dashboard()

        # Check and print alerts
        alerts = monitor.check_alerts()
        if alerts:
            print("\n🚨 ALERTS:")
            for alert in alerts:
                print(f"  {alert}")


if __name__ == "__main__":
    main()
