"""Data models for Bilibili Following Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class User:
    """Represents a Bilibili user."""

    mid: int
    name: str
    follower_count: int | None = None

    @property
    def space_url(self) -> str:
        """Return the URL to the user's space page."""
        return f'https://space.bilibili.com/{self.mid}'


@dataclass
class FilterConfig:
    """
    Configuration for filtering inactive / low-engagement users.

    Each filter is optional - only enabled filters are applied.
    A user matching ANY enabled filter will be flagged.
    """

    # Filter: user has too many followings (mass-following accounts)
    max_following: int | None = None

    # Filter: user hasn't posted in N days
    inactive_days: int | None = None

    # Filter: user's recent posts are mostly reposts (ratio 0.0-1.0)
    repost_ratio: float | None = None

    # Number of dynamics to check for repost/activity analysis
    dynamics_to_check: int = 10

    def is_enabled(self) -> bool:
        """Return True if any filter is enabled."""
        return any(
            [
                self.max_following is not None,
                self.inactive_days is not None,
                self.repost_ratio is not None,
            ]
        )


@dataclass
class FilteredUser:
    """
    A user that matched one or more filter criteria.

    Attributes
    ----------
    user : User
        The underlying user info.
    reasons : list[str]
        Human-readable reasons why this user was filtered.
    """

    user: User
    reasons: list[str] = field(default_factory=list)
