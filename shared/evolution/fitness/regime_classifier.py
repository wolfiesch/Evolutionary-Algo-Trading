"""
Regime classifier for market condition segmentation.

Classifies market periods into 5 regimes based on benchmark behavior:
- bull_calm: Rising market, low volatility
- bull_volatile: Rising market, high volatility
- bear_calm: Falling market, low volatility
- bear_volatile: Falling market, high volatility
- sideways: Range-bound market

This module is asset-agnostic. The benchmark (BTC for crypto, DXY for forex)
is passed in as a parameter.
"""
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import numpy as np


# Regime definitions based on benchmark return and volatility
# These thresholds are for DAILY windows. For shorter windows, use
# get_adaptive_thresholds() which scales based on window size.
REGIME_THRESHOLDS_DAILY = {
    # Return thresholds (over 1-day / 1440 1-min candles)
    "bull_return_min": 0.02,      # +2% = bullish
    "bear_return_max": -0.02,     # -2% = bearish
    # Volatility percentile threshold
    "volatility_high_percentile": 70,  # Above 70th percentile = volatile
}

# Thresholds for 1-hour windows (60 1-min candles)
# Derived from empirical analysis: ±0.3% gives ~25% bull, ~25% bear, ~50% sideways
REGIME_THRESHOLDS_HOURLY = {
    "bull_return_min": 0.003,     # +0.3% = bullish (1-hour)
    "bear_return_max": -0.003,    # -0.3% = bearish (1-hour)
    "volatility_high_percentile": 70,
}


def get_adaptive_thresholds(window_size: int) -> dict:
    """
    Get regime thresholds scaled to window size.

    The core insight: a 2% move in 24 hours is equivalent to
    roughly 0.08% per hour (sqrt scaling for random walk).

    Args:
        window_size: Number of 1-minute candles in window

    Returns:
        Dict with bull_return_min, bear_return_max, volatility_high_percentile
    """
    # Reference: 1440 candles = 1 day, threshold = 2%
    # Scale by sqrt(window/1440) for random-walk-like price behavior
    daily_candles = 1440
    daily_threshold = 0.02

    # sqrt scaling factor
    scale = (window_size / daily_candles) ** 0.5
    threshold = daily_threshold * scale

    # Floor at 0.2% to avoid noise, cap at 5% for very long windows
    threshold = max(0.002, min(0.05, threshold))

    return {
        "bull_return_min": threshold,
        "bear_return_max": -threshold,
        "volatility_high_percentile": 70,
    }


# Legacy alias for backwards compatibility
REGIME_THRESHOLDS = REGIME_THRESHOLDS_HOURLY

# Minimum candles per regime for valid testing
MIN_CANDLES_PER_REGIME = 100

# All regime names
REGIME_NAMES = ["bull_calm", "bull_volatile", "bear_calm", "bear_volatile", "sideways"]


@dataclass
class RegimeClassification:
    """Result of regime classification for a time period."""
    regime: str
    start_idx: int
    end_idx: int
    benchmark_return: float
    volatility_percentile: float
    candle_count: int


@dataclass
class RegimeSplitResult:
    """Result of splitting data by regime."""
    candles_by_regime: dict[str, pd.DataFrame]
    benchmark_by_regime: dict[str, pd.DataFrame]
    regime_stats: dict[str, dict]


def classify_period(
    benchmark_candles: pd.DataFrame,
    volatility_lookback: int = 20,
    thresholds: dict | None = None,
) -> str:
    """
    Classify a single period into one of 5 regimes.

    Args:
        benchmark_candles: OHLCV DataFrame for benchmark (e.g., BTC)
        volatility_lookback: Period for ATR calculation
        thresholds: Optional custom thresholds dict. If None, uses adaptive
                   thresholds based on the window size (len of benchmark_candles)

    Returns:
        Regime name string
    """
    if len(benchmark_candles) < volatility_lookback + 1:
        return "sideways"  # Default when insufficient data

    # Use adaptive thresholds if not provided
    if thresholds is None:
        thresholds = get_adaptive_thresholds(len(benchmark_candles))

    # Calculate return over period
    start_price = benchmark_candles['close'].iloc[0]
    end_price = benchmark_candles['close'].iloc[-1]
    period_return = (end_price - start_price) / start_price

    # Calculate volatility (ATR-based)
    high = benchmark_candles['high']
    low = benchmark_candles['low']
    close = benchmark_candles['close']

    # True Range
    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # ATR
    atr = true_range.rolling(window=volatility_lookback).mean()
    current_atr = atr.iloc[-1]

    # ATR as percentage of price
    atr_pct = current_atr / end_price if end_price > 0 else 0

    # Calculate historical ATR percentile (use all data)
    atr_series = atr.dropna()
    if len(atr_series) > 0:
        volatility_percentile = (atr_series < current_atr).mean() * 100
    else:
        volatility_percentile = 50  # Default

    # Classify using provided or adaptive thresholds
    is_bull = period_return >= thresholds["bull_return_min"]
    is_bear = period_return <= thresholds["bear_return_max"]
    is_volatile = volatility_percentile >= thresholds["volatility_high_percentile"]

    if is_bull and is_volatile:
        return "bull_volatile"
    elif is_bull and not is_volatile:
        return "bull_calm"
    elif is_bear and is_volatile:
        return "bear_volatile"
    elif is_bear and not is_volatile:
        return "bear_calm"
    else:
        return "sideways"


def split_by_regime(
    candles: pd.DataFrame,
    benchmark_candles: pd.DataFrame,
    window_size: int = 60,  # 1 hour for 1-min candles
    step_size: int = 30,    # Sliding window step
) -> RegimeSplitResult:
    """
    Split historical data into regime-specific chunks.

    Uses a sliding window approach to classify each period, then
    aggregates candles by regime.

    Args:
        candles: OHLCV DataFrame for the trading symbol
        benchmark_candles: OHLCV DataFrame for benchmark (BTC/DXY)
        window_size: Size of classification window in candles
        step_size: Step size for sliding window

    Returns:
        RegimeSplitResult with data split by regime
    """
    # Ensure DataFrames are aligned by index
    min_len = min(len(candles), len(benchmark_candles))
    candles = candles.iloc[:min_len].copy()
    benchmark_candles = benchmark_candles.iloc[:min_len].copy()

    # Initialize regime buckets
    regime_indices: dict[str, list[int]] = {r: [] for r in REGIME_NAMES}

    # Classify each window
    for start_idx in range(0, len(benchmark_candles) - window_size, step_size):
        end_idx = start_idx + window_size
        window = benchmark_candles.iloc[start_idx:end_idx]

        regime = classify_period(window)

        # Add all indices in window to regime bucket
        # (overlapping windows will create some duplication, which is fine)
        for idx in range(start_idx, end_idx):
            if idx not in regime_indices[regime]:
                regime_indices[regime].append(idx)

    # Build DataFrames for each regime
    candles_by_regime: dict[str, pd.DataFrame] = {}
    benchmark_by_regime: dict[str, pd.DataFrame] = {}
    regime_stats: dict[str, dict] = {}

    for regime in REGIME_NAMES:
        indices = sorted(set(regime_indices[regime]))
        if indices:
            candles_by_regime[regime] = candles.iloc[indices].reset_index(drop=True)
            benchmark_by_regime[regime] = benchmark_candles.iloc[indices].reset_index(drop=True)

            # Calculate stats
            if len(benchmark_by_regime[regime]) > 0:
                start_price = benchmark_by_regime[regime]['close'].iloc[0]
                end_price = benchmark_by_regime[regime]['close'].iloc[-1]
                regime_return = (end_price - start_price) / start_price if start_price > 0 else 0
            else:
                regime_return = 0

            regime_stats[regime] = {
                "candle_count": len(indices),
                "benchmark_return": regime_return,
                "pct_of_total": len(indices) / len(candles) * 100 if len(candles) > 0 else 0,
            }
        else:
            candles_by_regime[regime] = pd.DataFrame()
            benchmark_by_regime[regime] = pd.DataFrame()
            regime_stats[regime] = {
                "candle_count": 0,
                "benchmark_return": 0,
                "pct_of_total": 0,
            }

    return RegimeSplitResult(
        candles_by_regime=candles_by_regime,
        benchmark_by_regime=benchmark_by_regime,
        regime_stats=regime_stats,
    )


def get_regime_requirements() -> dict[str, float]:
    """
    Get the minimum Sharpe ratio requirements per regime.

    From CLAUDE.md: "Sharpe > 0.5 in 4/5 market regimes"

    Returns:
        Dict mapping regime name to minimum Sharpe requirement
    """
    return {regime: 0.5 for regime in REGIME_NAMES}


def calculate_regime_pass_count(
    regime_sharpes: dict[str, float],
    min_sharpe: float = 0.5,
) -> int:
    """
    Count how many regimes pass the minimum Sharpe threshold.

    Args:
        regime_sharpes: Dict mapping regime name to Sharpe ratio
        min_sharpe: Minimum Sharpe to pass

    Returns:
        Number of regimes that pass
    """
    return sum(1 for sharpe in regime_sharpes.values() if sharpe >= min_sharpe)


def has_negative_regime(regime_sharpes: dict[str, float]) -> tuple[bool, Optional[str]]:
    """
    Check if any regime has negative Sharpe (hard fail).

    From Phase 2 plan: "HARD FAIL: Any regime with negative Sharpe -> disqualified"

    Args:
        regime_sharpes: Dict mapping regime name to Sharpe ratio

    Returns:
        (has_negative, worst_regime_name)
    """
    for regime, sharpe in regime_sharpes.items():
        if sharpe < 0:
            return True, regime
    return False, None


def calculate_regime_multiplier(
    regime_sharpes: dict[str, float],
    required_passes: int = 4,
) -> float:
    """
    Calculate regime multiplier for fitness score.

    From Phase 2 plan:
    - regime_multiplier = 0 if <4 regimes pass (Sharpe >= 0.5)
    - else regime_multiplier = passed / 5

    Args:
        regime_sharpes: Dict mapping regime name to Sharpe ratio
        required_passes: Minimum regimes that must pass

    Returns:
        Multiplier from 0.0 to 1.0
    """
    pass_count = calculate_regime_pass_count(regime_sharpes)

    if pass_count < required_passes:
        return 0.0

    return pass_count / len(REGIME_NAMES)
