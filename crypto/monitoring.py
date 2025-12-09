"""
Monitoring and alerts for the evolution system.

Provides a CLI dashboard and alerting for:
- Evolution run status and history
- Shadow pool health
- Strategy performance tracking
- System health checks

Usage:
    # Show dashboard
    python monitoring.py

    # Watch mode (refresh every 30s)
    python monitoring.py --watch

    # Check specific component
    python monitoring.py --check-shadow-pool
    python monitoring.py --check-evolution-health
"""
import argparse
import json
import logging
import sys
import time
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

        print("\n" + "=" * 70)

    def check_alerts(self) -> list[str]:
        """
        Check for alert conditions.

        Returns list of alert messages.
        """
        alerts = []

        # Check data staleness
        data = self.get_data_status()
        if "error" not in data:
            for symbol, stats in data["symbols"].items():
                if stats["status"] == "STALE":
                    alerts.append(f"⚠️ DATA: {symbol} data is stale ({stats['age_minutes']:.0f} min old)")
                elif stats["status"] == "NO DATA":
                    alerts.append(f"❌ DATA: {symbol} has no data")

        # Check evolution
        evo = self.get_evolution_status()
        if "error" not in evo:
            if evo.get("hours_since_last", 0) > 48:
                alerts.append("⚠️ EVOLUTION: No evolution run in 48+ hours")
            if evo.get("success_rate", 1) < 0.5:
                alerts.append("⚠️ EVOLUTION: Success rate below 50%")

        # Check shadow pool
        shadow = self.get_shadow_pool_status()
        if "error" not in shadow and shadow["count"] == 0:
            alerts.append("ℹ️ SHADOW: Shadow pool is empty - no strategies deployed")

        return alerts


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
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    args = parser.parse_args()

    monitor = EvolutionMonitor()

    if args.check_alerts:
        alerts = monitor.check_alerts()
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
