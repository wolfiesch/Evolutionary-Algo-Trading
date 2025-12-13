"""Repository for candle data storage."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

from crypto.data.storage.models import Candle

# We can reuse the Candle model from crypto as it is generic enough 
# (OHLCV is universal). If we need specific fields later, we can subclass.

class ForexCandleRepository:
    """SQLite repository for OHLCV candle data (Forex)."""

    def __init__(self, db_path: Path):
        """Initialize repository and create schema.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self):
        """Create candles table with primary key and index."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    turnover REAL NOT NULL DEFAULT 0.0,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_symbol_timestamp
                ON candles (symbol, timestamp)
            """)
            conn.commit()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for SQLite connections.

        Yields:
            SQLite connection with row_factory set to dict
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def insert(self, candle: Candle):
        """Insert or replace single candle.

        Args:
            candle: Candle object to insert
        """
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO candles
                (symbol, timestamp, open, high, low, close, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candle.symbol,
                candle.timestamp,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.turnover
            ))
            conn.commit()

    def insert_batch(self, candles: list[Candle]) -> int:
        """Batch insert candles.

        Args:
            candles: List of Candle objects to insert

        Returns:
            Number of candles inserted
        """
        if not candles:
            return 0

        with self._connection() as conn:
            data = [
                (
                    c.symbol,
                    c.timestamp,
                    c.open,
                    c.high,
                    c.low,
                    c.close,
                    c.volume,
                    c.turnover
                )
                for c in candles
            ]
            conn.executemany("""
                INSERT OR REPLACE INTO candles
                (symbol, timestamp, open, high, low, close, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, data)
            conn.commit()
            return len(candles)

    def get_latest(self, symbol: str, limit: int = 100) -> list[Candle]:
        """Get most recent candles, returned in chronological order (oldest first).

        Args:
            symbol: Trading pair symbol
            limit: Maximum number of candles to return

        Returns:
            List of Candle objects, ordered oldest to newest
        """
        with self._connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM candles
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit))

            rows = cursor.fetchall()
            # Reverse to get chronological order (oldest first)
            candles = [
                Candle(
                    symbol=row['symbol'],
                    timestamp=row['timestamp'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume'],
                    turnover=row['turnover']
                )
                for row in reversed(rows)
            ]
            return candles

    def count(self, symbol: str | None = None) -> int:
        """Count candles."""
        with self._connection() as conn:
            if symbol is None:
                cursor = conn.execute("SELECT COUNT(*) as cnt FROM candles")
            else:
                cursor = conn.execute(
                    "SELECT COUNT(*) as cnt FROM candles WHERE symbol = ?",
                    (symbol,)
                )
            row = cursor.fetchone()
            return row['cnt']
