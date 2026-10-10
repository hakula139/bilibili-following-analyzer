"""Utility functions for Bilibili Following Analyzer."""

from __future__ import annotations

import csv
import json
from pathlib import Path

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
    if path is None:
        return set()
    try:
        contents = path.read_text(encoding='utf-8')
    except OSError as error:
        raise ValueError(
            f'Cannot read allow list {path}: {error.strerror or error}'
        ) from error

    allow_list: set[int] = set()
    for line_num, line in enumerate(contents.splitlines(), start=1):
        line = line.split('#')[0].strip()
        if line:
            try:
                mid = int(line)
                if mid <= 0:
                    raise ValueError
                allow_list.add(mid)
            except ValueError:
                raise ValueError(
                    f'Invalid UID at {path}:{line_num}: {line!r}'
                ) from None

    return allow_list


def _get_display_details(result: FilterResult) -> str:
    """Get display string for filter match details."""
    return '; '.join(match.detail or match.name for match in result.matches)


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

        details = _get_display_details(result)
        if details:
            print(f'  └─ {details}')


def _result_to_dict(result: FilterResult) -> dict[str, object]:
    """Convert a FilterResult to a dictionary for serialization."""
    return {
        'mid': result.following.mid,
        'name': result.following.name,
        'space_url': result.following.space_url,
        'is_mutual': result.following.is_mutual,
        'matched_filters': [match.name for match in result.matches],
        'details': [match.detail or match.name for match in result.matches],
    }


def output_results_to_file(results: list[FilterResult], path: Path) -> None:
    """
    Output filter results to a file.

    Parameters
    ----------
    results : list[FilterResult]
        The filter results to output.
    path : Path
        Output file path. Format determined by extension (.txt, .json, .csv).
    """
    suffix = path.suffix.lower()

    if suffix == '.json':
        data = [_result_to_dict(r) for r in results]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8'
        )
    elif suffix == '.csv':
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(
                ['mid', 'name', 'space_url', 'is_mutual', 'matched_filters', 'details']
            )
            for r in results:
                writer.writerow(
                    [
                        r.following.mid,
                        r.following.name,
                        r.following.space_url,
                        r.following.is_mutual,
                        ', '.join(match.name for match in r.matches),
                        _get_display_details(r),
                    ]
                )
    else:
        # Default to plain text
        lines: list[str] = []
        for r in results:
            lines.append(
                f'{r.following.name}\t{r.following.space_url}\t{_get_display_details(r)}'
            )
        path.write_text('\n'.join(lines), encoding='utf-8')

    print(f'Results saved to: {path}')
