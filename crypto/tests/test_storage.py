"""Tests for candle storage."""
import pytest
import tempfile
from pathlib import Path

from data.storage.models import Candle
from data.storage.repository import CandleRepository


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)

    yield db_path

    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def repo(temp_db):
    """Create a CandleRepository instance with temp database."""
    return CandleRepository(temp_db)


@pytest.fixture
def sample_candle():
    """Create a sample candle for testing."""
    return Candle(
        symbol="BTCUSDT",
        timestamp=1700000000000,
        open=35000.0,
        high=35500.0,
        low=34800.0,
        close=35200.0,
        volume=100.5,
        turnover=3520000.0
    )


@pytest.fixture
def sample_candles():
    """Create multiple sample candles for testing."""
    base_ts = 1700000000000
    return [
        Candle(
            symbol="BTCUSDT",
            timestamp=base_ts + i * 60000,  # 1 minute intervals
            open=35000.0 + i * 10,
            high=35500.0 + i * 10,
            low=34800.0 + i * 10,
            close=35200.0 + i * 10,
            volume=100.0 + i,
            turnover=3520000.0 + i * 1000
        )
        for i in range(10)
    ]


def test_insert_single_candle(repo, sample_candle):
    """Test inserting a single candle."""
    repo.insert(sample_candle)

    count = repo.count("BTCUSDT")
    assert count == 1

    candles = repo.get_latest("BTCUSDT", limit=1)
    assert len(candles) == 1
    assert candles[0].symbol == sample_candle.symbol
    assert candles[0].timestamp == sample_candle.timestamp
    assert candles[0].close == sample_candle.close


def test_upsert_existing_candle(repo, sample_candle):
    """Test updating an existing candle (upsert)."""
    # Insert original
    repo.insert(sample_candle)
    assert repo.count("BTCUSDT") == 1

    # Update with new price but same symbol and timestamp
    updated_candle = Candle(
        symbol=sample_candle.symbol,
        timestamp=sample_candle.timestamp,
        open=36000.0,
        high=36500.0,
        low=35800.0,
        close=36200.0,
        volume=150.0,
        turnover=5430000.0
    )
    repo.insert(updated_candle)

    # Should still have only 1 candle
    assert repo.count("BTCUSDT") == 1

    # Verify updated values
    candles = repo.get_latest("BTCUSDT", limit=1)
    assert candles[0].close == 36200.0
    assert candles[0].volume == 150.0


def test_batch_insert(repo, sample_candles):
    """Test batch insert."""
    count = repo.insert_batch(sample_candles)

    assert count == 10
    assert repo.count("BTCUSDT") == 10


def test_batch_insert_empty(repo):
    """Test batch insert with empty list."""
    count = repo.insert_batch([])
    assert count == 0


def test_get_latest_ordering(repo, sample_candles):
    """Test get_latest returns candles in chronological order (oldest first)."""
    repo.insert_batch(sample_candles)

    # Get latest 5 candles
    candles = repo.get_latest("BTCUSDT", limit=5)

    assert len(candles) == 5
    # Should be oldest first (chronological order)
    # The last 5 candles inserted have timestamps: base_ts + 5*60000 through base_ts + 9*60000
    # When returned oldest-first, that's indices 5,6,7,8,9 from sample_candles
    assert candles[0].timestamp == sample_candles[5].timestamp
    assert candles[1].timestamp == sample_candles[6].timestamp
    assert candles[2].timestamp == sample_candles[7].timestamp
    assert candles[3].timestamp == sample_candles[8].timestamp
    assert candles[4].timestamp == sample_candles[9].timestamp

    # Verify they're in ascending order
    for i in range(len(candles) - 1):
        assert candles[i].timestamp < candles[i + 1].timestamp


def test_get_range_boundaries(repo, sample_candles):
    """Test get_range with inclusive boundaries."""
    repo.insert_batch(sample_candles)

    # Get candles from index 2 to 6 (inclusive)
    start_ts = sample_candles[2].timestamp
    end_ts = sample_candles[6].timestamp

    candles = repo.get_range("BTCUSDT", start_ts, end_ts)

    assert len(candles) == 5  # Indices 2,3,4,5,6
    assert candles[0].timestamp == start_ts
    assert candles[-1].timestamp == end_ts

    # Verify chronological order
    for i in range(len(candles) - 1):
        assert candles[i].timestamp < candles[i + 1].timestamp


def test_get_range_no_matches(repo, sample_candles):
    """Test get_range with no matching candles."""
    repo.insert_batch(sample_candles)

    # Query time range before all candles
    start_ts = sample_candles[0].timestamp - 1000000
    end_ts = sample_candles[0].timestamp - 500000

    candles = repo.get_range("BTCUSDT", start_ts, end_ts)

    assert len(candles) == 0


def test_empty_results(repo):
    """Test queries on empty database."""
    candles = repo.get_latest("BTCUSDT", limit=10)
    assert len(candles) == 0

    candles = repo.get_range("BTCUSDT", 0, 9999999999999)
    assert len(candles) == 0

    count = repo.count("BTCUSDT")
    assert count == 0


def test_count_all_symbols(repo, sample_candles):
    """Test count function without symbol filter."""
    # Insert BTCUSDT candles
    repo.insert_batch(sample_candles)

    # Insert ETHUSDT candles
    eth_candles = [
        Candle(
            symbol="ETHUSDT",
            timestamp=1700000000000 + i * 60000,
            open=2000.0,
            high=2100.0,
            low=1900.0,
            close=2050.0,
            volume=50.0,
            turnover=102500.0
        )
        for i in range(5)
    ]
    repo.insert_batch(eth_candles)

    # Test count by symbol
    assert repo.count("BTCUSDT") == 10
    assert repo.count("ETHUSDT") == 5

    # Test count all
    assert repo.count() == 15


def test_count_with_symbol(repo, sample_candles):
    """Test count function with symbol filter."""
    repo.insert_batch(sample_candles)

    assert repo.count("BTCUSDT") == 10
    assert repo.count("ETHUSDT") == 0


def test_multiple_symbols(repo):
    """Test storing and retrieving multiple symbols."""
    btc_candle = Candle(
        symbol="BTCUSDT",
        timestamp=1700000000000,
        open=35000.0,
        high=35500.0,
        low=34800.0,
        close=35200.0,
        volume=100.0,
        turnover=3520000.0
    )

    eth_candle = Candle(
        symbol="ETHUSDT",
        timestamp=1700000000000,
        open=2000.0,
        high=2100.0,
        low=1900.0,
        close=2050.0,
        volume=50.0,
        turnover=102500.0
    )

    repo.insert(btc_candle)
    repo.insert(eth_candle)

    btc_candles = repo.get_latest("BTCUSDT", limit=10)
    eth_candles = repo.get_latest("ETHUSDT", limit=10)

    assert len(btc_candles) == 1
    assert len(eth_candles) == 1
    assert btc_candles[0].symbol == "BTCUSDT"
    assert eth_candles[0].symbol == "ETHUSDT"
