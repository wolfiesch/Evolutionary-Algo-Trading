#!/usr/bin/env python3
"""
Template-Based Evolution - Fixed Logic, Evolvable Parameters.

This script implements the parameter evolution architecture designed in
docs/plans/2025-12-15-parameter-evolution-architecture.md

Key differences from string-based evolution (evolve.py, evolve_h4.py):
1. Uses fixed strategy templates - only parameters evolve
2. Vectorized signal generation - much faster backtesting
3. Regime-switched weights - adapts to market conditions
4. Tractable search space - finite parameter combinations

Usage:
    python3 evolve_template.py --symbol=SOLUSDT --generations=10
    python3 evolve_template.py --symbol=BTCUSDT --timeframe=H4 --generations=20
    python3 evolve_template.py --symbol=ETHUSDT --enable-shorts --generations=10
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from dataclasses import asdict
from copy import deepcopy
import pandas as pd
import numpy as np

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crypto.config import settings
from crypto.data.storage.repository import CandleRepository

# Parameter evolution components
from shared.evolution.parameters import (
    CryptoParameters,
    WeightVector,
    discretize_parameters,
    repair_constraints,
    hash_parameters,
)
from shared.evolution.templates import CryptoStrategyTemplate
from shared.evolution.backtester.template_engine import (
    TemplateBacktester,
    TemplateBacktestConfig,
)
from shared.evolution.backtester.timeframe import (
    Timeframe,
    aggregate_candles,
    get_timeframe_config,
)
from shared.evolution.backtester.walk_forward import (
    WalkForwardConfig,
    WalkForwardValidator,
)
from shared.evolution.backtester import BacktestConfig, walk_forward_fitness
from shared.evolution.fitness import FitnessResult
from shared.evolution.mutator.parameter_mutation import (
    mutate_parameters,
    crossover_parameters,
    random_mutate_parameters,
    generate_initial_parameters,
    MutationResult,
)
from shared.evolution.mutator import create_default_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def candles_to_df(candles) -> pd.DataFrame:
    """Convert candle objects to DataFrame."""
    return pd.DataFrame([{
        'open': c.open,
        'high': c.high,
        'low': c.low,
        'close': c.close,
        'volume': c.volume,
        'timestamp': c.timestamp,
    } for c in candles])


def evaluate_params(
    params: CryptoParameters,
    template_class: type,
    backtester: TemplateBacktester,
    candles: pd.DataFrame,
    btc_candles: pd.DataFrame,
    symbol: str,
    wf_validator: WalkForwardValidator = None,
) -> tuple[FitnessResult, dict]:
    """
    Evaluate a parameter set using the template backtester.

    Args:
        params: Parameter set to evaluate
        template_class: Template class to use (CryptoStrategyTemplate)
        backtester: Configured backtester
        candles: Asset OHLCV data
        btc_candles: BTC OHLCV data for market filter
        symbol: Trading symbol
        wf_validator: Optional walk-forward validator

    Returns:
        Tuple of (FitnessResult, metadata_dict)
    """
    try:
        template = template_class(params)

        if wf_validator:
            # Walk-forward validation
            from shared.evolution.backtester.template_engine import create_evaluator_from_template
            evaluator = create_evaluator_from_template(template)

            wf_results = wf_validator.validate(
                evaluator=evaluator,
                candles=candles,
                benchmark_candles=btc_candles,
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
        else:
            # Simple backtest
            results = backtester.run(
                template=template,
                candles=candles,
                symbol=symbol,
            )

            fitness = FitnessResult(
                sharpe_ratio=results.sharpe_ratio,
                trade_count=results.trade_count,
                win_rate=results.win_rate,
                total_return=results.total_return,
                max_drawdown=results.max_drawdown,
            )

            # Score based on Sharpe, with trade count minimum
            if results.trade_count < 5:
                fitness.disqualified = True
                fitness.disqualification_reason = "Too few trades"
                fitness.final_score = 0.0
            else:
                fitness.final_score = results.sharpe_ratio

            return fitness, results.summary()

    except Exception as e:
        logger.error(f"Evaluation error: {e}")
        return FitnessResult(
            disqualified=True,
            disqualification_reason=f"Error: {str(e)}"
        ), {}


def run_template_evolution(
    symbol: str,
    generations: int = 10,
    population_size: int = 10,
    timeframe: Timeframe = Timeframe.H4,
    data_days: int = 180,
    enable_shorts: bool = False,
    use_llm: bool = True,
):
    """
    Run parameter-based evolution using strategy templates.

    Args:
        symbol: Trading symbol (e.g., "SOLUSDT")
        generations: Number of evolution generations
        population_size: Size of each generation
        timeframe: Candle timeframe for backtesting
        data_days: Days of historical data
        enable_shorts: Whether to allow short positions
        use_llm: Whether to use LLM for mutations (vs random-only)
    """
    db_path = settings.sqlite_path
    log_dir = settings.logs_dir

    tf_config = get_timeframe_config(timeframe)

    logger.info("=" * 60)
    logger.info("TEMPLATE EVOLUTION ENGINE")
    logger.info("=" * 60)
    logger.info(f"Symbol: {symbol}")
    logger.info(f"Timeframe: {timeframe.value}")
    logger.info(f"Data window: {data_days} days")
    logger.info(f"Generations: {generations}")
    logger.info(f"Population: {population_size}")
    logger.info(f"Shorts enabled: {enable_shorts}")
    logger.info(f"LLM mutations: {use_llm}")
    logger.info("=" * 60)

    # Load data
    repo = CandleRepository(db_path)
    candles_needed = data_days * 24 * 60

    logger.info("Loading candles...")
    btc_raw = repo.get_latest("BTCUSDT", limit=candles_needed)
    symbol_raw = repo.get_latest(symbol, limit=candles_needed)

    if len(btc_raw) < 1000 or len(symbol_raw) < 1000:
        logger.error("Insufficient data")
        return None

    btc_df_m1 = candles_to_df(btc_raw)
    symbol_df_m1 = candles_to_df(symbol_raw)

    # Aggregate to target timeframe
    if timeframe != Timeframe.M1:
        btc_df = aggregate_candles(btc_df_m1, timeframe, Timeframe.M1)
        symbol_df = aggregate_candles(symbol_df_m1, timeframe, Timeframe.M1)
        logger.info(f"Aggregated: BTC {len(btc_df_m1)} -> {len(btc_df)}, "
                   f"{symbol} {len(symbol_df_m1)} -> {len(symbol_df)}")
    else:
        btc_df = btc_df_m1
        symbol_df = symbol_df_m1

    # Setup backtester
    backtest_config = TemplateBacktestConfig(
        initial_equity=10_000,
        friction_per_side=0.0025,
        max_position_pct=0.10,
        stop_loss_pct=0.03,
        timeframe_minutes=tf_config.timeframe.value,
    )
    backtester = TemplateBacktester(backtest_config)

    # Walk-forward validator
    wf_config = WalkForwardConfig(
        train_bars=tf_config.walk_forward_train,
        test_bars=tf_config.walk_forward_test,
        step_bars=tf_config.walk_forward_step,
        min_windows=3,
    )
    wf_validator = WalkForwardValidator(BacktestConfig(
        timeframe_minutes=tf_config.timeframe.value,
        friction_per_side=0.0025,
    ), wf_config)

    # Initialize LLM client if enabled
    llm_client = None
    if use_llm:
        try:
            llm_client = create_default_client(log_dir=log_dir)
            logger.info(f"LLM: {llm_client.config.provider.value}")
        except Exception as e:
            logger.warning(f"LLM init failed: {e}, using random mutations")

    # Generate initial population
    logger.info(f"Generating initial population of {population_size}...")

    # Create seed parameters
    seed_params = CryptoParameters(
        allow_short=enable_shorts,
        weights_A=WeightVector(
            trend=0.2, momentum=0.3, mean_reversion=0.6, volatility=0.1, volume=0.1
        ),
        weights_B=WeightVector(
            trend=0.7, momentum=0.4, mean_reversion=0.1, volatility=0.2, volume=0.1
        ),
    )

    population = generate_initial_parameters(
        param_class=CryptoParameters,
        count=population_size,
        seed_params=seed_params,
    )

    # Set shorts flag on all population members
    for p in population:
        p.allow_short = enable_shorts

    # Evolution tracking
    best_params = None
    best_fitness = None
    best_score = float('-inf')
    generation_history = []
    seen_hashes = set()

    # Evolution loop
    for gen in range(generations):
        logger.info(f"\n{'='*40}")
        logger.info(f"GENERATION {gen + 1}/{generations}")
        logger.info(f"{'='*40}")

        # Evaluate population
        scored = []
        for i, params in enumerate(population):
            # Check for duplicates
            param_hash = hash_parameters(params)
            is_duplicate = param_hash in seen_hashes
            seen_hashes.add(param_hash)

            if is_duplicate and len(scored) > 0:
                logger.debug(f"  [{i+1}] Duplicate, skipping")
                continue

            fitness, metadata = evaluate_params(
                params=params,
                template_class=CryptoStrategyTemplate,
                backtester=backtester,
                candles=symbol_df,
                btc_candles=btc_df,
                symbol=symbol,
                wf_validator=wf_validator,
            )

            scored.append((params, fitness))

            status = "✓" if fitness.final_score > 0 else "✗"
            logger.info(f"  [{i+1}] {status} Score={fitness.final_score:.3f} "
                       f"Sharpe={fitness.sharpe_ratio:.2f} Trades={fitness.trade_count} "
                       f"WR={fitness.win_rate:.1%}")

        if not scored:
            logger.warning("No viable strategies this generation")
            continue

        # Sort by score
        scored.sort(key=lambda x: x[1].final_score, reverse=True)

        # Track best
        gen_best_params, gen_best_fitness = scored[0]
        if gen_best_fitness.final_score > best_score:
            best_params = deepcopy(gen_best_params)
            best_fitness = gen_best_fitness
            best_score = gen_best_fitness.final_score
            logger.info(f"  ★ New best! Score={best_score:.3f}")

        generation_history.append({
            'generation': gen + 1,
            'best_score': gen_best_fitness.final_score,
            'best_sharpe': gen_best_fitness.sharpe_ratio,
            'population_size': len(scored),
        })

        # Create next generation
        if gen < generations - 1:
            # Elitism: keep top 2
            elite_count = min(2, len(scored))
            next_pop = [deepcopy(scored[i][0]) for i in range(elite_count)]

            # Generate rest via mutation and crossover
            while len(next_pop) < population_size:
                if len(scored) >= 2 and np.random.random() < 0.3:
                    # Crossover
                    p1 = scored[np.random.randint(0, min(5, len(scored)))][0]
                    p2 = scored[np.random.randint(0, min(5, len(scored)))][0]
                    child = crossover_parameters(p1, p2, llm_client=llm_client)
                    child.allow_short = enable_shorts
                    next_pop.append(child)
                else:
                    # Mutation
                    parent_idx = np.random.randint(0, min(5, len(scored)))
                    parent = scored[parent_idx][0]
                    mutated, mutation = mutate_parameters(
                        params=parent,
                        sharpe=scored[parent_idx][1].sharpe_ratio,
                        win_rate=scored[parent_idx][1].win_rate,
                        max_dd=scored[parent_idx][1].max_drawdown,
                        trade_count=scored[parent_idx][1].trade_count,
                        llm_client=llm_client,
                    )
                    mutated.allow_short = enable_shorts
                    next_pop.append(mutated)

            population = next_pop

    # Results
    logger.info(f"\n{'='*60}")
    logger.info("EVOLUTION COMPLETE")
    logger.info("=" * 60)

    if best_params and best_fitness:
        logger.info(f"Best Score: {best_score:.3f}")
        logger.info(f"Best Sharpe: {best_fitness.sharpe_ratio:.2f}")
        logger.info(f"Best Win Rate: {best_fitness.win_rate:.1%}")
        logger.info(f"Best Trades: {best_fitness.trade_count}")
        logger.info(f"Max Drawdown: {best_fitness.max_drawdown:.1%}")

        # Save best parameters
        output_dir = log_dir / "template_strategies"
        output_dir.mkdir(exist_ok=True)

        output_file = output_dir / f"{symbol.lower()}_template_{datetime.now().strftime('%Y%m%d_%H%M')}.json"

        output_data = {
            'symbol': symbol,
            'timeframe': timeframe.value,
            'fitness': {
                'score': best_score,
                'sharpe_ratio': best_fitness.sharpe_ratio,
                'win_rate': best_fitness.win_rate,
                'trade_count': best_fitness.trade_count,
                'max_drawdown': best_fitness.max_drawdown,
            },
            'parameters': best_params.to_dict(),
            'generation_history': generation_history,
            'evolution_config': {
                'generations': generations,
                'population_size': population_size,
                'data_days': data_days,
                'enable_shorts': enable_shorts,
            },
            'created': datetime.now().isoformat(),
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)

        logger.info(f"\nSaved to: {output_file}")

        # Print key parameters
        logger.info(f"\nKey Parameters:")
        logger.info(f"  Weights A (Ranging): trend={best_params.weights_A.trend:.1f}, "
                   f"momentum={best_params.weights_A.momentum:.1f}, "
                   f"reversion={best_params.weights_A.mean_reversion:.1f}")
        logger.info(f"  Weights B (Trending): trend={best_params.weights_B.trend:.1f}, "
                   f"momentum={best_params.weights_B.momentum:.1f}, "
                   f"reversion={best_params.weights_B.mean_reversion:.1f}")
        logger.info(f"  Entry threshold: {best_params.entry_threshold_long:.2f}")
        logger.info(f"  Exit threshold: {best_params.exit_threshold_long:.2f}")
    else:
        logger.warning("No viable strategy found")

    logger.info(f"\nCompleted: {datetime.now().strftime('%m/%d/%Y %I:%M %p')}")

    return best_params, best_fitness


def main():
    parser = argparse.ArgumentParser(description="Template Evolution Engine")
    parser.add_argument("--symbol", type=str, default="SOLUSDT")
    parser.add_argument("--generations", type=int, default=10)
    parser.add_argument("--population", type=int, default=10)
    parser.add_argument("--timeframe", type=str, default="H4",
                       choices=["M1", "M5", "M15", "H1", "H4", "D1"])
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--enable-shorts", action="store_true")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM mutations")

    args = parser.parse_args()

    timeframe_map = {
        "M1": Timeframe.M1,
        "M5": Timeframe.M5,
        "M15": Timeframe.M15,
        "H1": Timeframe.H1,
        "H4": Timeframe.H4,
        "D1": Timeframe.D1,
    }

    run_template_evolution(
        symbol=args.symbol,
        generations=args.generations,
        population_size=args.population,
        timeframe=timeframe_map[args.timeframe],
        data_days=args.days,
        enable_shorts=args.enable_shorts,
        use_llm=not args.no_llm,
    )


if __name__ == "__main__":
    main()
