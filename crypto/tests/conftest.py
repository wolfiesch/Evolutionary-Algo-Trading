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
