#!/usr/bin/env python3
"""
Cross-validate a strategy across multiple symbols.
Usage: cd crypto && python scripts/validate_strategy.py
"""
import sys
from pathlib import Path

# Add paths for imports (same as evolve.py does when run from crypto/)
sys.path.insert(0, str(Path(__file__).parent.parent))  # crypto/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))  # project root

import pandas as pd
from data.storage.repository import CandleRepository
from shared.evolution.backtester import MinimalBacktester, BacktestConfig
from shared.evolution.fitness import calculate_fitness
from engine.strategy_logic.parser import GeneExpressionParser


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


def validate_strategy(
    entry_long: str,
    exit_long: str,
    symbols: list[str],
    db_path: str = None,
    candle_limit: int = 260000,
):
    """Validate a strategy across multiple symbols."""
    if db_path is None:
        db_path = str(Path(__file__).parent.parent / "data" / "candles.db")

    repo = CandleRepository(db_path)
    parser = GeneExpressionParser()

    # Create backtest config with defaults
    backtest_config = BacktestConfig()
    backtester = MinimalBacktester(backtest_config)

    # Load benchmark (BTC)
    btc_candles_raw = repo.get_latest("BTCUSDT", limit=candle_limit)
    btc_candles = candles_to_df(btc_candles_raw)
    print(f"Loaded {len(btc_candles)} BTC benchmark candles")

    results = {}

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Testing on {symbol}")
        print(f"{'='*60}")

        # Load candles
        candles_raw = repo.get_latest(symbol, limit=candle_limit)
        candles = candles_to_df(candles_raw)
        print(f"Loaded {len(candles)} candles")

        if len(candles) < 1000:
            print(f"  SKIPPED - insufficient data")
            continue

        # Create strategy and evaluator (same pattern as evolve.py)
        from engine.strategy_logic.parser import Strategy

        strategy = Strategy(
            name="SidewaysRange_V1",
            entry_long=entry_long,
            exit_long=exit_long,
        )

        def make_evaluator(strat, p):
            def evaluator(candles_df, benchmark_df, has_position):
                try:
                    signal = p.get_signal(strat, candles_df, benchmark_df, has_position)
                    return signal.value  # "ENTRY_LONG", "EXIT_LONG", or "HOLD"
                except Exception as e:
                    return "HOLD"
            return evaluator

        evaluator = make_evaluator(strategy, parser)

        try:
            # Run backtest
            bt_results = backtester.run(
                evaluator=evaluator,
                candles=candles,
                benchmark_candles=btc_candles,
                symbol=symbol,
            )

            # Calculate fitness
            fitness = calculate_fitness(bt_results)

            summary = bt_results.summary()

            # Helper to parse values that may contain % sign
            def parse_pct(val):
                if val is None:
                    return 0.0
                if isinstance(val, str):
                    return float(val.replace('%', ''))
                return float(val)

            # Convert to float - some values may already be percentages
            sharpe = parse_pct(summary.get('sharpe_ratio', 0))
            max_dd = parse_pct(summary.get('max_drawdown', 0))  # Already %
            trades = int(summary.get('trade_count', 0) or 0)
            win_rate = parse_pct(summary.get('win_rate', 0))
            total_ret = parse_pct(summary.get('total_return', 0))

            results[symbol] = {
                'sharpe': sharpe,
                'max_dd': max_dd,
                'trades': trades,
                'win_rate': win_rate,
                'total_return': total_ret,
                'disqualified': fitness.disqualified,
                'reason': fitness.disqualification_reason if fitness.disqualified else None,
            }

            if fitness.disqualified:
                print(f"  DISQUALIFIED: {fitness.disqualification_reason}")
            else:
                print(f"  Sharpe: {sharpe:.2f}")
                print(f"  Max DD: {max_dd:.1f}%")
                print(f"  Trades: {trades}")
                print(f"  Win Rate: {win_rate:.1f}%")
                print(f"  Total Return: {total_ret:.1f}%")

        except Exception as e:
            print(f"  ERROR: {e}")
            results[symbol] = {'error': str(e)}

    return results


if __name__ == "__main__":
    # BTC Winner: SidewaysRange_V1
    ENTRY = "asset_trend(60) >= 0 AND bb_position(20, 1) < -0.5 AND norm_rsi(14) < 0.3"
    EXIT = "norm_rsi(14) > 0.7 OR bb_position(20,1) > 0.5"

    print("="*60)
    print("CROSS-VALIDATION: SidewaysRange_V1 (BTC Winner)")
    print("="*60)
    print(f"Entry: {ENTRY}")
    print(f"Exit: {EXIT}")

    results = validate_strategy(
        entry_long=ENTRY,
        exit_long=EXIT,
        symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    )

    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    for symbol, r in results.items():
        if 'error' in r:
            print(f"{symbol}: ERROR - {r['error']}")
        elif r.get('disqualified'):
            print(f"{symbol}: DISQUALIFIED - {r['reason']}")
        else:
            print(f"{symbol}: Sharpe={r['sharpe']:.2f}, DD={r['max_dd']:.1f}%, Trades={r['trades']}, WinRate={r['win_rate']:.1f}%")
