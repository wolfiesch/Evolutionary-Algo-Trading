"""
SQLite Repository for Equities Swing Trading System.

Handles storage and retrieval of:
- Daily OHLCV candles
- Fundamental signals (from EDGAR)
- Filing events
- Universe membership
"""

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager
from datetime import date, datetime
from typing import Iterator, Optional

import pandas as pd

from data.storage.models import (
    DailyCandle,
    FundamentalSignal,
    FilingEvent,
    UniverseMember,
)

logger = logging.getLogger(__name__)


class EquitiesRepository:
    """
    SQLite repository for equities data.

    Provides storage for price data and fundamental signals with
    point-in-time query support for backtesting without look-ahead bias.
    """

    def __init__(self, db_path: Path):
        """
        Initialize repository and create schema.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self):
        """Create database tables and indexes."""
        with self._connection() as conn:
            # Daily candles table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_candles (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume INTEGER NOT NULL,
                    adj_close REAL,
                    PRIMARY KEY (symbol, date)
                )
            """)

            # Fundamental signals table (point-in-time)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS fundamental_signals (
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    signal_date TEXT NOT NULL,
                    signal_value REAL NOT NULL,
                    raw_data TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (symbol, signal_type, signal_date)
                )
            """)

            # Filing events table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS filing_events (
                    symbol TEXT NOT NULL,
                    filing_date TEXT NOT NULL,
                    form_type TEXT NOT NULL,
                    accession_number TEXT NOT NULL,
                    summary TEXT,
                    PRIMARY KEY (symbol, filing_date, form_type, accession_number)
                )
            """)

            # Universe membership table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS universe (
                    symbol TEXT PRIMARY KEY,
                    company_name TEXT,
                    sector TEXT,
                    industry TEXT,
                    market_cap REAL,
                    avg_volume REAL,
                    exchange TEXT,
                    last_updated TEXT
                )
            """)

            # Create indexes for common queries
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_symbol_date
                ON daily_candles (symbol, date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_signals_symbol_type_date
                ON fundamental_signals (symbol, signal_type, signal_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_filings_symbol_date
                ON filing_events (symbol, filing_date)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_universe_sector
                ON universe (sector)
            """)

            conn.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # =========================================================================
    # DAILY CANDLES
    # =========================================================================

    def save_daily_candles(self, candles: list[DailyCandle]) -> int:
        """
        Save daily candles (insert or replace).

        Args:
            candles: List of DailyCandle objects

        Returns:
            Number of candles saved
        """
        if not candles:
            return 0

        with self._connection() as conn:
            data = [
                (
                    c.symbol,
                    c.date.isoformat(),
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                    c.adj_close,
                )
                for c in candles
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO daily_candles
                (symbol, date, open, high, low, close, volume, adj_close)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(candles)

    def save_daily_candles_df(self, symbol: str, df: pd.DataFrame) -> int:
        """
        Save candles from DataFrame (output of MarketDataClient).

        Args:
            symbol: Stock symbol
            df: DataFrame with columns: date, open, high, low, close, volume, adj_close

        Returns:
            Number of candles saved
        """
        if df.empty:
            return 0

        candles = []
        for _, row in df.iterrows():
            dt = row["date"]
            if isinstance(dt, str):
                dt = date.fromisoformat(dt)
            elif isinstance(dt, datetime):
                dt = dt.date()

            candles.append(DailyCandle(
                symbol=symbol,
                date=dt,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=int(row["volume"]),
                adj_close=row.get("adj_close"),
            ))

        return self.save_daily_candles(candles)

    def get_daily_candles(
        self,
        symbol: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """
        Get daily candles as DataFrame.

        Args:
            symbol: Stock symbol
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with candle data, sorted oldest-first
        """
        with self._connection() as conn:
            query = "SELECT * FROM daily_candles WHERE symbol = ?"
            params = [symbol]

            if start_date:
                query += " AND date >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND date <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY date ASC"

            df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                df["date"] = pd.to_datetime(df["date"]).dt.date

            return df

    def get_latest_candles(
        self,
        symbol: str,
        count: int = 200
    ) -> pd.DataFrame:
        """
        Get most recent N candles.

        Args:
            symbol: Stock symbol
            count: Number of candles to fetch

        Returns:
            DataFrame sorted oldest-first (for indicator calculation)
        """
        with self._connection() as conn:
            # Get most recent, then reverse to oldest-first
            query = """
                SELECT * FROM daily_candles
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=[symbol, count])

            if not df.empty:
                df["date"] = pd.to_datetime(df["date"]).dt.date
                # Reverse to oldest-first
                df = df.iloc[::-1].reset_index(drop=True)

            return df

    def get_candle_count(self, symbol: Optional[str] = None) -> int:
        """Count candles in database."""
        with self._connection() as conn:
            if symbol:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM daily_candles WHERE symbol = ?",
                    (symbol,)
                )
            else:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM daily_candles")
            return cursor.fetchone()["cnt"]

    def get_symbols_with_data(self) -> list[str]:
        """Get list of symbols with candle data."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol"
            )
            return [row["symbol"] for row in cursor.fetchall()]

    # =========================================================================
    # FUNDAMENTAL SIGNALS
    # =========================================================================

    def save_fundamental_signal(self, signal: FundamentalSignal) -> None:
        """Save a fundamental signal."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO fundamental_signals
                (symbol, signal_type, signal_date, signal_value, raw_data)
                VALUES (?, ?, ?, ?, ?)
            """, (
                signal.symbol,
                signal.signal_type,
                signal.signal_date.isoformat(),
                signal.signal_value,
                signal.raw_data,
            ))
            conn.commit()

    def get_fundamental_signal(
        self,
        symbol: str,
        signal_type: str,
        as_of_date: date
    ) -> Optional[float]:
        """
        Get fundamental signal value as of a specific date.

        CRITICAL: This is a point-in-time query. It returns the most recent
        signal that was available ON OR BEFORE as_of_date, preventing
        look-ahead bias in backtesting.

        Args:
            symbol: Stock symbol
            signal_type: Type of signal (e.g., 'insider_buy_intensity')
            as_of_date: Date to query as of (backtest date)

        Returns:
            Signal value or None if no data available
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT signal_value FROM fundamental_signals
                WHERE symbol = ? AND signal_type = ? AND signal_date <= ?
                ORDER BY signal_date DESC
                LIMIT 1
            """, (symbol, signal_type, as_of_date.isoformat()))

            row = cursor.fetchone()
            return row["signal_value"] if row else None

    def get_fundamental_signal_history(
        self,
        symbol: str,
        signal_type: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> pd.DataFrame:
        """Get historical fundamental signals."""
        with self._connection() as conn:
            query = """
                SELECT signal_date, signal_value FROM fundamental_signals
                WHERE symbol = ? AND signal_type = ?
            """
            params = [symbol, signal_type]

            if start_date:
                query += " AND signal_date >= ?"
                params.append(start_date.isoformat())

            if end_date:
                query += " AND signal_date <= ?"
                params.append(end_date.isoformat())

            query += " ORDER BY signal_date ASC"

            df = pd.read_sql_query(query, conn, params=params)

            if not df.empty:
                df["signal_date"] = pd.to_datetime(df["signal_date"]).dt.date

            return df

    # =========================================================================
    # FILING EVENTS
    # =========================================================================

    def save_filing_event(self, event: FilingEvent) -> None:
        """Save a filing event."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO filing_events
                (symbol, filing_date, form_type, accession_number, summary)
                VALUES (?, ?, ?, ?, ?)
            """, (
                event.symbol,
                event.filing_date.isoformat(),
                event.form_type,
                event.accession_number,
                event.summary,
            ))
            conn.commit()

    def get_recent_filings(
        self,
        symbol: str,
        days: int = 90,
        form_types: Optional[list[str]] = None,
        as_of_date: Optional[date] = None,
    ) -> list[FilingEvent]:
        """
        Get recent filings for a symbol.

        Args:
            symbol: Stock symbol
            days: Number of days to look back
            form_types: Optional filter by form types
            as_of_date: Reference date (for point-in-time queries)
        """
        if as_of_date is None:
            as_of_date = date.today()

        from datetime import timedelta
        start_date = as_of_date - timedelta(days=days)

        with self._connection() as conn:
            query = """
                SELECT * FROM filing_events
                WHERE symbol = ? AND filing_date >= ? AND filing_date <= ?
            """
            params = [symbol, start_date.isoformat(), as_of_date.isoformat()]

            if form_types:
                placeholders = ",".join("?" for _ in form_types)
                query += f" AND form_type IN ({placeholders})"
                params.extend(form_types)

            query += " ORDER BY filing_date DESC"

            cursor = conn.execute(query, params)
            events = []
            for row in cursor.fetchall():
                events.append(FilingEvent(
                    symbol=row["symbol"],
                    filing_date=date.fromisoformat(row["filing_date"]),
                    form_type=row["form_type"],
                    accession_number=row["accession_number"],
                    summary=row["summary"],
                ))
            return events

    # =========================================================================
    # UNIVERSE MANAGEMENT
    # =========================================================================

    def save_universe_member(self, member: UniverseMember) -> None:
        """Save or update a universe member."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO universe
                (symbol, company_name, sector, industry, market_cap, avg_volume, exchange, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                member.symbol,
                member.company_name,
                member.sector,
                member.industry,
                member.market_cap,
                member.avg_volume,
                member.exchange,
                member.last_updated.isoformat() if member.last_updated else None,
            ))
            conn.commit()

    def save_universe_batch(self, members: list[UniverseMember]) -> int:
        """Save multiple universe members."""
        if not members:
            return 0

        with self._connection() as conn:
            data = [
                (
                    m.symbol,
                    m.company_name,
                    m.sector,
                    m.industry,
                    m.market_cap,
                    m.avg_volume,
                    m.exchange,
                    m.last_updated.isoformat() if m.last_updated else None,
                )
                for m in members
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO universe
                (symbol, company_name, sector, industry, market_cap, avg_volume, exchange, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(members)

    def get_universe(
        self,
        sector: Optional[str] = None,
        min_market_cap: Optional[float] = None,
        min_avg_volume: Optional[float] = None,
    ) -> list[UniverseMember]:
        """
        Get universe members with optional filters.

        Args:
            sector: Filter by sector
            min_market_cap: Minimum market cap
            min_avg_volume: Minimum average volume
        """
        with self._connection() as conn:
            query = "SELECT * FROM universe WHERE 1=1"
            params = []

            if sector:
                query += " AND sector = ?"
                params.append(sector)

            if min_market_cap:
                query += " AND market_cap >= ?"
                params.append(min_market_cap)

            if min_avg_volume:
                query += " AND avg_volume >= ?"
                params.append(min_avg_volume)

            query += " ORDER BY symbol"

            cursor = conn.execute(query, params)
            members = []
            for row in cursor.fetchall():
                last_updated = row["last_updated"]
                if last_updated:
                    last_updated = date.fromisoformat(last_updated)

                members.append(UniverseMember(
                    symbol=row["symbol"],
                    company_name=row["company_name"],
                    sector=row["sector"],
                    industry=row["industry"],
                    market_cap=row["market_cap"],
                    avg_volume=row["avg_volume"],
                    exchange=row["exchange"],
                    last_updated=last_updated,
                ))
            return members

    def get_universe_symbols(self) -> list[str]:
        """Get list of all symbols in universe."""
        with self._connection() as conn:
            cursor = conn.execute("SELECT symbol FROM universe ORDER BY symbol")
            return [row["symbol"] for row in cursor.fetchall()]

    def get_sectors(self) -> list[str]:
        """Get list of unique sectors in universe."""
        with self._connection() as conn:
            cursor = conn.execute(
                "SELECT DISTINCT sector FROM universe WHERE sector IS NOT NULL ORDER BY sector"
            )
            return [row["sector"] for row in cursor.fetchall()]

    def clear_universe(self) -> None:
        """Clear all universe members."""
        with self._connection() as conn:
            conn.execute("DELETE FROM universe")
            conn.commit()


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Quick test of repository."""
    from datetime import date, timedelta
    import tempfile

    # Create temp database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    print(f"Testing repository at: {db_path}")

    repo = EquitiesRepository(db_path)

    # Test saving candles
    candles = [
        DailyCandle("AAPL", date(2025, 1, 1), 180.0, 182.0, 179.0, 181.0, 1000000),
        DailyCandle("AAPL", date(2025, 1, 2), 181.0, 183.0, 180.0, 182.5, 1100000),
        DailyCandle("AAPL", date(2025, 1, 3), 182.5, 185.0, 182.0, 184.0, 1200000),
    ]
    saved = repo.save_daily_candles(candles)
    print(f"Saved {saved} candles")

    # Test reading candles
    df = repo.get_daily_candles("AAPL")
    print(f"Retrieved {len(df)} candles")
    print(df)

    # Test fundamental signal
    signal = FundamentalSignal(
        symbol="AAPL",
        signal_type="insider_buy_intensity",
        signal_date=date(2025, 1, 2),
        signal_value=0.75,
    )
    repo.save_fundamental_signal(signal)

    # Test point-in-time query
    val = repo.get_fundamental_signal("AAPL", "insider_buy_intensity", date(2025, 1, 1))
    print(f"Signal as of 1/1: {val}")  # Should be None (signal not available yet)

    val = repo.get_fundamental_signal("AAPL", "insider_buy_intensity", date(2025, 1, 3))
    print(f"Signal as of 1/3: {val}")  # Should be 0.75

    # Test universe
    member = UniverseMember(
        symbol="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3e12,
        avg_volume=50e6,
        exchange="NASDAQ",
        last_updated=date.today(),
    )
    repo.save_universe_member(member)

    universe = repo.get_universe()
    print(f"Universe: {[m.symbol for m in universe]}")

    # Cleanup
    db_path.unlink()
    print("Test passed!")


if __name__ == "__main__":
    quick_test()
