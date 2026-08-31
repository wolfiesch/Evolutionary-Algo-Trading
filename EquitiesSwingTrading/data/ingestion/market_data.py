"""
Market Data Client for Equities Swing Trading

Fetches daily OHLCV data from Yahoo Finance (development) or Polygon.io (production).
Includes SPY and VIX data for market regime filters.
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from pathlib import Path

import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class MarketDataError(Exception):
    """Raised when market data fetch fails."""
    pass


class YahooFinanceClient:
    """
    Yahoo Finance client for daily OHLCV data.

    Free tier with rate limiting. Good for development and backtesting.
    For production, migrate to Polygon.io.

    Rate limits:
    - ~2000 requests/hour (unofficial)
    - Recommend 5 req/sec to be safe
    """

    # Standard tickers for market regime
    SPY_TICKER = "SPY"
    VIX_TICKER = "^VIX"

    def __init__(
        self,
        max_workers: int = 5,
        rate_limit_per_sec: float = 5.0
    ):
        """
        Initialize Yahoo Finance client.

        Args:
            max_workers: Max parallel downloads
            rate_limit_per_sec: Requests per second limit
        """
        self.max_workers = max_workers
        self.rate_limit_per_sec = rate_limit_per_sec
        self._last_request_time = 0.0
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        min_interval = 1.0 / self.rate_limit_per_sec

        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self._last_request_time = time.time()

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Fetch daily OHLCV bars for a symbol.

        Args:
            symbol: Stock ticker (e.g., "AAPL", "MSFT")
            start_date: Start date for data
            end_date: End date (defaults to today)

        Returns:
            DataFrame with columns: date, open, high, low, close, volume, adj_close
            Sorted oldest-first (ascending by date).

        Raises:
            MarketDataError: If fetch fails
        """
        self._rate_limit()

        if end_date is None:
            end_date = date.today()

        try:
            ticker = yf.Ticker(symbol)

            # yfinance expects string dates
            df = ticker.history(
                start=start_date.isoformat(),
                end=(end_date + timedelta(days=1)).isoformat(),  # end is exclusive
                interval="1d",
                auto_adjust=False  # Keep both close and adj_close
            )

            if df.empty:
                logger.warning(f"No data returned for {symbol}")
                return pd.DataFrame()

            # Standardize column names (yfinance uses title case)
            df = df.rename(columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
                "Adj Close": "adj_close",
                "Dividends": "dividends",
                "Stock Splits": "splits"
            })

            # Keep only needed columns
            keep_cols = ["open", "high", "low", "close", "volume", "adj_close"]
            df = df[[c for c in keep_cols if c in df.columns]]

            # Reset index to get date as column
            df = df.reset_index()
            df = df.rename(columns={"Date": "date"})

            # Ensure date is date type (not datetime)
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.date

            # Sort oldest first (required by gene pool primitives)
            df = df.sort_values("date", ascending=True).reset_index(drop=True)

            logger.debug(f"Fetched {len(df)} bars for {symbol}")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch {symbol}: {e}")
            raise MarketDataError(f"Failed to fetch {symbol}: {e}") from e

    def fetch_spy_bars(self, days: int = 252) -> pd.DataFrame:
        """
        Fetch SPY data for market trend filter.

        Args:
            days: Number of trading days to fetch

        Returns:
            DataFrame with SPY daily bars
        """
        # Add buffer for weekends/holidays
        calendar_days = int(days * 1.5)
        start_date = date.today() - timedelta(days=calendar_days)

        return self.fetch_daily_bars(self.SPY_TICKER, start_date)

    def fetch_vix_bars(self, days: int = 252) -> pd.DataFrame:
        """
        Fetch VIX data for volatility regime filter.

        Args:
            days: Number of trading days to fetch

        Returns:
            DataFrame with VIX daily bars
        """
        calendar_days = int(days * 1.5)
        start_date = date.today() - timedelta(days=calendar_days)

        return self.fetch_daily_bars(self.VIX_TICKER, start_date)

    async def fetch_daily_bars_async(
        self,
        symbol: str,
        start_date: date,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """
        Async wrapper for fetch_daily_bars.

        Runs in thread pool to avoid blocking event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            self.fetch_daily_bars,
            symbol,
            start_date,
            end_date
        )

    async def bulk_fetch_async(
        self,
        symbols: list[str],
        start_date: date,
        end_date: Optional[date] = None,
        progress_callback: Optional[callable] = None
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch data for multiple symbols in parallel.

        Args:
            symbols: List of tickers
            start_date: Start date
            end_date: End date
            progress_callback: Optional callback(completed, total) for progress

        Returns:
            Dict mapping symbol -> DataFrame
        """
        results = {}
        failed = []
        completed = 0

        # Process in batches to respect rate limits
        batch_size = self.max_workers

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]

            tasks = [
                self.fetch_daily_bars_async(sym, start_date, end_date)
                for sym in batch
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for sym, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    logger.warning(f"Failed to fetch {sym}: {result}")
                    failed.append(sym)
                elif result is not None and not result.empty:
                    results[sym] = result

                completed += 1
                if progress_callback:
                    progress_callback(completed, len(symbols))

            # Small delay between batches
            await asyncio.sleep(0.5)

        if failed:
            logger.warning(f"Failed to fetch {len(failed)} symbols: {failed[:10]}...")

        logger.info(f"Successfully fetched {len(results)}/{len(symbols)} symbols")
        return results

    def get_ticker_info(self, symbol: str) -> dict:
        """
        Get ticker metadata (sector, market cap, etc).

        Args:
            symbol: Stock ticker

        Returns:
            Dict with ticker info
        """
        self._rate_limit()

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info

            return {
                "symbol": symbol,
                "name": info.get("longName") or info.get("shortName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "avg_volume": info.get("averageVolume"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
                "quote_type": info.get("quoteType"),
            }
        except Exception as e:
            logger.warning(f"Failed to get info for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    def validate_symbol(self, symbol: str) -> bool:
        """
        Check if a symbol is valid and has data.

        Args:
            symbol: Stock ticker

        Returns:
            True if symbol is valid
        """
        try:
            df = self.fetch_daily_bars(
                symbol,
                date.today() - timedelta(days=10)
            )
            return not df.empty
        except MarketDataError:
            return False


class MarketDataClient:
    """
    High-level market data client with provider abstraction.

    Currently supports Yahoo Finance. Add Polygon.io support
    when ready for production.
    """

    def __init__(
        self,
        provider: str = "yahoo",
        **kwargs
    ):
        """
        Initialize market data client.

        Args:
            provider: "yahoo" or "polygon" (future)
            **kwargs: Provider-specific options
        """
        if provider == "yahoo":
            self._client = YahooFinanceClient(**kwargs)
        elif provider == "polygon":
            raise NotImplementedError("Polygon.io support coming in production")
        else:
            raise ValueError(f"Unknown provider: {provider}")

        self.provider = provider

    def fetch_daily_bars(
        self,
        symbol: str,
        start_date: date,
        end_date: Optional[date] = None
    ) -> pd.DataFrame:
        """Fetch daily bars for a symbol."""
        return self._client.fetch_daily_bars(symbol, start_date, end_date)

    def fetch_spy_bars(self, days: int = 252) -> pd.DataFrame:
        """Fetch SPY data for market filter."""
        return self._client.fetch_spy_bars(days)

    def fetch_vix_bars(self, days: int = 252) -> pd.DataFrame:
        """Fetch VIX data for volatility regime."""
        return self._client.fetch_vix_bars(days)

    async def bulk_fetch_async(
        self,
        symbols: list[str],
        start_date: date,
        end_date: Optional[date] = None,
        progress_callback: Optional[callable] = None
    ) -> dict[str, pd.DataFrame]:
        """Fetch data for multiple symbols."""
        return await self._client.bulk_fetch_async(
            symbols, start_date, end_date, progress_callback
        )

    def get_ticker_info(self, symbol: str) -> dict:
        """Get ticker metadata."""
        return self._client.get_ticker_info(symbol)

    def validate_symbol(self, symbol: str) -> bool:
        """Check if symbol is valid."""
        return self._client.validate_symbol(symbol)


# =============================================================================
# QUICK TEST / DEVELOPMENT UTILITIES
# =============================================================================

def quick_test():
    """Quick test of market data client."""
    client = MarketDataClient(provider="yahoo")

    # Test single fetch
    print("Fetching AAPL...")
    df = client.fetch_daily_bars("AAPL", date.today() - timedelta(days=30))
    print(f"Got {len(df)} bars")
    print(df.head())

    # Test SPY
    print("\nFetching SPY...")
    spy = client.fetch_spy_bars(days=60)
    print(f"Got {len(spy)} SPY bars")

    # Test VIX
    print("\nFetching VIX...")
    vix = client.fetch_vix_bars(days=60)
    print(f"Got {len(vix)} VIX bars")

    # Test ticker info
    print("\nGetting AAPL info...")
    info = client.get_ticker_info("AAPL")
    print(f"Sector: {info.get('sector')}, Market Cap: {info.get('market_cap')}")


if __name__ == "__main__":
    quick_test()
