#!/usr/bin/env python3
"""Check for data gaps in the candles database."""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timedelta

def check_gaps(db_path: str, hours_back: int = 2, gap_threshold_minutes: int = 5):
    """
    Check for data gaps in the candles database.

    Args:
        db_path: Path to SQLite database
        hours_back: How many hours to look back
        gap_threshold_minutes: Gaps larger than this are reported
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Calculate time window (convert hours to milliseconds)
    now_ms = int(datetime.utcnow().timestamp() * 1000)
    lookback_ms = now_ms - (hours_back * 60 * 60 * 1000)
    gap_threshold_ms = gap_threshold_minutes * 60 * 1000

    print(f"Checking for gaps > {gap_threshold_minutes} minutes in last {hours_back} hours...")
    print(f"Time window: {datetime.fromtimestamp(lookback_ms/1000)} to {datetime.fromtimestamp(now_ms/1000)} UTC")
    print()

    # Query for gaps per symbol
    query = """
    WITH gaps AS (
        SELECT
            symbol,
            timestamp,
            LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp) as prev_ts,
            (timestamp - LAG(timestamp) OVER (PARTITION BY symbol ORDER BY timestamp)) as gap_ms
        FROM candles
        WHERE timestamp >= ?
    )
    SELECT
        symbol,
        datetime(prev_ts/1000, 'unixepoch') as gap_start,
        datetime(timestamp/1000, 'unixepoch') as gap_end,
        gap_ms / 60000.0 as gap_minutes
    FROM gaps
    WHERE gap_ms > ?
    ORDER BY symbol, timestamp
    """

    cursor.execute(query, (lookback_ms, gap_threshold_ms))
    results = cursor.fetchall()

    if not results:
        print("✅ No significant gaps found!")
    else:
        print(f"⚠️  Found {len(results)} gaps:")
        print()
        for symbol, gap_start, gap_end, gap_minutes in results:
            print(f"  {symbol:12s} | {gap_start} → {gap_end} | {gap_minutes:.1f} min gap")

    # Summary stats
    print()
    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM candles WHERE timestamp >= ?", (lookback_ms,))
    active_symbols = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM candles WHERE timestamp >= ?", (lookback_ms,))
    total_candles = cursor.fetchone()[0]

    print(f"Summary: {active_symbols} symbols, {total_candles} candles in last {hours_back}h")

    conn.close()
    return len(results)

if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/app/data/candles.db"
    hours_back = int(sys.argv[2]) if len(sys.argv) > 2 else 2

    gap_count = check_gaps(db_path, hours_back)
    sys.exit(0 if gap_count == 0 else 1)
