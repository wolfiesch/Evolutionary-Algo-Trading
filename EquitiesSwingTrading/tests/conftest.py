"""
Pytest fixtures for Equities Swing Trading tests.

Provides reusable test data and configuration.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from pathlib import Path
import tempfile


@pytest.fixture
def sample_daily_candles() -> pd.DataFrame:
    """
    Generate sample daily OHLCV data for testing.

    Creates 100 days of synthetic price data with realistic patterns.
    """
    np.random.seed(42)
    n_days = 100

    dates = [date.today() - timedelta(days=n_days - i - 1) for i in range(n_days)]

    # Generate price with upward drift + noise
    base_price = 100.0
    returns = np.random.normal(0.001, 0.02, n_days)  # 0.1% drift, 2% daily vol
    prices = base_price * np.cumprod(1 + returns)

    # Generate OHLCV from close prices
    df = pd.DataFrame({
        "date": dates,
        "close": prices,
        "open": prices * (1 + np.random.uniform(-0.01, 0.01, n_days)),
        "high": prices * (1 + np.random.uniform(0, 0.02, n_days)),
        "low": prices * (1 - np.random.uniform(0, 0.02, n_days)),
        "volume": np.random.randint(1000000, 10000000, n_days),
        "adj_close": prices,
    })

    # Ensure OHLC consistency
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    return df


@pytest.fixture
def sample_spy_uptrend() -> pd.DataFrame:
    """SPY data in a clear uptrend."""
    np.random.seed(42)
    n_days = 100

    dates = [date.today() - timedelta(days=n_days - i - 1) for i in range(n_days)]

    # Strong uptrend: 0.2% daily drift
    base_price = 400.0
    returns = np.random.normal(0.002, 0.01, n_days)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "date": dates,
        "close": prices,
        "open": prices * 0.999,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "volume": np.random.randint(50000000, 100000000, n_days),
    })

    return df


@pytest.fixture
def sample_spy_downtrend() -> pd.DataFrame:
    """SPY data in a clear downtrend."""
    np.random.seed(43)
    n_days = 100

    dates = [date.today() - timedelta(days=n_days - i - 1) for i in range(n_days)]

    # Downtrend: -0.15% daily drift
    base_price = 450.0
    returns = np.random.normal(-0.0015, 0.015, n_days)
    prices = base_price * np.cumprod(1 + returns)

    df = pd.DataFrame({
        "date": dates,
        "close": prices,
        "open": prices * 1.001,
        "high": prices * 1.005,
        "low": prices * 0.995,
        "volume": np.random.randint(50000000, 100000000, n_days),
    })

    return df


@pytest.fixture
def sample_vix_low() -> pd.DataFrame:
    """VIX data in low volatility regime (< 15)."""
    np.random.seed(44)
    n_days = 100

    dates = [date.today() - timedelta(days=n_days - i - 1) for i in range(n_days)]

    # Low VIX around 12-14
    base_vix = 13.0
    vix_values = base_vix + np.random.normal(0, 1, n_days)
    vix_values = np.clip(vix_values, 10, 16)

    df = pd.DataFrame({
        "date": dates,
        "close": vix_values,
        "open": vix_values + np.random.uniform(-0.5, 0.5, n_days),
        "high": vix_values + np.random.uniform(0.5, 1.5, n_days),
        "low": vix_values - np.random.uniform(0.5, 1.5, n_days),
        "volume": np.random.randint(1000000, 5000000, n_days),
    })

    return df


@pytest.fixture
def sample_vix_high() -> pd.DataFrame:
    """VIX data in high volatility regime (> 25)."""
    np.random.seed(45)
    n_days = 100

    dates = [date.today() - timedelta(days=n_days - i - 1) for i in range(n_days)]

    # High VIX around 28-35
    base_vix = 30.0
    vix_values = base_vix + np.random.normal(0, 3, n_days)
    vix_values = np.clip(vix_values, 22, 45)

    df = pd.DataFrame({
        "date": dates,
        "close": vix_values,
        "open": vix_values + np.random.uniform(-1, 1, n_days),
        "high": vix_values + np.random.uniform(1, 3, n_days),
        "low": vix_values - np.random.uniform(1, 3, n_days),
        "volume": np.random.randint(5000000, 15000000, n_days),
    })

    return df


@pytest.fixture
def temp_db_path() -> Path:
    """Create temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        return Path(f.name)


@pytest.fixture
def sample_universe() -> list[str]:
    """Sample universe for testing."""
    return [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA",
        "JPM", "V", "MA", "BAC", "GS",
        "UNH", "JNJ", "PFE", "ABBV", "MRK",
        "XOM", "CVX", "COP", "SLB", "EOG",
    ]
