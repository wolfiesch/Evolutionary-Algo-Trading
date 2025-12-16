#!/usr/bin/env python3
"""
Historical Data Download Script

Downloads 5 years of historical daily data for:
- SPY (market trend filter)
- VIX (volatility regime filter)
- All stocks in the trading universe

Stores data in SQLite for backtesting and evolution.

Usage:
    python scripts/download_historical.py [OPTIONS]

Options:
    --years N         Number of years of data to download (default: 5)
    --symbols SYMBOL  Comma-separated symbols to download (overrides universe)
    --universe-only   Only download universe, skip SPY/VIX
    --spy-vix-only    Only download SPY and VIX
    --max-symbols N   Maximum symbols from universe (default: all)
    --quick           Quick mode: 1 year, 50 symbols
    --verify          Verify existing data, fill gaps only
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.ingestion.market_data import MarketDataClient
from data.ingestion.universe import SEED_UNIVERSE
from data.storage.repository import EquitiesRepository
from config import DATA_DIR, get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class HistoricalDataDownloader:
    """Downloads and stores historical market data."""

    # Key market indices
    SPY_TICKER = "SPY"
    VIX_TICKER = "^VIX"

    def __init__(
        self,
        repository: EquitiesRepository,
        market_client: MarketDataClient,
        years: int = 5,
    ):
        """
        Initialize downloader.

        Args:
            repository: Database repository
            market_client: Market data client
            years: Years of history to download
        """
        self.repository = repository
        self.market_client = market_client
        self.years = years

        # Calculate date range
        self.end_date = date.today()
        self.start_date = self.end_date - timedelta(days=years * 365)

    def download_spy_vix(self) -> dict[str, int]:
        """
        Download SPY and VIX data.

        Returns:
            Dict with download counts for each symbol
        """
        results = {}

        for symbol, label in [(self.SPY_TICKER, "SPY"), (self.VIX_TICKER, "VIX")]:
            logger.info(f"Downloading {label} data ({self.years} years)...")

            try:
                df = self.market_client.fetch_daily_bars(
                    symbol, self.start_date, self.end_date
                )

                if df.empty:
                    logger.warning(f"No data returned for {label}")
                    results[symbol] = 0
                    continue

                # Save to repository
                count = self.repository.save_daily_candles_df(symbol, df)
                logger.info(f"  Saved {count} bars for {label}")
                results[symbol] = count

            except Exception as e:
                logger.error(f"Failed to download {label}: {e}")
                results[symbol] = 0

        return results

    async def download_universe(
        self,
        symbols: list[str],
        max_symbols: Optional[int] = None,
        progress_callback: Optional[callable] = None,
    ) -> dict[str, int]:
        """
        Download data for universe symbols.

        Args:
            symbols: List of symbols to download
            max_symbols: Maximum symbols to download (None = all)
            progress_callback: Optional callback(completed, total, symbol)

        Returns:
            Dict mapping symbol -> bars saved
        """
        if max_symbols:
            symbols = symbols[:max_symbols]

        logger.info(f"Downloading {len(symbols)} symbols ({self.years} years each)...")

        results = {}
        failed = []
        total = len(symbols)

        for i, symbol in enumerate(symbols):
            try:
                # Fetch data
                df = self.market_client.fetch_daily_bars(
                    symbol, self.start_date, self.end_date
                )

                if df.empty:
                    logger.debug(f"No data for {symbol}")
                    failed.append(symbol)
                    continue

                # Save to repository
                count = self.repository.save_daily_candles_df(symbol, df)
                results[symbol] = count

                # Progress update
                if progress_callback:
                    progress_callback(i + 1, total, symbol)
                elif (i + 1) % 10 == 0 or (i + 1) == total:
                    pct = (i + 1) / total * 100
                    logger.info(f"  Progress: {i + 1}/{total} ({pct:.0f}%) - {symbol}: {count} bars")

            except Exception as e:
                logger.warning(f"Failed {symbol}: {e}")
                failed.append(symbol)

            # Small delay to respect rate limits
            await asyncio.sleep(0.1)

        # Summary
        success = len(results)
        total_bars = sum(results.values())
        logger.info(f"Download complete: {success}/{total} symbols, {total_bars:,} total bars")

        if failed:
            logger.warning(f"Failed symbols ({len(failed)}): {failed[:20]}...")

        return results

    def verify_data(self, symbols: list[str]) -> dict[str, dict]:
        """
        Verify existing data and identify gaps.

        Args:
            symbols: Symbols to verify

        Returns:
            Dict with verification status for each symbol
        """
        logger.info(f"Verifying data for {len(symbols)} symbols...")

        status = {}
        expected_days = self.years * 252  # Approximate trading days

        for symbol in symbols:
            df = self.repository.get_daily_candles(symbol)

            if df.empty:
                status[symbol] = {"status": "missing", "bars": 0}
                continue

            bars = len(df)
            coverage = bars / expected_days * 100

            if coverage >= 90:
                status[symbol] = {"status": "complete", "bars": bars, "coverage": coverage}
            elif coverage >= 50:
                status[symbol] = {"status": "partial", "bars": bars, "coverage": coverage}
            else:
                status[symbol] = {"status": "sparse", "bars": bars, "coverage": coverage}

        # Summary
        complete = sum(1 for s in status.values() if s["status"] == "complete")
        partial = sum(1 for s in status.values() if s["status"] == "partial")
        missing = sum(1 for s in status.values() if s["status"] == "missing")

        logger.info(f"Verification: {complete} complete, {partial} partial, {missing} missing")

        return status

    def get_database_stats(self) -> dict:
        """Get statistics about data in the database."""
        symbols = self.repository.get_symbols_with_data()
        total_candles = self.repository.get_candle_count()

        # Check SPY and VIX
        spy_count = self.repository.get_candle_count(self.SPY_TICKER)
        vix_count = self.repository.get_candle_count(self.VIX_TICKER)

        return {
            "total_symbols": len(symbols),
            "total_candles": total_candles,
            "spy_bars": spy_count,
            "vix_bars": vix_count,
            "symbols": symbols,
        }


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Download historical market data for backtesting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full download (5 years, all universe)
    python scripts/download_historical.py

    # Quick test (1 year, 50 symbols)
    python scripts/download_historical.py --quick

    # Only SPY and VIX
    python scripts/download_historical.py --spy-vix-only

    # Specific symbols
    python scripts/download_historical.py --symbols AAPL,MSFT,GOOGL

    # Verify and fill gaps
    python scripts/download_historical.py --verify
        """,
    )

    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Years of historical data to download (default: 5)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        help="Comma-separated symbols to download (overrides universe)",
    )
    parser.add_argument(
        "--universe-only",
        action="store_true",
        help="Only download universe symbols, skip SPY/VIX",
    )
    parser.add_argument(
        "--spy-vix-only",
        action="store_true",
        help="Only download SPY and VIX",
    )
    parser.add_argument(
        "--max-symbols",
        type=int,
        help="Maximum symbols from universe",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: 1 year, 50 symbols",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing data and show gaps",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show database statistics only",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Custom database path (default: data/equities.db)",
    )

    args = parser.parse_args()

    # Apply quick mode settings
    if args.quick:
        args.years = 1
        args.max_symbols = 50

    # Initialize components
    db_path = Path(args.db_path) if args.db_path else DATA_DIR / "equities.db"
    logger.info(f"Database: {db_path}")

    repository = EquitiesRepository(db_path)
    market_client = MarketDataClient(provider="yahoo")

    downloader = HistoricalDataDownloader(
        repository=repository,
        market_client=market_client,
        years=args.years,
    )

    # Stats only mode
    if args.stats:
        stats = downloader.get_database_stats()
        print("\n=== Database Statistics ===")
        print(f"Total symbols: {stats['total_symbols']}")
        print(f"Total candles: {stats['total_candles']:,}")
        print(f"SPY bars: {stats['spy_bars']}")
        print(f"VIX bars: {stats['vix_bars']}")
        if stats['symbols']:
            print(f"\nSymbols: {', '.join(stats['symbols'][:20])}...")
        return

    # Determine symbols to download
    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",")]
    else:
        symbols = SEED_UNIVERSE.copy()

    # Verify mode
    if args.verify:
        all_symbols = [downloader.SPY_TICKER, downloader.VIX_TICKER] + symbols
        status = downloader.verify_data(all_symbols)

        print("\n=== Data Verification ===")
        for symbol, info in list(status.items())[:20]:
            print(f"  {symbol}: {info['status']} ({info.get('bars', 0)} bars)")

        # Show gaps
        gaps = [s for s, info in status.items() if info["status"] in ("missing", "sparse")]
        if gaps:
            print(f"\nSymbols needing download ({len(gaps)}): {gaps[:20]}...")
        return

    # Download SPY and VIX
    if not args.universe_only:
        print("\n=== Downloading Market Indices ===")
        spy_vix_results = downloader.download_spy_vix()

    # Download universe
    if not args.spy_vix_only:
        print("\n=== Downloading Universe ===")
        universe_results = await downloader.download_universe(
            symbols=symbols,
            max_symbols=args.max_symbols,
        )

    # Final stats
    print("\n=== Download Complete ===")
    stats = downloader.get_database_stats()
    print(f"Total symbols in database: {stats['total_symbols']}")
    print(f"Total candles: {stats['total_candles']:,}")
    print(f"SPY bars: {stats['spy_bars']}")
    print(f"VIX bars: {stats['vix_bars']}")


if __name__ == "__main__":
    asyncio.run(main())
