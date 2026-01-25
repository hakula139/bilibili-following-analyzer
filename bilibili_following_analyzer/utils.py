"""Utility functions for Bilibili Following Analyzer."""

from __future__ import annotations

import csv
import json
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


def _get_display_details(result: FilterResult) -> str:
    """Get display string for filter match details."""
    # Check for combined detail from composite filters
    combined = result.details.get('_combined')
    if combined:
        return combined

    # Build from individual filter details
    details: list[str] = []
    for filter_name in result.matched_filters:
        detail = result.details.get(filter_name)
        if detail:
            details.append(detail)
        else:
            details.append(filter_name)
    return '; '.join(details)


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
    # Get details - either from combined or individual
    combined = result.details.get('_combined')
    if combined:
        # Split combined detail by '; ' to get individual details
        details = [d.strip() for d in combined.split(';')]
    else:
        details = []
        for filter_name in result.matched_filters:
            detail = result.details.get(filter_name)
            details.append(detail if detail else filter_name)

    return {
        'mid': result.following.mid,
        'name': result.following.name,
        'space_url': result.following.space_url,
        'is_mutual': result.following.is_mutual,
        'matched_filters': result.matched_filters,
        'details': details,
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
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
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
                        ', '.join(r.matched_filters),
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
