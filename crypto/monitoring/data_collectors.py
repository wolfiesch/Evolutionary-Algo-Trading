"""
Data collectors for monitoring dashboard.

Reads from SQLite, log files, and JSON files to gather metrics.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from crypto.config import settings


def get_system_health() -> Dict[str, Any]:
    """
    Get system health status.

    Checks:
    - Database accessibility
    - Last candle timestamp (freshness)
    - Shadow trader log activity

    Returns:
        Health status dict
    """
    health = {
        "status": "healthy",
        "db_accessible": False,
        "last_candle_age_seconds": None,
        "shadow_trader_running": False,
        "uptime_hours": None,
    }

    # Check DB
    try:
        conn = sqlite3.connect(str(settings.sqlite_path))
        cursor = conn.cursor()

        # Get most recent candle
        cursor.execute("SELECT MAX(timestamp) FROM candles")
        last_ts = cursor.fetchone()[0]

        if last_ts:
            last_candle_time = datetime.fromtimestamp(last_ts / 1000.0)
            age_seconds = (datetime.utcnow() - last_candle_time).total_seconds()
            health["last_candle_age_seconds"] = int(age_seconds)
            health["db_accessible"] = True

            # If last candle is > 5 minutes old, mark degraded
            if age_seconds > 300:
                health["status"] = "degraded"

        conn.close()
    except Exception as e:
        health["status"] = "down"
        health["error"] = str(e)

    # Check shadow trader log
    shadow_log = settings.logs_dir / "shadow_trader.log"
    if shadow_log.exists():
        try:
            # Read last 10 lines to check for recent activity
            with open(shadow_log, "r") as f:
                lines = f.readlines()[-10:]

            if lines:
                # Parse last line timestamp
                last_line = lines[-1]
                if "timestamp" in last_line:
                    # Extract timestamp from JSON log line
                    try:
                        log_data = json.loads(last_line.split(" - ")[-1])
                        last_log_time = datetime.fromisoformat(log_data["timestamp"].replace("Z", ""))
                        log_age = (datetime.utcnow() - last_log_time).total_seconds()

                        if log_age < 300:  # Active in last 5 minutes
                            health["shadow_trader_running"] = True
                    except:
                        pass
        except Exception:
            pass

    return health


def get_candle_stats() -> Dict[str, Any]:
    """
    Get candle collection statistics.

    Returns:
        Candle stats per symbol and overall
    """
    stats = {
        "symbols": {},
        "total_candles": 0,
        "collection_rate_per_hour": 0,
    }

    try:
        conn = sqlite3.connect(str(settings.sqlite_path))
        cursor = conn.cursor()

        # Get per-symbol stats
        cursor.execute("""
            SELECT
                symbol,
                COUNT(*) as count,
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts
            FROM candles
            GROUP BY symbol
        """)

        for row in cursor.fetchall():
            symbol, count, first_ts, last_ts = row

            first_time = datetime.fromtimestamp(first_ts / 1000.0)
            last_time = datetime.fromtimestamp(last_ts / 1000.0)
            duration_hours = (last_time - first_time).total_seconds() / 3600.0

            stats["symbols"][symbol] = {
                "count": count,
                "first_timestamp": first_time.isoformat() + "Z",
                "last_timestamp": last_time.isoformat() + "Z",
                "days_of_data": round(duration_hours / 24, 2),
                "gaps": 0,  # [*TO-DO*] - Implement gap detection
            }
            stats["total_candles"] += count

        # Calculate collection rate (candles/hour across all symbols)
        if stats["symbols"]:
            first_symbol = list(stats["symbols"].keys())[0]
            symbol_stats = stats["symbols"][first_symbol]

            first_time = datetime.fromisoformat(symbol_stats["first_timestamp"].replace("Z", ""))
            last_time = datetime.fromisoformat(symbol_stats["last_timestamp"].replace("Z", ""))
            duration_hours = (last_time - first_time).total_seconds() / 3600.0

            if duration_hours > 0:
                stats["collection_rate_per_hour"] = int(stats["total_candles"] / duration_hours)

        conn.close()
    except Exception as e:
        stats["error"] = str(e)

    return stats


def get_evolution_summary() -> Dict[str, Any]:
    """
    Get evolution run summary.

    Reads from:
    - scheduler_history.jsonl (run history)
    - strategies/ directory (saved strategies)

    Returns:
        Evolution summary
    """
    summary = {
        "recent_runs": [],
        "best_strategy": None,
        "total_runs": 0,
        "success_rate": 0.0,
    }

    # Read scheduler history
    history_file = settings.logs_dir / "scheduler_history.jsonl"
    if history_file.exists():
        try:
            with open(history_file, "r") as f:
                runs = [json.loads(line) for line in f]

            summary["total_runs"] = len(runs)
            summary["recent_runs"] = runs[-10:]  # Last 10 runs

            if runs:
                successful = sum(1 for r in runs if r.get("success"))
                summary["success_rate"] = successful / len(runs)
        except Exception as e:
            summary["error"] = str(e)

    # Read best strategy from strategy store
    strategy_dir = settings.logs_dir / "strategies"
    if strategy_dir.exists():
        try:
            strategy_files = sorted(strategy_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

            if strategy_files:
                with open(strategy_files[0], "r") as f:
                    best = json.load(f)

                summary["best_strategy"] = {
                    "name": best.get("name"),
                    "score": best.get("final_score"),
                    "sharpe": best.get("sharpe_ratio"),
                    "win_rate": best.get("win_rate"),
                    "trade_count": best.get("trade_count"),
                    "created_at": best.get("created_at"),
                }
        except Exception:
            pass

    return summary


def get_shadow_pool_status() -> Dict[str, Any]:
    """
    Get shadow pool status.

    Reads from:
    - shadow_pool/ directory (active strategies)
    - trades_YYYY-MM-DD.log (recent signals)

    Returns:
        Shadow pool status
    """
    status = {
        "active_strategies": 0,
        "strategies": [],
        "total_signals_today": 0,
        "open_positions": 0,
    }

    # Read shadow pool directory
    shadow_dir = settings.logs_dir / "shadow_pool"
    if shadow_dir.exists():
        try:
            strategy_files = list(shadow_dir.glob("*.json"))
            status["active_strategies"] = len(strategy_files)

            for strategy_file in strategy_files[:10]:  # Limit to 10
                with open(strategy_file, "r") as f:
                    strat = json.load(f)

                status["strategies"].append({
                    "name": strat.get("name"),
                    "sharpe": strat.get("sharpe_ratio"),
                    "deployed_at": strat.get("promoted_at"),
                    "win_rate": strat.get("win_rate"),
                })
        except Exception:
            pass

    # Count today's signals from trade log
    today = datetime.utcnow().strftime("%Y-%m-%d")
    trade_log = settings.logs_dir / f"trades_{today}.log"

    if trade_log.exists():
        try:
            with open(trade_log, "r") as f:
                lines = f.readlines()

            status["total_signals_today"] = len(lines)

            # Count open positions (entries without exits)
            entries = [l for l in lines if "entry_long" in l]
            exits = [l for l in lines if "exit_long" in l]
            status["open_positions"] = len(entries) - len(exits)
        except Exception:
            pass

    return status


def get_data_quality_metrics() -> Dict[str, Any]:
    """
    Get data quality metrics.

    Reads from:
    - errors_YYYY-MM-DD.log (anomalies)

    Returns:
        Data quality metrics
    """
    metrics = {
        "anomalies_24h": 0,
        "volume_spikes": 0,
        "missing_candles": 0,
        "non_monotonic_timestamps": 0,
        "last_anomaly": None,
    }

    # Read last 2 days of error logs
    for days_ago in range(2):
        date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        error_log = settings.logs_dir / f"errors_{date}.log"

        if error_log.exists():
            try:
                with open(error_log, "r") as f:
                    lines = f.readlines()

                for line in lines:
                    if "Volume spike detected" in line:
                        metrics["volume_spikes"] += 1
                        metrics["anomalies_24h"] += 1

                        # Parse last anomaly
                        if not metrics["last_anomaly"]:
                            try:
                                # Extract details from log line
                                parts = line.split(" - ")
                                timestamp_str = parts[0]
                                details = parts[-1].strip()

                                metrics["last_anomaly"] = {
                                    "type": "volume_spike",
                                    "timestamp": timestamp_str,
                                    "details": details,
                                }
                            except:
                                pass

                    elif "Non-monotonic timestamp" in line:
                        metrics["non_monotonic_timestamps"] += 1
            except Exception:
                pass

    return metrics


def get_recent_signals(limit: int = 50) -> Dict[str, Any]:
    """
    Get recent trading signals.

    Args:
        limit: Maximum number of signals to return

    Returns:
        Recent signals
    """
    result = {
        "signals": [],
        "total_signals_24h": 0,
    }

    # Read last 2 days of trade logs
    for days_ago in range(2):
        date = (datetime.utcnow() - timedelta(days=days_ago)).strftime("%Y-%m-%d")
        trade_log = settings.logs_dir / f"trades_{date}.log"

        if trade_log.exists():
            try:
                with open(trade_log, "r") as f:
                    lines = f.readlines()

                result["total_signals_24h"] += len(lines)

                # Parse recent signals (reverse for newest first)
                for line in reversed(lines[-limit:]):
                    try:
                        # Extract JSON from log line
                        json_part = line.split(" - ")[-1]
                        signal_data = json.loads(json_part)

                        result["signals"].append(signal_data)
                    except:
                        pass

                if len(result["signals"]) >= limit:
                    break
            except Exception:
                pass

    result["signals"] = result["signals"][:limit]

    return result
