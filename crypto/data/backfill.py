"""
Historical data backfill script for Bybit.

Downloads historical 1-minute candles from Bybit's REST API and stores
them in the local SQLite database.

Usage:
    # Backfill last 30 days for default symbols
    python backfill.py

    # Backfill specific symbols
    python backfill.py --symbols BTCUSDT,SOLUSDT,ETHUSDT

    # Backfill specific number of days
    python backfill.py --days 7

    # Backfill specific date range (YYYY-MM-DD format)
    python backfill.py --start-date 2024-02-01 --end-date 2024-02-15

    # Specify database path
    python backfill.py --db data/candles.db

Note: Bybit API is geo-blocked in US. Run this on Fly.io if needed:
    fly ssh console -a crypto-alpha
    cd /app/crypto && python data/backfill.py
"""
import argparse
import logging
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.storage.models import Candle
from data.storage.repository import CandleRepository

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Bybit V5 API
BYBIT_BASE_URL = "https://api.bybit.com"
KLINE_ENDPOINT = "/v5/market/kline"

# Rate limiting
REQUEST_DELAY_SEC = 0.1  # 100ms between requests
MAX_CANDLES_PER_REQUEST = 200  # Bybit limit

# Default symbols
DEFAULT_SYMBOLS = ["BTCUSDT", "SOLUSDT", "ETHUSDT"]


def fetch_klines(
    symbol: str,
    start_ts: int,
    end_ts: int,
    interval: str = "1",
) -> list[dict]:
    """
    Fetch kline data from Bybit API.

    Args:
        symbol: Trading pair (e.g., "BTCUSDT")
        start_ts: Start timestamp in milliseconds
        end_ts: End timestamp in milliseconds
        interval: Candle interval ("1" = 1 minute)

    Returns:
        List of kline dictionaries
    """
    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "start": start_ts,
        "end": end_ts,
        "limit": MAX_CANDLES_PER_REQUEST,
    }

    try:
        response = requests.get(
            f"{BYBIT_BASE_URL}{KLINE_ENDPOINT}",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("retCode") != 0:
            logger.error(f"Bybit API error: {data.get('retMsg')}")
            return []

        return data.get("result", {}).get("list", [])

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        return []


def parse_klines(symbol: str, klines: list) -> list[Candle]:
    """
    Parse Bybit kline data into Candle objects.

    Bybit kline format: [startTime, open, high, low, close, volume, turnover]

    Args:
        symbol: Trading pair symbol
        klines: Raw kline data from API

    Returns:
        List of Candle objects
    """
    candles = []

    for kline in klines:
        try:
            # Bybit returns strings, need to convert
            candle = Candle(
                symbol=symbol,
                timestamp=int(kline[0]),
                open=float(kline[1]),
                high=float(kline[2]),
                low=float(kline[3]),
                close=float(kline[4]),
                volume=float(kline[5]),
                turnover=float(kline[6]) if len(kline) > 6 else 0.0,
            )
            candles.append(candle)
        except (IndexError, ValueError) as e:
            logger.warning(f"Failed to parse kline: {kline}, error: {e}")
            continue

    return candles


def backfill_symbol(
    repo: CandleRepository,
    symbol: str,
    start_ts: int,
    end_ts: int,
) -> int:
    """
    Backfill historical data for a single symbol.

    Args:
        repo: CandleRepository instance
        symbol: Trading pair symbol
        start_ts: Start timestamp in milliseconds
        end_ts: End timestamp in milliseconds

    Returns:
        Total number of candles inserted
    """
    total_inserted = 0
    current_end = end_ts

    # Bybit returns data in descending order (newest first)
    # We need to paginate backwards from end_ts to start_ts

    while current_end > start_ts:
        # Fetch batch
        klines = fetch_klines(symbol, start_ts, current_end)

        if not klines:
            logger.warning(f"No data returned for {symbol} ending at {current_end}")
            break

        # Parse and insert
        candles = parse_klines(symbol, klines)
        if candles:
            inserted = repo.insert_batch(candles)
            total_inserted += inserted

            # Log progress
            oldest = min(c.timestamp for c in candles)
            newest = max(c.timestamp for c in candles)
            logger.info(
                f"{symbol}: Inserted {inserted} candles "
                f"({datetime.fromtimestamp(oldest/1000)} to "
                f"{datetime.fromtimestamp(newest/1000)})"
            )

            # Move window back
            current_end = oldest - 1

        # Rate limiting
        time.sleep(REQUEST_DELAY_SEC)

        # Check if we got fewer than max (means we've reached the beginning)
        if len(klines) < MAX_CANDLES_PER_REQUEST:
            break

    return total_inserted


def run_backfill(
    symbols: list[str],
    start_time: datetime,
    end_time: datetime,
    db_path: Path,
):
    """
    Run backfill for multiple symbols.

    Args:
        symbols: List of trading pair symbols
        start_time: Start datetime (UTC)
        end_time: End datetime (UTC)
        db_path: Path to SQLite database
    """
    logger.info("=" * 60)
    logger.info("BYBIT HISTORICAL DATA BACKFILL")
    logger.info("=" * 60)
    logger.info(f"Symbols: {', '.join(symbols)}")
    logger.info(f"Start: {start_time}")
    logger.info(f"End: {end_time}")
    logger.info(f"Database: {db_path}")
    logger.info("=" * 60)

    # Convert to timestamps
    end_ts = int(end_time.timestamp() * 1000)
    start_ts = int(start_time.timestamp() * 1000)

    # Calculate expected candles
    time_diff = end_time - start_time
    expected_candles = int(time_diff.total_seconds() / 60)

    logger.info(f"Time range: {start_time} to {end_time}")
    logger.info(f"Expected candles per symbol: ~{expected_candles}")

    # Initialize repository
    repo = CandleRepository(db_path)

    # Check existing counts
    logger.info("\nExisting data:")
    for symbol in symbols:
        count = repo.count(symbol)
        logger.info(f"  {symbol}: {count} candles")

    # Backfill each symbol
    logger.info("\nStarting backfill...")

    results = {}
    for symbol in symbols:
        logger.info(f"\n--- Backfilling {symbol} ---")
        inserted = backfill_symbol(repo, symbol, start_ts, end_ts)
        results[symbol] = inserted

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL COMPLETE")
    logger.info("=" * 60)

    for symbol in symbols:
        final_count = repo.count(symbol)
        logger.info(f"  {symbol}: {final_count} total candles (+{results[symbol]} new)")

    total_new = sum(results.values())
    total_all = sum(repo.count(s) for s in symbols)
    logger.info(f"\nTotal: {total_all} candles across {len(symbols)} symbols")
    logger.info(f"New candles inserted: {total_new}")


def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical candle data from Bybit"
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(DEFAULT_SYMBOLS),
        help=f"Comma-separated symbols (default: {','.join(DEFAULT_SYMBOLS)})"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Number of days to backfill (default: 30, ignored if --start-date/--end-date provided)"
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default=None,
        help="Start date in YYYY-MM-DD format (UTC)"
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=None,
        help="End date in YYYY-MM-DD format (UTC)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: data/candles.db)"
    )

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",")]

    if args.db:
        db_path = Path(args.db)
    else:
        db_path = Path(__file__).parent / "candles.db"

    # Calculate time range
    if args.start_date and args.end_date:
        # Use specific date range
        try:
            start_time = datetime.strptime(args.start_date, "%Y-%m-%d")
            end_time = datetime.strptime(args.end_date, "%Y-%m-%d")

            # End date should be end of day
            end_time = end_time.replace(hour=23, minute=59, second=59)

            if start_time >= end_time:
                logger.error("Start date must be before end date")
                sys.exit(1)

            logger.info(f"Using date range: {args.start_date} to {args.end_date}")
        except ValueError as e:
            logger.error(f"Invalid date format: {e}")
            logger.error("Use YYYY-MM-DD format (e.g., 2024-02-01)")
            sys.exit(1)
    elif args.start_date or args.end_date:
        logger.error("Both --start-date and --end-date must be provided together")
        sys.exit(1)
    else:
        # Use days parameter (default behavior)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=args.days)
        logger.info(f"Using last {args.days} days")

    run_backfill(
        symbols=symbols,
        start_time=start_time,
        end_time=end_time,
        db_path=db_path,
    )


if __name__ == "__main__":
    main()
