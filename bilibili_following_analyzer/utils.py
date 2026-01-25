"""Utility functions for Bilibili Following Analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .filters import FilterResult


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


def print_filter_results(results: list[FilterResult]) -> None:
    """
    Print filter results to stdout.

    Parameters
    ----------
    results : list[FilterResult]
        The filter results to display.
    """
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)

    if not results:
        print('\nNo users matched the specified filters.')
        return

    print(f'\nMATCHED USERS ({len(results)} total):')
    print('-' * 40)

    for result in results:
        user = result.following
        print(f'{user.name} - {user.space_url}')

        # Show matched filter details
        details = []
        for filter_name in result.matched_filters:
            detail = result.details.get(filter_name)
            if detail:
                details.append(detail)
            else:
                details.append(filter_name)

        if details:
            print(f'  └─ {", ".join(details)}')
