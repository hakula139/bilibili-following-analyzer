"""Composable filter system for analyzing Bilibili followings."""

from __future__ import annotations

import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Self

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
class MatchInfo:
    """
    Result of a filter match operation.

    Attributes
    ----------
    matched : bool
        Whether the filter matched.
    detail : str or None
        Human-readable explanation of why the filter matched.
    filter_names : list[str]
        Names of the filters that matched (for composite filters, includes all
        sub-filters that contributed to the match).
    """

    matched: bool
    detail: str | None = None
    filter_names: list[str] = field(default_factory=list)

    @classmethod
    def no_match(cls) -> Self:
        """Create a non-matching result."""
        return cls(matched=False)

    @classmethod
    def match(cls, filter_name: str, detail: str | None = None) -> Self:
        """Create a matching result for a single filter."""
        return cls(matched=True, detail=detail, filter_names=[filter_name])


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
    def _require_param(cls, param: str | None) -> str:
        """Validate that a parameter is provided."""
        if param is None:
            raise ValueError(f'Filter {cls.name!r} requires a parameter')
        return param

    @classmethod
    def _parse_int_param(cls, param: str | None) -> int:
        """Parse and validate an integer parameter."""
        param = cls._require_param(param)
        try:
            return int(param)
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires an integer') from None

    @classmethod
    def _parse_float_param(cls, param: str | None) -> float:
        """Parse and validate a float parameter."""
        param = cls._require_param(param)
        try:
            return float(param)
        except ValueError:
            raise ValueError(f'Filter {cls.name!r} requires a number') from None

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
    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
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
        MatchInfo
            Match result including whether matched, detail, and filter names.
        """
        ...


# -----------------------------------------------------------------------------
# Concrete Filter Implementations
# -----------------------------------------------------------------------------


class NotFollowingBackFilter(Filter):
    """Filter users who don't follow back (one-way follow)."""

    name = 'not-following-back'
    description = 'Users who do not follow you back'

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        if not following.is_mutual:
            return MatchInfo.match(self.name, '未回关')
        return MatchInfo.no_match()


class MutualFollowFilter(Filter):
    """Filter users who are mutual follows."""

    name = 'mutual'
    description = 'Users who follow you back (mutual follows)'

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        if following.is_mutual:
            return MatchInfo.match(self.name, '互相关注')
        return MatchInfo.no_match()


class _ThresholdStatFilter(Filter):
    """
    Base class for filters that compare a user stat against a threshold.

    Subclasses must define class attributes for configuration.
    """

    has_param = True

    # Subclass configuration (to be overridden)
    stat_field: ClassVar[str]  # 'follower' or 'following'
    compare_above: ClassVar[bool]  # True for '>' comparison, False for '<'
    detail_prefix: ClassVar[str]  # Display prefix like '粉丝数' or '关注数'

    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    @classmethod
    def create(cls, param: str | None = None) -> Filter:
        return cls(cls._parse_int_param(param))

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        stat = ctx.get_user_stat(following.mid)
        value = stat.get(self.stat_field, 0)
        if self.compare_above:
            matched = value > self.threshold
        else:
            matched = value < self.threshold
        if matched:
            return MatchInfo.match(self.name, f'{self.detail_prefix} {value}')
        return MatchInfo.no_match()


class BelowFollowersFilter(_ThresholdStatFilter):
    """Filter users with fewer than N followers."""

    name = 'below-followers'
    description = 'Users with fewer than N followers'
    param_help = 'N (follower threshold)'
    stat_field = 'follower'
    compare_above = False
    detail_prefix = '粉丝数'


class AboveFollowersFilter(_ThresholdStatFilter):
    """Filter users with more than N followers."""

    name = 'above-followers'
    description = 'Users with more than N followers'
    param_help = 'N (follower threshold)'
    stat_field = 'follower'
    compare_above = True
    detail_prefix = '粉丝数'


class NoInteractionFilter(Filter):
    """Filter users who haven't interacted with recent content."""

    name = 'no-interaction'
    description = 'Users who have not interacted with your recent content'

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        if following.mid not in ctx.interacting_users:
            return MatchInfo.match(self.name, '无近期互动')
        return MatchInfo.no_match()


class TooManyFollowingsFilter(_ThresholdStatFilter):
    """Filter users who follow too many accounts."""

    name = 'too-many-followings'
    description = 'Users following more than N accounts'
    param_help = 'N (following threshold)'
    stat_field = 'following'
    compare_above = True
    detail_prefix = '关注数'


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
        return cls(cls._parse_int_param(param))

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        activity = ctx.get_user_activity(following.mid)

        if activity['is_deactivated']:
            return MatchInfo.match(self.name, '账号已注销')

        if activity['total_dynamics'] == 0:
            return MatchInfo.match(self.name, '无任何动态')

        if activity['last_post_ts'] is not None:
            now_ts = int(time.time())
            days_since_post = (now_ts - activity['last_post_ts']) // 86400
            if days_since_post > self.days:
                return MatchInfo.match(self.name, f'超过 {days_since_post} 天未更新')

        return MatchInfo.no_match()


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
        return cls(cls._parse_float_param(param))

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        activity = ctx.get_user_activity(following.mid)

        if activity['total_dynamics'] == 0:
            return MatchInfo.no_match()

        ratio = activity['repost_count'] / activity['total_dynamics']
        if ratio >= self.ratio:
            pct = int(ratio * 100)
            return MatchInfo.match(self.name, f'{pct}% 为转发')

        return MatchInfo.no_match()


class DeactivatedFilter(Filter):
    """Filter deactivated or inaccessible accounts."""

    name = 'deactivated'
    description = 'Users with deactivated or inaccessible accounts'

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        activity = ctx.get_user_activity(following.mid)
        if activity['is_deactivated']:
            return MatchInfo.match(self.name, '账号已注销或不可访问')
        return MatchInfo.no_match()


class NoPostsFilter(Filter):
    """Filter users who have never posted."""

    name = 'no-posts'
    description = 'Users who have no posts/dynamics at all'

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        activity = ctx.get_user_activity(following.mid)
        if not activity['is_deactivated'] and activity['total_dynamics'] == 0:
            return MatchInfo.match(self.name, '无任何动态')
        return MatchInfo.no_match()


# -----------------------------------------------------------------------------
# Composite Filters for Nested Logic
# -----------------------------------------------------------------------------


class AndFilter(Filter):
    """
    Composite filter that requires ALL child filters to match.

    Used for building complex filter expressions with nested logic.
    """

    name = 'and'
    description = 'All child filters must match'

    def __init__(self, filters: list[Filter]) -> None:
        self.filters = filters

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        all_details: list[str] = []
        all_filter_names: list[str] = []

        for f in self.filters:
            result = f.matches(following, ctx)
            if not result.matched:
                return MatchInfo.no_match()
            if result.detail:
                all_details.append(result.detail)
            all_filter_names.extend(result.filter_names)

        return MatchInfo(
            matched=True,
            detail='; '.join(all_details) if all_details else None,
            filter_names=all_filter_names,
        )


class OrFilter(Filter):
    """
    Composite filter that requires ANY child filter to match.

    Used for building complex filter expressions with nested logic.
    """

    name = 'or'
    description = 'Any child filter matches'

    def __init__(self, filters: list[Filter]) -> None:
        self.filters = filters

    def matches(self, following: Following, ctx: FilterContext) -> MatchInfo:
        all_details: list[str] = []
        all_filter_names: list[str] = []

        for f in self.filters:
            result = f.matches(following, ctx)
            if result.matched:
                if result.detail:
                    all_details.append(result.detail)
                all_filter_names.extend(result.filter_names)

        if all_filter_names:
            return MatchInfo(
                matched=True,
                detail='; '.join(all_details) if all_details else None,
                filter_names=all_filter_names,
            )
        return MatchInfo.no_match()


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


# -----------------------------------------------------------------------------
# Filter Expression Parser
# -----------------------------------------------------------------------------


class FilterExpressionParser:
    """
    Parser for complex filter expressions with nested AND/OR logic.

    Syntax
    ------
    - Filter names: `not-following-back`, `inactive:365`
    - AND: `+` (e.g., `a + b`)
    - OR: `|` (e.g., `a | b`)
    - Grouping: `(...)` (e.g., `(a + b) | c`)

    Precedence: `+` binds tighter than `|`, so `a + b | c` = `(a + b) | c`.

    Examples
    --------
    - `not-following-back + below-followers:5000`
    - `(a + b) | (c + d)`
    - `(a + b + (c | d | e)) | f`
    """

    def __init__(self, expr: str) -> None:
        self.expr = expr
        self.pos = 0
        self.length = len(expr)

    def parse(self) -> Filter:
        """Parse the expression and return a Filter."""
        result = self._parse_or()
        self._skip_whitespace()
        if self.pos < self.length:
            raise ValueError(
                f'Unexpected character at position {self.pos}: {self.expr[self.pos]!r}'
            )
        return result

    def _skip_whitespace(self) -> None:
        while self.pos < self.length and self.expr[self.pos] in ' \t\n':
            self.pos += 1

    def _parse_or(self) -> Filter:
        """Parse OR expressions (lowest precedence)."""
        left = self._parse_and()
        filters = [left]

        while True:
            self._skip_whitespace()
            if self.pos < self.length and self.expr[self.pos] == '|':
                self.pos += 1
                filters.append(self._parse_and())
            else:
                break

        if len(filters) == 1:
            return filters[0]
        return OrFilter(filters)

    def _parse_and(self) -> Filter:
        """Parse AND expressions (higher precedence than OR)."""
        left = self._parse_atom()
        filters = [left]

        while True:
            self._skip_whitespace()
            if self.pos < self.length and self.expr[self.pos] == '+':
                self.pos += 1
                filters.append(self._parse_atom())
            else:
                break

        if len(filters) == 1:
            return filters[0]
        return AndFilter(filters)

    def _parse_atom(self) -> Filter:
        """Parse atomic expressions (filter names or parenthesized groups)."""
        self._skip_whitespace()

        if self.pos >= self.length:
            raise ValueError('Unexpected end of expression')

        # Parenthesized group
        if self.expr[self.pos] == '(':
            self.pos += 1
            result = self._parse_or()
            self._skip_whitespace()
            if self.pos >= self.length or self.expr[self.pos] != ')':
                raise ValueError('Missing closing parenthesis')
            self.pos += 1
            return result

        # Filter name (with optional parameter)
        return self._parse_filter_name()

    def _parse_filter_name(self) -> Filter:
        """Parse a filter name like 'inactive:365' or 'not-following-back'."""
        self._skip_whitespace()
        start = self.pos

        # Read filter name (letters and hyphens)
        while self.pos < self.length and (
            self.expr[self.pos].isalpha()
            or self.expr[self.pos] == '-'
            or self.expr[self.pos].isdigit()
        ):
            self.pos += 1

        name = self.expr[start : self.pos]
        if not name:
            raise ValueError(f'Expected filter name at position {start}')

        # Check for parameter
        param = None
        if self.pos < self.length and self.expr[self.pos] == ':':
            self.pos += 1
            param_start = self.pos
            # Read parameter (anything until whitespace or operator)
            while self.pos < self.length and self.expr[self.pos] not in ' \t\n+|()':
                self.pos += 1
            param = self.expr[param_start : self.pos]

        # Look up and create filter
        if name not in FILTER_REGISTRY:
            available = ', '.join(sorted(FILTER_REGISTRY.keys()))
            raise ValueError(f'Unknown filter: {name!r}. Available: {available}')

        return FILTER_REGISTRY[name].create(param)


def parse_filter_expression(expr: str) -> Filter:
    """
    Parse a filter expression string into a composite Filter.

    Parameters
    ----------
    expr : str
        Filter expression with AND (+), OR (|), and parentheses.
        Example: `(not-following-back + below-followers:5000) | deactivated`

    Returns
    -------
    Filter
        The composite filter representing the expression.

    Raises
    ------
    ValueError
        If the expression syntax is invalid.
    """
    parser = FilterExpressionParser(expr)
    return parser.parse()
