"""Command-line interface for Bilibili Following Analyzer."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .cache import CachedDataFetcher, get_cache, get_cache_dir
from .client import BilibiliClient
from .filters import (
    Filter,
    FilterContext,
    FilterResult,
    Following,
    get_filter_help,
    parse_filter_spec,
)
from .utils import load_allow_list, print_filter_results


def _env_int(name: str, default: int) -> int:
    """
    Get an integer from an environment variable with a default.

    Parameters
    ----------
    name : str
        The environment variable name.
    default : int
        The default value if the variable is not set or empty.

    Returns
    -------
    int
        The parsed integer value.

    Raises
    ------
    SystemExit
        If the value is set but not a valid integer.
    """
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        msg = f'Error: {name} must be a valid integer, got {val!r}'
        raise SystemExit(msg) from None


def _env_float(name: str, default: float) -> float:
    """
    Get a float from an environment variable with a default.

    Parameters
    ----------
    name : str
        The environment variable name.
    default : float
        The default value if the variable is not set or empty.

    Returns
    -------
    float
        The parsed float value.

    Raises
    ------
    SystemExit
        If the value is set but not a valid float.
    """
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        raise SystemExit(f'Error: {name} must be a valid number, got {val!r}') from None


def _env_list(name: str) -> list[str]:
    """
    Get a list from an environment variable (comma-separated).

    Parameters
    ----------
    name : str
        The environment variable name.

    Returns
    -------
    list[str]
        List of values, or empty list if not set.
    """
    val = os.environ.get(name)
    if not val:
        return []
    return [v.strip() for v in val.split(',') if v.strip()]


class FilterHelpAction(argparse.Action):
    """Custom action to display filter help and exit."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[Any] | None,
        option_string: str | None = None,
    ) -> None:
        del parser, namespace, values, option_string  # Unused
        print(get_filter_help())
        sys.exit(0)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description='Analyze your Bilibili following list with composable filters',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='Use --list-filters to see all available filters and their syntax.',
    )

    parser.add_argument(
        '--mid',
        type=int,
        default=os.environ.get('MID'),
        help='Your Bilibili user ID (UID). Env: MID',
    )
    parser.add_argument(
        '--sessdata',
        type=str,
        default=os.environ.get('SESSDATA'),
        help='SESSDATA cookie for authentication. Env: SESSDATA',
    )
    parser.add_argument(
        '--allow-list',
        type=Path,
        default=os.environ.get('ALLOW_LIST'),
        help='Path to allow list file (one UID per line). Env: ALLOW_LIST',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=_env_float('DELAY', 0.3),
        help='Delay between API requests in seconds (default: 0.3). Env: DELAY',
    )

    # Filter arguments
    filter_group = parser.add_argument_group(
        'filter options',
        'Specify filters to apply. Use --list-filters for available options.',
    )
    filter_group.add_argument(
        '-f',
        '--filter',
        action='append',
        dest='filters',
        metavar='FILTER',
        help='Add a filter (repeatable). Format: name / name:param. Env: FILTERS',
    )
    filter_group.add_argument(
        '--filter-mode',
        choices=['and', 'or'],
        default=os.environ.get('FILTER_MODE', 'and'),
        help='How to combine filters: and (all match) / or (any). Env: FILTER_MODE',
    )
    filter_group.add_argument(
        '--list-filters',
        nargs=0,
        action=FilterHelpAction,
        help='List all available filters and exit',
    )

    # Interaction collection (for no-interaction filter)
    interaction_group = parser.add_argument_group(
        'interaction options',
        'Settings for the no-interaction filter.',
    )
    interaction_group.add_argument(
        '--num-videos',
        type=int,
        default=_env_int('NUM_VIDEOS', 10),
        help='Number of recent videos to check for interactions. Env: NUM_VIDEOS',
    )
    interaction_group.add_argument(
        '--num-dynamics',
        type=int,
        default=_env_int('NUM_DYNAMICS', 20),
        help='Number of recent dynamics to check for interactions. Env: NUM_DYNAMICS',
    )

    # Cache options
    cache_group = parser.add_argument_group(
        'cache options',
        'Control disk caching of API responses across runs.',
    )
    cache_group.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable disk caching (still uses in-memory cache for current run)',
    )
    cache_group.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear all cached data before running',
    )
    cache_group.add_argument(
        '--cache-dir',
        type=Path,
        help=f'Custom cache directory (default: {get_cache_dir()})',
    )

    return parser.parse_args()


def collect_interacting_users(
    client: BilibiliClient,
    my_mid: int,
    num_videos: int,
    num_dynamics: int,
) -> set[int]:
    """
    Collect all user IDs who interacted with recent posts.

    Parameters
    ----------
    client : BilibiliClient
        The authenticated API client.
    my_mid : int
        The user's own member ID.
    num_videos : int
        Number of recent videos to check.
    num_dynamics : int
        Number of recent dynamics to check.

    Returns
    -------
    set[int]
        Set of user IDs who have interacted.
    """
    from .client import BilibiliAPIError

    interacting_users: set[int] = set()

    # Collect from videos
    if num_videos > 0:
        print(f'Fetching recent {num_videos} videos...')
        video_count = 0
        for video in client.get_user_videos(my_mid, max_count=num_videos):
            aid = video['aid']
            title = video['title'][:30]
            print(f'  Checking video: {title}...')

            for comment in client.get_video_comments(aid, max_count=100):
                interacting_users.add(comment['member']['mid'])

            video_count += 1

        print(f'  Processed {video_count} videos')

    # Collect from dynamics
    if num_dynamics > 0:
        print(f'Fetching recent {num_dynamics} dynamics...')
        dynamic_count = 0
        for dynamic in client.get_user_dynamics(my_mid, max_count=num_dynamics):
            dynamic_id = dynamic['id_str']
            dynamic_type = dynamic.get('type', 'unknown')
            print(f'  Checking dynamic {dynamic_id} ({dynamic_type})...')

            # Get likes and forwards
            for reaction in client.get_dynamic_reactions(dynamic_id):
                interacting_users.add(reaction['mid'])

            # Get comments (some dynamic types don't support comments)
            try:
                for comment in client.get_dynamic_comments(dynamic_id, max_count=100):
                    interacting_users.add(comment['member']['mid'])
            except BilibiliAPIError as e:
                if e.code == -404:
                    pass  # Dynamic has no comment section
                else:
                    raise

            dynamic_count += 1

        print(f'  Processed {dynamic_count} dynamics')

    return interacting_users


def apply_filters(
    followings: list[Following],
    filters: list[Filter],
    ctx: FilterContext,
    mode: str,
) -> list[FilterResult]:
    """
    Apply filters to a list of followings.

    Parameters
    ----------
    followings : list[Following]
        The users to filter.
    filters : list[Filter]
        The filters to apply.
    ctx : FilterContext
        Shared context for filter evaluation.
    mode : str
        'and' (all filters must match) or 'or' (any filter matches).

    Returns
    -------
    list[FilterResult]
        Results for users who matched the filter criteria.
    """
    results: list[FilterResult] = []

    print(f'Applying {len(filters)} filter(s) in {mode.upper()} mode...')

    for following in followings:
        result = FilterResult(following=following)

        for f in filters:
            matched, detail = f.matches(following, ctx)
            if matched:
                result.add_match(f.name, detail)

        # Determine if this user should be included in results
        if mode == 'and':
            # All filters must match
            if len(result.matched_filters) == len(filters):
                results.append(result)
        else:  # mode == 'or'
            # Any filter matches
            if result.matched_filters:
                results.append(result)

    print(f'  Found {len(results)} matching users')

    return results


def main() -> None:
    """
    Main entry point for the CLI.

    Loads environment variables, parses arguments, and runs the analysis.
    """
    load_dotenv()
    args = parse_args()

    if not args.mid:
        raise SystemExit('Error: --mid is required (or set MID in .env)')

    # Collect filters from args and environment
    filter_specs: list[str] = args.filters or []
    env_filters = _env_list('FILTERS')
    filter_specs.extend(env_filters)

    if not filter_specs:
        raise SystemExit(
            'Error: At least one filter is required. '
            'Use --list-filters to see options.\n'
            'Example: -f not-following-back -f below-followers:5000'
        )

    # Parse filter specs into Filter instances
    filters: list[Filter] = []
    for spec in filter_specs:
        try:
            filters.append(parse_filter_spec(spec))
        except ValueError as e:
            raise SystemExit(f'Error: {e}') from None

    filter_names = ', '.join(f.name for f in filters)
    print(f'Filters: {filter_names} ({args.filter_mode.upper()} mode)')

    # Initialize disk cache
    cache_fetcher: CachedDataFetcher
    if args.no_cache:
        print('Disk cache: disabled')
        cache_fetcher = CachedDataFetcher(cache=None)
    else:
        disk_cache = get_cache(args.cache_dir)
        cache_fetcher = CachedDataFetcher(cache=disk_cache)
        cache_dir = args.cache_dir or get_cache_dir()
        print(f'Disk cache: {cache_dir}')

        if args.clear_cache:
            cache_fetcher.clear()
            print('  Cache cleared')

    # Load allow list
    allow_list = load_allow_list(args.allow_list)
    if allow_list:
        print(f'Loaded {len(allow_list)} users in allow list')

    # Check if we need to collect interactions (for no-interaction filter)
    needs_interactions = any(f.name == 'no-interaction' for f in filters)

    try:
        # Initialize client with context manager for proper cleanup
        with BilibiliClient(sessdata=args.sessdata, delay=args.delay) as client:
            # Collect interacting users if needed
            interacting_users: set[int] = set()
            if needs_interactions:
                total_posts = args.num_videos + args.num_dynamics
                if total_posts > 0:
                    interacting_users = collect_interacting_users(
                        client,
                        args.mid,
                        args.num_videos,
                        args.num_dynamics,
                    )
                    print(
                        f'\nFound {len(interacting_users)} unique users who interacted'
                    )

            # Build filter context
            ctx = FilterContext(
                client=client,
                my_mid=args.mid,
                interacting_users=interacting_users,
                cache=cache_fetcher,
            )

            # Fetch all followings
            print('Fetching followings...')
            followings: list[Following] = []
            for f in client.get_followings(args.mid):
                mid = int(f['mid'])
                if mid in allow_list:
                    continue
                followings.append(
                    Following(mid=mid, name=f['uname'], attribute=f['attribute'])
                )
            print(f'  Found {len(followings)} followings (after allow list)')

            # Apply filters
            results = apply_filters(followings, filters, ctx, args.filter_mode)

        # Print results
        print_filter_results(results)
    finally:
        cache_fetcher.close()
