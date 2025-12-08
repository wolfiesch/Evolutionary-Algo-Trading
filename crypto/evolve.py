"""
Phase 2A: Minimal Evolution Loop

Entry point for LLM-driven strategy evolution.

Usage:
    python evolve.py --generations=3 --symbol=SOLUSDT
    python evolve.py --generations=5 --symbol=ETHUSDT --population=5

Requirements:
    - OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable
    - Historical candle data in SQLite database
"""
import argparse
import logging
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crypto.config import settings
from crypto.data.storage.repository import CandleRepository
from crypto.engine.strategy_logic.parser import GeneExpressionParser, Strategy, Signal

from shared.evolution.backtester import MinimalBacktester, BacktestConfig
from shared.evolution.fitness import calculate_fitness, FitnessResult
from shared.evolution.mutator import (
    create_default_client,
    StrategyGenerator,
    GeneratedStrategy,
    generate_initial_population,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def create_evaluator(strategy: Strategy, parser: GeneExpressionParser):
    """
    Create an evaluator function for the backtester.

    This bridges the crypto-specific parser with the asset-agnostic backtester.

    Args:
        strategy: Parsed Strategy object
        parser: GeneExpressionParser instance

    Returns:
        Function that takes (candles_df, benchmark_df, has_position) -> signal_str
    """
    def evaluator(candles: pd.DataFrame, benchmark_candles: pd.DataFrame, has_position: bool) -> str:
        try:
            signal = parser.get_signal(strategy, candles, benchmark_candles, has_position)
            return signal.value  # "ENTRY_LONG", "EXIT_LONG", or "HOLD"
        except Exception as e:
            logger.debug(f"Evaluator error: {e}")
            return "HOLD"

    return evaluator


def evaluate_strategy(
    generated: GeneratedStrategy,
    candles: pd.DataFrame,
    benchmark_candles: pd.DataFrame,
    backtester: MinimalBacktester,
    parser: GeneExpressionParser,
    symbol: str,
) -> tuple[FitnessResult, dict]:
    """
    Evaluate a generated strategy via backtest.

    Args:
        generated: GeneratedStrategy from LLM
        candles: OHLCV DataFrame for trading symbol
        benchmark_candles: OHLCV DataFrame for benchmark (BTC)
        backtester: MinimalBacktester instance
        parser: GeneExpressionParser instance
        symbol: Symbol name

    Returns:
        (FitnessResult, backtest_summary_dict)
    """
    try:
        # Parse strategy
        strategy = parser.parse(generated.to_dict())

        # Create evaluator
        evaluator = create_evaluator(strategy, parser)

        # Run backtest
        results = backtester.run(
            evaluator=evaluator,
            candles=candles,
            benchmark_candles=benchmark_candles,
            symbol=symbol,
        )

        # Calculate fitness
        fitness = calculate_fitness(results)

        return fitness, results.summary()

    except Exception as e:
        logger.error(f"Failed to evaluate {generated.name}: {e}")
        # Return disqualified fitness
        return FitnessResult(
            disqualified=True,
            disqualification_reason=f"Evaluation error: {str(e)}"
        ), {}


def run_evolution(
    symbol: str,
    generations: int = 3,
    population_size: int = 3,
    db_path: Path = None,
    log_dir: Path = None,
):
    """
    Run the evolution loop.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        generations: Number of evolution generations
        population_size: Number of strategies per generation
        db_path: Path to SQLite database (default: settings.sqlite_path)
        log_dir: Directory for logs (default: settings.logs_dir)
    """
    if db_path is None:
        # Try cloud database first, fall back to local
        cloud_db = Path(__file__).parent / "data" / "candles_cloud.db"
        db_path = cloud_db if cloud_db.exists() else settings.sqlite_path

    if log_dir is None:
        log_dir = settings.logs_dir

    logger.info("=" * 60)
    logger.info("PHASE 2A: MINIMAL EVOLUTION LOOP")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population size: {population_size}")
    logger.info(f"Database: {db_path}")
    logger.info("=" * 60)

    # Initialize components
    logger.info("Initializing components...")

    # Repository
    repo = CandleRepository(db_path)

    # Load candle data
    logger.info(f"Loading candles for {symbol}...")
    symbol_candles = repo.get_latest(symbol, limit=5000)
    if len(symbol_candles) < 80:
        # [*TO-DO*] - Increase to 200+ when more data is available
        logger.error(f"Insufficient data for {symbol}: {len(symbol_candles)} candles (need 80+)")
        return

    logger.info(f"Loading benchmark candles (BTCUSDT)...")
    btc_candles = repo.get_latest("BTCUSDT", limit=5000)
    if len(btc_candles) < 80:
        # [*TO-DO*] - Increase to 200+ when more data is available
        logger.error(f"Insufficient BTC data: {len(btc_candles)} candles (need 80+)")
        return

    # Convert to DataFrames
    def candles_to_df(candles):
        return pd.DataFrame([{
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume,
            'timestamp': c.timestamp,
        } for c in candles])

    symbol_df = candles_to_df(symbol_candles)
    btc_df = candles_to_df(btc_candles)

    logger.info(f"Loaded {len(symbol_df)} {symbol} candles, {len(btc_df)} BTC candles")

    # Initialize backtester (crypto-specific config)
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,  # 0.25% Bybit taker fee + slippage
        max_position_pct=0.10,
        stop_loss_pct=0.03,
    )
    backtester = MinimalBacktester(backtest_config)

    # Initialize parser
    parser = GeneExpressionParser()

    # Initialize LLM
    logger.info("Initializing LLM client...")
    try:
        llm_client = create_default_client(log_dir=log_dir)
        logger.info(f"Using LLM provider: {llm_client.config.provider.value}")
    except ValueError as e:
        logger.error(f"LLM initialization failed: {e}")
        return

    # Initialize generator
    generator = StrategyGenerator(
        llm_client=llm_client,
        market_filter_name="btc_trend",
    )

    # Generate initial population
    logger.info(f"\n{'=' * 60}")
    logger.info("GENERATION 0: Creating initial population")
    logger.info("=" * 60)

    population: list[tuple[GeneratedStrategy, FitnessResult]] = []

    strategies = generate_initial_population(generator, size=population_size)
    if not strategies:
        logger.error("Failed to generate any initial strategies")
        return

    # Evaluate initial population
    for strat in strategies:
        logger.info(f"\nEvaluating: {strat.name}")
        logger.info(f"  Entry: {strat.entry_long}")
        logger.info(f"  Exit: {strat.exit_long}")

        fitness, summary = evaluate_strategy(
            strat, symbol_df, btc_df, backtester, parser, symbol
        )

        population.append((strat, fitness))

        if fitness.disqualified:
            logger.info(f"  Result: DISQUALIFIED - {fitness.disqualification_reason}")
        else:
            logger.info(f"  Result: Score={fitness.final_score:.3f}, "
                       f"Sharpe={fitness.sharpe_ratio:.2f}, "
                       f"DD={fitness.max_drawdown:.1%}, "
                       f"Trades={fitness.trade_count}")

    # Sort by fitness
    population.sort(key=lambda x: x[1].final_score, reverse=True)

    # Evolution loop
    for gen in range(1, generations + 1):
        logger.info(f"\n{'=' * 60}")
        logger.info(f"GENERATION {gen}")
        logger.info("=" * 60)

        # Get best strategy from previous generation
        best_strat, best_fitness = population[0]
        logger.info(f"Best from Gen {gen-1}: {best_strat.name} (Score: {best_fitness.final_score:.3f})")

        new_population: list[tuple[GeneratedStrategy, FitnessResult]] = []

        # Keep elite (best strategy unchanged)
        new_population.append((best_strat, best_fitness))

        # Generate mutations of the best
        for i in range(population_size - 1):
            logger.info(f"\nMutating {best_strat.name}...")

            mutated = generator.mutate(
                strategy=best_strat,
                sharpe=best_fitness.sharpe_ratio,
                win_rate=best_fitness.win_rate,
                max_dd=best_fitness.max_drawdown,
                trade_count=best_fitness.trade_count,
            )

            if mutated:
                logger.info(f"  Created: {mutated.name}")
                logger.info(f"  Mutation: {mutated.mutation_description}")
                logger.info(f"  Entry: {mutated.entry_long}")
                logger.info(f"  Exit: {mutated.exit_long}")

                fitness, summary = evaluate_strategy(
                    mutated, symbol_df, btc_df, backtester, parser, symbol
                )

                new_population.append((mutated, fitness))

                if fitness.disqualified:
                    logger.info(f"  Result: DISQUALIFIED - {fitness.disqualification_reason}")
                else:
                    logger.info(f"  Result: Score={fitness.final_score:.3f}, "
                               f"Sharpe={fitness.sharpe_ratio:.2f}, "
                               f"DD={fitness.max_drawdown:.1%}")
            else:
                logger.warning(f"  Mutation failed, generating new strategy...")
                new_strat = generator.generate()
                if new_strat:
                    fitness, _ = evaluate_strategy(
                        new_strat, symbol_df, btc_df, backtester, parser, symbol
                    )
                    new_population.append((new_strat, fitness))

        # Sort by fitness
        population = sorted(new_population, key=lambda x: x[1].final_score, reverse=True)

    # Final results
    logger.info(f"\n{'=' * 60}")
    logger.info("EVOLUTION COMPLETE")
    logger.info("=" * 60)

    logger.info("\nFinal Population (sorted by fitness):")
    for i, (strat, fitness) in enumerate(population):
        status = "DISQUALIFIED" if fitness.disqualified else f"Score={fitness.final_score:.3f}"
        logger.info(f"  {i+1}. {strat.name}: {status}")
        if not fitness.disqualified:
            logger.info(f"      Sharpe={fitness.sharpe_ratio:.2f}, "
                       f"DD={fitness.max_drawdown:.1%}, "
                       f"WinRate={fitness.win_rate:.1%}, "
                       f"Trades={fitness.trade_count}")

    # Best strategy
    best_strat, best_fitness = population[0]
    if not best_fitness.disqualified:
        logger.info(f"\nBest Strategy: {best_strat.name}")
        logger.info(f"  Entry: {best_strat.entry_long}")
        logger.info(f"  Exit: {best_strat.exit_long}")
        logger.info(f"  Final Score: {best_fitness.final_score:.3f}")
    else:
        logger.warning("\nNo viable strategy found in final population")

    logger.info(f"\nCompleted at: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}")


def main():
    parser = argparse.ArgumentParser(
        description="Phase 2A: Minimal Evolution Loop"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="SOLUSDT",
        help="Trading symbol (default: SOLUSDT)"
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=3,
        help="Number of evolution generations (default: 3)"
    )
    parser.add_argument(
        "--population",
        type=int,
        default=3,
        help="Population size (default: 3)"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: auto-detect)"
    )

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None

    run_evolution(
        symbol=args.symbol,
        generations=args.generations,
        population_size=args.population,
        db_path=db_path,
    )


if __name__ == "__main__":
    main()
