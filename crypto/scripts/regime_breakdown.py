#!/usr/bin/env python3
"""
Run regime breakdown analysis on a strategy.
Usage: cd crypto && python scripts/regime_breakdown.py
"""
import sys
from pathlib import Path

# Add paths for imports (same as evolve.py does when run from crypto/)
sys.path.insert(0, str(Path(__file__).parent.parent))  # crypto/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # project root

import pandas as pd
from data.storage.repository import CandleRepository
from shared.evolution.backtester import MinimalBacktester, BacktestConfig
from shared.evolution.fitness import calculate_fitness, REGIME_NAMES
from engine.strategy_logic.parser import GeneExpressionParser, Strategy


def candles_to_df(candles):
    """Convert list of Candle objects to DataFrame."""
    return pd.DataFrame([{
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
        'timestamp': c.timestamp,
    } for c in candles])


def run_regime_breakdown(
    entry_long: str,
    exit_long: str,
    symbol: str = "BTCUSDT",
    db_path: str = None,
    candle_limit: int = 260000,
):
    """Run regime-based backtest breakdown."""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "candles.db")

    repo = CandleRepository(db_path)
    parser = GeneExpressionParser()
    backtest_config = BacktestConfig()
    backtester = MinimalBacktester(backtest_config)

    # Load data
    print(f"Loading data for {symbol}...")
    candles_raw = repo.get_latest(symbol, limit=candle_limit)
    candles = candles_to_df(candles_raw)

    btc_candles_raw = repo.get_latest("BTCUSDT", limit=candle_limit)
    btc_candles = candles_to_df(btc_candles_raw)

    print(f"Loaded {len(candles)} {symbol} candles, {len(btc_candles)} BTC candles")

    # Create strategy
    strategy = Strategy(
        name="SidewaysRange_V1",
        entry_long=entry_long,
        exit_long=exit_long,
    )

    def make_evaluator(strat, p):
        def evaluator(candles_df, benchmark_df, has_position):
            try:
                signal = p.get_signal(strat, candles_df, benchmark_df, has_position)
                return signal.value
            except Exception:
                return "HOLD"
        return evaluator

    evaluator = make_evaluator(strategy, parser)

    # Run regime breakdown
    print("\nRunning regime breakdown...")
    regime_results = backtester.run_by_regime(
        evaluator=evaluator,
        candles=candles,
        benchmark_candles=btc_candles,
        symbol=symbol,
    )

    # Print results
    print("\n" + "=" * 70)
    print(f"REGIME BREAKDOWN: {symbol}")
    print("=" * 70)
    print(f"{'Regime':<20} {'Sharpe':>10} {'MaxDD':>10} {'Trades':>8} {'WinRate':>10} {'Return':>10}")
    print("-" * 70)

    for regime_name in REGIME_NAMES:
        if regime_name in regime_results:
            results = regime_results[regime_name]
            summary = results.summary()

            # Parse values
            def parse_pct(val):
                if val is None:
                    return 0.0
                if isinstance(val, str):
                    return float(val.replace('%', ''))
                return float(val)

            sharpe = parse_pct(summary.get('sharpe_ratio', 0))
            max_dd = parse_pct(summary.get('max_drawdown', 0))
            trades = int(summary.get('trade_count', 0) or 0)
            win_rate = parse_pct(summary.get('win_rate', 0))
            total_ret = parse_pct(summary.get('total_return', 0))

            status = "✅" if sharpe > 0.5 else "⚠️" if sharpe > 0 else "❌"
            print(f"{regime_name:<20} {sharpe:>9.2f} {max_dd:>9.1f}% {trades:>8} {win_rate:>9.1f}% {total_ret:>9.1f}% {status}")
        else:
            print(f"{regime_name:<20} {'N/A':>10} {'N/A':>10} {'N/A':>8} {'N/A':>10} {'N/A':>10}")

    print("=" * 70)

    # Summary
    positive_regimes = sum(1 for r in regime_results.values()
                         if float(str(r.summary().get('sharpe_ratio', 0)).replace('%', '')) > 0.5)
    total_regimes = len(regime_results)
    print(f"\nPositive Sharpe (>0.5) in {positive_regimes}/{total_regimes} regimes")

    if positive_regimes >= 4:
        print("✅ Strategy passes regime test (4+ regimes)")
    else:
        print("❌ Strategy FAILS regime test (need 4+ regimes)")

    return regime_results


if __name__ == "__main__":
    # BTC Winner: SidewaysRange_V1
    ENTRY = "asset_trend(60) >= 0 AND bb_position(20, 1) < -0.5 AND norm_rsi(14) < 0.3"
    EXIT = "norm_rsi(14) > 0.7 OR bb_position(20,1) > 0.5"

    print("=" * 70)
    print("REGIME BREAKDOWN ANALYSIS: SidewaysRange_V1 (BTC Winner)")
    print("=" * 70)
    print(f"Entry: {ENTRY}")
    print(f"Exit: {EXIT}")

    results = run_regime_breakdown(
        entry_long=ENTRY,
        exit_long=EXIT,
        symbol="BTCUSDT",
    )
