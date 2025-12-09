"""
Strategy persistence - save/load evolved strategies to JSON files.

Provides a simple file-based strategy store with:
- Save strategies with full metadata
- Load strategies for shadow trading or live trading
- List all saved strategies with filtering
- Delete obsolete strategies
"""
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass
class StrategyRecord:
    """
    Complete strategy record with metadata.

    Contains everything needed to reproduce and trade the strategy.
    """
    # Identity
    id: str  # Unique ID (uuid)
    name: str  # Human-readable name

    # Strategy logic (required fields)
    entry_long: str
    exit_long: str

    # Optional fields with defaults
    version: int = 1  # Version for tracking mutations
    entry_short: Optional[str] = None
    exit_short: Optional[str] = None

    # Metadata
    asset_class: str = "crypto"  # crypto, forex, etc.
    target_symbols: list[str] = field(default_factory=list)
    market_filter: str = "btc_trend"  # btc_trend for crypto, dxy_trend for forex

    # Evolution metadata
    rationale: Optional[str] = None
    parent_id: Optional[str] = None  # ID of parent strategy (if mutated)
    generation: int = 0  # Evolution generation this was created in
    mutation_type: Optional[str] = None
    mutation_description: Optional[str] = None

    # Performance metrics (from backtest)
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    trade_count: int = 0
    total_return: float = 0.0
    final_score: float = 0.0

    # Regime performance
    regime_scores: dict[str, float] = field(default_factory=dict)
    regime_pass_count: int = 0

    # Status
    status: str = "candidate"  # candidate, shadow, live, retired
    created_at: str = ""
    updated_at: str = ""
    shadow_start: Optional[str] = None
    live_start: Optional[str] = None
    retired_at: Optional[str] = None
    retired_reason: Optional[str] = None

    # Notes
    notes: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyRecord":
        """Create from dictionary."""
        # Handle missing fields gracefully
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)

    def to_trading_dict(self) -> dict:
        """Convert to minimal dict format for trading parser."""
        return {
            "strategy_name": self.name,
            "entry_long": self.entry_long,
            "exit_long": self.exit_long,
            "entry_short": self.entry_short,
            "exit_short": self.exit_short,
        }

    def update_timestamp(self):
        """Update the updated_at timestamp."""
        self.updated_at = datetime.utcnow().isoformat()

    def promote_to_shadow(self):
        """Mark strategy as in shadow trading."""
        self.status = "shadow"
        self.shadow_start = datetime.utcnow().isoformat()
        self.update_timestamp()

    def promote_to_live(self):
        """Mark strategy as live trading."""
        self.status = "live"
        self.live_start = datetime.utcnow().isoformat()
        self.update_timestamp()

    def retire(self, reason: str = ""):
        """Mark strategy as retired."""
        self.status = "retired"
        self.retired_at = datetime.utcnow().isoformat()
        self.retired_reason = reason
        self.update_timestamp()


class StrategyStore:
    """
    File-based strategy store.

    Stores each strategy as a JSON file in the store directory.
    Filename format: {id}_{name}.json

    Usage:
        store = StrategyStore(Path("./strategies"))

        # Save a strategy
        record = StrategyRecord(...)
        store.save(record)

        # Load a strategy
        record = store.load("strategy-id")

        # List all strategies
        strategies = store.list_all()

        # List by status
        shadow_strategies = store.list_by_status("shadow")
    """

    def __init__(self, store_dir: Path):
        """
        Initialize strategy store.

        Args:
            store_dir: Directory to store strategy JSON files
        """
        self.store_dir = Path(store_dir)
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, record: StrategyRecord) -> Path:
        """
        Save a strategy record.

        Args:
            record: Strategy record to save

        Returns:
            Path to saved file
        """
        record.update_timestamp()

        # Create safe filename
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in record.name)
        filename = f"{record.id}_{safe_name}.json"
        filepath = self.store_dir / filename

        with open(filepath, "w") as f:
            json.dump(record.to_dict(), f, indent=2)

        logger.info(f"Saved strategy: {record.name} ({record.id}) to {filepath}")
        return filepath

    def load(self, strategy_id: str) -> Optional[StrategyRecord]:
        """
        Load a strategy by ID.

        Args:
            strategy_id: Strategy ID (uuid)

        Returns:
            StrategyRecord or None if not found
        """
        # Find file matching ID
        for filepath in self.store_dir.glob("*.json"):
            if filepath.stem.startswith(strategy_id):
                try:
                    with open(filepath, "r") as f:
                        data = json.load(f)
                    return StrategyRecord.from_dict(data)
                except Exception as e:
                    logger.error(f"Failed to load {filepath}: {e}")
                    return None

        logger.warning(f"Strategy not found: {strategy_id}")
        return None

    def load_by_name(self, name: str) -> Optional[StrategyRecord]:
        """
        Load a strategy by name.

        Args:
            name: Strategy name

        Returns:
            StrategyRecord or None if not found
        """
        for record in self.list_all():
            if record.name == name:
                return record
        return None

    def delete(self, strategy_id: str) -> bool:
        """
        Delete a strategy by ID.

        Args:
            strategy_id: Strategy ID

        Returns:
            True if deleted, False if not found
        """
        for filepath in self.store_dir.glob("*.json"):
            if filepath.stem.startswith(strategy_id):
                filepath.unlink()
                logger.info(f"Deleted strategy: {strategy_id}")
                return True
        return False

    def list_all(self) -> list[StrategyRecord]:
        """
        List all strategies.

        Returns:
            List of all strategy records, sorted by final_score descending
        """
        records = []
        for filepath in self.store_dir.glob("*.json"):
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                records.append(StrategyRecord.from_dict(data))
            except Exception as e:
                logger.error(f"Failed to load {filepath}: {e}")

        # Sort by final score (best first)
        records.sort(key=lambda r: r.final_score, reverse=True)
        return records

    def list_by_status(self, status: str) -> list[StrategyRecord]:
        """
        List strategies by status.

        Args:
            status: Status to filter by (candidate, shadow, live, retired)

        Returns:
            List of matching strategy records
        """
        return [r for r in self.list_all() if r.status == status]

    def list_by_asset_class(self, asset_class: str) -> list[StrategyRecord]:
        """
        List strategies by asset class.

        Args:
            asset_class: Asset class to filter by (crypto, forex)

        Returns:
            List of matching strategy records
        """
        return [r for r in self.list_all() if r.asset_class == asset_class]

    def get_best(self,
                 asset_class: Optional[str] = None,
                 status: Optional[str] = None,
                 min_score: float = 0.0) -> Optional[StrategyRecord]:
        """
        Get the best strategy matching criteria.

        Args:
            asset_class: Filter by asset class
            status: Filter by status
            min_score: Minimum final score

        Returns:
            Best matching strategy or None
        """
        records = self.list_all()

        if asset_class:
            records = [r for r in records if r.asset_class == asset_class]
        if status:
            records = [r for r in records if r.status == status]
        records = [r for r in records if r.final_score >= min_score]

        return records[0] if records else None


# Convenience functions for common operations

def save_strategy(
    store_dir: Path,
    name: str,
    entry_long: str,
    exit_long: str,
    sharpe_ratio: float = 0.0,
    max_drawdown: float = 0.0,
    win_rate: float = 0.0,
    trade_count: int = 0,
    final_score: float = 0.0,
    asset_class: str = "crypto",
    target_symbols: list[str] = None,
    market_filter: str = "btc_trend",
    regime_scores: dict[str, float] = None,
    regime_pass_count: int = 0,
    generation: int = 0,
    parent_id: Optional[str] = None,
    rationale: Optional[str] = None,
    mutation_type: Optional[str] = None,
    mutation_description: Optional[str] = None,
    **kwargs,
) -> StrategyRecord:
    """
    Save a strategy with common parameters.

    Returns the saved StrategyRecord.
    """
    store = StrategyStore(store_dir)

    record = StrategyRecord(
        id=str(uuid.uuid4())[:8],  # Short UUID for readability
        name=name,
        entry_long=entry_long,
        exit_long=exit_long,
        asset_class=asset_class,
        target_symbols=target_symbols or [],
        market_filter=market_filter,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        win_rate=win_rate,
        trade_count=trade_count,
        final_score=final_score,
        regime_scores=regime_scores or {},
        regime_pass_count=regime_pass_count,
        generation=generation,
        parent_id=parent_id,
        rationale=rationale,
        mutation_type=mutation_type,
        mutation_description=mutation_description,
    )

    store.save(record)
    return record


def load_strategy(store_dir: Path, strategy_id: str) -> Optional[StrategyRecord]:
    """Load a strategy by ID."""
    store = StrategyStore(store_dir)
    return store.load(strategy_id)


def list_strategies(
    store_dir: Path,
    status: Optional[str] = None,
    asset_class: Optional[str] = None,
) -> list[StrategyRecord]:
    """List strategies with optional filtering."""
    store = StrategyStore(store_dir)

    if status:
        return store.list_by_status(status)
    elif asset_class:
        return store.list_by_asset_class(asset_class)
    else:
        return store.list_all()


def delete_strategy(store_dir: Path, strategy_id: str) -> bool:
    """Delete a strategy by ID."""
    store = StrategyStore(store_dir)
    return store.delete(strategy_id)
