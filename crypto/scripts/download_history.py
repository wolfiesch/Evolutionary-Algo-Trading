"""
Download historical candle data from Bybit for backtesting.

Usage:
    python download_history.py --symbol SOLUSDT --days 7
    python download_history.py --all --days 3
"""
import argparse
import time
import requests
import ssl
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Add paths for imports
crypto_dir = Path(__file__).parent.parent
project_dir = crypto_dir.parent
sys.path.insert(0, str(project_dir))
sys.path.insert(0, str(crypto_dir))

from data.storage.repository import CandleRepository
from data.storage.models import Candle

# Bybit public API (no auth needed for klines)
BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"

# Symbols to download
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "LINKUSDT"]


def fetch_klines(
    symbol: str,
    start_time: int,
    end_time: int,
    interval: str = "1",
) -> list[dict]:
    """
    Fetch klines from Bybit API.

    Args:
        symbol: Trading symbol (e.g., BTCUSDT)
        start_time: Start timestamp in milliseconds
        end_time: End timestamp in milliseconds
        interval: Candle interval ("1" = 1 minute)

    Returns:
        List of candle dicts
    """
    params = {
        "category": "linear",  # Perpetual futures
        "symbol": symbol,
        "interval": interval,
        "start": start_time,
        "end": end_time,
        "limit": 1000,
    }

    try:
        resp = requests.get(BYBIT_KLINE_URL, params=params, timeout=30)
        data = resp.json()

        if data.get("retCode") != 0:
            print(f"Error fetching {symbol}: {data.get('retMsg')}")
            return []

        # Bybit returns newest first, we want oldest first
        klines = data.get("result", {}).get("list", [])
        return list(reversed(klines))

    except Exception as e:
        print(f"Request error for {symbol}: {e}")
        return []


def download_symbol(
    repo: CandleRepository,
    symbol: str,
    days: int,
) -> int:
    """
    Download historical data for a single symbol.

    Args:
        repo: CandleRepository instance
        symbol: Trading symbol
        days: Number of days of history

    Returns:
        Number of candles downloaded
    """
    now = datetime.now(timezone.utc)
    end_time = int(now.timestamp() * 1000)
    start_time = end_time - (days * 24 * 60 * 60 * 1000)

    print(f"Downloading {symbol} ({days} days)...")

    all_candles = []
    current_start = start_time

    while current_start < end_time:
        # Fetch in chunks of 1000 candles
        chunk_end = min(current_start + (1000 * 60 * 1000), end_time)

        klines = fetch_klines(symbol, current_start, chunk_end)

        if not klines:
            break

        for k in klines:
            candle = Candle(
                symbol=symbol,
                timestamp=int(k[0]),
                open=float(k[1]),
                high=float(k[2]),
                low=float(k[3]),
                close=float(k[4]),
                volume=float(k[5]),
                turnover=float(k[6]) if len(k) > 6 else 0.0,
            )
            all_candles.append(candle)

        # Move to next chunk
        if klines:
            current_start = int(klines[-1][0]) + 60000  # +1 minute
        else:
            break

        # Rate limiting
        time.sleep(0.1)

    # Batch insert
    if all_candles:
        inserted = repo.insert_batch(all_candles)
        print(f"  Inserted {inserted} candles for {symbol}")
        return inserted

    return 0


def main(symbols: list[str], days: int, db_path: Path):
    """Main download function."""
    now = datetime.now(timezone.utc)
    print(f"Database: {db_path}")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Days: {days}")
    print(f"Start: {now - timedelta(days=days)}")
    print(f"End: {now}")
    print("-" * 50)

    repo = CandleRepository(db_path)

    total = 0
    for symbol in symbols:
        count = download_symbol(repo, symbol, days)
        total += count
        time.sleep(0.5)  # Rate limiting between symbols

    print("-" * 50)
    print(f"Total candles downloaded: {total}")

    # Show final counts
    print("\nDatabase counts:")
    for symbol in symbols:
        count = repo.count(symbol)
        print(f"  {symbol}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Bybit historical data")
    parser.add_argument(
        "--symbol",
        type=str,
        help="Single symbol to download (e.g., SOLUSDT)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download all default symbols"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=3,
        help="Number of days of history (default: 3)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Database path (default: crypto/data/candles_cloud.db)"
    )

    args = parser.parse_args()

    if args.symbol:
        symbols = [args.symbol]
    elif args.all:
        symbols = DEFAULT_SYMBOLS
    else:
        symbols = DEFAULT_SYMBOLS

    db_path = Path(args.db) if args.db else Path(__file__).parent.parent / "data" / "candles_cloud.db"

    main(symbols, args.days, db_path)
