"""
Monitoring dashboard for crypto-alpha system.

Provides web interface and API endpoints for:
- System health (WebSocket, DB, data collection)
- Evolution metrics (recent runs, best strategies)
- Shadow trading status (active strategies, signals)
- Data quality (anomalies, gaps, volume spikes)
"""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from flask import Flask, jsonify, render_template
from flask_cors import CORS

from crypto.config import settings
from crypto.monitoring.data_collectors import (
    get_system_health,
    get_candle_stats,
    get_evolution_summary,
    get_shadow_pool_status,
    get_data_quality_metrics,
    get_recent_signals,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for API access


@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template("dashboard.html")


@app.route("/api/health")
def api_health():
    """
    System health endpoint.

    Returns:
        {
            "status": "healthy|degraded|down",
            "websocket_connected": bool,
            "db_accessible": bool,
            "last_candle_age_seconds": int,
            "shadow_trader_running": bool,
            "uptime_hours": float
        }
    """
    try:
        health = get_system_health()
        return jsonify(health)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route("/api/candles")
def api_candles():
    """
    Candle statistics endpoint.

    Returns:
        {
            "symbols": {
                "BTCUSDT": {
                    "count": 4389,
                    "first_timestamp": "2025-12-08T10:00:00Z",
                    "last_timestamp": "2025-12-11T12:00:00Z",
                    "days_of_data": 3.08,
                    "gaps": 2
                },
                ...
            },
            "total_candles": 13167,
            "collection_rate_per_hour": 1440
        }
    """
    try:
        stats = get_candle_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Candle stats failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/evolution")
def api_evolution():
    """
    Evolution metrics endpoint.

    Returns:
        {
            "recent_runs": [
                {
                    "timestamp": "2025-12-11T02:00:00Z",
                    "run_number": 1,
                    "success": true,
                    "best_score": 0.85,
                    "duration_sec": 120.5
                },
                ...
            ],
            "best_strategy": {
                "name": "MeanReversion_V3",
                "score": 0.85,
                "sharpe": 1.2,
                "win_rate": 0.58,
                "trade_count": 45
            },
            "total_runs": 3,
            "success_rate": 0.67
        }
    """
    try:
        summary = get_evolution_summary()
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Evolution summary failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/shadow-pool")
def api_shadow_pool():
    """
    Shadow pool status endpoint.

    Returns:
        {
            "active_strategies": 3,
            "strategies": [
                {
                    "name": "MeanReversion_V3",
                    "sharpe": 1.2,
                    "deployed_at": "2025-12-11T02:00:00Z",
                    "signals_24h": 5,
                    "win_rate": 0.58
                },
                ...
            ],
            "total_signals_today": 12,
            "open_positions": 2
        }
    """
    try:
        status = get_shadow_pool_status()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Shadow pool status failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/data-quality")
def api_data_quality():
    """
    Data quality metrics endpoint.

    Returns:
        {
            "anomalies_24h": 3,
            "volume_spikes": 1,
            "missing_candles": 0,
            "non_monotonic_timestamps": 5,
            "last_anomaly": {
                "type": "volume_spike",
                "symbol": "ETHUSDT",
                "timestamp": "2025-12-11T12:00:00Z",
                "details": "3135.06 vs avg 189.92 (16.5x)"
            }
        }
    """
    try:
        metrics = get_data_quality_metrics()
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Data quality metrics failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/signals")
def api_signals():
    """
    Recent trading signals endpoint.

    Returns:
        {
            "signals": [
                {
                    "timestamp": "2025-12-11T12:00:00Z",
                    "symbol": "SOLUSDT",
                    "strategy": "MeanReversion_V3",
                    "signal": "entry_long",
                    "price": 150.23,
                    "btc_trend": 1.0,
                    "conditions": {
                        "btc_trend": 1.0,
                        "norm_rsi": -0.42,
                        "ema_trend": 1.0
                    }
                },
                ...
            ],
            "total_signals_24h": 12
        }
    """
    try:
        signals = get_recent_signals()
        return jsonify(signals)
    except Exception as e:
        logger.error(f"Recent signals failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/summary")
def api_summary():
    """
    Combined summary endpoint - all metrics in one call.

    Returns combined data from all other endpoints for dashboard overview.
    """
    try:
        summary = {
            "health": get_system_health(),
            "candles": get_candle_stats(),
            "evolution": get_evolution_summary(),
            "shadow_pool": get_shadow_pool_status(),
            "data_quality": get_data_quality_metrics(),
            "recent_signals": get_recent_signals(limit=10),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Summary failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/evolution-progress")
def api_evolution_progress():
    """
    Real-time evolution progress endpoint.

    Reads from progress JSON file written by evolution engine.

    Returns:
        {
            "phase": "initial_population|evolution",
            "generation": 1,
            "eval_count": 3,
            "total_evals": 20,
            "progress_pct": 15.0,
            "elapsed_sec": 120.5,
            "best_score": 2.45,
            "current_score": 1.23,
            "strategy_name": "MeanReversion_V1",
            "top_strategies": [
                {"name": "Strategy1", "score": 2.45},
                {"name": "Strategy2", "score": 1.89}
            ]
        }
    """
    try:
        progress_file = settings.logs_dir / "evolution_progress.json"
        if progress_file.exists():
            with open(progress_file) as f:
                progress = json.load(f)
            # Add file age for staleness detection
            age_sec = (datetime.utcnow() - datetime.fromisoformat(progress.get("timestamp", "2000-01-01"))).total_seconds()
            progress["age_sec"] = age_sec
            progress["is_stale"] = age_sec > 300  # Stale if > 5 min old
            return jsonify(progress)
        else:
            return jsonify({
                "status": "no_evolution_running",
                "message": "No evolution progress file found"
            })
    except Exception as e:
        logger.error(f"Evolution progress failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/evolution-progress/stream")
def api_evolution_stream():
    """
    Server-Sent Events (SSE) endpoint for real-time evolution updates.

    Usage (JavaScript):
        const evtSource = new EventSource('/api/evolution-progress/stream');
        evtSource.onmessage = (event) => {
            const progress = JSON.parse(event.data);
            updateUI(progress);
        };
    """
    from flask import Response
    import time

    def generate():
        last_data = None
        while True:
            try:
                progress_file = settings.logs_dir / "evolution_progress.json"
                if progress_file.exists():
                    with open(progress_file) as f:
                        data = f.read()

                    # Only send if data changed
                    if data != last_data:
                        last_data = data
                        yield f"data: {data}\n\n"
                else:
                    yield 'data: {"status": "no_evolution_running"}\n\n'

                time.sleep(2)  # Poll every 2 seconds
            except Exception as e:
                yield f'data: {{"error": "{str(e)}"}}\n\n'
                time.sleep(5)

    return Response(generate(), mimetype='text/event-stream')


def main():
    """Run the monitoring dashboard server."""
    import argparse

    parser = argparse.ArgumentParser(description="Crypto-alpha monitoring dashboard")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("CRYPTO-ALPHA MONITORING DASHBOARD")
    logger.info("=" * 60)
    logger.info(f"Listening on http://{args.host}:{args.port}")
    logger.info(f"Dashboard: http://{args.host}:{args.port}/")
    logger.info(f"API: http://{args.host}:{args.port}/api/summary")
    logger.info("=" * 60)

    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
