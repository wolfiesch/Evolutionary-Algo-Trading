"""
Phase 2D: Full Evolution Engine with Selection, Crossover & Checkpointing

Entry point for LLM-driven strategy evolution.

Usage:
    python evolve.py --generations=3 --symbol=SOLUSDT
    python evolve.py --generations=5 --symbol=ETHUSDT --population=5
    python evolve.py --generations=5 --symbol=SOLUSDT --regime       # Enable regime testing
    python evolve.py --generations=3 --portfolio                      # Multi-symbol portfolio
    python evolve.py --generations=3 --symbol=SOLUSDT --walkforward  # Walk-forward validation
    python evolve.py --generations=10 --full                          # Phase 2D full evolution engine

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

from shared.evolution.backtester import (
    MinimalBacktester,
    BacktestConfig,
    PortfolioBacktester,
    WalkForwardValidator,
    WalkForwardConfig,
    walk_forward_fitness,
)
from shared.evolution.fitness import (
    calculate_fitness,
    calculate_fitness_with_regimes,
    aggregate_regime_results,
    FitnessResult,
    split_by_regime,
    REGIME_NAMES,
)
from shared.evolution.mutator import (
    create_default_client,
    StrategyGenerator,
    GeneratedStrategy,
    generate_initial_population,
    MEAN_REVERSION_THEMES,
    # Phase 2D components
    EvolutionConfig,
    EvolutionEngine,
    CrossoverOperator,
)

# Configure logging with unbuffered handlers for real-time visibility
class FlushingStreamHandler(logging.StreamHandler):
    """StreamHandler that flushes after every write."""
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        FlushingStreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def get_market_filter_name(symbol: str) -> str:
    """
    Get the appropriate market filter primitive name for a trading symbol.

    Uses self-referential filters (asset_trend) which check the trading asset's
    own trend rather than cross-asset correlation (btc_trend) which often fails.

    Args:
        symbol: Trading pair (e.g., "BTCUSDT", "SOLUSDT", "ETHUSDT")

    Returns:
        Market filter primitive name to use in strategy generation
    """
    # Use asset_trend for all symbols - self-referential is more reliable
    # than cross-asset correlation
    return "asset_trend"


def create_evaluator(strategy: Strategy, parser: GeneExpressionParser):
    """
    Create an evaluator function for the single-symbol backtester.

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


def create_portfolio_evaluator(strategy: Strategy, parser: GeneExpressionParser):
    """
    Create an evaluator function for the portfolio backtester.

    Args:
        strategy: Parsed Strategy object
        parser: GeneExpressionParser instance

    Returns:
        Function that takes (symbol, candles_df, benchmark_df, has_position) -> signal_str
    """
    def evaluator(symbol: str, candles: pd.DataFrame, benchmark_candles: pd.DataFrame, has_position: bool) -> str:
        try:
            signal = parser.get_signal(strategy, candles, benchmark_candles, has_position)
            return signal.value
        except Exception as e:
            logger.debug(f"Portfolio evaluator error for {symbol}: {e}")
            return "HOLD"

    return evaluator


def evaluate_strategy(
    generated: GeneratedStrategy,
    candles: pd.DataFrame,
    benchmark_candles: pd.DataFrame,
    backtester: MinimalBacktester,
    parser: GeneExpressionParser,
    symbol: str,
    use_regime_testing: bool = False,
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
        use_regime_testing: If True, use Phase 2B regime-aware fitness

    Returns:
        (FitnessResult, backtest_summary_dict)
    """
    try:
        # Parse strategy
        strategy = parser.parse(generated.to_dict())

        # Create evaluator
        evaluator = create_evaluator(strategy, parser)

        if use_regime_testing:
            # Phase 2B: Run backtest by regime
            regime_results = backtester.run_by_regime(
                evaluator=evaluator,
                candles=candles,
                benchmark_candles=benchmark_candles,
                symbol=symbol,
            )

            # Aggregate results and calculate regime-aware fitness
            overall_results = aggregate_regime_results(regime_results)
            fitness = calculate_fitness_with_regimes(overall_results, regime_results)

            return fitness, overall_results.summary()
        else:
            # Phase 2A: Simple backtest
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


def evaluate_strategy_portfolio(
    generated: GeneratedStrategy,
    candles_dict: dict[str, pd.DataFrame],
    benchmark_candles: pd.DataFrame,
    backtester: PortfolioBacktester,
    parser: GeneExpressionParser,
) -> tuple[FitnessResult, dict]:
    """
    Evaluate a strategy on a portfolio of symbols (Phase 2C).

    Args:
        generated: GeneratedStrategy from LLM
        candles_dict: Dict of symbol -> OHLCV DataFrame
        benchmark_candles: OHLCV DataFrame for benchmark (BTC)
        backtester: PortfolioBacktester instance
        parser: GeneExpressionParser instance

    Returns:
        (FitnessResult, portfolio_summary_dict)
    """
    try:
        # Parse strategy
        strategy = parser.parse(generated.to_dict())

        # Create portfolio evaluator
        evaluator = create_portfolio_evaluator(strategy, parser)

        # Run portfolio backtest
        results = backtester.run(
            evaluator=evaluator,
            candles=candles_dict,
            benchmark_candles=benchmark_candles,
        )

        # Calculate fitness from portfolio results
        fitness = FitnessResult(
            sharpe_ratio=results.sharpe_ratio,
            max_drawdown=results.max_drawdown,
            trade_count=results.trade_count,
            win_rate=results.win_rate,
            profit_factor=results.profit_factor,
            total_return=results.total_return,
        )

        # Apply disqualification rules
        if results.trade_count < 3:
            fitness.disqualified = True
            fitness.disqualification_reason = f"Insufficient trades: {results.trade_count} < 3"
            fitness.final_score = 0.0
        elif results.max_drawdown > 0.25:
            fitness.disqualified = True
            fitness.disqualification_reason = f"Max drawdown too high: {results.max_drawdown:.1%}"
            fitness.final_score = 0.0
        elif results.win_rate < 0.15:
            fitness.disqualified = True
            fitness.disqualification_reason = f"Win rate too low: {results.win_rate:.1%}"
            fitness.final_score = 0.0
        else:
            # Calculate drawdown multiplier
            from shared.evolution.fitness import drawdown_penalty
            fitness.drawdown_multiplier = drawdown_penalty(results.max_drawdown)
            base_sharpe = max(0.0, results.sharpe_ratio)
            fitness.final_score = base_sharpe * fitness.drawdown_multiplier

        return fitness, results.summary()

    except Exception as e:
        logger.error(f"Failed to evaluate portfolio {generated.name}: {e}")
        return FitnessResult(
            disqualified=True,
            disqualification_reason=f"Portfolio evaluation error: {str(e)}"
        ), {}


def evaluate_strategy_walkforward(
    generated: GeneratedStrategy,
    candles: pd.DataFrame,
    benchmark_candles: pd.DataFrame,
    validator: WalkForwardValidator,
    parser: GeneExpressionParser,
    symbol: str,
) -> tuple[FitnessResult, dict]:
    """
    Evaluate a strategy using walk-forward validation (Phase 2C).

    Args:
        generated: GeneratedStrategy from LLM
        candles: OHLCV DataFrame for trading symbol
        benchmark_candles: OHLCV DataFrame for benchmark (BTC)
        validator: WalkForwardValidator instance
        parser: GeneExpressionParser instance
        symbol: Symbol name

    Returns:
        (FitnessResult, walkforward_summary_dict)
    """
    try:
        # Parse strategy
        strategy = parser.parse(generated.to_dict())

        # Create evaluator
        evaluator = create_evaluator(strategy, parser)

        # Run walk-forward validation
        wf_results = validator.validate(
            evaluator=evaluator,
            candles=candles,
            benchmark_candles=benchmark_candles,
            symbol=symbol,
        )

        # Calculate fitness from walk-forward results
        score, is_valid, reason = walk_forward_fitness(wf_results)

        fitness = FitnessResult(
            sharpe_ratio=wf_results.avg_sharpe,
            trade_count=wf_results.aggregated.trade_count if wf_results.aggregated else 0,
            win_rate=wf_results.avg_win_rate,
            total_return=wf_results.avg_return,
        )

        if not is_valid:
            fitness.disqualified = True
            fitness.disqualification_reason = reason
            fitness.final_score = 0.0
        else:
            fitness.final_score = score

        return fitness, wf_results.summary()

    except Exception as e:
        logger.error(f"Failed to evaluate walk-forward {generated.name}: {e}")
        return FitnessResult(
            disqualified=True,
            disqualification_reason=f"Walk-forward evaluation error: {str(e)}"
        ), {}


def run_evolution(
    symbol: str,
    generations: int = 3,
    population_size: int = 3,
    db_path: Path = None,
    log_dir: Path = None,
    use_regime_testing: bool = False,
    use_portfolio: bool = False,
    use_walkforward: bool = False,
    portfolio_symbols: list[str] = None,
):
    """
    Run the evolution loop.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        generations: Number of evolution generations
        population_size: Number of strategies per generation
        db_path: Path to SQLite database (default: settings.sqlite_path)
        log_dir: Directory for logs (default: settings.logs_dir)
        use_regime_testing: If True, use Phase 2B regime-aware fitness
        use_portfolio: If True, use Phase 2C multi-symbol portfolio testing
        use_walkforward: If True, use Phase 2C walk-forward validation
        portfolio_symbols: List of symbols for portfolio mode (default: SOLUSDT, ETHUSDT)
    """
    if db_path is None:
        # Use main database (settings.sqlite_path), fall back to cloud DB
        db_path = settings.sqlite_path
        if not db_path.exists():
            cloud_db = Path(__file__).parent / "data" / "candles_cloud.db"
            if cloud_db.exists():
                db_path = cloud_db

    if log_dir is None:
        log_dir = settings.logs_dir

    if portfolio_symbols is None:
        portfolio_symbols = ["SOLUSDT", "ETHUSDT"]

    # Determine mode
    if use_portfolio:
        phase = "2C"
        mode = "PORTFOLIO"
    elif use_walkforward:
        phase = "2C"
        mode = "WALK-FORWARD"
    elif use_regime_testing:
        phase = "2B"
        mode = "REGIME TESTING"
    else:
        phase = "2A"
        mode = "MINIMAL"

    logger.info("=" * 60)
    logger.info(f"PHASE {phase}: {mode} EVOLUTION LOOP")
    logger.info("=" * 60)
    if use_portfolio:
        logger.info(f"Symbols: {', '.join(portfolio_symbols)}")
    else:
        logger.info(f"Symbol: {symbol}")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population size: {population_size}")
    logger.info(f"Regime testing: {'ENABLED' if use_regime_testing else 'DISABLED'}")
    logger.info(f"Portfolio mode: {'ENABLED' if use_portfolio else 'DISABLED'}")
    logger.info(f"Walk-forward: {'ENABLED' if use_walkforward else 'DISABLED'}")
    logger.info(f"Database: {db_path}")
    logger.info("=" * 60)

    # Initialize components
    logger.info("Initializing components...")

    # Repository
    repo = CandleRepository(db_path)

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

    # Load benchmark candles (BTC)
    logger.info("Loading benchmark candles (BTCUSDT)...")
    btc_candles = repo.get_latest("BTCUSDT", limit=35000)  # ~24 days of 1-min data
    if len(btc_candles) < 80:
        # [*TO-DO*] - Increase to 200+ when more data is available
        logger.error(f"Insufficient BTC data: {len(btc_candles)} candles (need 80+)")
        return
    btc_df = candles_to_df(btc_candles)

    # Load symbol candle data
    if use_portfolio:
        # Portfolio mode: load multiple symbols
        candles_dict: dict[str, pd.DataFrame] = {}
        for sym in portfolio_symbols:
            logger.info(f"Loading candles for {sym}...")
            sym_candles = repo.get_latest(sym, limit=35000)  # ~24 days of 1-min data
            if len(sym_candles) < 80:
                logger.warning(f"Insufficient data for {sym}: {len(sym_candles)} candles (need 80+), skipping")
                continue
            candles_dict[sym] = candles_to_df(sym_candles)
            logger.info(f"  Loaded {len(candles_dict[sym])} candles")

        if not candles_dict:
            logger.error("No symbols have sufficient data for portfolio backtesting")
            return

        logger.info(f"Portfolio: {len(candles_dict)} symbols loaded")
        symbol_df = None  # Not used in portfolio mode
    else:
        # Single symbol mode
        logger.info(f"Loading candles for {symbol}...")
        symbol_candles = repo.get_latest(symbol, limit=35000)  # ~24 days of 1-min data
        if len(symbol_candles) < 80:
            # [*TO-DO*] - Increase to 200+ when more data is available
            logger.error(f"Insufficient data for {symbol}: {len(symbol_candles)} candles (need 80+)")
            return
        symbol_df = candles_to_df(symbol_candles)
        candles_dict = None  # Not used in single-symbol mode
        logger.info(f"Loaded {len(symbol_df)} {symbol} candles, {len(btc_df)} BTC candles")

    # Initialize backtester(s) (crypto-specific config)
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,  # 0.25% Bybit taker fee + slippage
        max_position_pct=0.10,
        stop_loss_pct=0.03,
        max_open_positions=5 if use_portfolio else 1,
        max_total_exposure=0.50,
    )

    backtester = MinimalBacktester(backtest_config)
    portfolio_backtester = PortfolioBacktester(backtest_config) if use_portfolio else None
    wf_validator = None
    if use_walkforward:
        wf_config = WalkForwardConfig(
            train_bars=2000,  # ~1.4 days training
            test_bars=500,    # ~8 hours test
            step_bars=500,    # Step by ~8 hours
            min_windows=3,    # Need at least 3 windows
        )
        wf_validator = WalkForwardValidator(backtest_config, wf_config)

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

    # Initialize generator with self-referential market filter
    market_filter = get_market_filter_name(symbol)
    logger.info(f"Using market filter: {market_filter}")

    generator = StrategyGenerator(
        llm_client=llm_client,
        market_filter_name=market_filter,
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

    # Log regime distribution if enabled
    if use_regime_testing and symbol_df is not None:
        split_result = split_by_regime(symbol_df, btc_df)
        logger.info("\nRegime distribution:")
        for regime in REGIME_NAMES:
            count = split_result.regime_stats.get(regime, {}).get("candle_count", 0)
            pct = split_result.regime_stats.get(regime, {}).get("pct_of_total", 0)
            logger.info(f"  {regime}: {count} candles ({pct:.1f}%)")

    # Helper function to evaluate a strategy based on mode
    def eval_strategy(strat: GeneratedStrategy) -> tuple[FitnessResult, dict]:
        if use_portfolio:
            return evaluate_strategy_portfolio(
                strat, candles_dict, btc_df, portfolio_backtester, parser
            )
        elif use_walkforward:
            return evaluate_strategy_walkforward(
                strat, symbol_df, btc_df, wf_validator, parser, symbol
            )
        else:
            return evaluate_strategy(
                strat, symbol_df, btc_df, backtester, parser, symbol,
                use_regime_testing=use_regime_testing
            )

    # Evaluate initial population
    for strat in strategies:
        logger.info(f"\nEvaluating: {strat.name}")
        logger.info(f"  Entry: {strat.entry_long}")
        logger.info(f"  Exit: {strat.exit_long}")

        fitness, summary = eval_strategy(strat)

        population.append((strat, fitness))

        if fitness.disqualified:
            logger.info(f"  Result: DISQUALIFIED - {fitness.disqualification_reason}")
        else:
            logger.info(f"  Result: Score={fitness.final_score:.3f}, "
                       f"Sharpe={fitness.sharpe_ratio:.2f}, "
                       f"DD={fitness.max_drawdown:.1%}, "
                       f"Trades={fitness.trade_count}")
            if use_regime_testing and fitness.regime_scores:
                logger.info(f"  Regime pass count: {fitness.regime_pass_count}/5")
                logger.info(fitness.regime_summary())

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

                fitness, summary = eval_strategy(mutated)

                new_population.append((mutated, fitness))

                if fitness.disqualified:
                    logger.info(f"  Result: DISQUALIFIED - {fitness.disqualification_reason}")
                else:
                    logger.info(f"  Result: Score={fitness.final_score:.3f}, "
                               f"Sharpe={fitness.sharpe_ratio:.2f}, "
                               f"DD={fitness.max_drawdown:.1%}")
                    if use_regime_testing and fitness.regime_scores:
                        logger.info(f"  Regime pass count: {fitness.regime_pass_count}/5")
            else:
                logger.warning(f"  Mutation failed, generating new strategy...")
                new_strat = generator.generate()
                if new_strat:
                    fitness, _ = eval_strategy(new_strat)
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


def run_full_evolution(
    symbol: str,
    generations: int = 10,
    population_size: int = 10,
    db_path: Path = None,
    log_dir: Path = None,
    checkpoint_dir: Path = None,
    resume_from: str = None,
    progress_callback=None,
    progress_file: Path = None,
    custom_themes: list[str] = None,
):
    """
    Run Phase 2D full evolution with the EvolutionEngine.

    Features tournament selection, crossover, elite preservation,
    diversity tracking, and checkpoint/resume capability.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        generations: Number of evolution generations
        population_size: Number of strategies per generation
        db_path: Path to SQLite database
        log_dir: Directory for logs
        checkpoint_dir: Directory for checkpoints
        resume_from: Path to checkpoint file to resume from
        progress_callback: Optional callback(strategy_name, fitness, progress_info) for real-time updates
        progress_file: Optional path to JSON file for progress polling
        custom_themes: Optional list of strategy themes to use instead of defaults
    """
    if db_path is None:
        # Use main database (settings.sqlite_path), fall back to cloud DB
        db_path = settings.sqlite_path
        if not db_path.exists():
            cloud_db = Path(__file__).parent / "data" / "candles_cloud.db"
            if cloud_db.exists():
                db_path = cloud_db

    if log_dir is None:
        log_dir = settings.logs_dir

    if checkpoint_dir is None:
        checkpoint_dir = log_dir / "checkpoints"

    logger.info("=" * 60)
    logger.info("PHASE 2D: FULL EVOLUTION ENGINE")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population size: {population_size}")
    logger.info(f"Database: {db_path}")
    logger.info(f"Checkpoint dir: {checkpoint_dir}")
    if resume_from:
        logger.info(f"Resuming from: {resume_from}")
    logger.info("=" * 60)

    # Initialize components
    logger.info("Initializing components...")

    # Repository
    repo = CandleRepository(db_path)

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

    # Load candles
    logger.info("Loading candles...")
    btc_candles = repo.get_latest("BTCUSDT", limit=35000)  # ~24 days of 1-min data
    if len(btc_candles) < 80:
        logger.error(f"Insufficient BTC data: {len(btc_candles)} candles (need 80+)")
        return

    symbol_candles = repo.get_latest(symbol, limit=35000)  # ~24 days of 1-min data
    if len(symbol_candles) < 80:
        logger.error(f"Insufficient {symbol} data: {len(symbol_candles)} candles (need 80+)")
        return

    btc_df = candles_to_df(btc_candles)
    symbol_df = candles_to_df(symbol_candles)
    logger.info(f"Loaded {len(symbol_df)} {symbol} candles, {len(btc_df)} BTC candles")

    # Initialize backtester
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,
        max_position_pct=0.10,
        stop_loss_pct=0.03,
    )
    backtester = MinimalBacktester(backtest_config)
    parser = GeneExpressionParser()

    # Initialize LLM
    logger.info("Initializing LLM client...")
    try:
        llm_client = create_default_client(log_dir=log_dir)
        logger.info(f"Using LLM provider: {llm_client.config.provider.value}")
    except ValueError as e:
        logger.error(f"LLM initialization failed: {e}")
        return

    # Initialize generator and crossover with self-referential market filter
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
        checkpoint_dir=str(checkpoint_dir),
        progress_file=str(progress_file) if progress_file else None,
    )

    # Create engine with optional progress callback
    engine = EvolutionEngine(
        config=config,
        generator=generator,
        progress_callback=progress_callback,
        crossover=crossover,
        evaluator=eval_strategy,
    )

    # Run evolution
    if resume_from:
        result = engine.run(resume_from=resume_from)
    else:
        # Generate initial population
        theme_mode = "mean-reversion" if custom_themes else "default"
        logger.info(f"Generating initial population of {population_size} (themes: {theme_mode})...")
        initial_pop = generate_initial_population(generator, size=population_size, custom_themes=custom_themes)

        if not initial_pop:
            logger.error("Failed to generate initial population")
            return

        result = engine.run(initial_population=initial_pop)

    # Final results
    logger.info(f"\n{'=' * 60}")
    logger.info("EVOLUTION COMPLETE")
    logger.info("=" * 60)

    logger.info(f"Generations run: {result.generations_run}")
    logger.info(f"Early stopped: {result.early_stopped}")

    if result.best_strategy and result.best_fitness:
        logger.info(f"\nBest Strategy: {result.best_strategy.name}")
        logger.info(f"  Entry: {result.best_strategy.entry_long}")
        logger.info(f"  Exit: {result.best_strategy.exit_long}")
        logger.info(f"  Final Score: {result.best_fitness.final_score:.3f}")
        logger.info(f"  Sharpe: {result.best_fitness.sharpe_ratio:.2f}")
        logger.info(f"  Max DD: {result.best_fitness.max_drawdown:.1%}")
        logger.info(f"  Win Rate: {result.best_fitness.win_rate:.1%}")
        logger.info(f"  Trades: {result.best_fitness.trade_count}")
    else:
        logger.warning("No viable strategy found")

    # Show fitness progression
    if result.fitness_history:
        logger.info("\nFitness Progression:")
        for entry in result.fitness_history[-5:]:  # Last 5 generations
            logger.info(f"  Gen {entry['generation']}: Best={entry['best_score']:.3f}, "
                       f"Avg={entry['avg_score']:.3f}, Diversity={entry['diversity']:.2f}")

    logger.info(f"\nCompleted at: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}")

    return result


def main():
    arg_parser = argparse.ArgumentParser(
        description="Phase 2D: Evolution Loop with Selection, Crossover & Checkpointing"
    )
    arg_parser.add_argument(
        "--symbol",
        type=str,
        default="SOLUSDT",
        help="Trading symbol for single-symbol mode (default: SOLUSDT)"
    )
    arg_parser.add_argument(
        "--generations",
        type=int,
        default=3,
        help="Number of evolution generations (default: 3)"
    )
    arg_parser.add_argument(
        "--population",
        type=int,
        default=3,
        help="Population size (default: 3)"
    )
    arg_parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: auto-detect)"
    )
    arg_parser.add_argument(
        "--regime",
        action="store_true",
        help="Enable Phase 2B regime testing (default: off)"
    )
    arg_parser.add_argument(
        "--portfolio",
        action="store_true",
        help="Enable Phase 2C multi-symbol portfolio mode (default: off)"
    )
    arg_parser.add_argument(
        "--walkforward",
        action="store_true",
        help="Enable Phase 2C walk-forward validation (default: off)"
    )
    arg_parser.add_argument(
        "--symbols",
        type=str,
        default="SOLUSDT,ETHUSDT",
        help="Comma-separated symbols for portfolio mode (default: SOLUSDT,ETHUSDT)"
    )
    # Phase 2D arguments
    arg_parser.add_argument(
        "--full",
        action="store_true",
        help="Enable Phase 2D full evolution engine with tournament selection, crossover, checkpointing"
    )
    arg_parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Path to checkpoint file to resume from (Phase 2D only)"
    )
    arg_parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default=None,
        help="Directory for checkpoints (Phase 2D only)"
    )
    arg_parser.add_argument(
        "--mean-reversion",
        action="store_true",
        help="Use mean-reversion focused themes (better for choppy/sideways markets)"
    )

    args = arg_parser.parse_args()

    db_path = Path(args.db) if args.db else None

    # Phase 2D: Full evolution engine
    if args.full:
        checkpoint_dir = Path(args.checkpoint_dir) if args.checkpoint_dir else None
        custom_themes = MEAN_REVERSION_THEMES if args.mean_reversion else None
        run_full_evolution(
            symbol=args.symbol,
            generations=args.generations,
            population_size=args.population,
            db_path=db_path,
            checkpoint_dir=checkpoint_dir,
            resume_from=args.resume,
            custom_themes=custom_themes,
        )
    else:
        # Phase 2A/2B/2C: Simple evolution loop
        portfolio_symbols = [s.strip() for s in args.symbols.split(",")]
        run_evolution(
            symbol=args.symbol,
            generations=args.generations,
            population_size=args.population,
            db_path=db_path,
            use_regime_testing=args.regime,
            use_portfolio=args.portfolio,
            use_walkforward=args.walkforward,
            portfolio_symbols=portfolio_symbols,
        )


if __name__ == "__main__":
    main()
