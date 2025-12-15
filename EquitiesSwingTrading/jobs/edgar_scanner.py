"""
Daily EDGAR Scanner Job for Equities Swing Trading.

Scans universe for:
- New insider trading activity (Form 4)
- Updated financial data (10-K, 10-Q)
- Risk factor changes

Stores signals in repository for use by fundamental primitives.
Designed to run daily via cron or scheduler.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from data.cache import Cache, CacheConfig, get_cache, cached
from data.ingestion.edgar_client import EdgarClient, EdgarConfig
from data.ingestion.universe import UniverseManager
from data.storage.repository import EquitiesRepository
from data.storage.models import FundamentalSignal, FilingEvent
from engine.gene_pool.fundamental import (
    insider_buy_intensity,
    revenue_cagr,
    earnings_quality,
    risk_change_intensity,
)
from config import config as app_config

logger = logging.getLogger(__name__)


@dataclass
class ScanConfig:
    """Configuration for EDGAR scanner."""
    # Scan parameters
    insider_lookback_days: int = 90
    financials_years: int = 3

    # Parallelism
    max_concurrent: int = 5

    # Filtering
    min_insider_value: float = 100_000  # Ignore small insider transactions

    # Paths
    db_path: Optional[Path] = None


@dataclass
class ScanResult:
    """Result of a scan run."""
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    symbols_scanned: int = 0
    symbols_with_updates: int = 0
    insider_signals: int = 0
    financial_signals: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.completed_at is None:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


class EdgarScanner:
    """
    Daily scanner for EDGAR data.

    Fetches insider trades, financials, and risk factors for all
    symbols in the universe and stores calculated signals.
    """

    # Signal type constants (match repository schema)
    SIGNAL_INSIDER_INTENSITY = "insider_intensity"
    SIGNAL_INSIDER_CLUSTER = "insider_cluster"
    SIGNAL_REVENUE_CAGR = "revenue_cagr"
    SIGNAL_EARNINGS_GROWTH = "earnings_growth"
    SIGNAL_EARNINGS_QUALITY = "earnings_quality"
    SIGNAL_RISK_CHANGE = "risk_change"
    SIGNAL_FUNDAMENTAL_SCORE = "fundamental_score"

    def __init__(
        self,
        edgar_client: EdgarClient,
        repository: EquitiesRepository,
        universe_manager: UniverseManager,
        cache: Optional[Cache] = None,
        config: Optional[ScanConfig] = None,
    ):
        """
        Initialize scanner.

        Args:
            edgar_client: EDGAR API client
            repository: Database repository
            universe_manager: Universe manager for symbol list
            cache: Optional cache instance
            config: Scanner configuration
        """
        self.edgar_client = edgar_client
        self.repository = repository
        self.universe_manager = universe_manager
        self.cache = cache or get_cache()
        self.config = config or ScanConfig()

    async def run_full_scan(
        self,
        symbols: Optional[list[str]] = None,
        progress_callback: Optional[callable] = None,
    ) -> ScanResult:
        """
        Run full EDGAR scan for all symbols.

        Args:
            symbols: Optional symbol list (uses universe if not provided)
            progress_callback: Optional callback(completed, total)

        Returns:
            ScanResult with statistics
        """
        result = ScanResult()

        try:
            # Get symbols to scan
            if symbols is None:
                symbols = self.universe_manager.get_universe()

            if not symbols:
                logger.warning("No symbols to scan")
                return result

            result.symbols_scanned = len(symbols)
            logger.info(f"Starting EDGAR scan for {len(symbols)} symbols")

            # Process symbols with controlled concurrency
            semaphore = asyncio.Semaphore(self.config.max_concurrent)
            tasks = []

            for i, symbol in enumerate(symbols):
                task = self._scan_symbol_with_semaphore(
                    symbol, semaphore, result
                )
                tasks.append(task)

            # Execute with progress tracking
            completed = 0
            for coro in asyncio.as_completed(tasks):
                await coro
                completed += 1
                if progress_callback:
                    progress_callback(completed, len(symbols))

        except Exception as e:
            logger.error(f"Scan failed: {e}")
            result.errors.append(str(e))

        finally:
            result.completed_at = datetime.utcnow()
            logger.info(
                f"Scan completed in {result.duration_seconds:.1f}s: "
                f"{result.symbols_with_updates}/{result.symbols_scanned} symbols updated, "
                f"{result.insider_signals} insider signals, "
                f"{result.financial_signals} financial signals"
            )

        return result

    async def _scan_symbol_with_semaphore(
        self,
        symbol: str,
        semaphore: asyncio.Semaphore,
        result: ScanResult,
    ) -> None:
        """Scan single symbol with concurrency control."""
        async with semaphore:
            await self._scan_symbol(symbol, result)

    async def _scan_symbol(
        self,
        symbol: str,
        result: ScanResult,
    ) -> None:
        """
        Scan single symbol for EDGAR data.

        Calculates and stores:
        - Insider intensity signals
        - Financial trajectory signals
        - Earnings quality signals
        - Risk change signals
        """
        try:
            signals_added = 0
            today = date.today()

            # Calculate insider signals
            try:
                insider = self._calculate_insider_signals(symbol)
                if insider:
                    for signal_type, value in insider.items():
                        self.repository.save_fundamental_signal(
                            FundamentalSignal(
                                symbol=symbol,
                                signal_type=signal_type,
                                signal_date=today,
                                signal_value=value,
                                source="edgar_scanner",
                            )
                        )
                        signals_added += 1
                        result.insider_signals += 1
            except Exception as e:
                logger.debug(f"Insider signal error for {symbol}: {e}")

            # Calculate financial signals
            try:
                financials = self._calculate_financial_signals(symbol)
                if financials:
                    for signal_type, value in financials.items():
                        self.repository.save_fundamental_signal(
                            FundamentalSignal(
                                symbol=symbol,
                                signal_type=signal_type,
                                signal_date=today,
                                signal_value=value,
                                source="edgar_scanner",
                            )
                        )
                        signals_added += 1
                        result.financial_signals += 1
            except Exception as e:
                logger.debug(f"Financial signal error for {symbol}: {e}")

            if signals_added > 0:
                result.symbols_with_updates += 1

        except Exception as e:
            logger.warning(f"Error scanning {symbol}: {e}")
            result.errors.append(f"{symbol}: {e}")

    def _calculate_insider_signals(self, symbol: str) -> dict[str, float]:
        """Calculate insider trading signals for symbol."""
        signals = {}

        # Get insider summary
        summary = self.edgar_client.get_insider_trades(
            symbol,
            days=self.config.insider_lookback_days,
        )

        if summary.total_buys == 0 and summary.total_sells == 0:
            return signals

        # Calculate intensity
        intensity = insider_buy_intensity(symbol, self.config.insider_lookback_days)
        signals[self.SIGNAL_INSIDER_INTENSITY] = intensity

        # Check for cluster buy
        if summary.unique_buyers >= 3:
            signals[self.SIGNAL_INSIDER_CLUSTER] = 1.0
        else:
            signals[self.SIGNAL_INSIDER_CLUSTER] = 0.0

        return signals

    def _calculate_financial_signals(self, symbol: str) -> dict[str, float]:
        """Calculate financial trajectory signals for symbol."""
        signals = {}

        # Revenue CAGR
        try:
            cagr = revenue_cagr(symbol, self.config.financials_years)
            signals[self.SIGNAL_REVENUE_CAGR] = cagr
        except Exception:
            pass

        # Earnings quality
        try:
            quality = earnings_quality(symbol)
            signals[self.SIGNAL_EARNINGS_QUALITY] = quality
        except Exception:
            pass

        # Risk change
        try:
            risk = risk_change_intensity(symbol)
            signals[self.SIGNAL_RISK_CHANGE] = risk
        except Exception:
            pass

        return signals

    def run_incremental_scan(
        self,
        symbols: Optional[list[str]] = None,
    ) -> ScanResult:
        """
        Run incremental scan for recent changes only.

        Only checks symbols that have had recent filings.
        More efficient than full scan for daily updates.
        """
        result = ScanResult()

        # Get symbols with recent activity
        if symbols is None:
            # Check filings from last 7 days
            # [*TO-DO*] - Implement SEC filing RSS feed check
            symbols = self.universe_manager.get_universe()[:50]  # Limit for now

        # Run synchronous scan for simplicity
        for symbol in symbols:
            self._scan_symbol_sync(symbol, result)

        result.completed_at = datetime.utcnow()
        return result

    def _scan_symbol_sync(self, symbol: str, result: ScanResult) -> None:
        """Synchronous symbol scan."""
        try:
            signals_added = 0
            today = date.today()

            # Insider signals
            insider = self._calculate_insider_signals(symbol)
            for signal_type, value in insider.items():
                self.repository.save_fundamental_signal(
                    FundamentalSignal(
                        symbol=symbol,
                        signal_type=signal_type,
                        signal_date=today,
                        signal_value=value,
                        source="edgar_scanner",
                    )
                )
                signals_added += 1
                result.insider_signals += 1

            # Financial signals
            financials = self._calculate_financial_signals(symbol)
            for signal_type, value in financials.items():
                self.repository.save_fundamental_signal(
                    FundamentalSignal(
                        symbol=symbol,
                        signal_type=signal_type,
                        signal_date=today,
                        signal_value=value,
                        source="edgar_scanner",
                    )
                )
                signals_added += 1
                result.financial_signals += 1

            if signals_added > 0:
                result.symbols_with_updates += 1

            result.symbols_scanned += 1

        except Exception as e:
            result.errors.append(f"{symbol}: {e}")


# =============================================================================
# CLI ENTRY POINTS
# =============================================================================

def run_daily_scan(
    db_path: Optional[Path] = None,
    edgar_url: str = "http://localhost:8000/api/v1",
    max_symbols: Optional[int] = None,
) -> ScanResult:
    """
    Run daily EDGAR scan.

    Args:
        db_path: Database path (uses config default if not provided)
        edgar_url: EDGAR API URL
        max_symbols: Optional limit on symbols to scan

    Returns:
        ScanResult with statistics
    """
    from data.ingestion.market_data import MarketDataClient

    # Initialize components
    db_path = db_path or app_config.data.db_path
    repository = EquitiesRepository(db_path)
    market_client = MarketDataClient(provider="yahoo")
    universe_manager = UniverseManager(market_client, repository)

    edgar_config = EdgarConfig(base_url=edgar_url)
    edgar_client = EdgarClient(edgar_config)

    scanner = EdgarScanner(
        edgar_client=edgar_client,
        repository=repository,
        universe_manager=universe_manager,
    )

    # Get symbols
    symbols = universe_manager.get_universe()
    if max_symbols:
        symbols = symbols[:max_symbols]

    # Run scan
    def progress(done, total):
        print(f"\rScanning: {done}/{total} ({100*done/total:.0f}%)", end="", flush=True)

    print(f"Starting EDGAR scan for {len(symbols)} symbols...")
    result = asyncio.run(
        scanner.run_full_scan(symbols, progress_callback=progress)
    )
    print()

    # Report results
    print(f"\n=== EDGAR Scan Results ===")
    print(f"Duration: {result.duration_seconds:.1f}s")
    print(f"Symbols scanned: {result.symbols_scanned}")
    print(f"Symbols with updates: {result.symbols_with_updates}")
    print(f"Insider signals: {result.insider_signals}")
    print(f"Financial signals: {result.financial_signals}")

    if result.errors:
        print(f"\nErrors ({len(result.errors)}):")
        for error in result.errors[:10]:
            print(f"  - {error}")
        if len(result.errors) > 10:
            print(f"  ... and {len(result.errors) - 10} more")

    return result


def quick_test():
    """Quick test of scanner with limited symbols."""
    print("Testing EDGAR scanner...")

    # Use temporary database
    import tempfile
    db_path = Path(tempfile.mkdtemp()) / "test.db"

    result = run_daily_scan(
        db_path=db_path,
        max_symbols=5,
    )

    if result.success:
        print("\n✓ Scanner test completed successfully")
    else:
        print(f"\n✗ Scanner test had {len(result.errors)} errors")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        quick_test()
    else:
        run_daily_scan()
