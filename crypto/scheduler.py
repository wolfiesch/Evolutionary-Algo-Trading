"""
Evolution scheduler - automated nightly evolution runs.

Provides a scheduler for running evolution at specified intervals
with automatic strategy handoff to shadow trading.

Usage:
    # Run immediately and exit
    python scheduler.py --run-now

    # Start scheduler (runs at 2 AM UTC daily)
    python scheduler.py --start

    # Custom schedule (every 12 hours)
    python scheduler.py --start --interval-hours=12

    # Dry run (no actual evolution, just test scheduling)
    python scheduler.py --dry-run
"""
import argparse
import logging
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from crypto.config import settings
from crypto.evolve import run_full_evolution

from shared.evolution.persistence import (
    StrategyStore,
    StrategyRecord,
    HandoffConfig,
    promote_best_from_evolution,
    get_shadow_pool_summary,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(settings.logs_dir / "scheduler.log"),
    ],
)
logger = logging.getLogger(__name__)

# Default schedule: 2 AM UTC daily
DEFAULT_RUN_HOUR_UTC = 2
DEFAULT_INTERVAL_HOURS = 24


class EvolutionScheduler:
    """
    Scheduler for automated evolution runs.

    Features:
    - Configurable run intervals
    - Automatic handoff to shadow trading
    - Run history tracking
    - Graceful shutdown handling
    """

    def __init__(
        self,
        interval_hours: int = DEFAULT_INTERVAL_HOURS,
        run_hour_utc: int = DEFAULT_RUN_HOUR_UTC,
        strategy_store_dir: Optional[Path] = None,
        shadow_pool_dir: Optional[Path] = None,
        checkpoint_dir: Optional[Path] = None,
        db_path: Optional[Path] = None,
    ):
        """
        Initialize scheduler.

        Args:
            interval_hours: Hours between runs (default: 24)
            run_hour_utc: Hour to run at (0-23, UTC, default: 2)
            strategy_store_dir: Directory for evolved strategies
            shadow_pool_dir: Directory for shadow pool
            checkpoint_dir: Directory for evolution checkpoints
            db_path: Path to candle database
        """
        self.interval_hours = interval_hours
        self.run_hour_utc = run_hour_utc

        # Set up directories
        self.strategy_store_dir = strategy_store_dir or (settings.logs_dir / "strategies")
        self.shadow_pool_dir = shadow_pool_dir or (settings.logs_dir / "shadow_pool")
        self.checkpoint_dir = checkpoint_dir or (settings.logs_dir / "evolution_checkpoints")
        self.db_path = db_path

        # Ensure directories exist
        self.strategy_store_dir.mkdir(parents=True, exist_ok=True)
        self.shadow_pool_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # State
        self._running = False
        self._last_run: Optional[datetime] = None
        self._run_count = 0

        # Run history
        self.history_path = settings.logs_dir / "scheduler_history.jsonl"

    def _calculate_next_run(self) -> datetime:
        """Calculate the next scheduled run time."""
        now = datetime.utcnow()

        if self.interval_hours == 24:
            # Daily at specific hour
            next_run = now.replace(
                hour=self.run_hour_utc,
                minute=0,
                second=0,
                microsecond=0,
            )
            if next_run <= now:
                next_run += timedelta(days=1)
        else:
            # Interval-based (from last run or now)
            if self._last_run:
                next_run = self._last_run + timedelta(hours=self.interval_hours)
            else:
                next_run = now + timedelta(hours=self.interval_hours)

        return next_run

    def _log_run(self, success: bool, message: str, duration_sec: float):
        """Log a run to history file."""
        import json

        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "run_number": self._run_count,
            "success": success,
            "message": message,
            "duration_sec": duration_sec,
        }

        with open(self.history_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def run_evolution(
        self,
        symbol: str = "SOLUSDT",
        generations: int = 10,
        population_size: int = 10,
    ) -> bool:
        """
        Run a single evolution cycle.

        Args:
            symbol: Trading symbol to evolve
            generations: Number of generations
            population_size: Population size

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        self._run_count += 1

        logger.info("=" * 60)
        logger.info(f"SCHEDULED EVOLUTION RUN #{self._run_count}")
        logger.info(f"Time: {datetime.utcnow().isoformat()}")
        logger.info("=" * 60)

        try:
            # Run evolution
            result = run_full_evolution(
                symbol=symbol,
                generations=generations,
                population_size=population_size,
                db_path=self.db_path,
                checkpoint_dir=self.checkpoint_dir,
            )

            if result and result.best_strategy and result.best_fitness:
                # Save best strategy to store
                store = StrategyStore(self.strategy_store_dir)

                record = StrategyRecord(
                    id=f"evo_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                    name=result.best_strategy.name,
                    entry_long=result.best_strategy.entry_long,
                    exit_long=result.best_strategy.exit_long,
                    asset_class="crypto",
                    target_symbols=[symbol],
                    market_filter="btc_trend",
                    sharpe_ratio=result.best_fitness.sharpe_ratio,
                    max_drawdown=result.best_fitness.max_drawdown,
                    win_rate=result.best_fitness.win_rate,
                    trade_count=result.best_fitness.trade_count,
                    final_score=result.best_fitness.final_score,
                    generation=result.generations_run,
                    rationale=result.best_strategy.rationale,
                )

                store.save(record)
                logger.info(f"Saved best strategy: {record.name} (Score: {record.final_score:.3f})")

                # Try to promote to shadow
                # Phase 1 testing: Use more lenient thresholds to get strategies
                # into shadow pool for observation. Production would use stricter defaults.
                handoff_config = HandoffConfig(
                    strategy_store_dir=self.strategy_store_dir,
                    shadow_pool_dir=self.shadow_pool_dir,
                    # Phase 1 relaxed thresholds (defaults: sharpe=0.5, regime=4, trades=30)
                    min_sharpe=0.3,
                    min_regime_passes=0,  # Disable regime testing for now (not enough data variety)
                    min_trade_count=10,
                )

                promoted = promote_best_from_evolution(
                    store_dir=self.strategy_store_dir,
                    shadow_pool_dir=self.shadow_pool_dir,
                    config=handoff_config,
                    max_promote=1,
                )

                if promoted:
                    logger.info(f"Promoted {len(promoted)} strategy to shadow pool")

                # Log shadow pool status
                pool_summary = get_shadow_pool_summary(self.shadow_pool_dir)
                logger.info(f"Shadow pool: {pool_summary['count']} strategies")

                duration = time.time() - start_time
                self._log_run(True, f"Best score: {record.final_score:.3f}", duration)
                self._last_run = datetime.utcnow()

                return True

            else:
                duration = time.time() - start_time
                self._log_run(False, "No viable strategy found", duration)
                self._last_run = datetime.utcnow()

                return False

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Evolution run failed: {e}")
            self._log_run(False, f"Error: {str(e)}", duration)
            self._last_run = datetime.utcnow()

            return False

    def start(self, dry_run: bool = False):
        """
        Start the scheduler loop.

        Args:
            dry_run: If True, don't actually run evolution
        """
        self._running = True

        # Set up signal handlers for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Shutdown signal received, stopping scheduler...")
            self._running = False

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("=" * 60)
        logger.info("EVOLUTION SCHEDULER STARTED")
        logger.info("=" * 60)
        logger.info(f"Interval: {self.interval_hours} hours")
        logger.info(f"Run hour (UTC): {self.run_hour_utc}:00")
        logger.info(f"Strategy store: {self.strategy_store_dir}")
        logger.info(f"Shadow pool: {self.shadow_pool_dir}")
        logger.info(f"Dry run: {dry_run}")
        logger.info("=" * 60)

        while self._running:
            next_run = self._calculate_next_run()
            wait_seconds = (next_run - datetime.utcnow()).total_seconds()

            if wait_seconds > 0:
                logger.info(f"Next run at: {next_run.isoformat()} UTC ({wait_seconds/3600:.1f} hours)")

                # Sleep in chunks to allow graceful shutdown
                while wait_seconds > 0 and self._running:
                    sleep_time = min(60, wait_seconds)  # Check every minute
                    time.sleep(sleep_time)
                    wait_seconds -= sleep_time

            if not self._running:
                break

            if dry_run:
                logger.info("DRY RUN: Would run evolution now")
                self._last_run = datetime.utcnow()
            else:
                self.run_evolution()

        logger.info("Scheduler stopped")

    def stop(self):
        """Stop the scheduler."""
        self._running = False


def main():
    parser = argparse.ArgumentParser(
        description="Evolution scheduler for automated nightly runs"
    )
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start the scheduler loop",
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Run evolution immediately and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually run evolution, just test scheduling",
    )
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=DEFAULT_INTERVAL_HOURS,
        help=f"Hours between runs (default: {DEFAULT_INTERVAL_HOURS})",
    )
    parser.add_argument(
        "--run-hour",
        type=int,
        default=DEFAULT_RUN_HOUR_UTC,
        help=f"Hour to run at (0-23, UTC, default: {DEFAULT_RUN_HOUR_UTC})",
    )
    parser.add_argument(
        "--symbol",
        type=str,
        default="BTCUSDT",
        help="Symbol to evolve (default: BTCUSDT)",
    )
    parser.add_argument(
        "--generations",
        type=int,
        default=10,
        help="Number of generations per run (default: 10)",
    )
    parser.add_argument(
        "--population",
        type=int,
        default=10,
        help="Population size (default: 10)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to candle database",
    )

    args = parser.parse_args()

    db_path = Path(args.db) if args.db else None

    scheduler = EvolutionScheduler(
        interval_hours=args.interval_hours,
        run_hour_utc=args.run_hour,
        db_path=db_path,
    )

    if args.run_now:
        # Run immediately and exit
        success = scheduler.run_evolution(
            symbol=args.symbol,
            generations=args.generations,
            population_size=args.population,
        )
        sys.exit(0 if success else 1)

    elif args.start:
        # Start scheduler loop
        scheduler.start(dry_run=args.dry_run)

    else:
        # Show current status
        next_run = scheduler._calculate_next_run()
        pool_summary = get_shadow_pool_summary(scheduler.shadow_pool_dir)

        print("Evolution Scheduler Status")
        print("=" * 40)
        print(f"Next scheduled run: {next_run.isoformat()} UTC")
        print(f"Shadow pool: {pool_summary['count']} strategies")
        if pool_summary['count'] > 0:
            print(f"  Avg Sharpe: {pool_summary.get('avg_sharpe', 0):.2f}")
            print(f"  Avg Max DD: {pool_summary.get('avg_max_dd', 0):.1%}")
        print("\nUse --start to begin scheduling, --run-now for immediate run")


if __name__ == "__main__":
    main()
