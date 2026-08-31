"""
Data Snapshot Module - freeze dataset for reproducible evolution runs.

Prevents issues where backfill running concurrently changes data mid-run.
Creates a frozen copy of data with metadata for audit trail.

Usage:
    # Create snapshot
    snapshot = DataSnapshot.create(
        candles_df=symbol_df,
        benchmark_df=btc_df,
        symbol="SOLUSDT",
        snapshot_dir=Path("crypto/data/snapshots"),
    )

    # Load snapshot
    snapshot = DataSnapshot.load(snapshot_id="snap_20251215_093400")
    symbol_df = snapshot.candles
    btc_df = snapshot.benchmark
"""
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class SnapshotMetadata:
    """Metadata about a data snapshot."""
    snapshot_id: str
    created_at: str
    symbol: str
    candle_count: int
    benchmark_count: int
    start_timestamp: int
    end_timestamp: int
    data_hash: str
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "symbol": self.symbol,
            "candle_count": self.candle_count,
            "benchmark_count": self.benchmark_count,
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "data_hash": self.data_hash,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SnapshotMetadata":
        return cls(
            snapshot_id=data["snapshot_id"],
            created_at=data["created_at"],
            symbol=data["symbol"],
            candle_count=data["candle_count"],
            benchmark_count=data["benchmark_count"],
            start_timestamp=data["start_timestamp"],
            end_timestamp=data["end_timestamp"],
            data_hash=data["data_hash"],
            notes=data.get("notes", ""),
        )


@dataclass
class DataSnapshot:
    """Frozen snapshot of candle data for reproducible backtesting."""
    metadata: SnapshotMetadata
    candles: pd.DataFrame
    benchmark: pd.DataFrame
    snapshot_dir: Path = field(default_factory=lambda: Path("data/snapshots"))

    @classmethod
    def create(
        cls,
        candles_df: pd.DataFrame,
        benchmark_df: pd.DataFrame,
        symbol: str,
        snapshot_dir: Path,
        notes: str = "",
    ) -> "DataSnapshot":
        """
        Create a new data snapshot.

        Args:
            candles_df: Trading symbol OHLCV data
            benchmark_df: Benchmark (BTC) OHLCV data
            symbol: Symbol name
            snapshot_dir: Directory to save snapshots
            notes: Optional notes about this snapshot

        Returns:
            DataSnapshot with metadata and data saved to disk
        """
        snapshot_dir = Path(snapshot_dir)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Generate snapshot ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"snap_{symbol}_{timestamp}"

        # Compute data hash for integrity checking
        data_hash = cls._compute_hash(candles_df, benchmark_df)

        # Extract timestamps
        if 'timestamp' in candles_df.columns:
            start_ts = int(candles_df['timestamp'].iloc[0])
            end_ts = int(candles_df['timestamp'].iloc[-1])
        else:
            start_ts = 0
            end_ts = len(candles_df)

        # Create metadata
        metadata = SnapshotMetadata(
            snapshot_id=snapshot_id,
            created_at=datetime.now().isoformat(),
            symbol=symbol,
            candle_count=len(candles_df),
            benchmark_count=len(benchmark_df),
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            data_hash=data_hash,
            notes=notes,
        )

        # Create snapshot
        snapshot = cls(
            metadata=metadata,
            candles=candles_df.copy(),
            benchmark=benchmark_df.copy(),
            snapshot_dir=snapshot_dir,
        )

        # Save to disk
        snapshot.save()

        logger.info(f"Created snapshot: {snapshot_id}")
        logger.info(f"  Symbol: {symbol}, Candles: {len(candles_df)}, Benchmark: {len(benchmark_df)}")
        logger.info(f"  Timestamp range: {start_ts} - {end_ts}")
        logger.info(f"  Data hash: {data_hash[:16]}...")

        return snapshot

    def save(self):
        """Save snapshot to disk."""
        snapshot_path = self.snapshot_dir / self.metadata.snapshot_id
        snapshot_path.mkdir(parents=True, exist_ok=True)

        # Save metadata
        metadata_file = snapshot_path / "metadata.json"
        with open(metadata_file, "w") as f:
            json.dump(self.metadata.to_dict(), f, indent=2)

        # Save data as parquet (efficient, compressed)
        candles_file = snapshot_path / "candles.parquet"
        benchmark_file = snapshot_path / "benchmark.parquet"

        self.candles.to_parquet(candles_file, index=False)
        self.benchmark.to_parquet(benchmark_file, index=False)

        logger.debug(f"Saved snapshot to: {snapshot_path}")

    @classmethod
    def load(
        cls,
        snapshot_id: str,
        snapshot_dir: Path,
        verify_hash: bool = True,
    ) -> Optional["DataSnapshot"]:
        """
        Load a snapshot from disk.

        Args:
            snapshot_id: Snapshot ID to load
            snapshot_dir: Directory containing snapshots
            verify_hash: If True, verify data integrity via hash

        Returns:
            DataSnapshot or None if not found/invalid
        """
        snapshot_path = Path(snapshot_dir) / snapshot_id

        if not snapshot_path.exists():
            logger.error(f"Snapshot not found: {snapshot_path}")
            return None

        # Load metadata
        metadata_file = snapshot_path / "metadata.json"
        with open(metadata_file) as f:
            metadata = SnapshotMetadata.from_dict(json.load(f))

        # Load data
        candles_file = snapshot_path / "candles.parquet"
        benchmark_file = snapshot_path / "benchmark.parquet"

        candles = pd.read_parquet(candles_file)
        benchmark = pd.read_parquet(benchmark_file)

        # Verify hash
        if verify_hash:
            actual_hash = cls._compute_hash(candles, benchmark)
            if actual_hash != metadata.data_hash:
                logger.error(
                    f"Snapshot hash mismatch! Expected {metadata.data_hash}, "
                    f"got {actual_hash}. Data may be corrupted."
                )
                return None

        logger.info(f"Loaded snapshot: {snapshot_id}")
        logger.info(f"  Created: {metadata.created_at}")
        logger.info(f"  Symbol: {metadata.symbol}, Candles: {len(candles)}, Benchmark: {len(benchmark)}")

        return cls(
            metadata=metadata,
            candles=candles,
            benchmark=benchmark,
            snapshot_dir=Path(snapshot_dir),
        )

    @staticmethod
    def _compute_hash(candles: pd.DataFrame, benchmark: pd.DataFrame) -> str:
        """Compute hash of data for integrity verification."""
        # Use first/last 10 rows + shape for fast hash
        candle_sample = pd.concat([candles.head(10), candles.tail(10)])
        bench_sample = pd.concat([benchmark.head(10), benchmark.tail(10)])

        combined = (
            f"candles:{len(candles)}:{candle_sample.to_json()}"
            f"benchmark:{len(benchmark)}:{bench_sample.to_json()}"
        )

        return hashlib.sha256(combined.encode()).hexdigest()

    @classmethod
    def list_snapshots(cls, snapshot_dir: Path) -> list[SnapshotMetadata]:
        """List all available snapshots."""
        snapshot_dir = Path(snapshot_dir)
        if not snapshot_dir.exists():
            return []

        snapshots = []
        for snap_path in snapshot_dir.iterdir():
            if snap_path.is_dir() and snap_path.name.startswith("snap_"):
                metadata_file = snap_path / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file) as f:
                        metadata = SnapshotMetadata.from_dict(json.load(f))
                        snapshots.append(metadata)

        # Sort by creation time (newest first)
        snapshots.sort(key=lambda m: m.created_at, reverse=True)
        return snapshots


def create_run_snapshot(
    candles_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    symbol: str,
    snapshot_dir: Path,
    run_id: str = None,
) -> DataSnapshot:
    """
    Convenience function to create a snapshot for an evolution run.

    Args:
        candles_df: Trading symbol data
        benchmark_df: Benchmark data
        symbol: Symbol name
        snapshot_dir: Directory for snapshots
        run_id: Optional run identifier

    Returns:
        DataSnapshot saved to disk
    """
    notes = f"Evolution run{f' {run_id}' if run_id else ''}"
    return DataSnapshot.create(
        candles_df=candles_df,
        benchmark_df=benchmark_df,
        symbol=symbol,
        snapshot_dir=snapshot_dir,
        notes=notes,
    )
