#!/usr/bin/env python3
"""
Backtester Sanity Check Harness

Validates that the backtester produces correct results by running known
baseline strategies and checking data quality.

Run before any evolution to ensure the backtester is working correctly.
If these checks fail, evolution results cannot be trusted.

Usage:
    python crypto/scripts/sanity_check_backtest.py
    python crypto/scripts/sanity_check_backtest.py --symbol=ETHUSDT --candles=5000
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

import pandas as pd
import numpy as np

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from crypto.config import settings
from crypto.data.storage.repository import CandleRepository
from shared.evolution.backtester import MinimalBacktester, BacktestConfig
from shared.evolution.fitness import calculate_fitness


# ANSI colors for terminal output
class Colors:
    PASS = "\033[92m"  # Green
    FAIL = "\033[91m"  # Red
    WARN = "\033[93m"  # Yellow
    INFO = "\033[94m"  # Blue
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}")


def print_result(name: str, passed: bool, details: str = ""):
    """Print a test result."""
    status = f"{Colors.PASS}PASS{Colors.END}" if passed else f"{Colors.FAIL}FAIL{Colors.END}"
    print(f"  [{status}] {name}")
    if details:
        print(f"         {details}")


def print_warning(message: str):
    """Print a warning message."""
    print(f"  [{Colors.WARN}WARN{Colors.END}] {message}")


def load_candles(symbol: str, benchmark: str, num_candles: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load candle data from database."""
    repo = CandleRepository(settings.sqlite_path)

    candles = repo.get_latest(symbol, num_candles)
    benchmark_candles = repo.get_latest(benchmark, num_candles)

    # Convert to DataFrame
    candles_df = pd.DataFrame([{
        'timestamp': c.timestamp,
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
    } for c in candles])

    benchmark_df = pd.DataFrame([{
        'timestamp': c.timestamp,
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
    } for c in benchmark_candles])

    return candles_df, benchmark_df


# =============================================================================
# DATA QUALITY CHECKS
# =============================================================================

def check_timestamp_ordering(candles_df: pd.DataFrame) -> tuple[bool, str]:
    """Check that timestamps are strictly increasing."""
    if len(candles_df) < 2:
        return False, "Not enough candles to check ordering"

    timestamps = candles_df['timestamp'].values
    is_sorted = all(timestamps[i] < timestamps[i+1] for i in range(len(timestamps)-1))

    if not is_sorted:
        # Find first violation
        for i in range(len(timestamps)-1):
            if timestamps[i] >= timestamps[i+1]:
                return False, f"Timestamp not increasing at index {i}: {timestamps[i]} >= {timestamps[i+1]}"

    return True, f"{len(candles_df)} candles, all timestamps strictly increasing"


def check_duplicate_timestamps(candles_df: pd.DataFrame) -> tuple[bool, str]:
    """Check for duplicate timestamps."""
    duplicates = candles_df['timestamp'].duplicated().sum()

    if duplicates > 0:
        return False, f"Found {duplicates} duplicate timestamps"

    return True, "No duplicate timestamps"


def check_gaps(candles_df: pd.DataFrame, expected_interval_ms: int = 60000) -> tuple[bool, str]:
    """
    Check for gaps in timestamp sequence.

    Note: This is a data quality check, not a backtester correctness check.
    Gaps are common in real market data and the backtester should handle them.
    We warn but don't fail unless gaps are extreme.
    """
    if len(candles_df) < 2:
        return False, "Not enough candles to check gaps"

    timestamps = candles_df['timestamp'].values
    diffs = np.diff(timestamps)

    # Expected interval is 60000ms (1 minute)
    expected = expected_interval_ms

    # Allow for small variations (up to 10% tolerance)
    normal_gaps = (diffs >= expected * 0.9) & (diffs <= expected * 1.1)
    abnormal_count = (~normal_gaps).sum()

    if abnormal_count > 0:
        max_gap = diffs.max()
        max_gap_minutes = max_gap / 60000
        gap_pct = abnormal_count / len(diffs) * 100

        # Only fail if >10% of intervals are gaps OR max gap > 60 minutes
        severe = gap_pct > 10 or max_gap_minutes > 60

        status_msg = (
            f"{abnormal_count} gaps ({gap_pct:.1f}% of intervals). "
            f"Max gap: {max_gap_minutes:.1f} min. "
            f"{'SEVERE - may affect results' if severe else 'Minor - acceptable for backtesting'}"
        )

        return not severe, status_msg

    return True, f"All {len(diffs)} intervals are ~{expected_interval_ms/60000:.1f} minute(s)"


def check_price_anomalies(candles_df: pd.DataFrame, max_pct_move: float = 0.20) -> tuple[bool, str]:
    """Check for suspicious single-candle price moves."""
    if len(candles_df) < 2:
        return False, "Not enough candles"

    # Calculate single-candle returns
    returns = candles_df['close'].pct_change().dropna().abs()

    anomalies = (returns > max_pct_move).sum()
    max_move = returns.max()

    if anomalies > 0:
        return False, (
            f"Found {anomalies} candles with >{max_pct_move*100:.0f}% move. "
            f"Max single-candle move: {max_move*100:.1f}%"
        )

    return True, f"Max single-candle move: {max_move*100:.2f}%"


def check_volume_anomalies(candles_df: pd.DataFrame) -> tuple[bool, str]:
    """Check for zero or negative volume."""
    zero_volume = (candles_df['volume'] <= 0).sum()

    if zero_volume > 0:
        return False, f"Found {zero_volume} candles with zero/negative volume"

    return True, f"All candles have positive volume"


def run_data_quality_checks(candles_df: pd.DataFrame, symbol: str) -> int:
    """Run all data quality checks. Returns number of failures."""
    print_header(f"DATA QUALITY CHECKS ({symbol})")

    failures = 0

    checks = [
        ("Timestamp ordering", check_timestamp_ordering(candles_df)),
        ("Duplicate timestamps", check_duplicate_timestamps(candles_df)),
        ("Gap detection (1-min candles)", check_gaps(candles_df)),
        ("Price anomalies (<20% single-candle)", check_price_anomalies(candles_df)),
        ("Volume anomalies", check_volume_anomalies(candles_df)),
    ]

    for name, (passed, details) in checks:
        print_result(name, passed, details)
        if not passed:
            failures += 1

    return failures


# =============================================================================
# BASELINE STRATEGY EVALUATORS
# =============================================================================

def always_long_evaluator(candles: pd.DataFrame, benchmark: pd.DataFrame, has_position: bool) -> str:
    """Always long - enter immediately, never exit."""
    if not has_position:
        return "ENTRY_LONG"
    return "HOLD"


def always_flat_evaluator(candles: pd.DataFrame, benchmark: pd.DataFrame, has_position: bool) -> str:
    """Never trade - always hold cash."""
    return "HOLD"


def simple_ma_crossover_evaluator(candles: pd.DataFrame, benchmark: pd.DataFrame, has_position: bool) -> str:
    """
    Simple MA crossover: long when fast EMA > slow EMA.
    Uses 9/21 EMA crossover - a classic trend-following signal.
    """
    if len(candles) < 21:
        return "HOLD"

    close = candles['close']
    fast_ema = close.ewm(span=9, adjust=False).mean()
    slow_ema = close.ewm(span=21, adjust=False).mean()

    fast_current = fast_ema.iloc[-1]
    slow_current = slow_ema.iloc[-1]

    if not has_position and fast_current > slow_current:
        return "ENTRY_LONG"
    elif has_position and fast_current < slow_current:
        return "EXIT_LONG"

    return "HOLD"


# =============================================================================
# BACKTEST SANITY CHECKS
# =============================================================================

def check_buy_and_hold(
    candles_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    backtester: MinimalBacktester,
    symbol: str,
) -> tuple[bool, str]:
    """
    Run buy-and-hold strategy and verify it matches asset return.

    The backtest return should approximately equal:
        position_pct * ((final_price / initial_price) - 1) - (2 * friction * position_pct)

    Note: We account for max_position_pct since the backtester doesn't go 100% into positions.
    """
    results = backtester.run(
        evaluator=always_long_evaluator,
        candles=candles_df,
        benchmark_candles=benchmark_df,
        symbol=symbol,
    )

    # Calculate expected return accounting for position sizing
    initial_price = candles_df['close'].iloc[60]  # After warmup
    final_price = candles_df['close'].iloc[-1]
    gross_asset_return = (final_price / initial_price) - 1

    # Position sizing adjustment
    position_pct = backtester.config.max_position_pct  # e.g., 0.5 = 50%

    # Expected return = position_pct * asset_return - friction costs
    # Friction on position value at entry and exit
    friction = backtester.config.friction_per_side
    expected_net_return = (position_pct * gross_asset_return) - (2 * friction * position_pct)

    actual_return = results.total_return

    # Allow 10% relative tolerance or 1% absolute tolerance
    tolerance = 0.10
    diff = abs(actual_return - expected_net_return)
    relative_diff = diff / abs(expected_net_return) if expected_net_return != 0 else diff

    passed = relative_diff < tolerance or diff < 0.01

    details = (
        f"Asset return: {gross_asset_return*100:.2f}% × {position_pct*100:.0f}% position, "
        f"Expected: {expected_net_return*100:.2f}%, Actual: {actual_return*100:.2f}%, "
        f"Diff: {diff*100:.2f}% ({results.trade_count} trades, DD: {results.max_drawdown*100:.1f}%)"
    )

    return passed, details


def check_always_flat(
    candles_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    backtester: MinimalBacktester,
    symbol: str,
) -> tuple[bool, str]:
    """
    Run always-flat strategy and verify ~0 return, ~0 drawdown.

    Never trading should result in:
        - 0 trades
        - 0 return
        - 0 drawdown
    """
    results = backtester.run(
        evaluator=always_flat_evaluator,
        candles=candles_df,
        benchmark_candles=benchmark_df,
        symbol=symbol,
    )

    passed = True
    issues = []

    if results.trade_count != 0:
        issues.append(f"trades={results.trade_count} (expected 0)")
        passed = False

    if abs(results.total_return) > 0.001:
        issues.append(f"return={results.total_return*100:.3f}% (expected ~0%)")
        passed = False

    if results.max_drawdown > 0.001:
        issues.append(f"drawdown={results.max_drawdown*100:.3f}% (expected ~0%)")
        passed = False

    if passed:
        details = f"0 trades, 0% return, 0% drawdown - as expected"
    else:
        details = f"ISSUES: {', '.join(issues)}"

    return passed, details


def check_ma_crossover(
    candles_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    backtester: MinimalBacktester,
    symbol: str,
) -> tuple[bool, str]:
    """
    Run simple MA crossover and verify plausible behavior.

    Expected:
        - At least some trades (strategy should trigger)
        - Reasonable trade count (not 0, not excessive)
        - Metrics should be finite (no NaN/inf)
    """
    results = backtester.run(
        evaluator=simple_ma_crossover_evaluator,
        candles=candles_df,
        benchmark_candles=benchmark_df,
        symbol=symbol,
    )

    passed = True
    issues = []

    # Should have at least some trades
    if results.trade_count == 0:
        issues.append("0 trades - strategy never triggered")
        passed = False

    # Should not have excessive trades (> 1 trade per 100 candles is suspicious)
    max_reasonable_trades = len(candles_df) / 100
    if results.trade_count > max_reasonable_trades:
        issues.append(f"{results.trade_count} trades seems excessive for {len(candles_df)} candles")
        # Not a hard fail, just a warning

    # Metrics should be finite
    if not np.isfinite(results.sharpe_ratio):
        issues.append(f"Sharpe is not finite: {results.sharpe_ratio}")
        passed = False

    if not np.isfinite(results.total_return):
        issues.append(f"Return is not finite: {results.total_return}")
        passed = False

    if passed:
        details = (
            f"{results.trade_count} trades, "
            f"Return: {results.total_return*100:.2f}%, "
            f"Sharpe: {results.sharpe_ratio:.2f}, "
            f"Win rate: {results.win_rate*100:.1f}%, "
            f"DD: {results.max_drawdown*100:.1f}%"
        )
    else:
        details = f"ISSUES: {', '.join(issues)}"

    return passed, details


def check_fee_units(backtester: MinimalBacktester) -> tuple[bool, str]:
    """
    Verify fee configuration makes sense.

    Fees should be in decimal form (0.001 = 0.1%), not percentage (0.1 = 10%).
    """
    friction = backtester.config.friction_per_side

    # Reasonable range: 0.01% to 1% per side
    if friction < 0.0001:
        return False, f"Friction {friction} seems too low (< 0.01%). Is it in the right units?"

    if friction > 0.01:
        return False, f"Friction {friction} seems too high (> 1%). Is it in decimal form (not percentage)?"

    return True, f"Friction per side: {friction*100:.3f}% ({friction*10000:.1f} bps)"


def run_backtest_sanity_checks(
    candles_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    backtester: MinimalBacktester,
    symbol: str,
) -> int:
    """Run all backtest sanity checks. Returns number of failures."""
    print_header(f"BACKTEST SANITY CHECKS ({symbol})")

    failures = 0

    # Fee units check
    passed, details = check_fee_units(backtester)
    print_result("Fee units sanity", passed, details)
    if not passed:
        failures += 1

    # Buy and hold
    passed, details = check_buy_and_hold(candles_df, benchmark_df, backtester, symbol)
    print_result("Buy-and-hold matches asset return", passed, details)
    if not passed:
        failures += 1

    # Always flat
    passed, details = check_always_flat(candles_df, benchmark_df, backtester, symbol)
    print_result("Always-flat has zero activity", passed, details)
    if not passed:
        failures += 1

    # MA crossover
    passed, details = check_ma_crossover(candles_df, benchmark_df, backtester, symbol)
    print_result("MA crossover produces trades", passed, details)
    if not passed:
        failures += 1

    return failures


# =============================================================================
# FITNESS FUNCTION CHECKS
# =============================================================================

def check_fitness_not_saturated() -> tuple[bool, str]:
    """
    Verify that fitness function doesn't collapse to 0 for negative Sharpe.

    This was a critical bug: max(0, sharpe) made all negative-Sharpe
    strategies indistinguishable.
    """
    from shared.evolution.backtester.models import BacktestResults

    # Create mock results with negative Sharpe
    mock_results = BacktestResults(
        symbol="TEST",
        trade_count=20,
        win_rate=0.4,
        sharpe_ratio=-2.0,  # Negative Sharpe
        max_drawdown=0.15,
        total_return=-0.05,
        profit_factor=0.8,
    )

    fitness = calculate_fitness(mock_results)

    # Score should NOT be 0 for negative Sharpe - should preserve ranking signal
    if fitness.final_score == 0.0:
        return False, f"Score is 0 for Sharpe=-2.0 - fitness saturation bug still present!"

    # Score should be negative for negative Sharpe (after penalties)
    if fitness.final_score > 0:
        return False, f"Score is positive ({fitness.final_score:.3f}) for negative Sharpe - suspicious"

    return True, f"Negative Sharpe produces rankable score: {fitness.final_score:.3f}"


def check_fitness_ranking_preserved() -> tuple[bool, str]:
    """
    Verify that Sharpe=-2 ranks higher than Sharpe=-5.

    This ensures evolution can learn "which direction to improve".
    """
    from shared.evolution.backtester.models import BacktestResults

    # Create two mock results with different negative Sharpes
    less_bad = BacktestResults(
        symbol="TEST",
        trade_count=20,
        win_rate=0.4,
        sharpe_ratio=-2.0,  # Less negative
        max_drawdown=0.15,
        total_return=-0.03,
        profit_factor=0.9,
    )

    more_bad = BacktestResults(
        symbol="TEST",
        trade_count=20,
        win_rate=0.3,
        sharpe_ratio=-5.0,  # More negative
        max_drawdown=0.15,
        total_return=-0.10,
        profit_factor=0.5,
    )

    fitness_less_bad = calculate_fitness(less_bad)
    fitness_more_bad = calculate_fitness(more_bad)

    if fitness_less_bad.final_score <= fitness_more_bad.final_score:
        return False, (
            f"Ranking broken: Sharpe=-2 score ({fitness_less_bad.final_score:.3f}) "
            f"<= Sharpe=-5 score ({fitness_more_bad.final_score:.3f})"
        )

    return True, (
        f"Sharpe=-2 ({fitness_less_bad.final_score:.3f}) > "
        f"Sharpe=-5 ({fitness_more_bad.final_score:.3f}) - ranking preserved"
    )


def run_fitness_checks() -> int:
    """Run fitness function checks. Returns number of failures."""
    print_header("FITNESS FUNCTION CHECKS")

    failures = 0

    passed, details = check_fitness_not_saturated()
    print_result("Fitness doesn't saturate at 0", passed, details)
    if not passed:
        failures += 1

    passed, details = check_fitness_ranking_preserved()
    print_result("Negative Sharpe ranking preserved", passed, details)
    if not passed:
        failures += 1

    return failures


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Backtest sanity checks")
    parser.add_argument("--symbol", default="SOLUSDT", help="Trading symbol")
    parser.add_argument("--benchmark", default="BTCUSDT", help="Benchmark symbol")
    parser.add_argument("--candles", type=int, default=10000, help="Number of candles to load")
    parser.add_argument("--friction", type=float, default=0.001, help="Friction per side (default 0.1%)")
    args = parser.parse_args()

    print(f"\n{Colors.BOLD}BACKTESTER SANITY CHECK{Colors.END}")
    print(f"Symbol: {args.symbol}, Benchmark: {args.benchmark}")
    print(f"Candles: {args.candles}, Friction: {args.friction*100:.3f}%")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Load data
    print(f"\nLoading candle data...")
    try:
        candles_df, benchmark_df = load_candles(args.symbol, args.benchmark, args.candles)
        print(f"  Loaded {len(candles_df)} {args.symbol} candles")
        print(f"  Loaded {len(benchmark_df)} {args.benchmark} candles")

        if len(candles_df) < 100:
            print(f"\n{Colors.FAIL}ERROR: Not enough candles loaded. Check database.{Colors.END}")
            sys.exit(1)

    except Exception as e:
        print(f"\n{Colors.FAIL}ERROR loading data: {e}{Colors.END}")
        sys.exit(1)

    # Create backtester
    config = BacktestConfig(
        friction_per_side=args.friction,
        max_position_pct=0.5,
        stop_loss_pct=0.05,
        initial_equity=10000.0,
    )
    backtester = MinimalBacktester(config)

    # Run all checks
    total_failures = 0

    total_failures += run_data_quality_checks(candles_df, args.symbol)
    total_failures += run_backtest_sanity_checks(candles_df, benchmark_df, backtester, args.symbol)
    total_failures += run_fitness_checks()

    # Summary
    print_header("SUMMARY")

    if total_failures == 0:
        print(f"\n{Colors.PASS}✓ All sanity checks passed!{Colors.END}")
        print("  Backtester appears to be working correctly.")
        print("  You can proceed with evolution runs.\n")
        sys.exit(0)
    else:
        print(f"\n{Colors.FAIL}✗ {total_failures} check(s) failed!{Colors.END}")
        print("  DO NOT run evolution until these issues are fixed.")
        print("  Evolution results will not be trustworthy.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
