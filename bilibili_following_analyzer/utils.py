"""Utility functions for Bilibili Following Analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .models import FilteredUser, User


def load_allow_list(path: Path | None) -> set[int]:
    """
    Load allow list from a file.

    Parameters
    ----------
    path : Path or None
        Path to the allow list file. One UID per line, # for comments.

    Returns
    -------
    set[int]
        Set of user IDs in the allow list.
    """
    if not path or not path.exists():
        return set()

    allow_list: set[int] = set()
    for line_num, line in enumerate(path.read_text().splitlines(), start=1):
        line = line.split('#')[0].strip()
        if line:
            try:
                allow_list.add(int(line))
            except ValueError:
                print(f'Warning: Invalid UID at {path}:{line_num}, skipping: {line!r}')

    return allow_list


def print_results(
    not_following_back: list[User],
    no_interaction: list[User],
    filtered_users: list[FilteredUser] | None = None,
) -> None:
    """
    Print analysis results to stdout.

    Parameters
    ----------
    not_following_back : list[User]
        Users who don't follow back and have few followers.
    no_interaction : list[User]
        Users who haven't interacted with recent posts.
    filtered_users : list[FilteredUser] or None, optional
        Users filtered out by activity criteria.
    """
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)

    if not_following_back:
        print(f'\n NOT FOLLOWING BACK ({len(not_following_back)} users):')
        print('-' * 40)
        for user in not_following_back:
            suffix = (
                f' ({user.follower_count} followers)' if user.follower_count else ''
            )
            print(f'{user.name}{suffix} - {user.space_url}')
    else:
        print('\n Everyone is following you back (or above follower threshold)!')

    if no_interaction:
        print(f'\n NO RECENT INTERACTION ({len(no_interaction)} users):')
        print('-' * 40)
        for user in no_interaction:
            suffix = ''
            if user.follower_count is not None:
                suffix = f' ({user.follower_count} followers)'
            print(f'{user.name}{suffix} - {user.space_url}')
    else:
        print('\n All followings have interacted with your recent posts!')

    if filtered_users:
        print(f'\n FILTERED (inactive/low-engagement) ({len(filtered_users)} users):')
        print('-' * 40)
        for fu in filtered_users:
            reasons_str = ', '.join(fu.reasons)
            print(f'{fu.user.name} - {fu.user.space_url}')
            print(f'  Reason: {reasons_str}')
