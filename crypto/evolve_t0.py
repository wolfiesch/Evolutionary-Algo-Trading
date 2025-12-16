"""
T0 Quick Fixes Evolution Script

Tests whether ProFiT-style methodology can improve results:
1. 4-hour candles (instead of 1-minute) for more stable Sharpe
2. Seed strategies from proven patterns (not from scratch)
3. Walk-forward validation during evolution

Usage:
    python crypto/evolve_t0.py --symbol=BTCUSDT --generations=10
    python crypto/evolve_t0.py --symbol=ETHUSDT --generations=10 --seed=rsi_bounce
    python crypto/evolve_t0.py --symbol=SOLUSDT --generations=10 --seed=bollinger_mean_reversion

Expected outcome: If T0 approach works, we should see:
- Positive Sharpe ratios (> 0.0)
- More stable fitness scores across generations
- Walk-forward validation showing out-of-sample profitability
"""
import argparse
import json
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
from crypto.evolve import (
    get_market_filter_name,
    create_evaluator,
)

from shared.evolution.backtester import (
    MinimalBacktester,
    BacktestConfig,
    WalkForwardValidator,
    WalkForwardConfig,
    walk_forward_fitness,
    # T0 Fix: Multi-timeframe support
    Timeframe,
    aggregate_candles,
    get_timeframe_config,
)
from shared.evolution.fitness import (
    calculate_fitness,
    FitnessResult,
)
from shared.evolution.mutator import (
    create_default_client,
    StrategyGenerator,
    GeneratedStrategy,
    generate_initial_population,
    EvolutionConfig,
    EvolutionEngine,
    CrossoverOperator,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Directory for seed strategies
SEED_DIR = Path(__file__).parent / "seed_strategies"

# Available seed strategies
SEED_STRATEGIES = {
    "bollinger_mean_reversion": SEED_DIR / "bollinger_mean_reversion.json",
    "trend_following_ema": SEED_DIR / "trend_following_ema.json",
    "rsi_bounce": SEED_DIR / "rsi_bounce.json",
}


def load_seed_strategy(name: str) -> GeneratedStrategy:
    """Load a seed strategy from JSON file."""
    if name not in SEED_STRATEGIES:
        raise ValueError(f"Unknown seed strategy: {name}. Available: {list(SEED_STRATEGIES.keys())}")

    path = SEED_STRATEGIES[name]
    with open(path) as f:
        data = json.load(f)

    return GeneratedStrategy(
        name=f"Seed_{data['strategy_name']}",
        entry_long=data["entry_long"],
        exit_long=data["exit_long"],
        rationale=data.get("rationale", "Seed strategy"),
    )


def candles_to_df(candles):
    """Convert candle objects to DataFrame."""
    return pd.DataFrame([{
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
        'timestamp': c.timestamp,
    } for c in candles])


def run_t0_evolution(
    symbol: str,
    generations: int = 10,
    population_size: int = 8,
    seed_name: str = None,
    timeframe: Timeframe = Timeframe.H4,
    use_walkforward: bool = True,
    db_path: Path = None,
    recent_days: int = None,
):
    """
    Run T0 evolution with 4H candles, seed strategies, and walk-forward.

    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        generations: Number of generations to run
        population_size: Population size
        seed_name: Name of seed strategy to use (optional)
        timeframe: Target timeframe for aggregation (default: 4H)
        use_walkforward: Whether to use walk-forward validation
        db_path: Path to SQLite database
        recent_days: Limit data to most recent N days (T2 Approach 1)
    """
    if db_path is None:
        db_path = settings.sqlite_path
        if not db_path.exists():
            cloud_db = Path(__file__).parent / "data" / "candles_cloud.db"
            if cloud_db.exists():
                db_path = cloud_db

    logger.info("=" * 60)
    logger.info("T0/T2 EVOLUTION TEST: ProFiT-Style Methodology")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe.name} ({timeframe.value} minutes)")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population: {population_size}")
    logger.info(f"Seed strategy: {seed_name or 'None'}")
    logger.info(f"Walk-forward: {'ENABLED' if use_walkforward else 'DISABLED'}")
    logger.info(f"Recent days limit: {recent_days or 'None (use all data)'}")
    logger.info(f"Database: {db_path}")
    logger.info("=" * 60)

    # Get timeframe config
    tf_config = get_timeframe_config(timeframe)
    logger.info(f"\nTimeframe config:")
    logger.info(f"  Bars per year: {tf_config.bars_per_year}")
    logger.info(f"  Warmup bars: {tf_config.warmup_bars}")
    logger.info(f"  WF train/test/step: {tf_config.walk_forward_train}/{tf_config.walk_forward_test}/{tf_config.walk_forward_step}")

    # Load raw 1-minute candles
    logger.info("\nLoading candle data...")
    repo = CandleRepository(db_path)

    # Need enough 1-min candles to aggregate to 4H
    # For 1 year of 4H data (2190 bars), we need 2190 * 240 = 525,600 1-min bars
    required_1min_bars = 2190 * timeframe.value  # 1 year at target timeframe

    btc_candles_raw = repo.get_latest("BTCUSDT", limit=required_1min_bars)
    symbol_candles_raw = repo.get_latest(symbol, limit=required_1min_bars)

    if len(btc_candles_raw) < 1000:
        logger.error(f"Insufficient BTC data: {len(btc_candles_raw)} candles")
        return None

    if len(symbol_candles_raw) < 1000:
        logger.error(f"Insufficient {symbol} data: {len(symbol_candles_raw)} candles")
        return None

    logger.info(f"  Raw 1-min candles: BTC={len(btc_candles_raw)}, {symbol}={len(symbol_candles_raw)}")

    # Convert to DataFrames
    btc_df_1min = candles_to_df(btc_candles_raw)
    symbol_df_1min = candles_to_df(symbol_candles_raw)

    # Aggregate to 4H timeframe
    logger.info(f"\nAggregating to {timeframe.name}...")
    btc_df = aggregate_candles(btc_df_1min, timeframe, Timeframe.M1)
    symbol_df = aggregate_candles(symbol_df_1min, timeframe, Timeframe.M1)

    logger.info(f"  Aggregated candles: BTC={len(btc_df)}, {symbol}={len(symbol_df)}")

    # T2 Approach 1: Limit to recent data if specified
    if recent_days:
        bars_per_day = 24 * 60 // timeframe.value  # e.g., 6 bars per day at 4H
        max_bars = recent_days * bars_per_day

        if len(symbol_df) > max_bars:
            symbol_df = symbol_df.tail(max_bars).reset_index(drop=True)
            logger.info(f"  Limited {symbol} to recent {recent_days} days: {len(symbol_df)} bars")

        if len(btc_df) > max_bars:
            btc_df = btc_df.tail(max_bars).reset_index(drop=True)
            logger.info(f"  Limited BTC to recent {recent_days} days: {len(btc_df)} bars")

    # Calculate date range
    if len(symbol_df) > 0:
        start_ts = symbol_df['timestamp'].iloc[0]
        end_ts = symbol_df['timestamp'].iloc[-1]
        start_date = datetime.utcfromtimestamp(start_ts / 1000)
        end_date = datetime.utcfromtimestamp(end_ts / 1000)
        logger.info(f"  Date range: {start_date.date()} to {end_date.date()} ({(end_date - start_date).days} days)")

    # Initialize backtester with 4H timeframe
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,  # 0.25% Bybit taker + slippage
        max_position_pct=0.10,
        stop_loss_pct=0.03,
        timeframe_minutes=timeframe.value,  # T0 Fix: Use 4H for Sharpe annualization
    )

    backtester = MinimalBacktester(backtest_config)
    parser = GeneExpressionParser()

    # Initialize walk-forward validator with 4H-appropriate settings
    wf_validator = None
    if use_walkforward:
        wf_config = WalkForwardConfig(
            train_bars=tf_config.walk_forward_train,  # 30 days at 4H
            test_bars=tf_config.walk_forward_test,    # 7 days at 4H
            step_bars=tf_config.walk_forward_step,    # 7 days step
            min_windows=5,  # Need at least 5 test windows
        )
        wf_validator = WalkForwardValidator(backtest_config, wf_config)
        logger.info(f"\nWalk-forward config (4H bars):")
        logger.info(f"  Train: {wf_config.train_bars} bars (~{wf_config.train_bars * 4 / 24:.0f} days)")
        logger.info(f"  Test: {wf_config.test_bars} bars (~{wf_config.test_bars * 4 / 24:.0f} days)")
        logger.info(f"  Step: {wf_config.step_bars} bars (~{wf_config.step_bars * 4 / 24:.0f} days)")

        # Check if we have enough data for walk-forward
        min_bars_needed = wf_config.train_bars + (wf_config.test_bars * wf_config.min_windows)
        if len(symbol_df) < min_bars_needed:
            logger.warning(f"Insufficient data for {wf_config.min_windows} walk-forward windows")
            logger.warning(f"  Need: {min_bars_needed} bars, Have: {len(symbol_df)} bars")
            logger.warning("  Continuing with fewer windows or disabling walk-forward...")

    # Initialize LLM
    logger.info("\nInitializing LLM client...")
    try:
        llm_client = create_default_client(log_dir=settings.logs_dir)
        logger.info(f"Using LLM provider: {llm_client.config.provider.value}")
    except ValueError as e:
        logger.error(f"LLM initialization failed: {e}")
        return None

    # Initialize generator with appropriate market filter
    market_filter = get_market_filter_name(symbol)
    logger.info(f"Using market filter: {market_filter}")

    generator = StrategyGenerator(
        llm_client=llm_client,
        market_filter_name=market_filter,
    )
    crossover = CrossoverOperator(
        llm_client=llm_client,
        market_filter_name=market_filter,
    )

    # Create evaluation function
    def eval_strategy(generated: GeneratedStrategy) -> tuple[FitnessResult, dict]:
        try:
            strategy = parser.parse(generated.to_dict())
            evaluator = create_evaluator(strategy, parser)

            if use_walkforward and wf_validator:
                # Walk-forward validation mode
                wf_results = wf_validator.validate(
                    evaluator=evaluator,
                    candles=symbol_df,
                    benchmark_candles=btc_df,
                    symbol=symbol,
                )
                # Lower threshold for 4H timeframe (larger windows = more variance)
                min_sharpe = 0.2 if timeframe.value >= 240 else 0.3
                score, is_valid, reason = walk_forward_fitness(wf_results, min_avg_sharpe=min_sharpe)
                fitness = FitnessResult(
                    sharpe_ratio=wf_results.avg_sharpe,
                    trade_count=wf_results.aggregated.trade_count if wf_results.aggregated else 0,
                    win_rate=wf_results.avg_win_rate,
                    total_return=wf_results.avg_return,
                    max_drawdown=wf_results.aggregated.max_drawdown if wf_results.aggregated else 0,
                )
                if not is_valid:
                    fitness.disqualified = True
                    fitness.disqualification_reason = reason
                    fitness.final_score = 0.0
                else:
                    fitness.final_score = score
                return fitness, wf_results.summary()
            else:
                # Standard backtester mode
                results = backtester.run(
                    evaluator=evaluator,
                    candles=symbol_df,
                    benchmark_candles=btc_df,
                    symbol=symbol,
                )
                fitness = calculate_fitness(results)
                return fitness, results.summary()
        except Exception as e:
            logger.error(f"Evaluation error for {generated.name}: {e}")
            return FitnessResult(
                disqualified=True,
                disqualification_reason=f"Evaluation error: {str(e)}"
            ), {}

    # Load seed strategy if specified
    seed_strategy = None
    if seed_name:
        try:
            seed_strategy = load_seed_strategy(seed_name)
            logger.info(f"\nLoaded seed strategy: {seed_strategy.name}")
            logger.info(f"  Entry: {seed_strategy.entry_long}")
            logger.info(f"  Exit: {seed_strategy.exit_long}")

            # Quick test of seed strategy
            logger.info("\nTesting seed strategy...")
            seed_fitness, seed_summary = eval_strategy(seed_strategy)
            if seed_fitness.disqualified:
                logger.warning(f"  Seed strategy DISQUALIFIED: {seed_fitness.disqualification_reason}")
            else:
                logger.info(f"  Seed Sharpe: {seed_fitness.sharpe_ratio:.2f}")
                logger.info(f"  Seed Trades: {seed_fitness.trade_count}")
                logger.info(f"  Seed Win Rate: {seed_fitness.win_rate:.1%}")
                logger.info(f"  Seed Max DD: {seed_fitness.max_drawdown:.1%}")
        except Exception as e:
            logger.warning(f"Failed to load seed strategy '{seed_name}': {e}")

    # Configure evolution
    config = EvolutionConfig(
        population_size=population_size,
        generations=generations,
        elite_count=2,
        mutation_rate=0.7,
        crossover_rate=0.3,
        tournament_size=3,
        max_stagnation=5,
        checkpoint_interval=3,
        checkpoint_dir=str(settings.logs_dir / "checkpoints" / "t0"),
    )

    # Create engine
    engine = EvolutionEngine(
        config=config,
        generator=generator,
        crossover=crossover,
        evaluator=eval_strategy,
    )

    # Generate initial population
    logger.info(f"\nGenerating initial population...")
    gen_size = population_size - 1 if seed_strategy else population_size
    initial_pop = generate_initial_population(generator, size=gen_size)

    if seed_strategy:
        initial_pop.insert(0, seed_strategy)
        logger.info(f"  Added seed strategy to population (total: {len(initial_pop)})")

    if not initial_pop:
        logger.error("Failed to generate initial population")
        return None

    # Run evolution
    logger.info(f"\n{'=' * 60}")
    logger.info("Starting Evolution")
    logger.info("=" * 60)

    result = engine.run(initial_population=initial_pop)

    # Results
    logger.info(f"\n{'=' * 60}")
    logger.info("T0 EVOLUTION COMPLETE")
    logger.info("=" * 60)

    logger.info(f"\nGenerations run: {result.generations_run}")
    logger.info(f"Early stopped: {result.early_stopped}")

    if result.best_strategy and result.best_fitness:
        logger.info(f"\nBest Strategy: {result.best_strategy.name}")
        logger.info(f"  Entry: {result.best_strategy.entry_long}")
        logger.info(f"  Exit: {result.best_strategy.exit_long}")
        logger.info(f"\nPerformance (4H timeframe):")
        logger.info(f"  Final Score: {result.best_fitness.final_score:.3f}")
        logger.info(f"  Sharpe Ratio: {result.best_fitness.sharpe_ratio:.2f}")
        logger.info(f"  Max Drawdown: {result.best_fitness.max_drawdown:.1%}")
        logger.info(f"  Win Rate: {result.best_fitness.win_rate:.1%}")
        logger.info(f"  Trades: {result.best_fitness.trade_count}")

        # T0 Success criteria (timeframe-aware trade count)
        logger.info(f"\n{'=' * 60}")
        logger.info("T0 SUCCESS CRITERIA CHECK")
        logger.info("=" * 60)

        # Trade count threshold: 4H trades less frequently than 1min
        min_trades = 7 if timeframe.value >= 240 else 10

        sharpe_ok = result.best_fitness.sharpe_ratio > 0.0
        trades_ok = result.best_fitness.trade_count >= min_trades
        dd_ok = result.best_fitness.max_drawdown < 0.30

        logger.info(f"  Positive Sharpe (> 0.0): {'PASS' if sharpe_ok else 'FAIL'} ({result.best_fitness.sharpe_ratio:.2f})")
        logger.info(f"  Sufficient trades (>= {min_trades}): {'PASS' if trades_ok else 'FAIL'} ({result.best_fitness.trade_count})")
        logger.info(f"  Acceptable DD (< 30%): {'PASS' if dd_ok else 'FAIL'} ({result.best_fitness.max_drawdown:.1%})")

        if sharpe_ok and trades_ok and dd_ok:
            logger.info("\n  >>> T0 APPROACH SHOWS PROMISE - Continue refining <<<")
        else:
            logger.info("\n  >>> T0 APPROACH NEEDS WORK - Consider pivoting to Option B <<<")
    else:
        logger.warning("\nNo viable strategy found")
        logger.info("\n  >>> T0 APPROACH FAILED - Consider pivoting to Option B <<<")

    # Show fitness progression
    if result.fitness_history:
        logger.info("\nFitness Progression:")
        for entry in result.fitness_history:
            logger.info(f"  Gen {entry['generation']}: Best={entry['best_score']:.3f}, "
                       f"Avg={entry['avg_score']:.3f}, Diversity={entry['diversity']:.2f}")

    logger.info(f"\nCompleted at: {datetime.now().strftime('%m/%d/%Y %I:%M %p PST')}")

    return result


def main():
    parser = argparse.ArgumentParser(
        description="T0 Evolution Test: ProFiT-Style Methodology (4H candles, seed strategies, walk-forward)"
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Trading symbol (default: BTCUSDT)"
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=10,
        help="Number of generations (default: 10)"
    )
    parser.add_argument(
        "--population",
        type=int,
        default=8,
        help="Population size (default: 8)"
    )
    parser.add_argument(
        "--seed",
        type=str,
        choices=list(SEED_STRATEGIES.keys()),
        default=None,
        help=f"Seed strategy to use: {list(SEED_STRATEGIES.keys())}"
    )
    parser.add_argument(
        "--timeframe",
        type=str,
        choices=["H1", "H4", "D1"],
        default="H4",
        help="Target timeframe (default: H4)"
    )
    parser.add_argument(
        "--no-walkforward",
        action="store_true",
        help="Disable walk-forward validation"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database"
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=None,
        help="Limit data to most recent N days (T2 Approach 1)"
    )

    args = parser.parse_args()

    timeframe_map = {
        "H1": Timeframe.H1,
        "H4": Timeframe.H4,
        "D1": Timeframe.D1,
    }

    run_t0_evolution(
        symbol=args.symbol,
        generations=args.generations,
        population_size=args.population,
        seed_name=args.seed,
        timeframe=timeframe_map[args.timeframe],
        use_walkforward=not args.no_walkforward,
        db_path=Path(args.db) if args.db else None,
        recent_days=args.recent_days,
    )


if __name__ == "__main__":
    main()
