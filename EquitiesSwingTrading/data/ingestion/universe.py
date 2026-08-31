"""
Universe Manager for Equities Swing Trading.

Manages the tradable stock universe with filtering by:
- Market cap
- Average daily volume
- Price
- Exchange
- EDGAR coverage

Provides sector breakdown and refresh scheduling.
"""

import logging
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import asyncio

import pandas as pd

from data.ingestion.market_data import MarketDataClient
from data.storage.models import UniverseMember
from data.storage.repository import EquitiesRepository
from config import config, UniverseConfig

logger = logging.getLogger(__name__)


# Pre-curated list of large-cap stocks for initial universe
# This avoids expensive screener API calls during development
SEED_UNIVERSE = [
    # Technology
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "INTC", "CRM",
    "ORCL", "ADBE", "CSCO", "AVGO", "TXN", "QCOM", "IBM", "NOW", "INTU", "AMAT",
    "MU", "LRCX", "ADI", "KLAC", "SNPS", "CDNS", "MRVL", "FTNT", "PANW", "CRWD",

    # Healthcare
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY",
    "AMGN", "GILD", "CVS", "ISRG", "VRTX", "REGN", "MDT", "SYK", "BSX", "ZTS",
    "BDX", "EW", "HCA", "CI", "HUM", "MCK", "IDXX", "DXCM", "IQV", "A",

    # Financials
    "BRK-B", "JPM", "V", "MA", "BAC", "WFC", "GS", "MS", "AXP", "SCHW",
    "BLK", "C", "SPGI", "CME", "ICE", "PNC", "USB", "TFC", "CB", "AON",
    "MMC", "AIG", "MET", "PRU", "TRV", "ALL", "AFL", "AMP", "MSCI", "MCO",

    # Consumer Discretionary
    "HD", "MCD", "NKE", "SBUX", "LOW", "TJX", "BKNG", "MAR", "CMG", "ORLY",
    "AZO", "ROST", "DG", "DLTR", "ULTA", "YUM", "DHI", "LEN", "PHM", "NVR",
    "GM", "F", "APTV", "LVS", "WYNN", "MGM", "EXPE", "ABNB", "LULU", "DECK",

    # Consumer Staples
    "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "CL", "EL",
    "KMB", "GIS", "K", "HSY", "SJM", "CAG", "CPB", "HRL", "MKC", "CLX",
    "KHC", "STZ", "BF-B", "TAP", "KDP", "MNST", "CHD", "WBA", "KR", "SYY",

    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "PXD",
    "DVN", "HES", "FANG", "HAL", "BKR", "KMI", "WMB", "OKE", "TRGP", "LNG",

    # Industrials
    "CAT", "DE", "UNP", "UPS", "RTX", "HON", "BA", "LMT", "GE", "MMM",
    "ETN", "ITW", "EMR", "ROK", "PH", "CTAS", "FAST", "PAYX", "ODFL", "CSX",
    "NSC", "GD", "NOC", "TDG", "WM", "RSG", "VRSK", "IR", "SWK", "CARR",

    # Materials
    "LIN", "APD", "SHW", "ECL", "DD", "NEM", "FCX", "NUE", "VMC", "MLM",
    "PPG", "ALB", "IFF", "CE", "EMN", "FMC", "CF", "MOS", "BALL", "AVY",

    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "SRE", "EXC", "XEL", "PCG", "WEC",
    "ED", "ES", "DTE", "PEG", "AWK", "AEE", "CMS", "CNP", "NI", "EVRG",

    # Real Estate (REITs)
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "DLR", "AVB",
    "EQR", "VTR", "ARE", "MAA", "UDR", "ESS", "INVH", "SUI", "ELS", "CPT",

    # Communication Services
    "GOOG", "DIS", "NFLX", "CMCSA", "VZ", "T", "TMUS", "CHTR", "EA", "TTWO",
    "ATVI", "WBD", "PARA", "FOX", "FOXA", "OMC", "IPG", "LYV", "MTCH", "SNAP",
]


class UniverseManager:
    """
    Manages the tradable stock universe.

    Filters stocks by market cap, volume, price, and other criteria.
    Provides sector breakdown and refresh scheduling.
    """

    # Sector ETF mappings for sector analysis
    SECTOR_ETFS = {
        "Technology": "XLK",
        "Healthcare": "XLV",
        "Financials": "XLF",
        "Consumer Discretionary": "XLY",
        "Consumer Staples": "XLP",
        "Energy": "XLE",
        "Industrials": "XLI",
        "Materials": "XLB",
        "Utilities": "XLU",
        "Real Estate": "XLRE",
        "Communication Services": "XLC",
    }

    def __init__(
        self,
        market_client: MarketDataClient,
        repository: EquitiesRepository,
        config: UniverseConfig = None,
    ):
        """
        Initialize universe manager.

        Args:
            market_client: Client for fetching market data
            repository: Database repository
            config: Universe configuration
        """
        self.market_client = market_client
        self.repository = repository
        self.config = config or UniverseConfig()
        self._universe_cache: list[str] = []
        self._cache_time: Optional[datetime] = None

    def get_seed_universe(self) -> list[str]:
        """
        Get pre-curated seed universe.

        Returns list of known large-cap, liquid stocks
        to bootstrap the system without API calls.
        """
        return SEED_UNIVERSE.copy()

    async def build_universe(
        self,
        seed_symbols: Optional[list[str]] = None,
        progress_callback: Optional[callable] = None,
    ) -> list[UniverseMember]:
        """
        Build/refresh the tradable universe.

        Args:
            seed_symbols: Starting list of symbols to filter
            progress_callback: Optional callback(completed, total)

        Returns:
            List of UniverseMember objects that pass all filters
        """
        if seed_symbols is None:
            seed_symbols = self.get_seed_universe()

        logger.info(f"Building universe from {len(seed_symbols)} seed symbols")

        valid_members = []
        total = len(seed_symbols)

        for i, symbol in enumerate(seed_symbols):
            try:
                # Get ticker info
                info = self.market_client.get_ticker_info(symbol)

                if "error" in info:
                    logger.debug(f"Skipping {symbol}: {info.get('error')}")
                    continue

                # Apply filters
                market_cap = info.get("market_cap") or 0
                avg_volume = info.get("avg_volume") or 0
                quote_type = info.get("quote_type", "")

                # Skip if ETF
                if self.config.exclude_etfs and quote_type == "ETF":
                    logger.debug(f"Skipping {symbol}: ETF")
                    continue

                # Market cap filter
                if market_cap < self.config.min_market_cap:
                    logger.debug(
                        f"Skipping {symbol}: market cap ${market_cap/1e9:.1f}B "
                        f"< ${self.config.min_market_cap/1e9:.1f}B"
                    )
                    continue

                # Volume filter
                if avg_volume < self.config.min_avg_daily_volume:
                    logger.debug(
                        f"Skipping {symbol}: avg volume ${avg_volume/1e6:.1f}M "
                        f"< ${self.config.min_avg_daily_volume/1e6:.1f}M"
                    )
                    continue

                # Create member
                member = UniverseMember(
                    symbol=symbol,
                    company_name=info.get("name"),
                    sector=info.get("sector"),
                    industry=info.get("industry"),
                    market_cap=market_cap,
                    avg_volume=avg_volume,
                    exchange=info.get("exchange"),
                    last_updated=date.today(),
                )
                valid_members.append(member)

            except Exception as e:
                logger.warning(f"Error processing {symbol}: {e}")

            if progress_callback:
                progress_callback(i + 1, total)

        # Sort by market cap (largest first)
        valid_members.sort(key=lambda m: m.market_cap or 0, reverse=True)

        # Apply max symbols limit
        if len(valid_members) > self.config.max_symbols:
            valid_members = valid_members[:self.config.max_symbols]

        logger.info(f"Universe built: {len(valid_members)} stocks passed filters")

        # Save to database
        self.repository.save_universe_batch(valid_members)
        self._universe_cache = [m.symbol for m in valid_members]
        self._cache_time = datetime.now()

        return valid_members

    def get_universe(self) -> list[str]:
        """
        Get current universe symbols.

        Returns cached list if available, otherwise loads from database.
        """
        if self._universe_cache:
            return self._universe_cache.copy()

        # Load from database
        members = self.repository.get_universe()
        self._universe_cache = [m.symbol for m in members]

        return self._universe_cache.copy()

    def get_sector_breakdown(self) -> dict[str, list[str]]:
        """
        Get symbols grouped by sector.

        Returns:
            Dict mapping sector name to list of symbols
        """
        members = self.repository.get_universe()

        sectors: dict[str, list[str]] = {}
        for m in members:
            sector = m.sector or "Unknown"
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(m.symbol)

        return sectors

    def get_sector_etf(self, sector: str) -> Optional[str]:
        """Get sector ETF symbol for a given sector."""
        return self.SECTOR_ETFS.get(sector)

    def filter_by_sector(self, sector: str) -> list[str]:
        """Get symbols in a specific sector."""
        members = self.repository.get_universe(sector=sector)
        return [m.symbol for m in members]

    def filter_by_market_cap(
        self,
        min_cap: Optional[float] = None,
        max_cap: Optional[float] = None,
    ) -> list[str]:
        """Filter universe by market cap range."""
        members = self.repository.get_universe(min_market_cap=min_cap)

        if max_cap:
            members = [m for m in members if (m.market_cap or 0) <= max_cap]

        return [m.symbol for m in members]

    def needs_refresh(self) -> bool:
        """Check if universe needs to be refreshed."""
        if not self._cache_time:
            return True

        age = datetime.now() - self._cache_time
        return age > self.config.refresh_interval

    def save_to_json(self, filepath: Path) -> None:
        """Save universe to JSON file."""
        members = self.repository.get_universe()
        data = {
            "updated": datetime.now().isoformat(),
            "count": len(members),
            "members": [m.to_dict() for m in members],
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

        logger.info(f"Saved universe to {filepath}")

    def load_from_json(self, filepath: Path) -> list[str]:
        """Load universe from JSON file."""
        with open(filepath) as f:
            data = json.load(f)

        members = [UniverseMember.from_dict(m) for m in data["members"]]
        self.repository.save_universe_batch(members)
        self._universe_cache = [m.symbol for m in members]

        logger.info(f"Loaded {len(members)} symbols from {filepath}")
        return self._universe_cache.copy()


# =============================================================================
# QUICK BUILD UTILITY
# =============================================================================

async def quick_build_universe(
    db_path: Optional[Path] = None,
    max_symbols: int = 50,
) -> list[str]:
    """
    Quick utility to build a small universe for testing.

    Args:
        db_path: Path to database (uses temp if None)
        max_symbols: Maximum symbols to include

    Returns:
        List of symbols in universe
    """
    import tempfile

    if db_path is None:
        db_path = Path(tempfile.mkdtemp()) / "equities.db"

    client = MarketDataClient(provider="yahoo")
    repo = EquitiesRepository(db_path)

    # Use subset of seed universe for quick build
    seed = SEED_UNIVERSE[:max_symbols * 2]  # Oversample to account for filtering

    cfg = UniverseConfig(max_symbols=max_symbols)
    manager = UniverseManager(client, repo, cfg)

    def progress(done, total):
        print(f"\rProcessing: {done}/{total} ({100*done/total:.0f}%)", end="")

    print(f"Building universe (max {max_symbols} symbols)...")
    members = await manager.build_universe(seed, progress_callback=progress)
    print(f"\nDone! {len(members)} symbols in universe")

    # Show sector breakdown
    print("\nSector breakdown:")
    sectors = manager.get_sector_breakdown()
    for sector, symbols in sorted(sectors.items()):
        print(f"  {sector}: {len(symbols)}")

    return [m.symbol for m in members]


def quick_test():
    """Synchronous test wrapper."""
    import asyncio
    return asyncio.run(quick_build_universe(max_symbols=30))


if __name__ == "__main__":
    quick_test()
