#!/usr/bin/env python3
"""
H4 Evolution - Uses proper timeframe aggregation for walk-forward validation.

Key differences from evolve.py:
1. Aggregates 1-min candles to H4 (4-hour) candles
2. Uses H4-appropriate walk-forward config (60d train, 15d test)
3. Limits data to ~180 days for reasonable backtest period

Usage:
    python3 evolve_h4.py --symbol=SOLUSDT --generations=10 --population=5
    python3 evolve_h4.py --symbol=ETHUSDT --seed=crypto/seeds/eth_vwap_reversion_v1.json
    python3 evolve_h4.py --symbol=BTCUSDT --seed=crypto/seeds/btc_momentum_trend_v1.json --market-filter=asset_trend
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

from shared.evolution.backtester import (
    MinimalBacktester,
    BacktestConfig,
    WalkForwardValidator,
    WalkForwardConfig,
    walk_forward_fitness,
)
from shared.evolution.backtester.timeframe import (
    Timeframe,
    aggregate_candles,
    get_timeframe_config,
    TIMEFRAME_CONFIGS,
)
from shared.evolution.fitness import calculate_fitness, FitnessResult
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


def get_market_filter_name(symbol: str) -> str:
    """Get appropriate market filter for symbol."""
    if symbol.upper().startswith("BTC"):
        return "asset_trend"
    return "btc_trend"


def create_evaluator(strategy: Strategy, parser: GeneExpressionParser):
    """Create evaluator function for backtester."""
    def evaluator(candles: pd.DataFrame, benchmark_candles: pd.DataFrame, has_position: bool) -> str:
        try:
            signal = parser.get_signal(strategy, candles, benchmark_candles, has_position)
            return signal.value
        except Exception as e:
            logger.debug(f"Evaluator error: {e}")
            return "HOLD"
    return evaluator


def run_h4_evolution(
    symbol: str,
    generations: int = 10,
    population_size: int = 5,
    seed_strategy_path: Path = None,
    market_filter_override: str = None,
    data_days: int = 180,
):
    """
    Run evolution with H4 timeframe aggregation.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT", "BTCUSDT")
        generations: Number of evolution generations
        population_size: Strategies per generation
        seed_strategy_path: Optional seed strategy JSON file
        market_filter_override: Override market filter primitive
        data_days: Days of historical data to use (default: 180)
    """
    db_path = settings.sqlite_path
    log_dir = settings.logs_dir

    # Get H4 timeframe config
    h4_config = get_timeframe_config(Timeframe.H4)

    logger.info("=" * 60)
    logger.info("H4 EVOLUTION ENGINE")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: H4 (4-hour candles)")
    logger.info(f"Data window: {data_days} days")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population: {population_size}")
    logger.info(f"Walk-forward: train={h4_config.walk_forward_train} bars ({h4_config.walk_forward_train/6:.0f} days), "
                f"test={h4_config.walk_forward_test} bars ({h4_config.walk_forward_test/6:.0f} days)")
    logger.info("=" * 60)

    # Load raw 1-min data
    repo = CandleRepository(db_path)

    # Calculate how many 1-min candles we need for data_days
    candles_needed = data_days * 24 * 60  # days * hours * minutes

    logger.info("Loading and aggregating candles...")

    def candles_to_df(candles):
        return pd.DataFrame([{
            'open': c.open,
            'high': c.high,
            'low': c.low,
            'close': c.close,
            'volume': c.volume,
            'timestamp': c.timestamp,
        } for c in candles])

    # Load BTC candles (benchmark)
    btc_candles_raw = repo.get_latest("BTCUSDT", limit=candles_needed)
    if len(btc_candles_raw) < 1000:
        logger.error(f"Insufficient BTC data: {len(btc_candles_raw)} candles")
        return None
    btc_df_m1 = candles_to_df(btc_candles_raw)
    btc_df_h4 = aggregate_candles(btc_df_m1, Timeframe.H4, Timeframe.M1)
    logger.info(f"BTC: {len(btc_df_m1)} M1 -> {len(btc_df_h4)} H4 candles")

    # Load symbol candles
    symbol_candles_raw = repo.get_latest(symbol, limit=candles_needed)
    if len(symbol_candles_raw) < 1000:
        logger.error(f"Insufficient {symbol} data: {len(symbol_candles_raw)} candles")
        return None
    symbol_df_m1 = candles_to_df(symbol_candles_raw)
    symbol_df_h4 = aggregate_candles(symbol_df_m1, Timeframe.H4, Timeframe.M1)
    logger.info(f"{symbol}: {len(symbol_df_m1)} M1 -> {len(symbol_df_h4)} H4 candles")

    # Initialize backtester with H4-appropriate config
    backtest_config = BacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,  # 0.25% Bybit fee
        max_position_pct=0.10,
        stop_loss_pct=0.03,
        timeframe_minutes=240,  # H4 = 240 minutes
    )
    backtester = MinimalBacktester(backtest_config)
    parser = GeneExpressionParser()

    # Walk-forward validator with H4 config
    wf_config = WalkForwardConfig(
        train_bars=h4_config.walk_forward_train,  # 360 bars = 60 days
        test_bars=h4_config.walk_forward_test,    # 90 bars = 15 days
        step_bars=h4_config.walk_forward_step,    # 45 bars = 7.5 days
        min_windows=3,
    )
    wf_validator = WalkForwardValidator(backtest_config, wf_config)
    logger.info(f"Walk-forward: {wf_config.train_bars} train, {wf_config.test_bars} test, {wf_config.step_bars} step")

    # Initialize LLM
    logger.info("Initializing LLM...")
    try:
        llm_client = create_default_client(log_dir=log_dir)
        logger.info(f"LLM provider: {llm_client.config.provider.value}, model: {llm_client.config.model}")
    except ValueError as e:
        logger.error(f"LLM init failed: {e}")
        return None

    # Market filter
    market_filter = market_filter_override or get_market_filter_name(symbol)
    logger.info(f"Market filter: {market_filter}")

    generator = StrategyGenerator(llm_client=llm_client, market_filter_name=market_filter)
    crossover = CrossoverOperator(llm_client=llm_client, market_filter_name=market_filter)

    # Evaluation function
    def eval_strategy(generated: GeneratedStrategy) -> tuple[FitnessResult, dict]:
        try:
            strategy = parser.parse(generated.to_dict())
            evaluator = create_evaluator(strategy, parser)

            wf_results = wf_validator.validate(
                evaluator=evaluator,
                candles=symbol_df_h4,
                benchmark_candles=btc_df_h4,
                symbol=symbol,
            )

            score, is_valid, reason = walk_forward_fitness(wf_results)

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

        except Exception as e:
            logger.error(f"Eval error for {generated.name}: {e}")
            return FitnessResult(
                disqualified=True,
                disqualification_reason=f"Eval error: {str(e)}"
            ), {}

    # Evolution config
    config = EvolutionConfig(
        population_size=population_size,
        generations=generations,
        elite_count=2,
        mutation_rate=0.7,
        crossover_rate=0.3,
        tournament_size=3,
        max_stagnation=5,
        checkpoint_interval=3,
        checkpoint_dir=str(log_dir / "checkpoints"),
    )

    engine = EvolutionEngine(
        config=config,
        generator=generator,
        crossover=crossover,
        evaluator=eval_strategy,
    )

    # Load seed strategy if provided
    seed_strategy = None
    if seed_strategy_path and seed_strategy_path.exists():
        try:
            with open(seed_strategy_path) as f:
                seed_data = json.load(f)
            seed_strategy = GeneratedStrategy(
                name=f"Seed_{seed_data.get('strategy_name', 'Unknown')}",
                entry_long=seed_data.get('entry_long', ''),
                exit_long=seed_data.get('exit_long', ''),
                rationale=f"Transplanted from {seed_data.get('strategy_name', 'unknown')}",
            )
            logger.info(f"Seed: {seed_strategy.name}")
            logger.info(f"  Entry: {seed_strategy.entry_long}")
            logger.info(f"  Exit: {seed_strategy.exit_long}")
        except Exception as e:
            logger.warning(f"Failed to load seed: {e}")

    # Generate initial population
    gen_size = population_size - 1 if seed_strategy else population_size
    logger.info(f"Generating {gen_size} initial strategies...")
    initial_pop = generate_initial_population(generator, size=gen_size)

    if seed_strategy:
        initial_pop.insert(0, seed_strategy)

    if not initial_pop:
        logger.error("No initial population")
        return None

    # Run evolution
    result = engine.run(initial_population=initial_pop)

    # Results
    logger.info(f"\n{'=' * 60}")
    logger.info("EVOLUTION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Generations: {result.generations_run}")
    logger.info(f"Early stop: {result.early_stopped}")

    if result.best_strategy and result.best_fitness:
        logger.info(f"\nBest: {result.best_strategy.name}")
        logger.info(f"  Entry: {result.best_strategy.entry_long}")
        logger.info(f"  Exit: {result.best_strategy.exit_long}")
        logger.info(f"  Score: {result.best_fitness.final_score:.3f}")
        logger.info(f"  Sharpe: {result.best_fitness.sharpe_ratio:.2f}")
        logger.info(f"  DD: {result.best_fitness.max_drawdown:.1%}")
        logger.info(f"  WinRate: {result.best_fitness.win_rate:.1%}")
        logger.info(f"  Trades: {result.best_fitness.trade_count}")
    else:
        logger.warning("No viable strategy found")

    logger.info(f"\nCompleted: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}")

    return result


def main():
    parser = argparse.ArgumentParser(description="H4 Evolution Engine")
    parser.add_argument("--symbol", type=str, default="SOLUSDT")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--population", type=int, default=5)
    parser.add_argument("--seed", type=str, default=None)
    parser.add_argument("--market-filter", type=str, choices=["btc_trend", "asset_trend"])
    parser.add_argument("--days", type=int, default=180, help="Days of historical data")

    args = parser.parse_args()

    seed_path = Path(args.seed) if args.seed else None

    run_h4_evolution(
        symbol=args.symbol,
        generations=args.generations,
        population_size=args.population,
        seed_strategy_path=seed_path,
        market_filter_override=args.market_filter,
        data_days=args.days,
    )


if __name__ == "__main__":
    main()
