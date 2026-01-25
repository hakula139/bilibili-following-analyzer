"""Command-line interface for Bilibili Following Analyzer."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv
from tqdm import tqdm

from .cache import CachedDataFetcher, get_cache, get_cache_dir
from .client import BilibiliClient
from .filters import (
    Filter,
    FilterContext,
    FilterResult,
    Following,
    get_filter_help,
    parse_filter_expression,
    parse_filter_spec,
)
from .utils import load_allow_list, output_results_to_file, print_filter_results


T = TypeVar('T')


def _env_parse(name: str, default: T, parser: Callable[[str], T], type_name: str) -> T:
    """
    Parse an environment variable with a type converter.

    Parameters
    ----------
    name : str
        The environment variable name.
    default : T
        The default value if the variable is not set or empty.
    parser : Callable[[str], T]
        Function to convert string to the desired type.
    type_name : str
        Human-readable type name for error messages.

    Returns
    -------
    T
        The parsed value.

    Raises
    ------
    SystemExit
        If the value is set but cannot be parsed.
    """
    val = os.environ.get(name)
    if not val:
        return default
    try:
        return parser(val)
    except ValueError:
        msg = f'Error: {name} must be a valid {type_name}, got {val!r}'
        raise SystemExit(msg) from None


def _env_int(name: str, default: int) -> int:
    """Get an integer from an environment variable with a default."""
    return _env_parse(name, default, int, 'integer')


def _env_float(name: str, default: float) -> float:
    """Get a float from an environment variable with a default."""
    return _env_parse(name, default, float, 'number')


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
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Limit analysis to the first N followings (for testing)',
    )
    output_default = os.environ.get('OUTPUT')
    parser.add_argument(
        '-o',
        '--output',
        type=Path,
        metavar='FILE',
        default=Path(output_default) if output_default else None,
        help='Output results to a file (supports .txt, .json, .csv). Env: OUTPUT',
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
        '--filter-expr',
        type=str,
        metavar='EXPR',
        default=os.environ.get('FILTER_EXPR'),
        help=(
            'Complex filter expression with nested AND/OR logic. '
            'Use + for AND, | for OR, () for grouping. '
            'Example: "(a + b) | (c + d + (e | f))". Env: FILTER_EXPR'
        ),
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


def _collect_video_interactions(
    client: BilibiliClient,
    mid: int,
    num_videos: int,
    users: set[int],
) -> None:
    """
    Collect user IDs from video comments.

    Parameters
    ----------
    client : BilibiliClient
        The authenticated API client.
    mid : int
        The user's member ID whose videos to check.
    num_videos : int
        Number of recent videos to check.
    users : set[int]
        Set to add interacting user IDs to (modified in place).
    """
    videos = list(client.get_user_videos(mid, max_count=num_videos))
    for video in tqdm(videos, desc='Videos', unit='video'):
        aid = video['aid']
        for comment in client.get_video_comments(aid, max_count=100):
            users.add(comment['member']['mid'])


def _collect_dynamic_interactions(
    client: BilibiliClient,
    mid: int,
    num_dynamics: int,
    users: set[int],
) -> None:
    """
    Collect user IDs from dynamic reactions and comments.

    Parameters
    ----------
    client : BilibiliClient
        The authenticated API client.
    mid : int
        The user's member ID whose dynamics to check.
    num_dynamics : int
        Number of recent dynamics to check.
    users : set[int]
        Set to add interacting user IDs to (modified in place).
    """
    from .client import BilibiliAPIError

    dynamics = list(client.get_user_dynamics(mid, max_count=num_dynamics))
    for dynamic in tqdm(dynamics, desc='Dynamics', unit='dyn'):
        dynamic_id = dynamic['id_str']

        # Get likes and forwards
        for reaction in client.get_dynamic_reactions(dynamic_id):
            users.add(reaction['mid'])

        # Get comments (some dynamic types don't support comments)
        try:
            for comment in client.get_dynamic_comments(dynamic_id, max_count=100):
                users.add(comment['member']['mid'])
        except BilibiliAPIError as e:
            if e.code == -404:
                pass  # Dynamic has no comment section
            else:
                raise


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
    interacting_users: set[int] = set()

    if num_videos > 0:
        _collect_video_interactions(client, my_mid, num_videos, interacting_users)

    if num_dynamics > 0:
        _collect_dynamic_interactions(client, my_mid, num_dynamics, interacting_users)

    return interacting_users


def apply_filters(
    followings: list[Following],
    filters: list[Filter],
    ctx: FilterContext,
    mode: str,
) -> list[FilterResult]:
    """
    Apply filters to a list of followings (simple mode).

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

    for following in tqdm(followings, desc='Filtering', unit='user'):
        result = FilterResult(following=following)

        for f in filters:
            match_info = f.matches(following, ctx)
            if match_info.matched:
                result.add_match(f.name, match_info.detail)

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


def apply_filter_expression(
    followings: list[Following],
    composite_filter: Filter,
    ctx: FilterContext,
) -> list[FilterResult]:
    """
    Apply a composite filter expression to a list of followings.

    Parameters
    ----------
    followings : list[Following]
        The users to filter.
    composite_filter : Filter
        A composite filter (AndFilter / OrFilter) representing the expression.
    ctx : FilterContext
        Shared context for filter evaluation.

    Returns
    -------
    list[FilterResult]
        Results for users who matched the filter expression.
    """
    results: list[FilterResult] = []

    print('Applying filter expression...')

    for following in tqdm(followings, desc='Filtering', unit='user'):
        match_info = composite_filter.matches(following, ctx)
        if match_info.matched:
            result = FilterResult(following=following)
            # Add each matched filter individually
            for filter_name in match_info.filter_names:
                result.add_match(filter_name, None)
            # Store the combined detail under a special key for display
            if match_info.detail:
                result.details['_combined'] = match_info.detail
            results.append(result)

    print(f'  Found {len(results)} matching users')

    return results


def _collect_filter_specs(args: argparse.Namespace) -> list[str]:
    """Collect filter specs from args and environment."""
    filter_specs: list[str] = args.filters or []
    env_filters = _env_list('FILTERS')
    filter_specs.extend(env_filters)

    if not filter_specs:
        raise SystemExit(
            'Error: At least one filter is required. '
            'Use --list-filters to see options.\n'
            'Example: -f not-following-back -f below-followers:5000'
        )

    return filter_specs


def _parse_filters(filter_specs: list[str]) -> list[Filter]:
    """Parse filter specifications into Filter instances."""
    filters: list[Filter] = []
    for spec in filter_specs:
        try:
            filters.append(parse_filter_spec(spec))
        except ValueError as e:
            raise SystemExit(f'Error: {e}') from None
    return filters


def _setup_cache(args: argparse.Namespace) -> CachedDataFetcher:
    """Initialize disk cache based on arguments."""
    if args.no_cache:
        print('Disk cache: disabled')
        return CachedDataFetcher(cache=None)

    disk_cache = get_cache(args.cache_dir)
    cache_fetcher = CachedDataFetcher(cache=disk_cache)
    cache_dir = args.cache_dir or get_cache_dir()
    print(f'Disk cache: {cache_dir}')

    if args.clear_cache:
        cache_fetcher.clear()
        print('  Cache cleared')

    return cache_fetcher


def _fetch_followings(
    client: BilibiliClient,
    mid: int,
    allow_list: set[int],
    limit: int | None = None,
) -> list[Following]:
    """Fetch followings and filter by allow list."""
    print('Fetching followings...')
    followings: list[Following] = []
    for f in client.get_followings(mid):
        user_mid = int(f['mid'])
        if user_mid in allow_list:
            continue
        followings.append(
            Following(mid=user_mid, name=f['uname'], attribute=f['attribute'])
        )
        if limit and len(followings) >= limit:
            break
    print(f'  Found {len(followings)} followings (after allow list)')
    return followings


def _needs_interaction_data(filter_obj: Filter) -> bool:
    """Check if a filter (possibly composite) needs interaction data."""
    from .filters import AndFilter, OrFilter

    if filter_obj.name == 'no-interaction':
        return True
    if isinstance(filter_obj, (AndFilter, OrFilter)):
        return any(_needs_interaction_data(f) for f in filter_obj.filters)
    return False


def _run_analysis(
    args: argparse.Namespace,
    filters: list[Filter] | None,
    composite_filter: Filter | None,
    cache_fetcher: CachedDataFetcher,
    allow_list: set[int],
) -> list[FilterResult]:
    """
    Run the main analysis with the API client.

    Either filters (simple mode) or composite_filter (expression mode) should be set.
    """
    # Check if we need interaction data
    if composite_filter:
        needs_interactions = _needs_interaction_data(composite_filter)
    else:
        needs_interactions = any(f.name == 'no-interaction' for f in (filters or []))

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
                print(f'\nFound {len(interacting_users)} unique users who interacted')

        # Build filter context
        ctx = FilterContext(
            client=client,
            my_mid=args.mid,
            interacting_users=interacting_users,
            cache=cache_fetcher,
        )

        # Fetch followings and apply filters
        followings = _fetch_followings(client, args.mid, allow_list, args.limit)

        if composite_filter:
            return apply_filter_expression(followings, composite_filter, ctx)
        else:
            return apply_filters(followings, filters or [], ctx, args.filter_mode)


def main() -> None:
    """
    Main entry point for the CLI.

    Loads environment variables, parses arguments, and runs the analysis.
    """
    load_dotenv()
    args = parse_args()

    if not args.mid:
        raise SystemExit('Error: --mid is required (or set MID in .env)')

    # Parse filters (expression mode or simple mode)
    filters: list[Filter] | None = None
    composite_filter: Filter | None = None

    if args.filter_expr:
        # Expression mode: parse complex filter expression
        try:
            composite_filter = parse_filter_expression(args.filter_expr)
            print(f'Filter expression: {args.filter_expr}')
        except ValueError as e:
            raise SystemExit(f'Error parsing filter expression: {e}') from None
    else:
        # Simple mode: use -f/--filter options
        filter_specs = _collect_filter_specs(args)
        filters = _parse_filters(filter_specs)
        filter_names = ', '.join(f.name for f in filters)
        print(f'Filters: {filter_names} ({args.filter_mode.upper()} mode)')

    # Initialize cache and load allow list
    cache_fetcher = _setup_cache(args)
    allow_list = load_allow_list(args.allow_list)
    if allow_list:
        print(f'Loaded {len(allow_list)} users in allow list')

    try:
        results = _run_analysis(
            args, filters, composite_filter, cache_fetcher, allow_list
        )
        print_filter_results(results)
        if args.output:
            output_results_to_file(results, args.output)
    finally:
        cache_fetcher.close()
