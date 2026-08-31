"""
Tests for caching layer.
"""

import pytest
import time
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import sys
sys.path.insert(0, ".")

from data.cache import (
    Cache,
    CacheConfig,
    CacheEntry,
    CacheStats,
    cached,
    get_cache,
    set_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_false_when_valid(self):
        """Entry should not be expired when within TTL."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert entry.is_expired is False

    def test_is_expired_true_when_past_ttl(self):
        """Entry should be expired when past TTL."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        assert entry.is_expired is True

    def test_ttl_remaining(self):
        """Should correctly calculate remaining TTL."""
        entry = CacheEntry(
            key="test",
            value="data",
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=60),
        )
        # Should be approximately 60 seconds
        assert 58 <= entry.ttl_remaining <= 60


class TestCache:
    """Tests for Cache class."""

    @pytest.fixture
    def cache(self):
        """Create cache with short TTLs for testing."""
        config = CacheConfig(
            default_ttl=5,
            insider_ttl=10,
            financials_ttl=20,
        )
        return Cache(config)

    def test_set_and_get(self, cache):
        """Should store and retrieve values."""
        cache.set("key1", {"data": 123})
        result = cache.get("key1")
        assert result == {"data": 123}

    def test_get_nonexistent_returns_none(self, cache):
        """Should return None for nonexistent keys."""
        result = cache.get("nonexistent")
        assert result is None

    def test_expiration(self):
        """Should expire entries after TTL."""
        config = CacheConfig(default_ttl=1)  # 1 second TTL
        cache = Cache(config)

        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        # Wait for expiration
        time.sleep(1.5)

        assert cache.get("key1") is None

    def test_category_ttls(self, cache):
        """Should apply different TTLs for different categories."""
        cache.set("insider", "data", category=Cache.INSIDER)
        cache.set("financial", "data", category=Cache.FINANCIALS)

        # Check entries have different expiration times
        entry1 = cache._entries.get("insider")
        entry2 = cache._entries.get("financial")

        # Insider TTL is 10s, Financials is 20s
        assert entry1.ttl_remaining < entry2.ttl_remaining

    def test_delete(self, cache):
        """Should delete entries."""
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        result = cache.delete("key1")
        assert result is True
        assert cache.get("key1") is None

    def test_delete_nonexistent(self, cache):
        """Should return False when deleting nonexistent key."""
        result = cache.delete("nonexistent")
        assert result is False

    def test_clear_all(self, cache):
        """Should clear all entries."""
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        count = cache.clear()

        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_clear_by_category(self, cache):
        """Should clear only entries in specified category."""
        cache.set("insider1", "data1", category=Cache.INSIDER)
        cache.set("insider2", "data2", category=Cache.INSIDER)
        cache.set("financial1", "data3", category=Cache.FINANCIALS)

        count = cache.clear(category=Cache.INSIDER)

        assert count == 2
        assert cache.get("insider1") is None
        assert cache.get("financial1") == "data3"


class TestCacheStats:
    """Tests for cache statistics."""

    def test_hit_rate_calculation(self):
        """Should correctly calculate hit rate."""
        stats = CacheStats(hits=7, misses=3)
        assert stats.hit_rate == 0.7

    def test_hit_rate_zero_requests(self):
        """Should return 0 when no requests."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_stats_tracking(self):
        """Cache should track statistics."""
        config = CacheConfig(default_ttl=60)
        cache = Cache(config)

        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats()

        assert stats.sets == 1
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.hit_rate == pytest.approx(0.667, rel=0.01)


class TestCachedDecorator:
    """Tests for @cached decorator."""

    def test_caches_function_result(self):
        """Should cache function results."""
        config = CacheConfig(default_ttl=60)
        cache = Cache(config)

        call_count = 0

        @cached(cache, category="default")
        def expensive_func(x):
            nonlocal call_count
            call_count += 1
            return x * 2

        # First call - should execute function
        result1 = expensive_func(5)
        assert result1 == 10
        assert call_count == 1

        # Second call - should use cache
        result2 = expensive_func(5)
        assert result2 == 10
        assert call_count == 1  # Not incremented

        # Different argument - should execute function
        result3 = expensive_func(10)
        assert result3 == 20
        assert call_count == 2

    def test_cache_key_includes_args(self):
        """Should create unique cache keys for different arguments."""
        config = CacheConfig(default_ttl=60)
        cache = Cache(config)

        @cached(cache)
        def func(a, b):
            return a + b

        func(1, 2)
        func(3, 4)

        stats = cache.stats()
        assert stats.entries == 2  # Two different cache entries


class TestCachePersistence:
    """Tests for cache persistence to disk."""

    def test_save_and_load(self):
        """Should save cache to disk and reload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "cache.pkl"

            # Create and populate cache
            config = CacheConfig(
                default_ttl=3600,
                persist_path=persist_path,
            )
            cache1 = Cache(config)
            cache1.set("key1", {"data": 123})
            cache1.set("key2", [1, 2, 3])
            cache1._save_to_disk()

            # Create new cache and load
            cache2 = Cache(config)

            assert cache2.get("key1") == {"data": 123}
            assert cache2.get("key2") == [1, 2, 3]

    def test_expired_entries_not_loaded(self):
        """Should not load expired entries from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            persist_path = Path(tmpdir) / "cache.pkl"

            # Create cache with short TTL
            config = CacheConfig(
                default_ttl=1,  # 1 second
                persist_path=persist_path,
            )
            cache1 = Cache(config)
            cache1.set("key1", "value1")
            cache1._save_to_disk()

            # Wait for expiration
            time.sleep(1.5)

            # Load - should not include expired entry
            cache2 = Cache(config)
            assert cache2.get("key1") is None


class TestCacheCleanup:
    """Tests for cache cleanup functionality."""

    def test_cleanup_removes_expired(self):
        """Cleanup should remove expired entries."""
        config = CacheConfig(default_ttl=1)
        cache = Cache(config)

        cache.set("key1", "value1")
        cache.set("key2", "value2")

        time.sleep(1.5)

        # Add new entry to avoid empty cache
        cache.set("key3", "value3")

        removed = cache._cleanup()

        assert removed >= 2  # key1 and key2 should be removed
        assert cache.get("key3") == "value3"  # key3 should remain


class TestGlobalCache:
    """Tests for global cache functions."""

    def test_get_cache_creates_singleton(self):
        """get_cache should return same instance."""
        # Reset global cache
        set_cache(None)

        cache1 = get_cache()
        cache2 = get_cache()

        assert cache1 is cache2

    def test_set_cache_replaces_global(self):
        """set_cache should replace global instance."""
        custom_cache = Cache(CacheConfig(default_ttl=999))
        set_cache(custom_cache)

        assert get_cache() is custom_cache


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
