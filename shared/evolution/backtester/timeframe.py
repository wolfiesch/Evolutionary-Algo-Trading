"""
Timeframe utilities - candle aggregation and period calculations.

T0 Fix: Support multi-timeframe backtesting for more stable Sharpe calculations.
"""
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum


class Timeframe(Enum):
    """Supported timeframes for backtesting."""
    M1 = 1       # 1 minute
    M5 = 5       # 5 minutes
    M15 = 15     # 15 minutes
    M30 = 30     # 30 minutes
    H1 = 60      # 1 hour
    H4 = 240     # 4 hours
    D1 = 1440    # 1 day


# Bars per year for each timeframe (for Sharpe annualization)
BARS_PER_YEAR = {
    Timeframe.M1: 525600,    # 365.25 * 24 * 60
    Timeframe.M5: 105120,    # 525600 / 5
    Timeframe.M15: 35040,    # 525600 / 15
    Timeframe.M30: 17520,    # 525600 / 30
    Timeframe.H1: 8760,      # 24 * 365.25
    Timeframe.H4: 2190,      # 8760 / 4
    Timeframe.D1: 365,       # days per year
}


@dataclass
class TimeframeConfig:
    """Configuration for a specific timeframe."""
    timeframe: Timeframe
    bars_per_year: int
    warmup_bars: int         # Bars needed for indicator warmup
    walk_forward_train: int  # Training window size
    walk_forward_test: int   # Test window size
    walk_forward_step: int   # Step size between windows


# Pre-configured settings for each timeframe
TIMEFRAME_CONFIGS = {
    Timeframe.M1: TimeframeConfig(
        timeframe=Timeframe.M1,
        bars_per_year=525600,
        warmup_bars=60,        # 1 hour warmup
        walk_forward_train=4320,   # 3 days
        walk_forward_test=1440,    # 1 day
        walk_forward_step=1440,    # 1 day
    ),
    Timeframe.H1: TimeframeConfig(
        timeframe=Timeframe.H1,
        bars_per_year=8760,
        warmup_bars=24,        # 1 day warmup
        walk_forward_train=720,    # 30 days
        walk_forward_test=168,     # 7 days
        walk_forward_step=168,     # 7 days
    ),
    Timeframe.H4: TimeframeConfig(
        timeframe=Timeframe.H4,
        bars_per_year=2190,
        warmup_bars=42,        # 7 days warmup (6 bars/day * 7)
        walk_forward_train=360,    # 60 days (6 bars/day * 60) - more robust training
        walk_forward_test=90,      # 15 days - enough for meaningful trade samples
        walk_forward_step=45,      # 7.5 days - overlapping windows for more validation
    ),
    Timeframe.D1: TimeframeConfig(
        timeframe=Timeframe.D1,
        bars_per_year=365,
        warmup_bars=30,        # 30 days warmup
        walk_forward_train=90,     # 3 months
        walk_forward_test=30,      # 1 month
        walk_forward_step=30,      # 1 month
    ),
}


def get_timeframe_config(timeframe: Timeframe) -> TimeframeConfig:
    """Get configuration for a specific timeframe."""
    if timeframe not in TIMEFRAME_CONFIGS:
        # Fall back to M1 for unsupported timeframes
        return TIMEFRAME_CONFIGS[Timeframe.M1]
    return TIMEFRAME_CONFIGS[timeframe]


def aggregate_candles(
    candles: pd.DataFrame,
    target_timeframe: Timeframe,
    source_timeframe: Timeframe = Timeframe.M1,
) -> pd.DataFrame:
    """
    Aggregate candles from source timeframe to target timeframe.

    Args:
        candles: DataFrame with OHLCV data (must have timestamp column in ms)
        target_timeframe: Target timeframe (e.g., H4)
        source_timeframe: Source timeframe (default M1)

    Returns:
        Aggregated DataFrame with OHLCV at target timeframe

    Example:
        # Convert 1-minute candles to 4-hour candles
        h4_candles = aggregate_candles(m1_candles, Timeframe.H4, Timeframe.M1)
    """
    if target_timeframe.value <= source_timeframe.value:
        # No aggregation needed
        return candles.copy()

    df = candles.copy()

    # Ensure timestamp is in correct format
    if 'timestamp' not in df.columns:
        raise ValueError("DataFrame must have 'timestamp' column (Unix ms)")

    # Convert timestamp to datetime for resampling
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
    df.set_index('datetime', inplace=True)

    # Calculate resampling rule
    target_minutes = target_timeframe.value
    resample_rule = f'{target_minutes}min'

    # Aggregate OHLCV
    aggregated = df.resample(resample_rule, label='left', closed='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum',
        'timestamp': 'first',  # Keep first timestamp of period
    })

    # Handle optional columns
    if 'turnover' in df.columns:
        turnover_agg = df.resample(resample_rule, label='left', closed='left')['turnover'].sum()
        aggregated['turnover'] = turnover_agg

    # Remove rows with NaN (incomplete periods)
    aggregated = aggregated.dropna(subset=['open', 'high', 'low', 'close'])

    # Reset index to get datetime as column, then drop it
    aggregated = aggregated.reset_index()

    # Convert datetime back to timestamp (ms) - use the start of each period
    aggregated['timestamp'] = aggregated['datetime'].astype(np.int64) // 10**6
    aggregated = aggregated.drop(columns=['datetime'])

    # Ensure correct column order
    cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if 'turnover' in aggregated.columns:
        cols.append('turnover')
    aggregated = aggregated[cols]

    return aggregated


def estimate_data_requirements(
    target_timeframe: Timeframe,
    desired_bars: int,
    source_timeframe: Timeframe = Timeframe.M1,
) -> int:
    """
    Estimate how many source bars are needed to produce desired target bars.

    Args:
        target_timeframe: Target timeframe
        desired_bars: Number of bars wanted at target timeframe
        source_timeframe: Source timeframe

    Returns:
        Number of source bars needed (with 10% buffer for incomplete periods)
    """
    ratio = target_timeframe.value / source_timeframe.value
    # Add 10% buffer for edge cases
    return int(desired_bars * ratio * 1.1)


def get_periods_per_year(timeframe: Timeframe) -> int:
    """Get the number of periods per year for Sharpe annualization."""
    return BARS_PER_YEAR.get(timeframe, 525600)
