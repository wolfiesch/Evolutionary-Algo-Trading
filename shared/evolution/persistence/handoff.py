"""
Shadow trader handoff - promote evolved strategies to shadow trading.

Provides functions to:
- Convert StrategyRecord to shadow trader format
- Deploy strategies to the shadow trader pool
- Manage the transition from evolution to production
"""
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared.evolution.persistence.strategy_store import (
    StrategyStore,
    StrategyRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class HandoffConfig:
    """Configuration for strategy handoff."""

    # Minimum fitness requirements
    min_sharpe: float = 0.5
    min_regime_passes: int = 4  # Out of 5 regimes
    max_drawdown: float = 0.20  # 20% max
    min_trade_count: int = 30

    # Handoff paths
    strategy_store_dir: Path = Path("strategies")
    shadow_pool_dir: Path = Path("shadow_pool")

    # Maximum active shadow strategies
    max_shadow_strategies: int = 5


def qualify_for_shadow(
    record: StrategyRecord,
    config: HandoffConfig = None,
) -> tuple[bool, str]:
    """
    Check if a strategy qualifies for shadow trading.

    Args:
        record: Strategy record to evaluate
        config: Handoff configuration

    Returns:
        (qualified, reason) - True if qualified, False with rejection reason
    """
    config = config or HandoffConfig()

    # Check Sharpe ratio
    if record.sharpe_ratio < config.min_sharpe:
        return False, f"Sharpe ratio {record.sharpe_ratio:.2f} < {config.min_sharpe}"

    # Check regime passes
    if record.regime_pass_count < config.min_regime_passes:
        return False, f"Regime passes {record.regime_pass_count}/5 < {config.min_regime_passes}/5"

    # Check max drawdown
    if record.max_drawdown > config.max_drawdown:
        return False, f"Max drawdown {record.max_drawdown:.1%} > {config.max_drawdown:.1%}"

    # Check trade count
    if record.trade_count < config.min_trade_count:
        return False, f"Trade count {record.trade_count} < {config.min_trade_count}"

    return True, "Qualified for shadow trading"


def get_shadow_strategy_format(record: StrategyRecord) -> dict:
    """
    Convert a StrategyRecord to shadow trader JSON format.

    Returns the format expected by the crypto shadow trader.
    """
    return {
        "strategy_name": record.name,
        "strategy_id": record.id,
        "entry_long": record.entry_long,
        "exit_long": record.exit_long,
        "entry_short": record.entry_short,
        "exit_short": record.exit_short,
        # Metadata for tracking
        "evolved_at": record.created_at,
        "generation": record.generation,
        "backtest_sharpe": record.sharpe_ratio,
        "backtest_max_dd": record.max_drawdown,
        "regime_pass_count": record.regime_pass_count,
        "target_symbols": record.target_symbols,
    }


def handoff_to_shadow(
    record: StrategyRecord,
    shadow_pool_dir: Path,
    config: HandoffConfig = None,
) -> tuple[bool, str, Optional[Path]]:
    """
    Hand off a strategy from evolution to shadow trading.

    Args:
        record: Strategy record to hand off
        shadow_pool_dir: Directory for shadow strategy files
        config: Handoff configuration

    Returns:
        (success, message, output_path)
    """
    config = config or HandoffConfig()

    # Check qualification
    qualified, reason = qualify_for_shadow(record, config)
    if not qualified:
        logger.warning(f"Strategy {record.name} not qualified: {reason}")
        return False, reason, None

    # Check if we have room in the shadow pool
    shadow_pool_dir = Path(shadow_pool_dir)
    shadow_pool_dir.mkdir(parents=True, exist_ok=True)

    existing_shadow = list(shadow_pool_dir.glob("*.json"))
    if len(existing_shadow) >= config.max_shadow_strategies:
        logger.warning(
            f"Shadow pool full ({len(existing_shadow)}/{config.max_shadow_strategies}). "
            f"Consider retiring underperforming strategies."
        )
        return False, f"Shadow pool full ({config.max_shadow_strategies} max)", None

    # Convert and save
    shadow_format = get_shadow_strategy_format(record)

    # Use a descriptive filename
    filename = f"shadow_{record.id}_{record.name.replace(' ', '_')}.json"
    output_path = shadow_pool_dir / filename

    with open(output_path, "w") as f:
        json.dump(shadow_format, f, indent=2)

    # Update record status
    record.promote_to_shadow()

    logger.info(f"Strategy {record.name} handed off to shadow pool: {output_path}")
    return True, f"Successfully deployed to {output_path}", output_path


def load_shadow_pool(shadow_pool_dir: Path) -> list[dict]:
    """
    Load all strategies from the shadow pool.

    Args:
        shadow_pool_dir: Directory containing shadow strategy files

    Returns:
        List of strategy dictionaries
    """
    shadow_pool_dir = Path(shadow_pool_dir)
    if not shadow_pool_dir.exists():
        return []

    strategies = []
    for filepath in shadow_pool_dir.glob("*.json"):
        try:
            with open(filepath, "r") as f:
                strategies.append(json.load(f))
        except Exception as e:
            logger.error(f"Failed to load shadow strategy {filepath}: {e}")

    return strategies


def retire_shadow_strategy(
    shadow_pool_dir: Path,
    strategy_id: str,
    reason: str = "",
    archive_dir: Optional[Path] = None,
) -> bool:
    """
    Retire a strategy from the shadow pool.

    Args:
        shadow_pool_dir: Directory containing shadow strategies
        strategy_id: ID of strategy to retire
        reason: Reason for retirement
        archive_dir: Optional directory to archive retired strategies

    Returns:
        True if strategy was retired, False if not found
    """
    shadow_pool_dir = Path(shadow_pool_dir)

    for filepath in shadow_pool_dir.glob("*.json"):
        if strategy_id in filepath.stem:
            if archive_dir:
                archive_dir = Path(archive_dir)
                archive_dir.mkdir(parents=True, exist_ok=True)

                # Read and update metadata
                with open(filepath, "r") as f:
                    data = json.load(f)
                data["retired_at"] = datetime.utcnow().isoformat()
                data["retired_reason"] = reason

                # Save to archive
                archive_path = archive_dir / filepath.name
                with open(archive_path, "w") as f:
                    json.dump(data, f, indent=2)

            # Remove from shadow pool
            filepath.unlink()
            logger.info(f"Retired shadow strategy {strategy_id}: {reason}")
            return True

    logger.warning(f"Shadow strategy {strategy_id} not found")
    return False


def promote_best_from_evolution(
    store_dir: Path,
    shadow_pool_dir: Path,
    config: HandoffConfig = None,
    max_promote: int = 1,
) -> list[StrategyRecord]:
    """
    Promote the best strategies from evolution to shadow trading.

    This is the main entry point for automated handoff.

    Args:
        store_dir: Directory containing evolved strategies
        shadow_pool_dir: Directory for shadow strategies
        config: Handoff configuration
        max_promote: Maximum number of strategies to promote

    Returns:
        List of promoted strategy records
    """
    config = config or HandoffConfig()
    store = StrategyStore(store_dir)

    # Get all candidate strategies
    candidates = store.list_by_status("candidate")
    if not candidates:
        logger.info("No candidate strategies available for promotion")
        return []

    # Sort by fitness score
    candidates.sort(key=lambda r: r.final_score, reverse=True)

    promoted = []
    for record in candidates:
        if len(promoted) >= max_promote:
            break

        # Check qualification
        qualified, reason = qualify_for_shadow(record, config)
        if not qualified:
            logger.debug(f"Skipping {record.name}: {reason}")
            continue

        # Hand off to shadow
        success, message, path = handoff_to_shadow(record, shadow_pool_dir, config)
        if success:
            # Update in store
            store.save(record)
            promoted.append(record)
            logger.info(f"Promoted {record.name} to shadow pool")
        else:
            # Pool might be full
            if "full" in message.lower():
                break

    return promoted


def get_shadow_pool_summary(shadow_pool_dir: Path) -> dict:
    """
    Get summary statistics for the shadow pool.

    Args:
        shadow_pool_dir: Directory containing shadow strategies

    Returns:
        Dictionary with pool statistics
    """
    strategies = load_shadow_pool(shadow_pool_dir)

    if not strategies:
        return {
            "count": 0,
            "strategies": [],
        }

    return {
        "count": len(strategies),
        "strategies": [
            {
                "id": s.get("strategy_id"),
                "name": s.get("strategy_name"),
                "sharpe": s.get("backtest_sharpe"),
                "max_dd": s.get("backtest_max_dd"),
                "regime_passes": s.get("regime_pass_count"),
                "evolved_at": s.get("evolved_at"),
            }
            for s in strategies
        ],
        "avg_sharpe": sum(s.get("backtest_sharpe", 0) for s in strategies) / len(strategies),
        "avg_max_dd": sum(s.get("backtest_max_dd", 0) for s in strategies) / len(strategies),
    }
