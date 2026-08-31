#!/usr/bin/env python3
"""
Strategy Evolution Script

Backtests and validates seed strategies using walk-forward validation.
This is the entry point for strategy evolution and validation.

Usage:
    python scripts/evolve_strategies.py [OPTIONS]

Options:
    --quick           Quick mode: smaller universe, shorter validation
    --strategy NAME   Test specific strategy only
    --list            List all available strategies
    --validate        Run walk-forward validation
    --backtest        Run simple backtest (no walk-forward)
"""

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

# Add project roots to path
PROJECT_ROOT = Path(__file__).parent.parent
SHARED_ROOT = PROJECT_ROOT.parent / "shared"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(SHARED_ROOT.parent))

import pandas as pd
import numpy as np

from config import get_config, DATA_DIR
from data.storage.repository import EquitiesRepository
from data.ingestion.universe import SEED_UNIVERSE
from strategies.seed_strategies import (
    get_seed_strategies,
    get_default_strategies,
    validate_strategy,
    ALL_STRATEGIES,
)
from evolution.backtester.evaluator import (
    Strategy,
    EquitiesEvaluator,
    FundamentalContext,
)
from shared.evolution.backtester.models import BacktestConfig, WalkForwardConfig
from shared.evolution.backtester.engine import MinimalBacktester
from shared.evolution.backtester.walk_forward import WalkForwardValidator, walk_forward_fitness

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class EvolutionRunner:
    """
    Runs strategy evolution and validation.

    Supports:
    - Simple backtesting on historical data
    - Walk-forward validation for overfitting detection
    - Strategy comparison and ranking
    """

    def __init__(
        self,
        repository: EquitiesRepository,
        config: BacktestConfig = None,
    ):
        """
        Initialize evolution runner.

        Args:
            repository: Database repository with historical data
            config: Backtest configuration
        """
        self.repository = repository
        self.config = config or BacktestConfig(
            initial_equity=100_000.0,
            friction_per_side=0.0003,  # 0.03% for equities
            max_position_pct=0.05,
            max_open_positions=20,
            stop_loss_pct=0.05,
            warmup_bars=60,
        )
        self.backtester = MinimalBacktester(self.config)

    def get_historical_data(
        self,
        symbols: list[str],
        years: int = 5,
    ) -> dict[str, pd.DataFrame]:
        """
        Load historical data from repository.

        Args:
            symbols: Symbols to load
            years: Years of history

        Returns:
            Dict mapping symbol -> OHLCV DataFrame
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)

        data = {}
        for symbol in symbols:
            df = self.repository.get_daily_candles(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            if not df.empty and len(df) >= 100:
                data[symbol] = df

        return data

    def get_spy_vix_data(self, years: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Load SPY and VIX data."""
        end_date = date.today()
        start_date = end_date - timedelta(days=years * 365)

        spy = self.repository.get_daily_candles("SPY", start_date, end_date)
        vix = self.repository.get_daily_candles("^VIX", start_date, end_date)

        return spy, vix

    def create_evaluator(
        self,
        strategy: Strategy,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        fundamental_context: Optional[FundamentalContext] = None,
    ) -> callable:
        """
        Create evaluator function for a strategy.

        Returns function with signature:
            (candles, benchmark, has_position) -> str
        """
        evaluator = EquitiesEvaluator(
            spy_data=spy_data,
            vix_data=vix_data,
            fundamental_context=fundamental_context,
        )

        return evaluator.create_evaluator(strategy)

    def backtest_strategy(
        self,
        strategy: Strategy,
        symbol: str,
        candles: pd.DataFrame,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        fundamental_context: Optional[FundamentalContext] = None,
    ) -> dict:
        """
        Run backtest for a single strategy on a single symbol.

        Returns:
            Dict with backtest results
        """
        if len(candles) < self.config.warmup_bars:
            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "error": "Insufficient data",
                "trade_count": 0,
            }

        try:
            evaluator = self.create_evaluator(
                strategy=strategy,
                spy_data=spy_data,
                vix_data=vix_data,
                fundamental_context=fundamental_context,
            )

            results = self.backtester.run(
                evaluator=evaluator,
                candles=candles,
                benchmark_candles=spy_data,
                symbol=symbol,
            )

            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "trade_count": results.trade_count,
                "win_rate": results.win_rate,
                "total_return": results.total_return,
                "sharpe_ratio": results.sharpe_ratio,
                "max_drawdown": results.max_drawdown,
                "profit_factor": results.profit_factor,
                "final_equity": results.final_equity,
            }

        except Exception as e:
            logger.warning(f"Backtest failed for {strategy.name} on {symbol}: {e}")
            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "error": str(e),
                "trade_count": 0,
            }

    def validate_strategy(
        self,
        strategy: Strategy,
        symbol: str,
        candles: pd.DataFrame,
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
        fundamental_context: Optional[FundamentalContext] = None,
        train_bars: int = 252,  # 1 year
        test_bars: int = 63,    # 3 months
    ) -> dict:
        """
        Run walk-forward validation for a strategy.

        Returns:
            Dict with validation results
        """
        if len(candles) < train_bars + test_bars:
            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "error": "Insufficient data for walk-forward",
                "valid": False,
            }

        try:
            evaluator = self.create_evaluator(
                strategy=strategy,
                spy_data=spy_data,
                vix_data=vix_data,
                fundamental_context=fundamental_context,
            )

            wf_config = WalkForwardConfig(
                train_bars=train_bars,
                test_bars=test_bars,
                step_bars=test_bars,  # Non-overlapping windows
                min_windows=3,
            )

            validator = WalkForwardValidator(
                backtest_config=self.config,
                wf_config=wf_config,
            )

            wf_results = validator.validate(
                evaluator=evaluator,
                candles=candles,
                benchmark_candles=spy_data,
                symbol=symbol,
            )

            score, is_valid, reason = walk_forward_fitness(wf_results)

            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "window_count": wf_results.window_count,
                "avg_sharpe": wf_results.avg_sharpe,
                "sharpe_std": wf_results.sharpe_std,
                "avg_return": wf_results.avg_return,
                "avg_win_rate": wf_results.avg_win_rate,
                "all_profitable": wf_results.all_windows_profitable,
                "fitness_score": score,
                "valid": is_valid,
                "reason": reason,
            }

        except Exception as e:
            logger.warning(f"Validation failed for {strategy.name} on {symbol}: {e}")
            return {
                "symbol": symbol,
                "strategy": strategy.name,
                "error": str(e),
                "valid": False,
            }

    def run_portfolio_backtest(
        self,
        strategy: Strategy,
        symbols: list[str],
        candle_data: dict[str, pd.DataFrame],
        spy_data: pd.DataFrame,
        vix_data: pd.DataFrame,
    ) -> dict:
        """
        Run backtest across multiple symbols (portfolio mode).

        Returns aggregated results.
        """
        results = []
        total_trades = 0
        total_pnl = 0.0

        for symbol in symbols:
            if symbol not in candle_data:
                continue

            result = self.backtest_strategy(
                strategy=strategy,
                symbol=symbol,
                candles=candle_data[symbol],
                spy_data=spy_data,
                vix_data=vix_data,
            )

            if "error" not in result:
                results.append(result)
                total_trades += result["trade_count"]
                # Approximate PnL from return
                total_pnl += self.config.initial_equity * result["total_return"]

        if not results:
            return {
                "strategy": strategy.name,
                "symbols_tested": 0,
                "error": "No valid results",
            }

        avg_sharpe = np.mean([r["sharpe_ratio"] for r in results])
        avg_win_rate = np.mean([r["win_rate"] for r in results if r["trade_count"] > 0])
        avg_return = np.mean([r["total_return"] for r in results])
        avg_drawdown = np.mean([r["max_drawdown"] for r in results])

        return {
            "strategy": strategy.name,
            "symbols_tested": len(results),
            "total_trades": total_trades,
            "avg_sharpe": avg_sharpe,
            "avg_win_rate": avg_win_rate,
            "avg_return": avg_return,
            "avg_drawdown": avg_drawdown,
            "total_pnl": total_pnl,
        }


def list_strategies():
    """List all available strategies."""
    print("\n=== Available Seed Strategies ===\n")

    for i, strategy in enumerate(ALL_STRATEGIES, 1):
        errors = validate_strategy(strategy)
        status = "valid" if not errors else "INVALID"

        print(f"{i:2}. {strategy.name} [{status}]")
        print(f"    Entry: {strategy.entry_long[:70]}...")
        print(f"    Exit:  {strategy.exit_long[:70]}...")
        print()


def run_backtest(args):
    """Run backtest for strategies."""
    cfg = get_config(args.env)
    repository = EquitiesRepository(cfg.database.db_path)
    runner = EvolutionRunner(repository)

    # Check for data
    symbols = repository.get_symbols_with_data()
    if len(symbols) < 5:
        print("\nInsufficient data in database.")
        print("Run 'python main.py download --quick' first.")
        return

    # Load SPY/VIX
    spy_data, vix_data = runner.get_spy_vix_data(years=args.years)
    if spy_data.empty or vix_data.empty:
        print("\nMissing SPY or VIX data.")
        print("Run 'python main.py download --spy-vix-only' first.")
        return

    # Determine strategies to test
    if args.strategy:
        strategies = [s for s in ALL_STRATEGIES if s.name == args.strategy]
        if not strategies:
            print(f"Strategy '{args.strategy}' not found.")
            return
    else:
        strategies = get_default_strategies() if args.quick else ALL_STRATEGIES

    # Determine symbols
    test_symbols = symbols[:20] if args.quick else symbols[:50]

    # Load data
    print(f"\nLoading data for {len(test_symbols)} symbols...")
    candle_data = runner.get_historical_data(test_symbols, years=args.years)
    print(f"Loaded {len(candle_data)} symbols with sufficient data")

    # Run backtests
    print(f"\nRunning backtests for {len(strategies)} strategies...")
    print("-" * 80)

    results = []
    for strategy in strategies:
        result = runner.run_portfolio_backtest(
            strategy=strategy,
            symbols=list(candle_data.keys()),
            candle_data=candle_data,
            spy_data=spy_data,
            vix_data=vix_data,
        )
        results.append(result)

        if "error" not in result:
            print(
                f"{strategy.name:25} | "
                f"Trades: {result['total_trades']:4} | "
                f"Sharpe: {result['avg_sharpe']:+6.2f} | "
                f"Return: {result['avg_return']*100:+6.1f}% | "
                f"DD: {result['avg_drawdown']*100:5.1f}%"
            )
        else:
            print(f"{strategy.name:25} | Error: {result.get('error', 'Unknown')}")

    # Sort by Sharpe
    valid_results = [r for r in results if "error" not in r and r.get("avg_sharpe")]
    valid_results.sort(key=lambda r: r["avg_sharpe"], reverse=True)

    print("\n" + "=" * 80)
    print("Top Strategies by Sharpe Ratio:")
    print("=" * 80)
    for i, r in enumerate(valid_results[:5], 1):
        print(f"{i}. {r['strategy']:25} Sharpe: {r['avg_sharpe']:+.2f}")


def run_validation(args):
    """Run walk-forward validation."""
    cfg = get_config(args.env)
    repository = EquitiesRepository(cfg.database.db_path)
    runner = EvolutionRunner(repository)

    # Check for data
    symbols = repository.get_symbols_with_data()
    if len(symbols) < 5:
        print("\nInsufficient data in database.")
        print("Run 'python main.py download --quick' first.")
        return

    # Load SPY/VIX
    spy_data, vix_data = runner.get_spy_vix_data(years=args.years)

    # Determine strategies
    if args.strategy:
        strategies = [s for s in ALL_STRATEGIES if s.name == args.strategy]
    else:
        strategies = get_default_strategies()

    # Use smaller set for validation
    test_symbols = symbols[:10] if args.quick else symbols[:30]

    # Load data
    print(f"\nLoading data for {len(test_symbols)} symbols...")
    candle_data = runner.get_historical_data(test_symbols, years=args.years)

    # Run validation
    print(f"\nRunning walk-forward validation for {len(strategies)} strategies...")
    print("-" * 80)

    for strategy in strategies:
        print(f"\n{strategy.name}:")

        valid_count = 0
        total_count = 0

        for symbol in list(candle_data.keys())[:5]:  # Limit for speed
            result = runner.validate_strategy(
                strategy=strategy,
                symbol=symbol,
                candles=candle_data[symbol],
                spy_data=spy_data,
                vix_data=vix_data,
                train_bars=126 if args.quick else 252,  # 6 months or 1 year
                test_bars=42 if args.quick else 63,     # 2 months or 3 months
            )

            total_count += 1
            if result.get("valid"):
                valid_count += 1
                print(
                    f"  {symbol}: Sharpe={result['avg_sharpe']:+.2f}, "
                    f"Windows={result['window_count']}, "
                    f"Score={result['fitness_score']:.2f}"
                )
            elif "error" in result:
                print(f"  {symbol}: Error - {result['error']}")
            else:
                print(f"  {symbol}: Invalid - {result.get('reason', 'Unknown')}")

        print(f"  Summary: {valid_count}/{total_count} symbols passed validation")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Strategy Evolution and Validation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "action",
        choices=["list", "backtest", "validate"],
        nargs="?",
        default="list",
        help="Action to perform",
    )
    parser.add_argument(
        "--env",
        choices=["development", "staging", "production"],
        default="development",
        help="Environment",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode with reduced data",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        help="Specific strategy to test",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Years of historical data",
    )

    args = parser.parse_args()

    if args.action == "list":
        list_strategies()
    elif args.action == "backtest":
        run_backtest(args)
    elif args.action == "validate":
        run_validation(args)


if __name__ == "__main__":
    main()
