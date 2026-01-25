"""Disk-based caching for API responses."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import diskcache
import platformdirs


if TYPE_CHECKING:
    from diskcache import Cache


# Default TTLs in seconds
TTL_USER_STAT = 24 * 60 * 60  # 24 hours - follower / following counts change slowly
TTL_USER_ACTIVITY = 6 * 60 * 60  # 6 hours - post activity changes more often

# Cache size limit (10 MB - sufficient for ~1000 users with stat + activity data)
CACHE_SIZE_LIMIT = 10 * 1024 * 1024

# App name for platformdirs
APP_NAME = 'bilibili-analyzer'


def get_cache_dir() -> Path:
    """
    Get the cache directory path.

    Uses platformdirs to find the appropriate user cache directory:
    - Linux: ~/.cache/bilibili-analyzer/
    - macOS: ~/Library/Caches/bilibili-analyzer/
    - Windows: C:/Users/<user>/AppData/Local/bilibili-analyzer/Cache/

    Returns
    -------
    Path
        The cache directory path.
    """
    return Path(platformdirs.user_cache_dir(APP_NAME))


def get_cache(directory: Path | None = None) -> Cache:
    """
    Get a diskcache Cache instance.

    Parameters
    ----------
    directory : Path or None
        Custom cache directory. If None, uses the default from get_cache_dir().

    Returns
    -------
    Cache
        A diskcache Cache instance.
    """
    cache_dir = directory or get_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return diskcache.Cache(str(cache_dir), size_limit=CACHE_SIZE_LIMIT)


def make_user_stat_key(mid: int) -> str:
    """Generate cache key for user stat data."""
    return f'user_stat:{mid}'


def make_user_activity_key(mid: int) -> str:
    """Generate cache key for user activity data."""
    return f'user_activity:{mid}'


class CachedDataFetcher:
    """
    Wrapper that adds caching to data fetching operations.

    Attributes
    ----------
    cache : Cache or None
        The diskcache Cache instance, or None if caching is disabled.
    """

    def __init__(self, cache: Cache | None = None) -> None:
        """
        Initialize the cached data fetcher.

        Parameters
        ----------
        cache : Cache or None
            The cache instance. Pass None to disable caching.
        """
        self.cache = cache

    def get_or_fetch(
        self,
        key: str,
        fetcher: Any,
        ttl: int,
    ) -> Any:
        """
        Get value from cache or fetch it.

        Parameters
        ----------
        key : str
            The cache key.
        fetcher : callable
            Function to call if cache miss. Should return the value to cache.
        ttl : int
            Time-to-live in seconds.

        Returns
        -------
        Any
            The cached or freshly fetched value.
        """
        if self.cache is None:
            return fetcher()

        value = self.cache.get(key)
        if value is not None:
            return value

        value = fetcher()
        self.cache.set(key, value, expire=ttl)
        return value

    def clear(self) -> None:
        """Clear all cached data."""
        if self.cache is not None:
            self.cache.clear()

    def close(self) -> None:
        """Close the cache."""
        if self.cache is not None:
            self.cache.close()
