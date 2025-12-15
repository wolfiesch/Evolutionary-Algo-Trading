"""
Strategy Deduplication - prevents re-evaluating identical strategies.

Strategies are hashed by their canonical form (normalized entry/exit conditions),
not by name. This catches:
- Exact duplicates from LLM regenerating the same strategy
- Near-duplicates with minor whitespace/formatting differences
- Renamed strategies that are functionally identical

Usage:
    dedup = StrategyDeduplicator()

    # Check before evaluation
    if dedup.is_duplicate(strategy):
        cached_fitness = dedup.get_cached_fitness(strategy)
    else:
        fitness = evaluate(strategy)
        dedup.register(strategy, fitness)
"""
import hashlib
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

from shared.evolution.fitness.models import FitnessResult

logger = logging.getLogger(__name__)


@dataclass
class DeduplicationStats:
    """Statistics about deduplication performance."""
    total_seen: int = 0
    duplicates_found: int = 0
    evaluations_saved: int = 0
    unique_strategies: int = 0

    @property
    def duplicate_rate(self) -> float:
        """Percentage of strategies that were duplicates."""
        if self.total_seen == 0:
            return 0.0
        return self.duplicates_found / self.total_seen * 100

    def summary(self) -> str:
        """Return summary string."""
        return (
            f"Dedup: {self.duplicates_found}/{self.total_seen} duplicates "
            f"({self.duplicate_rate:.1f}%), {self.evaluations_saved} evals saved, "
            f"{self.unique_strategies} unique strategies"
        )


class StrategyDeduplicator:
    """
    Detects and caches duplicate strategies to avoid redundant evaluation.

    Canonicalization rules:
    1. Lowercase everything
    2. Remove all whitespace
    3. Sort conditions within AND clauses alphabetically
    4. Round numeric constants to 1 decimal place
    5. Normalize comparison operators (>= and > are distinct)

    The hash is computed from (canonical_entry_long, canonical_exit_long).
    Strategy name is ignored since it often contains version suffixes.
    """

    def __init__(self):
        """Initialize deduplicator with empty cache."""
        # Maps canonical_hash -> (strategy_name, FitnessResult)
        self._cache: dict[str, tuple[str, FitnessResult]] = {}
        self._stats = DeduplicationStats()

    @property
    def stats(self) -> DeduplicationStats:
        """Get deduplication statistics."""
        return self._stats

    def canonicalize(self, expression: str) -> str:
        """
        Convert a strategy expression to canonical form.

        Args:
            expression: Entry or exit condition string

        Returns:
            Canonicalized string for hashing
        """
        if not expression:
            return ""

        # 1. Lowercase
        expr = expression.lower()

        # 2. Remove all whitespace
        expr = re.sub(r'\s+', '', expr)

        # 3. Normalize numeric constants to 1 decimal place
        # Match patterns like (14), (9,21), (-0.4), (0.6)
        def normalize_numbers(match):
            num_str = match.group(1)
            try:
                # Handle integers and floats
                num = float(num_str)
                if num == int(num):
                    return str(int(num))
                return f"{num:.1f}"
            except ValueError:
                return num_str

        # Match numbers in various contexts
        expr = re.sub(r'([+-]?\d+\.?\d*)', normalize_numbers, expr)

        # 4. Sort conditions within AND clauses
        # Split by AND, sort, rejoin
        if ' and ' in expression.lower() or 'and' in expr:
            # Split on 'and' (case-insensitive, already lowercased)
            parts = re.split(r'and', expr)
            # Sort and rejoin
            parts = sorted([p.strip() for p in parts if p.strip()])
            expr = 'AND'.join(parts)

        return expr

    def compute_hash(self, entry_long: str, exit_long: str) -> str:
        """
        Compute canonical hash for a strategy.

        Args:
            entry_long: Entry condition
            exit_long: Exit condition

        Returns:
            SHA256 hash of canonical form (first 16 chars)
        """
        canonical_entry = self.canonicalize(entry_long)
        canonical_exit = self.canonicalize(exit_long)

        combined = f"ENTRY:{canonical_entry}|EXIT:{canonical_exit}"

        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def get_strategy_hash(self, strategy) -> str:
        """
        Get hash for a GeneratedStrategy object.

        Args:
            strategy: GeneratedStrategy instance

        Returns:
            Canonical hash string
        """
        return self.compute_hash(strategy.entry_long, strategy.exit_long)

    def is_duplicate(self, strategy) -> bool:
        """
        Check if strategy is a duplicate of one already seen.

        Args:
            strategy: GeneratedStrategy to check

        Returns:
            True if duplicate, False if new
        """
        self._stats.total_seen += 1

        strategy_hash = self.get_strategy_hash(strategy)
        is_dup = strategy_hash in self._cache

        if is_dup:
            self._stats.duplicates_found += 1
            original_name, _ = self._cache[strategy_hash]
            logger.debug(
                f"Duplicate detected: '{strategy.name}' matches '{original_name}' "
                f"(hash: {strategy_hash})"
            )

        return is_dup

    def get_cached_fitness(self, strategy) -> Optional[FitnessResult]:
        """
        Get cached fitness for a duplicate strategy.

        Args:
            strategy: GeneratedStrategy to look up

        Returns:
            Cached FitnessResult or None if not found
        """
        strategy_hash = self.get_strategy_hash(strategy)

        if strategy_hash in self._cache:
            self._stats.evaluations_saved += 1
            _, fitness = self._cache[strategy_hash]
            return fitness

        return None

    def register(self, strategy, fitness: FitnessResult):
        """
        Register a strategy and its fitness in the cache.

        Args:
            strategy: GeneratedStrategy that was evaluated
            fitness: FitnessResult from evaluation
        """
        strategy_hash = self.get_strategy_hash(strategy)

        if strategy_hash not in self._cache:
            self._cache[strategy_hash] = (strategy.name, fitness)
            self._stats.unique_strategies += 1

    def clear(self):
        """Clear the cache (useful between runs)."""
        self._cache.clear()
        self._stats = DeduplicationStats()

    def get_unique_count(self) -> int:
        """Get number of unique strategies seen."""
        return len(self._cache)

    def export_hashes(self) -> dict[str, str]:
        """
        Export hash -> strategy name mapping.

        Useful for debugging and analysis.
        """
        return {h: name for h, (name, _) in self._cache.items()}


def deduplicate_population(
    strategies: list,
    deduplicator: Optional[StrategyDeduplicator] = None,
) -> list:
    """
    Remove duplicate strategies from a list.

    Args:
        strategies: List of GeneratedStrategy objects
        deduplicator: Optional existing deduplicator (creates new if None)

    Returns:
        List with duplicates removed (keeps first occurrence)
    """
    if deduplicator is None:
        deduplicator = StrategyDeduplicator()

    unique = []
    seen_hashes = set()

    for strategy in strategies:
        strategy_hash = deduplicator.get_strategy_hash(strategy)

        if strategy_hash not in seen_hashes:
            seen_hashes.add(strategy_hash)
            unique.append(strategy)
        else:
            logger.debug(f"Removing duplicate from population: {strategy.name}")

    removed = len(strategies) - len(unique)
    if removed > 0:
        logger.info(f"Deduplication: removed {removed} duplicates, {len(unique)} unique remain")

    return unique
