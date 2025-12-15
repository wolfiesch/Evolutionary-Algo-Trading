"""
Caching Layer for Equities Swing Trading.

Provides TTL-based caching for EDGAR and market data:
- Insider trades: 24 hours (Form 4s filed within 2 days)
- Financials: 7 days (10-K/10-Q are quarterly)
- Company info: 30 days (rarely changes)
- Market data: 1 hour (for intraday updates)

Supports both in-memory and optional disk persistence.
"""

import json
import logging
import hashlib
import pickle
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheConfig:
    """Configuration for cache layer."""
    # Default TTLs in seconds
    insider_ttl: int = 24 * 60 * 60      # 24 hours
    financials_ttl: int = 7 * 24 * 60 * 60  # 7 days
    company_info_ttl: int = 30 * 24 * 60 * 60  # 30 days
    market_data_ttl: int = 60 * 60        # 1 hour
    default_ttl: int = 60 * 60            # 1 hour default

    # Persistence
    persist_path: Optional[Path] = None
    persist_on_write: bool = False  # Auto-save on each write

    # Memory limits
    max_entries: int = 10000
    cleanup_threshold: float = 0.9  # Cleanup when 90% full


@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: datetime
    category: str = "default"
    hits: int = 0

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at

    @property
    def ttl_remaining(self) -> float:
        """Remaining TTL in seconds."""
        return max(0, (self.expires_at - datetime.utcnow()).total_seconds())


class CacheError(Exception):
    """Base exception for cache errors."""
    pass


class Cache:
    """
    TTL-based in-memory cache with optional disk persistence.

    Thread-safe implementation supporting different TTLs per category.
    """

    # Category constants
    INSIDER = "insider"
    FINANCIALS = "financials"
    COMPANY_INFO = "company_info"
    MARKET_DATA = "market_data"

    def __init__(self, config: Optional[CacheConfig] = None):
        """
        Initialize cache.

        Args:
            config: Cache configuration. Uses defaults if not provided.
        """
        self.config = config or CacheConfig()
        self._entries: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = CacheStats()

        # Load from disk if persistence enabled
        if self.config.persist_path and self.config.persist_path.exists():
            self._load_from_disk()

    def _get_ttl(self, category: str) -> int:
        """Get TTL for a category in seconds."""
        ttl_map = {
            self.INSIDER: self.config.insider_ttl,
            self.FINANCIALS: self.config.financials_ttl,
            self.COMPANY_INFO: self.config.company_info_ttl,
            self.MARKET_DATA: self.config.market_data_ttl,
        }
        return ttl_map.get(category, self.config.default_ttl)

    def _make_key(self, *args, **kwargs) -> str:
        """Create cache key from arguments."""
        key_parts = [str(a) for a in args]
        key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
        key_string = ":".join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()

    def get(
        self,
        key: str,
        category: str = "default",
    ) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key
            category: Cache category (for TTL lookup)

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._entries.get(key)

            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired:
                del self._entries[key]
                self._stats.misses += 1
                self._stats.expirations += 1
                return None

            entry.hits += 1
            self._stats.hits += 1
            return entry.value

    def set(
        self,
        key: str,
        value: Any,
        category: str = "default",
        ttl: Optional[int] = None,
    ) -> None:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            category: Cache category
            ttl: Optional custom TTL (uses category default if not specified)
        """
        if ttl is None:
            ttl = self._get_ttl(category)

        now = datetime.utcnow()

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
            category=category,
        )

        with self._lock:
            # Check if cleanup needed
            if len(self._entries) >= self.config.max_entries * self.config.cleanup_threshold:
                self._cleanup()

            self._entries[key] = entry
            self._stats.sets += 1

        # Persist if enabled
        if self.config.persist_on_write and self.config.persist_path:
            self._save_to_disk()

    def delete(self, key: str) -> bool:
        """
        Delete entry from cache.

        Returns:
            True if entry was deleted, False if not found
        """
        with self._lock:
            if key in self._entries:
                del self._entries[key]
                return True
            return False

    def clear(self, category: Optional[str] = None) -> int:
        """
        Clear cache entries.

        Args:
            category: If specified, only clear entries in this category

        Returns:
            Number of entries cleared
        """
        with self._lock:
            if category is None:
                count = len(self._entries)
                self._entries.clear()
                return count

            keys_to_delete = [
                k for k, v in self._entries.items()
                if v.category == category
            ]
            for k in keys_to_delete:
                del self._entries[k]
            return len(keys_to_delete)

    def _cleanup(self) -> int:
        """
        Remove expired entries and oldest entries if over limit.

        Returns:
            Number of entries removed
        """
        removed = 0

        with self._lock:
            # First pass: remove expired
            expired_keys = [
                k for k, v in self._entries.items()
                if v.is_expired
            ]
            for k in expired_keys:
                del self._entries[k]
                removed += 1

            # Second pass: if still over limit, remove oldest
            if len(self._entries) >= self.config.max_entries:
                # Sort by created_at, remove oldest
                sorted_entries = sorted(
                    self._entries.items(),
                    key=lambda x: x[1].created_at
                )
                to_remove = len(self._entries) - int(self.config.max_entries * 0.8)

                for key, _ in sorted_entries[:to_remove]:
                    del self._entries[key]
                    removed += 1

        self._stats.cleanups += 1
        logger.debug(f"Cache cleanup: removed {removed} entries")

        return removed

    def _save_to_disk(self) -> None:
        """Save cache to disk."""
        if not self.config.persist_path:
            return

        try:
            with self._lock:
                data = {
                    "version": 1,
                    "saved_at": datetime.utcnow().isoformat(),
                    "entries": {
                        k: {
                            "value": v.value,
                            "created_at": v.created_at.isoformat(),
                            "expires_at": v.expires_at.isoformat(),
                            "category": v.category,
                        }
                        for k, v in self._entries.items()
                        if not v.is_expired
                    }
                }

            self.config.persist_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config.persist_path, "wb") as f:
                pickle.dump(data, f)

            logger.debug(f"Cache saved to {self.config.persist_path}")

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def _load_from_disk(self) -> None:
        """Load cache from disk."""
        if not self.config.persist_path or not self.config.persist_path.exists():
            return

        try:
            with open(self.config.persist_path, "rb") as f:
                data = pickle.load(f)

            if data.get("version") != 1:
                logger.warning("Cache version mismatch, skipping load")
                return

            loaded = 0
            for key, entry_data in data.get("entries", {}).items():
                expires_at = datetime.fromisoformat(entry_data["expires_at"])

                # Skip if already expired
                if expires_at <= datetime.utcnow():
                    continue

                entry = CacheEntry(
                    key=key,
                    value=entry_data["value"],
                    created_at=datetime.fromisoformat(entry_data["created_at"]),
                    expires_at=expires_at,
                    category=entry_data["category"],
                )

                self._entries[key] = entry
                loaded += 1

            logger.info(f"Loaded {loaded} entries from cache file")

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")

    def stats(self) -> "CacheStats":
        """Get cache statistics."""
        with self._lock:
            self._stats.entries = len(self._entries)
            self._stats.categories = {}
            for entry in self._entries.values():
                cat = entry.category
                if cat not in self._stats.categories:
                    self._stats.categories[cat] = 0
                self._stats.categories[cat] += 1

        return self._stats


@dataclass
class CacheStats:
    """Cache statistics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    expirations: int = 0
    cleanups: int = 0
    entries: int = 0
    categories: dict[str, int] = field(default_factory=dict)

    @property
    def hit_rate(self) -> float:
        """Cache hit rate (0.0 to 1.0)."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total


# =============================================================================
# CACHING DECORATOR
# =============================================================================

def cached(
    cache: Cache,
    category: str = "default",
    ttl: Optional[int] = None,
    key_prefix: str = "",
) -> Callable:
    """
    Decorator for caching function results.

    Args:
        cache: Cache instance to use
        category: Cache category (determines TTL)
        ttl: Optional custom TTL
        key_prefix: Optional prefix for cache keys

    Example:
        @cached(cache, category=Cache.INSIDER)
        def get_insider_trades(symbol: str, days: int) -> InsiderSummary:
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # Build cache key
            key_parts = [key_prefix, func.__name__] if key_prefix else [func.__name__]
            key_parts.extend(str(a) for a in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key = ":".join(key_parts)

            # Check cache
            result = cache.get(key, category)
            if result is not None:
                return result

            # Call function
            result = func(*args, **kwargs)

            # Cache result
            cache.set(key, result, category, ttl)

            return result

        return wrapper
    return decorator


# =============================================================================
# GLOBAL CACHE INSTANCE
# =============================================================================

_global_cache: Optional[Cache] = None


def get_cache(config: Optional[CacheConfig] = None) -> Cache:
    """
    Get or create global cache instance.

    Args:
        config: Configuration for new cache (ignored if cache exists)

    Returns:
        Global cache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = Cache(config)
    return _global_cache


def set_cache(cache: Cache) -> None:
    """Set global cache instance (useful for testing)."""
    global _global_cache
    _global_cache = cache


# =============================================================================
# QUICK TEST
# =============================================================================

def quick_test():
    """Test cache functionality."""
    print("Testing cache layer...")

    # Create cache with short TTLs for testing
    config = CacheConfig(
        default_ttl=5,
        insider_ttl=10,
    )
    cache = Cache(config)

    # Test basic set/get
    cache.set("test1", {"value": 123}, category=Cache.INSIDER)
    result = cache.get("test1")
    assert result == {"value": 123}, "Basic set/get failed"
    print("✓ Basic set/get works")

    # Test hit rate
    cache.get("test1")  # Hit
    cache.get("nonexistent")  # Miss
    stats = cache.stats()
    print(f"✓ Hit rate: {stats.hit_rate:.1%}")

    # Test decorator
    @cached(cache, category=Cache.FINANCIALS)
    def expensive_function(x: int) -> int:
        print(f"  Computing {x}...")
        return x * 2

    print("Testing cached decorator:")
    result1 = expensive_function(5)  # Should compute
    result2 = expensive_function(5)  # Should hit cache
    assert result1 == result2 == 10
    print("✓ Decorator caching works")

    # Test clear
    cache.clear()
    stats = cache.stats()
    assert stats.entries == 0, "Clear failed"
    print("✓ Clear works")

    print("\n✓ All cache tests passed")


if __name__ == "__main__":
    quick_test()
