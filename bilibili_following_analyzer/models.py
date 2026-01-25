"""Data models for Bilibili Following Analyzer."""

from __future__ import annotations

from dataclasses import dataclass


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
