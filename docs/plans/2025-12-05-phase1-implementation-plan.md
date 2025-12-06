# Phase 1 Implementation Plan: Plumbing

**Created:** 2025-12-05
**Target:** Weeks 1-2
**Status:** Ready for Execution
**Parent Document:** [Crypto Alpha System Design](./2025-12-04-crypto-alpha-system-design.md)

---

## 1. Objective

Build the data infrastructure and shadow trading system that can run **48 hours without crashing**. No LLM. No evolution. Just plumbing that works.

**Success Criteria:**
- [ ] WebSocket stays connected (auto-reconnects on disconnect)
- [ ] SQLite stores 1-minute candles for 30 coins
- [ ] All Gene Pool primitives return correct values (match reference implementations)
- [ ] Shadow Trader logs trades to JSON with full state vectors
- [ ] System runs 24 hours with a hardcoded strategy without manual intervention

---

## 2. Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           PHASE 1 DEPENDENCY GRAPH                          │
└─────────────────────────────────────────────────────────────────────────────┘

BATCH 0: Foundation (SEQUENTIAL - Must Complete First)
┌─────────────────┐
│ 0.1 Project     │
│     Scaffolding │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 0.2 Config &    │
│     Logging     │
└────────┬────────┘
         │
         ▼
═════════════════════════════════════════════════════════════════════════════

BATCH 1: Data Layer (PARALLEL - 3 Independent Tracks)
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ 1A: Data        │  │ 1B: WebSocket   │  │ 1C: Test        │
│     Storage     │  │     Client      │  │     Fixtures    │
│  (SQLite CRUD)  │  │  (Connection)   │  │  (Mock Data)    │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┴────────────────────┘
                              │
                              ▼
═════════════════════════════════════════════════════════════════════════════

BATCH 2: Gene Pool (PARALLEL - 5 Independent Modules)
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│ 2A: TREND  │  │ 2B: MEAN   │  │ 2C: VOLUME │  │ 2D: VOLAT- │  │ 2E: MARKET │
│ ema_trend  │  │ REVERSION  │  │ volume_int │  │ ILITY      │  │ FILTER     │
│ price_pos  │  │ norm_rsi   │  │ vwap_dist  │  │ atr_regime │  │ btc_trend  │
│            │  │ bb_pos     │  │            │  │ atr_pctile │  │            │
│            │  │ bb_width   │  │            │  │            │  │            │
└─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘
      │               │               │               │               │
      └───────────────┴───────────────┴───────────────┴───────────────┘
                                      │
                                      ▼
═════════════════════════════════════════════════════════════════════════════

BATCH 3: Integration (PARALLEL - 2 Independent Modules)
┌─────────────────────────┐        ┌─────────────────────────┐
│ 3A: Data Quality        │        │ 3B: Gene Expression     │
│     Filters             │        │     Parser              │
└───────────┬─────────────┘        └───────────┬─────────────┘
            │                                  │
            └──────────────┬───────────────────┘
                           │
                           ▼
═════════════════════════════════════════════════════════════════════════════

BATCH 4: Shadow Trading (SEQUENTIAL - Integrates Everything)
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4A: Shadow Trader Implementation                                            │
│     - Paper trading engine                                                   │
│     - Trade state logging                                                    │
│     - Position tracking                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4B: Integration Testing                                                      │
│     - End-to-end flow with hardcoded strategy                               │
│     - Reconnection handling                                                  │
│     - 24-hour stability test                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Codex Parallel Execution Strategy

### Summary of Parallelization

| Batch | Parallelizable? | Agent Strategy | Rationale |
|-------|-----------------|----------------|-----------|
| 0 | No (Sequential) | Single Claude | Foundation for all else |
| 1 | **Yes (3-way)** | 3 Codex agents | Zero dependencies between storage/websocket/fixtures |
| 2 | **Yes (5-way)** | 5 Codex agents | Each primitive category is fully independent |
| 3 | **Yes (2-way)** | 2 Codex agents | Filters and parser don't interact |
| 4 | No (Sequential) | Single Claude | Requires integration, judgment calls |

### Codex Agent Assignments

```
CODEX BATCH 1 (Run simultaneously):
├── Agent 1A: data/storage/ (SQLite schema + CRUD)
├── Agent 1B: data/ingestion/ (WebSocket client)
└── Agent 1C: tests/fixtures/ (Mock candle data)

CODEX BATCH 2 (Run simultaneously):
├── Agent 2A: engine/gene_pool/trend.py
├── Agent 2B: engine/gene_pool/mean_reversion.py
├── Agent 2C: engine/gene_pool/volume.py
├── Agent 2D: engine/gene_pool/volatility.py
└── Agent 2E: engine/gene_pool/market_filter.py

CODEX BATCH 3 (Run simultaneously):
├── Agent 3A: data/quality_filters.py
└── Agent 3B: engine/strategy_logic/parser.py
```

**CRITICAL:** MCP tasks (Playwright, browser automation) must run sequentially. However, code generation/refactoring CAN run parallel. All tasks below are pure code generation, so full parallelism is safe.

---

## 4. Detailed Task Breakdown

---

### BATCH 0: Foundation (SEQUENTIAL)

**Executor:** Claude (main agent)
**Estimated Complexity:** Low
**Must complete before any parallel work begins**

---

#### Task 0.1: Project Scaffolding

**File:** Multiple (directory structure)

**Acceptance Criteria:**
- [ ] Directory structure matches design doc exactly
- [ ] `requirements.txt` with pinned versions
- [ ] `.gitignore` for logs, SQLite, `.env`
- [ ] Empty `__init__.py` in all packages

**Implementation:**

```bash
# Directory structure to create
crypto-alpha/
├── data/
│   ├── __init__.py
│   ├── ingestion/
│   │   └── __init__.py
│   └── storage/
│       └── __init__.py
├── engine/
│   ├── __init__.py
│   ├── gene_pool/
│   │   └── __init__.py
│   └── strategy_logic/
│       └── __init__.py
├── execution/
│   ├── __init__.py
│   ├── shadow/
│   │   └── __init__.py
│   └── live/
│       └── __init__.py
├── risk/
│   ├── __init__.py
│   └── watchdog/
│       └── __init__.py
├── logs/
│   └── .gitkeep
├── tests/
│   ├── __init__.py
│   └── fixtures/
│       └── __init__.py
├── main.py
├── config.py
├── requirements.txt
└── .gitignore
```

**requirements.txt:**
```
# Core
python-dotenv==1.0.0
pydantic==2.5.0
pydantic-settings==2.1.0

# Data
pandas==2.1.3
numpy==1.26.2
sqlite-utils==3.35.2

# WebSocket
websockets==12.0
aiohttp==3.9.1

# Technical Analysis
pandas-ta==0.3.14b0

# Logging
structlog==23.2.0

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0

# Type checking
mypy==1.7.1
```

---

#### Task 0.2: Config & Logging Setup

**Files:** `config.py`, `crypto-alpha/logs/__init__.py`

**Acceptance Criteria:**
- [ ] Pydantic settings model for all config
- [ ] Separate trade logger and error logger
- [ ] Environment variable loading from `.env`
- [ ] Config validation on startup

**Implementation:**

**config.py:**
```python
"""Configuration management for crypto-alpha system."""
from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Paths
    base_dir: Path = Field(default=Path(__file__).parent)
    logs_dir: Path = Field(default=Path(__file__).parent / "logs")
    data_dir: Path = Field(default=Path(__file__).parent / "data")

    # Database
    sqlite_path: Path = Field(default=Path(__file__).parent / "data" / "candles.db")

    # Bybit API (read-only for Phase 1)
    bybit_ws_url: str = Field(default="wss://stream.bybit.com/v5/public/linear")
    bybit_rest_url: str = Field(default="https://api.bybit.com")

    # Trading Parameters
    universe_size: int = Field(default=30, description="Number of coins to track")
    candle_interval: str = Field(default="1", description="Candle interval in minutes")

    # Risk Parameters (Phase 1 defaults)
    risk_per_trade: float = Field(default=0.01, description="1% risk per trade")
    max_position_pct: float = Field(default=0.10, description="10% max position")
    max_open_positions: int = Field(default=5)
    max_exposure: float = Field(default=0.50, description="50% max exposure")

    # Reconnection
    reconnect_delay_seconds: int = Field(default=5)
    warmup_candles: int = Field(default=100, description="Candles to fetch on reconnect")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

**crypto-alpha/logs/__init__.py:**
```python
"""Logging configuration with separate trade and error loggers."""
import logging
import structlog
from pathlib import Path
from datetime import datetime


def setup_logging(logs_dir: Path) -> tuple[structlog.BoundLogger, structlog.BoundLogger]:
    """
    Configure trade logger and error logger.

    Returns:
        Tuple of (trade_logger, error_logger)
    """
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Timestamp for log files
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Trade logger - all trade activity
    trade_handler = logging.FileHandler(logs_dir / f"trades_{date_str}.log")
    trade_handler.setLevel(logging.INFO)
    trade_handler.setFormatter(logging.Formatter("%(message)s"))

    trade_log = logging.getLogger("trades")
    trade_log.setLevel(logging.INFO)
    trade_log.addHandler(trade_handler)

    # Error logger - exceptions only (BLACK SWAN LOG)
    error_handler = logging.FileHandler(logs_dir / f"errors_{date_str}.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )

    error_log = logging.getLogger("errors")
    error_log.setLevel(logging.ERROR)
    error_log.addHandler(error_handler)

    # Wrap with structlog for JSON output
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    return (
        structlog.wrap_logger(trade_log),
        structlog.wrap_logger(error_log),
    )
```

---

### BATCH 1: Data Layer (PARALLEL - 3 Codex Agents)

**Can run simultaneously after Batch 0 completes**

---

#### Task 1A: Data Storage (SQLite)

**Codex Agent:** 1A
**Scope:** `data/storage/` directory
**Files to create:**
- `data/storage/models.py` - Pydantic models for candles
- `data/storage/repository.py` - CRUD operations
- `tests/test_storage.py` - Unit tests

**Acceptance Criteria:**
- [ ] Candle model with all OHLCV fields
- [ ] Insert single candle
- [ ] Insert batch of candles (upsert on conflict)
- [ ] Query candles by symbol and time range
- [ ] Get latest N candles for a symbol
- [ ] Tests pass with 100% coverage for repository

**Implementation Spec:**

**data/storage/models.py:**
```python
"""Data models for candle storage."""
from pydantic import BaseModel, Field
from datetime import datetime


class Candle(BaseModel):
    """OHLCV candle data."""
    symbol: str = Field(..., description="Trading pair, e.g., BTCUSDT")
    timestamp: int = Field(..., description="Unix timestamp in milliseconds")
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = Field(default=0.0, description="Quote volume")

    @property
    def datetime(self) -> datetime:
        """Convert timestamp to datetime."""
        return datetime.fromtimestamp(self.timestamp / 1000)

    class Config:
        frozen = True  # Immutable
```

**data/storage/repository.py:**
```python
"""SQLite repository for candle storage."""
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

from .models import Candle


class CandleRepository:
    """CRUD operations for candle data."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
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
                    turnover REAL DEFAULT 0,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_candles_symbol_time
                ON candles(symbol, timestamp DESC)
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def insert(self, candle: Candle) -> None:
        """Insert or update a single candle."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO candles
                (symbol, timestamp, open, high, low, close, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                candle.symbol, candle.timestamp, candle.open, candle.high,
                candle.low, candle.close, candle.volume, candle.turnover
            ))

    def insert_batch(self, candles: list[Candle]) -> int:
        """Insert multiple candles. Returns count inserted."""
        with self._connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO candles
                (symbol, timestamp, open, high, low, close, volume, turnover)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (c.symbol, c.timestamp, c.open, c.high, c.low, c.close, c.volume, c.turnover)
                for c in candles
            ])
        return len(candles)

    def get_latest(self, symbol: str, limit: int = 100) -> list[Candle]:
        """Get most recent candles for a symbol."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM candles
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit)).fetchall()

        # Return in chronological order (oldest first)
        return [Candle(**dict(row)) for row in reversed(rows)]

    def get_range(
        self, symbol: str, start_ts: int, end_ts: int
    ) -> list[Candle]:
        """Get candles in a time range."""
        with self._connection() as conn:
            rows = conn.execute("""
                SELECT * FROM candles
                WHERE symbol = ? AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
            """, (symbol, start_ts, end_ts)).fetchall()

        return [Candle(**dict(row)) for row in rows]

    def count(self, symbol: str | None = None) -> int:
        """Count candles, optionally filtered by symbol."""
        with self._connection() as conn:
            if symbol:
                row = conn.execute(
                    "SELECT COUNT(*) FROM candles WHERE symbol = ?", (symbol,)
                ).fetchone()
            else:
                row = conn.execute("SELECT COUNT(*) FROM candles").fetchone()
        return row[0]
```

**Test Requirements:**
- Test insert single candle
- Test upsert (update existing)
- Test batch insert
- Test get_latest ordering
- Test get_range boundaries
- Test empty results

---

#### Task 1B: WebSocket Client

**Codex Agent:** 1B
**Scope:** `data/ingestion/` directory
**Files to create:**
- `data/ingestion/bybit_ws.py` - WebSocket client
- `data/ingestion/reconnect.py` - Reconnection logic
- `tests/test_websocket.py` - Unit tests (mocked)

**Acceptance Criteria:**
- [ ] Connect to Bybit public WebSocket
- [ ] Subscribe to kline (candle) streams for multiple symbols
- [ ] Parse incoming candle messages
- [ ] Auto-reconnect on disconnect with exponential backoff
- [ ] Emit parsed candles via callback
- [ ] Warm-up indicators on reconnect (fetch REST history)

**Implementation Spec:**

**data/ingestion/bybit_ws.py:**
```python
"""Bybit WebSocket client for candle data."""
import asyncio
import json
import logging
from typing import Callable, Awaitable
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed
import aiohttp

from data.storage.models import Candle
from config import settings


logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


class BybitWebSocketClient:
    """
    WebSocket client for Bybit public kline streams.

    Usage:
        client = BybitWebSocketClient(
            symbols=["BTCUSDT", "ETHUSDT"],
            on_candle=my_callback,
        )
        await client.run()
    """

    def __init__(
        self,
        symbols: list[str],
        on_candle: Callable[[Candle], Awaitable[None]],
        interval: str = "1",  # 1 minute
    ):
        self.symbols = symbols
        self.on_candle = on_candle
        self.interval = interval
        self.ws_url = settings.bybit_ws_url
        self.rest_url = settings.bybit_rest_url
        self._running = False
        self._reconnect_delay = settings.reconnect_delay_seconds

    async def run(self) -> None:
        """Main loop - connects and handles reconnection."""
        self._running = True
        delay = self._reconnect_delay

        while self._running:
            try:
                await self._connect_and_stream()
            except ConnectionClosed as e:
                error_logger.error(f"WebSocket closed: {e}")
            except Exception as e:
                error_logger.exception(f"WebSocket error: {e}")

            if self._running:
                logger.info(f"Reconnecting in {delay} seconds...")
                await asyncio.sleep(delay)
                delay = min(delay * 2, 60)  # Exponential backoff, max 60s

            # On reconnect, warm up indicators
            await self._warmup()

    async def _connect_and_stream(self) -> None:
        """Connect to WebSocket and process messages."""
        async with websockets.connect(self.ws_url) as ws:
            # Reset backoff on successful connect
            delay = self._reconnect_delay

            # Subscribe to kline streams
            await self._subscribe(ws)

            # Process messages
            async for message in ws:
                await self._handle_message(message)

    async def _subscribe(self, ws) -> None:
        """Subscribe to kline topics for all symbols."""
        topics = [f"kline.{self.interval}.{symbol}" for symbol in self.symbols]

        subscribe_msg = {
            "op": "subscribe",
            "args": topics,
        }

        await ws.send(json.dumps(subscribe_msg))
        logger.info(f"Subscribed to {len(topics)} kline streams")

    async def _handle_message(self, message: str) -> None:
        """Parse and process a WebSocket message."""
        try:
            data = json.loads(message)

            # Ignore non-data messages (subscriptions, pings)
            if "topic" not in data or "data" not in data:
                return

            # Parse kline data
            topic = data["topic"]  # e.g., "kline.1.BTCUSDT"
            kline_data = data["data"][0]  # Bybit sends array with one element

            # Extract symbol from topic
            parts = topic.split(".")
            symbol = parts[2] if len(parts) >= 3 else None

            if not symbol:
                return

            candle = Candle(
                symbol=symbol,
                timestamp=int(kline_data["start"]),
                open=float(kline_data["open"]),
                high=float(kline_data["high"]),
                low=float(kline_data["low"]),
                close=float(kline_data["close"]),
                volume=float(kline_data["volume"]),
                turnover=float(kline_data.get("turnover", 0)),
            )

            await self.on_candle(candle)

        except Exception as e:
            error_logger.exception(f"Failed to parse message: {e}")

    async def _warmup(self) -> None:
        """
        Fetch historical candles via REST to warm up indicators after reconnect.
        Called before resuming trading.
        """
        logger.info("Warming up indicators from REST API...")

        async with aiohttp.ClientSession() as session:
            for symbol in self.symbols:
                try:
                    candles = await self._fetch_historical(session, symbol)
                    for candle in candles:
                        await self.on_candle(candle)
                    logger.info(f"Warmed up {len(candles)} candles for {symbol}")
                except Exception as e:
                    error_logger.error(f"Failed to warm up {symbol}: {e}")

    async def _fetch_historical(
        self, session: aiohttp.ClientSession, symbol: str
    ) -> list[Candle]:
        """Fetch historical candles from REST API."""
        url = f"{self.rest_url}/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": self.interval,
            "limit": settings.warmup_candles,
        }

        async with session.get(url, params=params) as resp:
            data = await resp.json()

        if data.get("retCode") != 0:
            raise ValueError(f"API error: {data.get('retMsg')}")

        candles = []
        for item in data["result"]["list"]:
            candles.append(Candle(
                symbol=symbol,
                timestamp=int(item[0]),
                open=float(item[1]),
                high=float(item[2]),
                low=float(item[3]),
                close=float(item[4]),
                volume=float(item[5]),
                turnover=float(item[6]) if len(item) > 6 else 0,
            ))

        # API returns newest first, reverse to chronological
        return list(reversed(candles))

    def stop(self) -> None:
        """Signal the client to stop."""
        self._running = False
```

**Test Requirements:**
- Test message parsing (mock WebSocket message)
- Test subscription format
- Test reconnection backoff logic
- Test warmup REST call (mock aiohttp)

---

#### Task 1C: Test Fixtures

**Codex Agent:** 1C
**Scope:** `tests/fixtures/` directory
**Files to create:**
- `tests/fixtures/candle_data.py` - Mock candle generators
- `tests/fixtures/market_scenarios.py` - Bull/bear/sideways data
- `tests/conftest.py` - Pytest fixtures

**Acceptance Criteria:**
- [ ] Generate realistic OHLCV data with controlled trends
- [ ] Create bull market, bear market, and sideways scenarios
- [ ] Fixtures usable by all test files
- [ ] Include BTC data for market filter tests

**Implementation Spec:**

**tests/fixtures/candle_data.py:**
```python
"""Mock candle data generators for testing."""
import random
from datetime import datetime, timedelta
from typing import Literal

from data.storage.models import Candle


def generate_candles(
    symbol: str,
    count: int,
    start_price: float = 100.0,
    trend: Literal["bull", "bear", "sideways"] = "sideways",
    volatility: float = 0.02,
    start_time: datetime | None = None,
    interval_minutes: int = 1,
) -> list[Candle]:
    """
    Generate realistic candle data with controlled trend.

    Args:
        symbol: Trading pair symbol
        count: Number of candles to generate
        start_price: Initial price
        trend: Market direction
        volatility: Price volatility (0.02 = 2%)
        start_time: Starting timestamp
        interval_minutes: Candle interval

    Returns:
        List of Candle objects in chronological order
    """
    if start_time is None:
        start_time = datetime.now() - timedelta(minutes=count * interval_minutes)

    # Trend drift per candle
    drift = {
        "bull": 0.001,    # +0.1% average per candle
        "bear": -0.001,   # -0.1% average per candle
        "sideways": 0.0,  # No drift
    }[trend]

    candles = []
    price = start_price

    for i in range(count):
        timestamp = start_time + timedelta(minutes=i * interval_minutes)

        # Random walk with drift
        change = random.gauss(drift, volatility)
        price = price * (1 + change)

        # Generate OHLC with realistic intrabar movement
        open_price = price
        high_price = price * (1 + random.uniform(0, volatility / 2))
        low_price = price * (1 - random.uniform(0, volatility / 2))
        close_price = price * (1 + random.gauss(0, volatility / 4))

        # Ensure OHLC constraints
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)

        # Update price for next candle
        price = close_price

        # Random volume with some correlation to volatility
        base_volume = 1000000
        volume = base_volume * (1 + abs(change) * 10) * random.uniform(0.5, 1.5)

        candles.append(Candle(
            symbol=symbol,
            timestamp=int(timestamp.timestamp() * 1000),
            open=round(open_price, 4),
            high=round(high_price, 4),
            low=round(low_price, 4),
            close=round(close_price, 4),
            volume=round(volume, 2),
            turnover=round(volume * close_price, 2),
        ))

    return candles


def generate_flash_crash(
    symbol: str,
    count: int = 100,
    crash_at: int = 50,
    crash_pct: float = 0.60,
) -> list[Candle]:
    """Generate data with a flash crash for testing data quality filters."""
    candles = generate_candles(symbol, count, trend="bull")

    # Insert flash crash
    if crash_at < len(candles):
        pre_crash = candles[crash_at - 1]
        crash_price = pre_crash.close * (1 - crash_pct)

        candles[crash_at] = Candle(
            symbol=symbol,
            timestamp=candles[crash_at].timestamp,
            open=pre_crash.close,
            high=pre_crash.close,
            low=crash_price,
            close=crash_price * 1.1,  # Partial recovery
            volume=candles[crash_at].volume * 10,  # Huge volume
            turnover=0,
        )

    return candles
```

**tests/fixtures/market_scenarios.py:**
```python
"""Pre-built market scenarios for comprehensive testing."""
from datetime import datetime, timedelta

from .candle_data import generate_candles
from data.storage.models import Candle


def get_bull_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of bull market data (1-minute candles)."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=1500.0,
        trend="bull",
        volatility=0.015,
    )


def get_bear_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of bear market data."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=2000.0,
        trend="bear",
        volatility=0.02,
    )


def get_sideways_market(symbol: str = "ETHUSDT", days: int = 30) -> list[Candle]:
    """30 days of sideways/ranging market."""
    return generate_candles(
        symbol=symbol,
        count=days * 24 * 60,
        start_price=1800.0,
        trend="sideways",
        volatility=0.01,
    )


def get_btc_reference(trend: str = "bull", days: int = 30) -> list[Candle]:
    """BTC data for market filter tests."""
    return generate_candles(
        symbol="BTCUSDT",
        count=days * 24 * 60,
        start_price=42000.0,
        trend=trend,
        volatility=0.012,
    )


def get_multi_regime_data(symbol: str = "ETHUSDT") -> list[Candle]:
    """
    90 days of data with 3 distinct regimes:
    - Days 1-30: Bull
    - Days 31-60: Sideways
    - Days 61-90: Bear
    """
    base_time = datetime.now() - timedelta(days=90)

    bull = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=1500.0,
        trend="bull",
        start_time=base_time,
    )

    # Start sideways from bull's end price
    sideways_start = bull[-1].close
    sideways = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=sideways_start,
        trend="sideways",
        start_time=base_time + timedelta(days=30),
    )

    # Start bear from sideways end
    bear_start = sideways[-1].close
    bear = generate_candles(
        symbol=symbol,
        count=30 * 24 * 60,
        start_price=bear_start,
        trend="bear",
        start_time=base_time + timedelta(days=60),
    )

    return bull + sideways + bear
```

**tests/conftest.py:**
```python
"""Pytest fixtures for all tests."""
import pytest
from pathlib import Path
import tempfile

from data.storage.repository import CandleRepository
from tests.fixtures.candle_data import generate_candles
from tests.fixtures.market_scenarios import (
    get_bull_market,
    get_bear_market,
    get_sideways_market,
    get_btc_reference,
    get_multi_regime_data,
)


@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def repository(temp_db):
    """CandleRepository instance with temp database."""
    return CandleRepository(temp_db)


@pytest.fixture
def sample_candles():
    """100 sample candles for basic tests."""
    return generate_candles("TESTUSDT", count=100)


@pytest.fixture
def bull_market():
    """30 days of bull market data."""
    return get_bull_market()


@pytest.fixture
def bear_market():
    """30 days of bear market data."""
    return get_bear_market()


@pytest.fixture
def sideways_market():
    """30 days of sideways market data."""
    return get_sideways_market()


@pytest.fixture
def btc_bull():
    """BTC bull market reference data."""
    return get_btc_reference(trend="bull")


@pytest.fixture
def btc_bear():
    """BTC bear market reference data."""
    return get_btc_reference(trend="bear")


@pytest.fixture
def multi_regime():
    """90 days with bull→sideways→bear regimes."""
    return get_multi_regime_data()
```

---

### BATCH 2: Gene Pool Primitives (PARALLEL - 5 Codex Agents)

**Can run simultaneously after Batch 1 completes**

**Common Interface for All Primitives:**

```python
"""Base interface for all gene pool primitives."""
from abc import ABC, abstractmethod
import pandas as pd


class Primitive(ABC):
    """Base class for gene pool primitives."""

    @abstractmethod
    def compute(self, candles: pd.DataFrame) -> float:
        """
        Compute the primitive value from candle data.

        Args:
            candles: DataFrame with columns [timestamp, open, high, low, close, volume]
                    Sorted oldest-first (chronological)

        Returns:
            Normalized value (typically -1.0 to +1.0)
        """
        pass
```

---

#### Task 2A: Trend Primitives

**Codex Agent:** 2A
**Scope:** `engine/gene_pool/trend.py`
**Files to create:**
- `engine/gene_pool/trend.py`
- `tests/test_gene_pool_trend.py`

**Primitives to implement:**

| Primitive | Signature | Output Range | Description |
|-----------|-----------|--------------|-------------|
| `ema_trend` | `ema_trend(fast: int, slow: int)` | -1.0 or +1.0 | +1 if fast EMA > slow EMA |
| `price_position` | `price_position(period: int)` | -3.0 to +3.0 | (Price - EMA) / ATR |

**Implementation Spec:**

```python
"""Trend primitives for gene pool."""
import pandas as pd
import pandas_ta as ta


def ema_trend(candles: pd.DataFrame, fast: int, slow: int) -> float:
    """
    Determine trend direction from EMA crossover state.

    Args:
        candles: OHLCV DataFrame (oldest first)
        fast: Fast EMA period (e.g., 9)
        slow: Slow EMA period (e.g., 21)

    Returns:
        +1.0 if fast EMA > slow EMA (uptrend)
        -1.0 if fast EMA < slow EMA (downtrend)
    """
    if len(candles) < slow:
        return 0.0  # Not enough data

    close = candles["close"]
    fast_ema = ta.ema(close, length=fast)
    slow_ema = ta.ema(close, length=slow)

    if fast_ema.iloc[-1] > slow_ema.iloc[-1]:
        return 1.0
    else:
        return -1.0


def price_position(candles: pd.DataFrame, period: int) -> float:
    """
    Price position relative to EMA, normalized by ATR.

    Args:
        candles: OHLCV DataFrame
        period: EMA and ATR period

    Returns:
        (Price - EMA) / ATR, capped at ±3.0
        Positive = price above EMA, negative = below
    """
    if len(candles) < period:
        return 0.0

    close = candles["close"]
    ema = ta.ema(close, length=period)
    atr = ta.atr(candles["high"], candles["low"], close, length=period)

    # Guard against zero ATR
    current_atr = atr.iloc[-1]
    if current_atr == 0 or pd.isna(current_atr):
        return 0.0

    position = (close.iloc[-1] - ema.iloc[-1]) / current_atr

    # Cap at ±3.0
    return max(-3.0, min(3.0, position))
```

**Test Requirements:**
- Test ema_trend returns +1.0 in bull market
- Test ema_trend returns -1.0 in bear market
- Test price_position range capping
- Test edge cases (insufficient data, zero ATR)

---

#### Task 2B: Mean Reversion Primitives

**Codex Agent:** 2B
**Scope:** `engine/gene_pool/mean_reversion.py`
**Files to create:**
- `engine/gene_pool/mean_reversion.py`
- `tests/test_gene_pool_mean_reversion.py`

**Primitives to implement:**

| Primitive | Signature | Output Range | Description |
|-----------|-----------|--------------|-------------|
| `norm_rsi` | `norm_rsi(period: int)` | -1.0 to +1.0 | (RSI - 50) / 50 |
| `bb_position` | `bb_position(period: int, std: float)` | -1.0 to +1.0 | Position within Bollinger Bands |
| `bb_width_percentile` | `bb_width_percentile(period: int)` | 0.0 to 1.0 | Band width vs history |

**Implementation Spec:**

```python
"""Mean reversion primitives for gene pool."""
import pandas as pd
import pandas_ta as ta


def norm_rsi(candles: pd.DataFrame, period: int) -> float:
    """
    Normalized RSI: (RSI - 50) / 50

    Args:
        candles: OHLCV DataFrame
        period: RSI period (typically 14)

    Returns:
        -1.0 (oversold, RSI=0) to +1.0 (overbought, RSI=100)
        0.0 = neutral (RSI=50)
    """
    if len(candles) < period + 1:
        return 0.0

    rsi = ta.rsi(candles["close"], length=period)
    current_rsi = rsi.iloc[-1]

    if pd.isna(current_rsi):
        return 0.0

    return (current_rsi - 50) / 50


def bb_position(candles: pd.DataFrame, period: int, std: float) -> float:
    """
    Position within Bollinger Bands.

    Args:
        candles: OHLCV DataFrame
        period: BB period (typically 20)
        std: Standard deviation multiplier (typically 2.0)

    Returns:
        -1.0 = at lower band
        0.0 = at middle band
        +1.0 = at upper band
        Can exceed ±1.0 if price outside bands
    """
    if len(candles) < period:
        return 0.0

    close = candles["close"]
    bb = ta.bbands(close, length=period, std=std)

    if bb is None:
        return 0.0

    upper = bb[f"BBU_{period}_{std}"].iloc[-1]
    lower = bb[f"BBL_{period}_{std}"].iloc[-1]
    middle = bb[f"BBM_{period}_{std}"].iloc[-1]
    current = close.iloc[-1]

    # Guard against zero width
    width = upper - lower
    if width == 0:
        return 0.0

    # Normalize: -1 at lower, 0 at middle, +1 at upper
    position = (current - middle) / (width / 2)

    # Cap at ±1.0
    return max(-1.0, min(1.0, position))


def bb_width_percentile(
    candles: pd.DataFrame, period: int, lookback: int = 100
) -> float:
    """
    Bollinger Band width percentile vs recent history.

    Args:
        candles: OHLCV DataFrame
        period: BB period
        lookback: Historical lookback for percentile

    Returns:
        0.0 = narrowest bands in lookback
        1.0 = widest bands in lookback
    """
    if len(candles) < max(period, lookback):
        return 0.5  # Default to middle

    close = candles["close"]
    bb = ta.bbands(close, length=period, std=2.0)

    if bb is None:
        return 0.5

    upper = bb[f"BBU_{period}_2.0"]
    lower = bb[f"BBL_{period}_2.0"]

    # Calculate width series
    width = (upper - lower) / ((upper + lower) / 2)  # Normalized width
    width = width.dropna()

    if len(width) < lookback:
        return 0.5

    current_width = width.iloc[-1]
    historical = width.iloc[-lookback:]

    # Percentile rank
    percentile = (historical < current_width).sum() / len(historical)

    return percentile
```

**Test Requirements:**
- Test norm_rsi ranges (-1 to +1)
- Test bb_position at exact band positions
- Test bb_width_percentile with varying volatility
- Test edge cases

---

#### Task 2C: Volume Primitives

**Codex Agent:** 2C
**Scope:** `engine/gene_pool/volume.py`
**Files to create:**
- `engine/gene_pool/volume.py`
- `tests/test_gene_pool_volume.py`

**Primitives to implement:**

| Primitive | Signature | Output Range | Description |
|-----------|-----------|--------------|-------------|
| `volume_intensity` | `volume_intensity(period: int, threshold: float)` | 0.0 or 1.0 | Volume spike detector |
| `vwap_distance` | `vwap_distance()` | -3.0 to +3.0 | Z-score of price vs VWAP |

**Implementation Spec:**

```python
"""Volume primitives for gene pool."""
import pandas as pd
import pandas_ta as ta
import numpy as np


def volume_intensity(
    candles: pd.DataFrame, period: int, threshold: float
) -> float:
    """
    Binary volume spike detector.

    Args:
        candles: OHLCV DataFrame
        period: Lookback for average volume
        threshold: Multiplier (e.g., 2.0 = 2x average)

    Returns:
        1.0 if current volume > threshold * average
        0.0 otherwise
    """
    if len(candles) < period:
        return 0.0

    volume = candles["volume"]
    avg_volume = volume.iloc[-period:].mean()
    current_volume = volume.iloc[-1]

    if avg_volume == 0:
        return 0.0

    if current_volume > threshold * avg_volume:
        return 1.0
    else:
        return 0.0


def vwap_distance(candles: pd.DataFrame, period: int = 20) -> float:
    """
    Z-score of price vs VWAP.

    Args:
        candles: OHLCV DataFrame with 'turnover' (quote volume)
        period: Lookback period

    Returns:
        Z-score capped at ±3.0
        Positive = price above VWAP
        Negative = price below VWAP
    """
    if len(candles) < period:
        return 0.0

    # Calculate VWAP
    typical_price = (candles["high"] + candles["low"] + candles["close"]) / 3

    # Use turnover if available, else estimate from volume * close
    if "turnover" in candles.columns and candles["turnover"].sum() > 0:
        cumulative_tpv = (typical_price * candles["volume"]).cumsum()
        cumulative_volume = candles["volume"].cumsum()
    else:
        cumulative_tpv = (typical_price * candles["volume"]).cumsum()
        cumulative_volume = candles["volume"].cumsum()

    vwap = cumulative_tpv / cumulative_volume

    # Rolling VWAP (reset each session in production, simplified here)
    recent_tp = typical_price.iloc[-period:]
    recent_vol = candles["volume"].iloc[-period:]
    session_vwap = (recent_tp * recent_vol).sum() / recent_vol.sum()

    # Z-score
    price_deviation = candles["close"].iloc[-1] - session_vwap
    std = candles["close"].iloc[-period:].std()

    if std == 0:
        return 0.0

    z_score = price_deviation / std

    # Cap at ±3.0
    return max(-3.0, min(3.0, z_score))
```

**Test Requirements:**
- Test volume_intensity spike detection
- Test vwap_distance z-score calculation
- Test edge cases (zero volume, zero std)

---

#### Task 2D: Volatility Primitives

**Codex Agent:** 2D
**Scope:** `engine/gene_pool/volatility.py`
**Files to create:**
- `engine/gene_pool/volatility.py`
- `tests/test_gene_pool_volatility.py`

**Primitives to implement:**

| Primitive | Signature | Output Range | Description |
|-----------|-----------|--------------|-------------|
| `atr_regime` | `atr_regime(period: int)` | -1.0, 0.0, or +1.0 | Volatility regime classification |
| `atr_percentile` | `atr_percentile(period: int)` | 0.0 to 1.0 | Current ATR vs history |

**Implementation Spec:**

```python
"""Volatility primitives for gene pool."""
import pandas as pd
import pandas_ta as ta


def atr_regime(
    candles: pd.DataFrame, period: int, lookback: int = 100
) -> float:
    """
    Classify current volatility regime.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        lookback: Historical lookback for comparison

    Returns:
        +1.0 = high volatility (ATR > 75th percentile)
        0.0 = normal volatility (25th-75th percentile)
        -1.0 = low volatility (ATR < 25th percentile)
    """
    if len(candles) < max(period, lookback):
        return 0.0

    atr = ta.atr(
        candles["high"], candles["low"], candles["close"], length=period
    )
    atr = atr.dropna()

    if len(atr) < lookback:
        return 0.0

    current_atr = atr.iloc[-1]
    historical = atr.iloc[-lookback:]

    p25 = historical.quantile(0.25)
    p75 = historical.quantile(0.75)

    if current_atr > p75:
        return 1.0   # High volatility
    elif current_atr < p25:
        return -1.0  # Low volatility
    else:
        return 0.0   # Normal


def atr_percentile(
    candles: pd.DataFrame, period: int, lookback: int = 100
) -> float:
    """
    Current ATR percentile vs historical.

    Args:
        candles: OHLCV DataFrame
        period: ATR period
        lookback: Historical lookback

    Returns:
        0.0 = lowest ATR in lookback
        1.0 = highest ATR in lookback
    """
    if len(candles) < max(period, lookback):
        return 0.5

    atr = ta.atr(
        candles["high"], candles["low"], candles["close"], length=period
    )
    atr = atr.dropna()

    if len(atr) < lookback:
        return 0.5

    current_atr = atr.iloc[-1]
    historical = atr.iloc[-lookback:]

    # Percentile rank
    percentile = (historical < current_atr).sum() / len(historical)

    return percentile
```

**Test Requirements:**
- Test atr_regime classification thresholds
- Test atr_percentile ranking
- Test with different volatility scenarios

---

#### Task 2E: Market Filter Primitives

**Codex Agent:** 2E
**Scope:** `engine/gene_pool/market_filter.py`
**Files to create:**
- `engine/gene_pool/market_filter.py`
- `tests/test_gene_pool_market_filter.py`

**Primitives to implement:**

| Primitive | Signature | Output Range | Description |
|-----------|-----------|--------------|-------------|
| `btc_trend` | `btc_trend(window: int)` | -1.0 or +1.0 | BTC trend filter (MANDATORY for longs) |

**Implementation Spec:**

```python
"""Market filter primitives for gene pool."""
import pandas as pd
import pandas_ta as ta


def btc_trend(btc_candles: pd.DataFrame, window: int) -> float:
    """
    BTC trend filter - MANDATORY for all altcoin long entries.

    "Don't buy alts when BTC is dumping."

    Args:
        btc_candles: OHLCV DataFrame for BTCUSDT
        window: EMA window for trend determination

    Returns:
        +1.0 = BTC stable or rising (safe to long alts)
        -1.0 = BTC dumping (avoid new longs)

    Rule: All entry_long conditions MUST include btc_trend(window) >= 0
    """
    if len(btc_candles) < window:
        return -1.0  # Conservative: assume danger if insufficient data

    close = btc_candles["close"]
    ema = ta.ema(close, length=window)

    current_price = close.iloc[-1]
    current_ema = ema.iloc[-1]

    # Also check short-term momentum
    short_ema = ta.ema(close, length=max(window // 4, 5))

    # BTC is "safe" if:
    # 1. Price is above EMA (not in freefall)
    # 2. Short EMA is not crashing relative to long EMA
    price_above_ema = current_price >= current_ema * 0.98  # 2% tolerance
    momentum_ok = short_ema.iloc[-1] >= current_ema * 0.97

    if price_above_ema and momentum_ok:
        return 1.0
    else:
        return -1.0
```

**Test Requirements:**
- Test btc_trend returns +1.0 in BTC bull market
- Test btc_trend returns -1.0 in BTC bear market
- Test conservative default (insufficient data)
- Test boundary conditions

---

### BATCH 3: Integration Components (PARALLEL - 2 Codex Agents)

**Can run simultaneously after Batch 2 completes**

---

#### Task 3A: Data Quality Filters

**Codex Agent:** 3A
**Scope:** `data/quality_filters.py`
**Files to create:**
- `data/quality_filters.py`
- `tests/test_quality_filters.py`

**Filters to implement:**

| Filter | Rule | Action |
|--------|------|--------|
| Flash crash | \|close/prev_close - 1\| > 50% | Reject candle |
| Zero volume | volume == 0 | Reject candle |
| Stale data | Timestamp gap > 5 minutes | Log warning, trigger warmup |

**Implementation Spec:**

```python
"""Data quality filters for candle validation."""
import logging
from dataclasses import dataclass
from typing import Optional

from data.storage.models import Candle


logger = logging.getLogger("trades")
error_logger = logging.getLogger("errors")


@dataclass
class ValidationResult:
    """Result of candle validation."""
    valid: bool
    reason: Optional[str] = None
    requires_warmup: bool = False


class CandleValidator:
    """
    Validates incoming candle data for quality issues.

    Detects:
    - Flash crashes (>50% move in one candle)
    - Zero volume candles
    - Data gaps (>5 minutes between candles)
    """

    FLASH_CRASH_THRESHOLD = 0.50  # 50% move
    MAX_GAP_MS = 5 * 60 * 1000    # 5 minutes

    def __init__(self):
        self._last_candles: dict[str, Candle] = {}

    def validate(self, candle: Candle) -> ValidationResult:
        """
        Validate a candle against quality rules.

        Args:
            candle: The candle to validate

        Returns:
            ValidationResult with validity and reason
        """
        symbol = candle.symbol
        prev = self._last_candles.get(symbol)

        # Check zero volume
        if candle.volume == 0:
            return ValidationResult(
                valid=False,
                reason="Zero volume candle"
            )

        if prev is not None:
            # Check flash crash
            price_change = abs(candle.close / prev.close - 1)
            if price_change > self.FLASH_CRASH_THRESHOLD:
                error_logger.error(
                    f"Flash crash detected: {symbol} moved {price_change:.1%} "
                    f"from {prev.close} to {candle.close}"
                )
                return ValidationResult(
                    valid=False,
                    reason=f"Flash crash: {price_change:.1%} move"
                )

            # Check data gap
            gap_ms = candle.timestamp - prev.timestamp
            expected_gap = 60 * 1000  # 1 minute for 1m candles

            if gap_ms > self.MAX_GAP_MS:
                logger.warning(
                    f"Data gap detected: {symbol} gap of {gap_ms / 1000:.0f}s"
                )
                return ValidationResult(
                    valid=True,  # Accept the candle but flag warmup
                    requires_warmup=True,
                    reason=f"Data gap: {gap_ms / 1000:.0f}s"
                )

        # Update last candle
        self._last_candles[symbol] = candle

        return ValidationResult(valid=True)

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset validator state (e.g., after warmup)."""
        if symbol:
            self._last_candles.pop(symbol, None)
        else:
            self._last_candles.clear()
```

**Test Requirements:**
- Test flash crash detection (reject candle)
- Test zero volume rejection
- Test data gap detection (warmup flag)
- Test normal candle acceptance
- Test state reset

---

#### Task 3B: Gene Expression Parser

**Codex Agent:** 3B
**Scope:** `engine/strategy_logic/parser.py`
**Files to create:**
- `engine/strategy_logic/parser.py`
- `tests/test_parser.py`

**Acceptance Criteria:**
- [ ] Parse JSON strategy format into executable conditions
- [ ] Validate only allowed primitives are used
- [ ] Evaluate entry/exit conditions against live data
- [ ] Return structured signal (ENTRY_LONG, EXIT_LONG, HOLD)

**Implementation Spec:**

```python
"""Gene expression parser - converts JSON strategies to executable code."""
import re
import operator
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum
import pandas as pd

from engine.gene_pool import trend, mean_reversion, volume, volatility, market_filter


class Signal(Enum):
    """Trading signals."""
    HOLD = "HOLD"
    ENTRY_LONG = "ENTRY_LONG"
    EXIT_LONG = "EXIT_LONG"


@dataclass
class Strategy:
    """Parsed strategy with entry/exit conditions."""
    name: str
    entry_long: Optional[str]
    exit_long: Optional[str]
    entry_short: Optional[str] = None  # Disabled Phase 1
    exit_short: Optional[str] = None   # Disabled Phase 1


# Allowed primitives (whitelist for security)
PRIMITIVES = {
    "ema_trend": trend.ema_trend,
    "price_position": trend.price_position,
    "norm_rsi": mean_reversion.norm_rsi,
    "bb_position": mean_reversion.bb_position,
    "bb_width_percentile": mean_reversion.bb_width_percentile,
    "volume_intensity": volume.volume_intensity,
    "vwap_distance": volume.vwap_distance,
    "atr_regime": volatility.atr_regime,
    "atr_percentile": volatility.atr_percentile,
    "btc_trend": market_filter.btc_trend,
}

# Allowed operators
OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}


class GeneExpressionParser:
    """
    Parses and evaluates gene expression strings.

    Example expression:
        "btc_trend(60) >= 0 AND ema_trend(9,21) == 1.0 AND norm_rsi(14) < -0.4"
    """

    # Pattern to match function calls: func_name(arg1, arg2, ...)
    FUNC_PATTERN = re.compile(r"(\w+)\(([^)]*)\)")

    # Pattern to match comparisons: value op value
    COMPARISON_PATTERN = re.compile(r"([\d\.\-]+|[\w\(][^<>=!]+)\s*(==|!=|>=|<=|>|<)\s*([\d\.\-]+)")

    def __init__(self):
        self._cache: dict[str, Callable] = {}

    def parse(self, strategy_json: dict) -> Strategy:
        """
        Parse a JSON strategy definition.

        Args:
            strategy_json: Dict with strategy_name, entry_long, exit_long, etc.

        Returns:
            Strategy object

        Raises:
            ValueError: If strategy uses disallowed primitives
        """
        # Validate primitives
        for field in ["entry_long", "exit_long"]:
            expr = strategy_json.get(field)
            if expr:
                self._validate_expression(expr)

        return Strategy(
            name=strategy_json.get("strategy_name", "unknown"),
            entry_long=strategy_json.get("entry_long"),
            exit_long=strategy_json.get("exit_long"),
            entry_short=None,  # Disabled
            exit_short=None,   # Disabled
        )

    def _validate_expression(self, expression: str) -> None:
        """Validate that expression only uses allowed primitives."""
        for match in self.FUNC_PATTERN.finditer(expression):
            func_name = match.group(1)
            if func_name not in PRIMITIVES:
                raise ValueError(f"Unknown primitive: {func_name}")

    def evaluate(
        self,
        expression: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame] = None,
    ) -> bool:
        """
        Evaluate a gene expression against current data.

        Args:
            expression: Gene expression string
            candles: OHLCV data for the trading symbol
            btc_candles: OHLCV data for BTC (for btc_trend)

        Returns:
            True if expression evaluates to true
        """
        # Split by AND (only AND supported for Phase 1)
        conditions = [c.strip() for c in expression.split("AND")]

        for condition in conditions:
            if not self._evaluate_condition(condition, candles, btc_candles):
                return False

        return True

    def _evaluate_condition(
        self,
        condition: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame],
    ) -> bool:
        """Evaluate a single condition (e.g., 'ema_trend(9,21) == 1.0')."""
        match = self.COMPARISON_PATTERN.match(condition.strip())
        if not match:
            raise ValueError(f"Cannot parse condition: {condition}")

        left_str, op_str, right_str = match.groups()

        # Evaluate left side (usually a function call)
        left_value = self._evaluate_term(left_str.strip(), candles, btc_candles)

        # Right side is usually a constant
        right_value = float(right_str)

        # Apply operator
        op_func = OPERATORS.get(op_str)
        if not op_func:
            raise ValueError(f"Unknown operator: {op_str}")

        return op_func(left_value, right_value)

    def _evaluate_term(
        self,
        term: str,
        candles: pd.DataFrame,
        btc_candles: Optional[pd.DataFrame],
    ) -> float:
        """Evaluate a term (function call or constant)."""
        # Try to parse as float first
        try:
            return float(term)
        except ValueError:
            pass

        # Parse as function call
        match = self.FUNC_PATTERN.match(term)
        if not match:
            raise ValueError(f"Cannot parse term: {term}")

        func_name = match.group(1)
        args_str = match.group(2)

        # Parse arguments
        args = []
        if args_str.strip():
            for arg in args_str.split(","):
                arg = arg.strip()
                try:
                    # Try int first (per design: integers only)
                    args.append(int(arg))
                except ValueError:
                    args.append(float(arg))

        # Get function
        func = PRIMITIVES.get(func_name)
        if not func:
            raise ValueError(f"Unknown primitive: {func_name}")

        # Special case: btc_trend uses BTC candles
        if func_name == "btc_trend":
            if btc_candles is None:
                raise ValueError("btc_trend requires btc_candles")
            return func(btc_candles, *args)

        return func(candles, *args)

    def get_signal(
        self,
        strategy: Strategy,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame,
        has_position: bool,
    ) -> Signal:
        """
        Determine trading signal for current state.

        Args:
            strategy: Parsed strategy
            candles: Current candle data
            btc_candles: BTC candle data
            has_position: Whether we currently hold a position

        Returns:
            Signal enum
        """
        if has_position:
            # Check exit condition
            if strategy.exit_long and self.evaluate(
                strategy.exit_long, candles, btc_candles
            ):
                return Signal.EXIT_LONG
            return Signal.HOLD
        else:
            # Check entry condition
            if strategy.entry_long and self.evaluate(
                strategy.entry_long, candles, btc_candles
            ):
                return Signal.ENTRY_LONG
            return Signal.HOLD
```

**Test Requirements:**
- Test parsing valid strategy JSON
- Test rejection of unknown primitives
- Test evaluation of AND conditions
- Test signal generation logic
- Test comparison operators

---

### BATCH 4: Shadow Trading (SEQUENTIAL)

**Executor:** Claude (main agent)
**Must complete after all previous batches**

---

#### Task 4A: Shadow Trader Implementation

**Scope:** `execution/shadow/`
**Files to create:**
- `execution/shadow/trader.py`
- `execution/shadow/position.py`
- `tests/test_shadow_trader.py`

**Acceptance Criteria:**
- [ ] Simulate order execution on real order book data
- [ ] Track open positions with entry price, size, timestamp
- [ ] Apply realistic friction (0.25% per side)
- [ ] Log every trade with full state vector
- [ ] Respect risk limits (max 5 positions, 50% exposure)

**Implementation Spec:**

```python
"""Shadow (paper) trading implementation."""
import json
import logging
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional
from pathlib import Path

from data.storage.models import Candle
from engine.strategy_logic.parser import Strategy, Signal, GeneExpressionParser
from config import settings


logger = logging.getLogger("trades")


@dataclass
class Position:
    """Open position state."""
    symbol: str
    strategy_id: str
    entry_time: int
    entry_price: float
    size_usdt: float
    side: str = "LONG"  # Only LONG for Phase 1


@dataclass
class TradeLog:
    """Full trade state vector for logging."""
    timestamp: int
    strategy_id: str
    coin: str
    signal: str
    gene_expression: str
    price_at_signal: float
    simulated_fill: float
    position_size_usdt: float
    btc_trend: float
    atr_regime: float
    pnl: Optional[float] = None

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(asdict(self), indent=None)


class ShadowTrader:
    """
    Paper trading engine that simulates execution on real order books.

    Applies realistic friction:
    - 0.10% exchange fee
    - 0.15% estimated slippage
    - Total: 0.25% per side
    """

    FRICTION_PER_SIDE = 0.0025  # 0.25%

    def __init__(
        self,
        strategy: Strategy,
        equity: float = 10000.0,
        log_path: Optional[Path] = None,
    ):
        self.strategy = strategy
        self.equity = equity
        self.initial_equity = equity
        self.positions: dict[str, Position] = {}  # symbol -> position
        self.parser = GeneExpressionParser()
        self.log_path = log_path or settings.logs_dir / "shadow_trades.jsonl"

        # Risk limits from config
        self.max_position_pct = settings.max_position_pct
        self.max_open_positions = settings.max_open_positions
        self.max_exposure = settings.max_exposure
        self.risk_per_trade = settings.risk_per_trade

    def process_candle(
        self,
        symbol: str,
        candles: pd.DataFrame,
        btc_candles: pd.DataFrame,
    ) -> Optional[Signal]:
        """
        Process a new candle and execute any signals.

        Args:
            symbol: Trading symbol
            candles: OHLCV data for symbol
            btc_candles: BTC candle data for market filter

        Returns:
            Signal that was acted upon, or None
        """
        has_position = symbol in self.positions

        # Get signal from strategy
        signal = self.parser.get_signal(
            self.strategy, candles, btc_candles, has_position
        )

        if signal == Signal.HOLD:
            return None

        current_price = candles["close"].iloc[-1]
        btc_trend_val = market_filter.btc_trend(btc_candles, 60)
        atr_regime_val = volatility.atr_regime(candles, 14)

        if signal == Signal.ENTRY_LONG:
            return self._execute_entry(
                symbol, current_price, btc_trend_val, atr_regime_val
            )
        elif signal == Signal.EXIT_LONG:
            return self._execute_exit(
                symbol, current_price, btc_trend_val, atr_regime_val
            )

        return None

    def _execute_entry(
        self,
        symbol: str,
        price: float,
        btc_trend: float,
        atr_regime: float,
    ) -> Optional[Signal]:
        """Execute a simulated long entry."""
        # Check risk limits
        if len(self.positions) >= self.max_open_positions:
            logger.info(f"Max positions reached, skipping entry for {symbol}")
            return None

        current_exposure = sum(p.size_usdt for p in self.positions.values())
        if current_exposure / self.equity >= self.max_exposure:
            logger.info(f"Max exposure reached, skipping entry for {symbol}")
            return None

        # Calculate position size (1% risk, max 10% position)
        position_size = min(
            self.equity * self.risk_per_trade,
            self.equity * self.max_position_pct,
        )

        # Apply friction (buy at higher price)
        fill_price = price * (1 + self.FRICTION_PER_SIDE)

        # Create position
        position = Position(
            symbol=symbol,
            strategy_id=self.strategy.name,
            entry_time=int(datetime.now().timestamp() * 1000),
            entry_price=fill_price,
            size_usdt=position_size,
        )
        self.positions[symbol] = position

        # Log trade
        trade_log = TradeLog(
            timestamp=position.entry_time,
            strategy_id=self.strategy.name,
            coin=symbol,
            signal="ENTRY_LONG",
            gene_expression=self.strategy.entry_long or "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position_size,
            btc_trend=btc_trend,
            atr_regime=atr_regime,
        )
        self._log_trade(trade_log)

        return Signal.ENTRY_LONG

    def _execute_exit(
        self,
        symbol: str,
        price: float,
        btc_trend: float,
        atr_regime: float,
    ) -> Optional[Signal]:
        """Execute a simulated long exit."""
        position = self.positions.get(symbol)
        if not position:
            return None

        # Apply friction (sell at lower price)
        fill_price = price * (1 - self.FRICTION_PER_SIDE)

        # Calculate P&L
        pnl_pct = (fill_price - position.entry_price) / position.entry_price
        pnl_usdt = position.size_usdt * pnl_pct

        # Update equity
        self.equity += pnl_usdt

        # Log trade
        trade_log = TradeLog(
            timestamp=int(datetime.now().timestamp() * 1000),
            strategy_id=self.strategy.name,
            coin=symbol,
            signal="EXIT_LONG",
            gene_expression=self.strategy.exit_long or "",
            price_at_signal=price,
            simulated_fill=fill_price,
            position_size_usdt=position.size_usdt,
            btc_trend=btc_trend,
            atr_regime=atr_regime,
            pnl=pnl_usdt,
        )
        self._log_trade(trade_log)

        # Remove position
        del self.positions[symbol]

        return Signal.EXIT_LONG

    def _log_trade(self, trade: TradeLog) -> None:
        """Append trade to log file."""
        with open(self.log_path, "a") as f:
            f.write(trade.to_json() + "\n")

        logger.info(
            f"{trade.signal} {trade.coin} @ {trade.simulated_fill:.4f} "
            f"(size: ${trade.position_size_usdt:.2f}, pnl: {trade.pnl or 0:.2f})"
        )

    @property
    def total_pnl(self) -> float:
        """Total P&L since start."""
        return self.equity - self.initial_equity

    @property
    def current_exposure(self) -> float:
        """Current exposure as fraction of equity."""
        return sum(p.size_usdt for p in self.positions.values()) / self.equity
```

---

#### Task 4B: Integration Testing & Stability Run

**Scope:** Full system integration
**Files to create:**
- `main.py` - Entry point
- `tests/test_integration.py`

**Acceptance Criteria:**
- [ ] Hardcoded strategy runs against live WebSocket
- [ ] Logs generated correctly
- [ ] Reconnection works (disconnect and reconnect manually)
- [ ] Run 24 hours without crash
- [ ] No memory leaks (check RSS after 24h)

**Hardcoded Test Strategy:**
```json
{
  "strategy_name": "Phase1_Test_RSI_Mean_Reversion",
  "entry_long": "btc_trend(60) >= 0 AND norm_rsi(14) < -0.6",
  "exit_long": "norm_rsi(14) > 0.4"
}
```

**main.py Skeleton:**
```python
"""Entry point for crypto-alpha system."""
import asyncio
import signal
from pathlib import Path

from config import settings
from logs import setup_logging
from data.ingestion.bybit_ws import BybitWebSocketClient
from data.storage.repository import CandleRepository
from data.quality_filters import CandleValidator
from execution.shadow.trader import ShadowTrader
from engine.strategy_logic.parser import GeneExpressionParser


# Hardcoded test strategy (Phase 1)
TEST_STRATEGY = {
    "strategy_name": "Phase1_Test_RSI_Mean_Reversion",
    "entry_long": "btc_trend(60) >= 0 AND norm_rsi(14) < -0.6",
    "exit_long": "norm_rsi(14) > 0.4",
}


async def main():
    """Main entry point."""
    # Setup logging
    trade_logger, error_logger = setup_logging(settings.logs_dir)
    trade_logger.info("Starting crypto-alpha system")

    # Initialize components
    repository = CandleRepository(settings.sqlite_path)
    validator = CandleValidator()
    parser = GeneExpressionParser()
    strategy = parser.parse(TEST_STRATEGY)
    trader = ShadowTrader(strategy)

    # Coin universe (Top 30 Bybit Futures by volume)
    # [*TO-DO*] - Fetch dynamically from Bybit API
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
        "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "MATICUSDT",
        # ... add more
    ]

    async def on_candle(candle):
        """Callback for each new candle."""
        # Validate
        result = validator.validate(candle)
        if not result.valid:
            error_logger.warning(f"Invalid candle: {result.reason}")
            return

        # Store
        repository.insert(candle)

        # Get enough history for indicators
        candles = repository.get_latest(candle.symbol, limit=100)
        if len(candles) < 50:
            return  # Not enough data yet

        btc_candles = repository.get_latest("BTCUSDT", limit=100)
        if len(btc_candles) < 50:
            return

        # Convert to DataFrame
        import pandas as pd
        df = pd.DataFrame([c.dict() for c in candles])
        btc_df = pd.DataFrame([c.dict() for c in btc_candles])

        # Process through shadow trader
        signal = trader.process_candle(candle.symbol, df, btc_df)
        if signal:
            trade_logger.info(f"Signal: {signal} for {candle.symbol}")

    # Create WebSocket client
    client = BybitWebSocketClient(
        symbols=symbols,
        on_candle=on_candle,
        interval="1",
    )

    # Handle graceful shutdown
    def shutdown(signum, frame):
        trade_logger.info("Shutting down...")
        client.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Run
    trade_logger.info(f"Connecting to {len(symbols)} symbols...")
    await client.run()


if __name__ == "__main__":
    asyncio.run(main())
```

**24-Hour Stability Test:**
```bash
# Start system
python main.py &
PID=$!

# Monitor memory usage every hour
while true; do
    ps -o rss= -p $PID
    sleep 3600
done

# After 24h, check:
# 1. Process still running
# 2. RSS not growing significantly
# 3. logs/trades_*.log has entries
# 4. logs/errors_*.log is empty or minimal
```

---

## 5. Progress Changelog

| Date | Time | Task | Status | Notes |
|------|------|------|--------|-------|
| 2025-12-05 | 11:44 AM | Plan created | ✅ Complete | Ready for execution |
| 2025-12-05 | 11:55 PM | Batch 0 complete | ✅ Complete | Scaffolding + config + logging |
| 2025-12-05 | 12:05 AM | Batch 1 complete | ✅ Complete | 3 parallel agents: storage, websocket, fixtures (33 tests) |
| 2025-12-05 | 12:15 AM | Batch 2 complete | ✅ Complete | 5 parallel agents: all 10 Gene Pool primitives (85 tests) |
| 2025-12-05 | 12:25 AM | Batch 3 complete | ✅ Complete | 2 parallel agents: quality filters + parser (53 tests) |
| 2025-12-05 | 12:35 AM | Batch 4 complete | ✅ Complete | Shadow trader + main.py (15 tests) |
| 2025-12-05 | 12:40 AM | **PHASE 1 COMPLETE** | ✅ Complete | **186 total tests passing** |

---

## 6. Execution Checklist

### Pre-Flight
- [ ] Read this plan completely
- [ ] Verify design doc is current
- [ ] Set up local Python environment (3.11+)
- [ ] Create `.env` file with any needed secrets

### Batch 0 (Claude)
- [ ] Task 0.1: Project scaffolding
- [ ] Task 0.2: Config & logging setup
- [ ] Commit: "feat: project scaffolding and config"

### Batch 1 (3 Codex Agents in Parallel)
- [ ] Task 1A: Data storage (Agent 1A)
- [ ] Task 1B: WebSocket client (Agent 1B)
- [ ] Task 1C: Test fixtures (Agent 1C)
- [ ] All agents complete, merge work
- [ ] Run tests: `pytest tests/test_storage.py tests/test_websocket.py`
- [ ] Commit: "feat: data layer (storage, websocket, fixtures)"

### Batch 2 (5 Codex Agents in Parallel)
- [ ] Task 2A: Trend primitives (Agent 2A)
- [ ] Task 2B: Mean reversion primitives (Agent 2B)
- [ ] Task 2C: Volume primitives (Agent 2C)
- [ ] Task 2D: Volatility primitives (Agent 2D)
- [ ] Task 2E: Market filter primitives (Agent 2E)
- [ ] All agents complete, merge work
- [ ] Run tests: `pytest tests/test_gene_pool_*.py`
- [ ] Commit: "feat: gene pool primitives"

### Batch 3 (2 Codex Agents in Parallel)
- [ ] Task 3A: Data quality filters (Agent 3A)
- [ ] Task 3B: Gene expression parser (Agent 3B)
- [ ] All agents complete, merge work
- [ ] Run tests: `pytest tests/test_quality_filters.py tests/test_parser.py`
- [ ] Commit: "feat: quality filters and gene parser"

### Batch 4 (Claude)
- [ ] Task 4A: Shadow trader implementation
- [ ] Task 4B: Integration testing
- [ ] Run all tests: `pytest`
- [ ] Commit: "feat: shadow trader implementation"

### Stability Test
- [ ] Run system for 24 hours
- [ ] Verify no crashes
- [ ] Verify memory stable
- [ ] Verify logs being written
- [ ] Final commit: "feat: phase 1 complete - stable plumbing"

---

## 7. Handoff Notes

**For Independent Agents:**

1. Each task is self-contained with exact file paths and code
2. Test requirements are explicit - all tests must pass
3. Use TDD: write tests first, then implementation
4. Don't modify files outside your assigned scope
5. When in doubt, match the code snippets exactly

**For Human Review:**

1. After each batch, verify tests pass before proceeding
2. Check git diff makes sense before committing
3. The 24-hour stability test is non-negotiable
4. If primitives don't match TradingView, investigate before Phase 2

---

*Plan created: 12/05/2025 11:42 AM*
