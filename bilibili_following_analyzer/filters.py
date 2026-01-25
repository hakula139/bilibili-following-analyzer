"""Composable filter system for analyzing Bilibili followings."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

from .cache import (
    TTL_USER_ACTIVITY,
    TTL_USER_STAT,
    CachedDataFetcher,
    make_user_activity_key,
    make_user_stat_key,
)


if TYPE_CHECKING:
    from .client import BilibiliClient


@dataclass
class FilterContext:
    """
    Shared context for filter evaluation.

    Contains data that filters may need, fetched once and shared across filters.
    Supports both in-memory (session) and disk-based (cross-run) caching.

    Attributes
    ----------
    client : BilibiliClient
        The API client for fetching additional data.
    my_mid : int
        The user's own member ID.
    interacting_users : set[int]
        Set of user IDs who have interacted with recent content.
    cache : CachedDataFetcher
        Disk cache for persistent storage across runs.
    user_stats : dict[int, dict]
        In-memory cache for user stats (hot cache for current session).
    user_activity : dict[int, dict]
        In-memory cache for user activity (hot cache for current session).
    """

    client: BilibiliClient
    my_mid: int
    interacting_users: set[int] = field(default_factory=set)
    cache: CachedDataFetcher = field(default_factory=CachedDataFetcher)
    user_stats: dict[int, dict[str, Any]] = field(default_factory=dict)
    user_activity: dict[int, dict[str, Any]] = field(default_factory=dict)

    def get_user_stat(self, mid: int) -> dict[str, Any]:
        """
        Get user stat with two-level caching.

        First checks in-memory cache, then disk cache, then fetches from API.
        """
        if mid in self.user_stats:
            return self.user_stats[mid]

        key = make_user_stat_key(mid)
        stat = self.cache.get_or_fetch(
            key,
            lambda: self.client.get_user_stat(mid),
            TTL_USER_STAT,
        )
        self.user_stats[mid] = stat
        return stat

    def get_user_activity(self, mid: int, max_dynamics: int = 10) -> dict[str, Any]:
        """
        Get user activity with two-level caching.

        First checks in-memory cache, then disk cache, then fetches from API.
        """
        if mid in self.user_activity:
            return self.user_activity[mid]

        key = make_user_activity_key(mid)
        activity = self.cache.get_or_fetch(
            key,
            lambda: self.client.get_user_activity(mid, max_dynamics=max_dynamics),
            TTL_USER_ACTIVITY,
        )
        self.user_activity[mid] = activity
        return activity


@dataclass
class Following:
    """
    A following user with their relationship data.

    Attributes
    ----------
    mid : int
        The user's member ID.
    name : str
        The user's display name.
    attribute : int
        Relationship attribute (2 = one-way, 6 = mutual).
    """

    mid: int
    name: str
    attribute: int

    @property
    def is_mutual(self) -> bool:
        """Return True if this is a mutual follow."""
        return self.attribute == 6

    @property
    def space_url(self) -> str:
        """Return the URL to the user's space page."""
        return f'https://space.bilibili.com/{self.mid}'


@dataclass
class FilterResult:
    """
    Result of applying filters to a user.

    Attributes
    ----------
    following : Following
        The user that was filtered.
    matched_filters : list[str]
        Names of filters that matched this user.
    details : dict[str, str]
        Additional details from each matched filter.
    """

    following: Following
    matched_filters: list[str] = field(default_factory=list)
    details: dict[str, str] = field(default_factory=dict)

    def add_match(self, filter_name: str, detail: str | None = None) -> None:
        """Record a filter match."""
        self.matched_filters.append(filter_name)
        if detail:
            self.details[filter_name] = detail


class Filter(ABC):
    """
    Abstract base class for all filters.

    Subclasses must implement the `matches` method and define class attributes.
    """

    # Filter name used in CLI (e.g., 'not-following-back')
    name: ClassVar[str]

    # Human-readable description for help text
    description: ClassVar[str]

    # Whether this filter accepts a parameter (e.g., 'inactive:365')
    has_param: ClassVar[bool] = False

    # Parameter description for help text (if has_param is True)
    param_help: ClassVar[str] = ''

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        """
        Factory method to create a filter instance.

        Parameters
        ----------
        param : str or None
            Optional parameter string to parse.

        Returns
        -------
        Filter
            The instantiated filter.

        Raises
        ------
        ValueError
            If the parameter is invalid or missing when required.
        """
        if cls.has_param:
            raise NotImplementedError(
                f'{cls.__name__} must override create() to handle parameters'
            )
        if param is not None:
            raise ValueError(f'Filter {cls.name!r} does not accept parameters')
        return cls()

    @abstractmethod
    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        """
        Check if a following matches this filter.

        Parameters
        ----------
        following : Following
            The user to check.
        ctx : FilterContext
            Shared context with cached data.

        Returns
        -------
        tuple[bool, str | None]
            (matched, detail) where matched is True if the filter applies,
            and detail is an optional human-readable explanation.
        """
        ...


# -----------------------------------------------------------------------------
# Concrete Filter Implementations
# -----------------------------------------------------------------------------


class NotFollowingBackFilter(Filter):
    """Filter users who don't follow back (one-way follow)."""

    name = 'not-following-back'
    description = 'Users who do not follow you back'

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        if not following.is_mutual:
            return True, '未回关'
        return False, None


class MutualFollowFilter(Filter):
    """Filter users who are mutual follows."""

    name = 'mutual'
    description = 'Users who follow you back (mutual follows)'

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        if following.is_mutual:
            return True, '互相关注'
        return False, None


class BelowFollowersFilter(Filter):
    """Filter users with fewer than N followers."""

    name = 'below-followers'
    description = 'Users with fewer than N followers'
    has_param = True
    param_help = 'N (follower threshold)'

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        try:
            return cls(int(param))
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires an integer') from None

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        stat = ctx.get_user_stat(following.mid)
        follower_count = stat.get('follower', 0)
        if follower_count < self.threshold:
            return True, f'粉丝数 {follower_count}'
        return False, None


class AboveFollowersFilter(Filter):
    """Filter users with more than N followers."""

    name = 'above-followers'
    description = 'Users with more than N followers'
    has_param = True
    param_help = 'N (follower threshold)'

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        try:
            return cls(int(param))
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires an integer') from None

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        stat = ctx.get_user_stat(following.mid)
        follower_count = stat.get('follower', 0)
        if follower_count > self.threshold:
            return True, f'粉丝数 {follower_count}'
        return False, None


class NoInteractionFilter(Filter):
    """Filter users who haven't interacted with recent content."""

    name = 'no-interaction'
    description = 'Users who have not interacted with your recent content'

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        if following.mid not in ctx.interacting_users:
            return True, '无近期互动'
        return False, None


class TooManyFollowingsFilter(Filter):
    """Filter users who follow too many accounts."""

    name = 'too-many-followings'
    description = 'Users following more than N accounts'
    has_param = True
    param_help = 'N (following threshold)'

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        try:
            return cls(int(param))
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires an integer') from None

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        stat = ctx.get_user_stat(following.mid)
        following_count = stat.get('following', 0)
        if following_count > self.threshold:
            return True, f'关注数 {following_count}'
        return False, None


class InactiveFilter(Filter):
    """Filter users who haven't posted in N days."""

    name = 'inactive'
    description = 'Users who have not posted in N days'
    has_param = True
    param_help = 'DAYS (inactivity threshold)'

    def __init__(self, days: int) -> None:
        self.days = days

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        try:
            return cls(int(param))
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires an integer') from None

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        activity = ctx.get_user_activity(following.mid)

        if activity['is_deactivated']:
            return True, '账号已注销'

        if activity['total_dynamics'] == 0:
            return True, '无任何动态'

        if activity['last_post_ts'] is not None:
            now_ts = int(time.time())
            days_since_post = (now_ts - activity['last_post_ts']) // 86400
            if days_since_post > self.days:
                return True, f'超过 {days_since_post} 天未更新'

        return False, None


class RepostRatioFilter(Filter):
    """Filter users whose recent posts are mostly reposts."""

    name = 'repost-ratio'
    description = 'Users whose repost ratio exceeds RATIO (0.0-1.0)'
    has_param = True
    param_help = 'RATIO (e.g., 0.8 for 80%)'

    def __init__(self, ratio: float) -> None:
        self.ratio = ratio

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        try:
            return cls(float(param))
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires a float') from None

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        activity = ctx.get_user_activity(following.mid)

        if activity['total_dynamics'] == 0:
            return False, None

        ratio = activity['repost_count'] / activity['total_dynamics']
        if ratio >= self.ratio:
            pct = int(ratio * 100)
            return True, f'{pct}% 为转发'

        return False, None


class DeactivatedFilter(Filter):
    """Filter deactivated or inaccessible accounts."""

    name = 'deactivated'
    description = 'Users with deactivated or inaccessible accounts'

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        activity = ctx.get_user_activity(following.mid)
        if activity['is_deactivated']:
            return True, '账号已注销或不可访问'
        return False, None


class NoPostsFilter(Filter):
    """Filter users who have never posted."""

    name = 'no-posts'
    description = 'Users who have no posts/dynamics at all'

    def matches(
        self, following: Following, ctx: FilterContext
    ) -> tuple[bool, str | None]:
        activity = ctx.get_user_activity(following.mid)
        if not activity['is_deactivated'] and activity['total_dynamics'] == 0:
            return True, '无任何动态'
        return False, None


# -----------------------------------------------------------------------------
# Filter Registry
# -----------------------------------------------------------------------------

# All available filter classes
ALL_FILTERS: list[type[Filter]] = [
    NotFollowingBackFilter,
    MutualFollowFilter,
    BelowFollowersFilter,
    AboveFollowersFilter,
    NoInteractionFilter,
    TooManyFollowingsFilter,
    InactiveFilter,
    RepostRatioFilter,
    DeactivatedFilter,
    NoPostsFilter,
]

# Map filter names to their classes
FILTER_REGISTRY: dict[str, type[Filter]] = {f.name: f for f in ALL_FILTERS}


def parse_filter_spec(spec: str) -> Filter:
    """
    Parse a filter specification string into a Filter instance.

    Parameters
    ----------
    spec : str
        Filter spec like 'not-following-back' or 'inactive:365'.

    Returns
    -------
    Filter
        The instantiated filter.

    Raises
    ------
    ValueError
        If the filter name is unknown or parameter is invalid.
    """
    # Parse name and optional parameter
    match = re.match(r'^([a-z-]+)(?::(.+))?$', spec)
    if not match:
        raise ValueError(f'Invalid filter spec: {spec!r}')

    name, param = match.groups()

    if name not in FILTER_REGISTRY:
        available = ', '.join(sorted(FILTER_REGISTRY.keys()))
        raise ValueError(f'Unknown filter: {name!r}. Available: {available}')

    filter_cls = FILTER_REGISTRY[name]
    return filter_cls.create(param)


def get_filter_help() -> str:
    """Generate help text for all available filters."""
    lines = ['Available filters:']
    for f in ALL_FILTERS:
        if f.has_param:
            lines.append(f'  {f.name}:<{f.param_help}>')
        else:
            lines.append(f'  {f.name}')
        lines.append(f'      {f.description}')
    return '\n'.join(lines)
