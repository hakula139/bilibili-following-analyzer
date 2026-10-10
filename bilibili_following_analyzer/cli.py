"""Command-line interface for Bilibili Following Analyzer."""

from __future__ import annotations

import argparse
import math
import os
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from tqdm import tqdm

from .cache import (
    USER_ACTIVITY_KEY_PREFIX,
    CachedDataFetcher,
    get_cache,
    get_cache_dir,
)
from .client import ActivityStatus, BilibiliAPIError, BilibiliClient, UserActivity
from .filters import (
    AndFilter,
    Filter,
    FilterContext,
    FilterResult,
    Following,
    OrFilter,
    get_filter_help,
    parse_filter_expression,
    parse_filter_spec,
)
from .utils import load_allow_list, output_results_to_file, print_filter_results


def _report_activity_failures(ctx: FilterContext) -> None:
    """Print a summary of users whose activity could not be fetched.

    Surfaces fetch failures (rate limits, risk-control challenges, etc.) so
    they aren't silently treated as "no posts" by activity-based filters.
    """
    failed = [
        a for a in ctx.user_activity.values() if a.status == ActivityStatus.UNAVAILABLE
    ]
    if not failed:
        return

    by_code = Counter(a.error_code for a in failed)
    breakdown = ', '.join(f'code={code}: {n}' for code, n in by_code.most_common())
    print(
        f'\nWarning: activity fetch failed for {len(failed)} user(s) '
        f'({breakdown}); they were skipped by activity-based filters.'
    )


def _purge_unavailable_activity(cache_fetcher: CachedDataFetcher) -> int:
    """Evict cached activity entries whose status is ``UNAVAILABLE``.

    Successful (``OK``) and ``DEACTIVATED`` entries stay cached so a re-run
    only re-fetches the previously failed users. Returns the number of
    entries purged.
    """
    cache = cache_fetcher.cache
    if cache is None:
        return 0

    purged = 0
    for key in list(cache):
        if not isinstance(key, str) or not key.startswith(USER_ACTIVITY_KEY_PREFIX):
            continue
        value = cache.get(key)
        if (
            isinstance(value, UserActivity)
            and value.status == ActivityStatus.UNAVAILABLE
        ):
            del cache[key]
            purged += 1
    return purged


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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
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
        default=os.environ.get('DELAY', '0.3'),
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
    filter_selection = filter_group.add_mutually_exclusive_group()
    filter_selection.add_argument(
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
    filter_selection.add_argument(
        '--filter-expr',
        type=str,
        metavar='EXPR',
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
        default=os.environ.get('NUM_VIDEOS', '10'),
        help='Number of recent videos to check for interactions. Env: NUM_VIDEOS',
    )
    interaction_group.add_argument(
        '--num-dynamics',
        type=int,
        default=os.environ.get('NUM_DYNAMICS', '20'),
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
        '--retry-failed',
        action='store_true',
        help=(
            'Evict cached UNAVAILABLE activity entries before running so '
            'previously failed users are retried; OK/DEACTIVATED entries '
            'stay cached and are skipped.'
        ),
    )
    cache_group.add_argument(
        '--cache-dir',
        type=Path,
        help=f'Custom cache directory (default: {get_cache_dir()})',
    )

    args = parser.parse_args(argv)
    if args.filter_mode not in ('and', 'or'):
        parser.error('--filter-mode must be and or or')
    if not math.isfinite(args.delay) or args.delay < 0:
        parser.error('--delay must be a finite nonnegative number')
    if args.mid is not None and args.mid <= 0:
        parser.error('--mid must be a positive integer')
    for name in ('limit', 'num_videos', 'num_dynamics'):
        value = getattr(args, name)
        if value is not None and value < 0:
            parser.error(f'--{name.replace("_", "-")} must be a nonnegative integer')
    if args.filters is None and args.filter_expr is None:
        args.filter_expr = os.environ.get('FILTER_EXPR')
    return args


def _comment_user_ids(comments: Iterable[dict[str, Any]]) -> Iterator[int]:
    """Yield authors of comments and the nested replies included in the response."""
    for comment in comments:
        yield int(comment['member']['mid'])
        yield from _comment_user_ids(comment.get('replies') or [])


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
        users.update(_comment_user_ids(client.get_comments(aid, type_=1)))


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
    dynamics = list(client.get_user_dynamics(mid, max_count=num_dynamics))
    for dynamic in tqdm(dynamics, desc='Dynamics', unit='dyn'):
        dynamic_id = dynamic['id_str']

        # Get likes and forwards
        for reaction in client.get_dynamic_reactions(dynamic_id):
            users.add(int(reaction['mid']))

        basic = dynamic['basic']
        if basic['comment_type']:
            users.update(
                _comment_user_ids(
                    client.get_comments(
                        basic['comment_id_str'], type_=basic['comment_type']
                    )
                )
            )


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
    followings: list[Following], filter_obj: Filter, ctx: FilterContext
) -> list[FilterResult]:
    """Evaluate a filter tree and preserve each contributing leaf match."""
    results: list[FilterResult] = []
    for following in tqdm(followings, desc='Filtering', unit='user'):
        result = filter_obj.matches(following, ctx)
        if result.matched:
            results.append(FilterResult(following, result.matches))
    print(f'  Found {len(results)} matching users')
    return results


def _collect_filter_specs(args: argparse.Namespace) -> list[str]:
    """Collect filter specs from args and environment."""
    filter_specs = args.filters if args.filters is not None else _env_list('FILTERS')

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
    elif args.retry_failed:
        purged = _purge_unavailable_activity(cache_fetcher)
        print(f'  Retry mode: purged {purged} previously failed activity entries')

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
    if limit == 0:
        return followings
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
    if filter_obj.name == 'no-interaction':
        return True
    if isinstance(filter_obj, (AndFilter, OrFilter)):
        return any(_needs_interaction_data(f) for f in filter_obj.filters)
    return False


def _run_analysis(
    args: argparse.Namespace,
    filter_obj: Filter,
    cache_fetcher: CachedDataFetcher,
    allow_list: set[int],
) -> list[FilterResult]:
    """Collect the data required by a filter tree and evaluate followings."""
    needs_interactions = _needs_interaction_data(filter_obj)
    if needs_interactions and args.num_videos + args.num_dynamics == 0:
        raise ValueError('no-interaction requires a nonempty video or dynamic sample')

    with BilibiliClient(sessdata=args.sessdata, delay=args.delay) as client:
        interacting_users = None
        if needs_interactions:
            interacting_users = collect_interacting_users(
                client, args.mid, args.num_videos, args.num_dynamics
            )
            print(f'\nFound {len(interacting_users)} unique users who interacted')

        ctx = FilterContext(
            client=client,
            my_mid=args.mid,
            interacting_users=interacting_users,
            cache=cache_fetcher,
        )
        followings = _fetch_followings(client, args.mid, allow_list, args.limit)
        results = apply_filters(followings, filter_obj, ctx)
        _report_activity_failures(ctx)
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

    try:
        if args.filter_expr:
            filter_obj = parse_filter_expression(args.filter_expr)
            print(f'Filter expression: {args.filter_expr}')
        else:
            filters = _parse_filters(_collect_filter_specs(args))
            filter_obj = (
                AndFilter(filters) if args.filter_mode == 'and' else OrFilter(filters)
            )
            filter_names = ', '.join(filter_.name for filter_ in filters)
            print(f'Filters: {filter_names} ({args.filter_mode.upper()} mode)')
        allow_list = load_allow_list(args.allow_list)
    except ValueError as error:
        raise SystemExit(f'Error: {error}') from None

    if allow_list:
        print(f'Loaded {len(allow_list)} users in allow list')
    cache_fetcher = _setup_cache(args)
    try:
        results = _run_analysis(args, filter_obj, cache_fetcher, allow_list)
        print_filter_results(results)
        if args.output:
            output_results_to_file(results, args.output)
    except (ValueError, BilibiliAPIError, requests.RequestException) as error:
        raise SystemExit(f'Error: {error}') from None
    finally:
        cache_fetcher.close()
