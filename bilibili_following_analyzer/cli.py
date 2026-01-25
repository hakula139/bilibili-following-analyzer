"""Command-line interface for Bilibili Following Analyzer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import (
    analyze_followings,
    collect_interacting_users,
    filter_inactive_users,
)
from .client import BilibiliClient
from .models import FilterConfig
from .utils import load_allow_list, print_results


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


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns
    -------
    argparse.Namespace
        Parsed arguments with fields: mid, sessdata, follower_threshold,
        num_videos, num_dynamics, allow_list, delay.
    """
    parser = argparse.ArgumentParser(
        description='Analyze your Bilibili following list',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        '--mid',
        type=int,
        default=os.environ.get('MID'),
        help='Your Bilibili user ID (UID)',
    )
    parser.add_argument(
        '--sessdata',
        type=str,
        default=os.environ.get('SESSDATA'),
        help='SESSDATA cookie for authentication (required for some features)',
    )
    parser.add_argument(
        '--follower-threshold',
        type=int,
        default=_env_int('FOLLOWER_THRESHOLD', 5000),
        help='Only report non-followers with fewer than this many followers',
    )
    parser.add_argument(
        '--num-videos',
        type=int,
        default=_env_int('NUM_VIDEOS', 10),
        help='Number of recent videos to check for interactions',
    )
    parser.add_argument(
        '--num-dynamics',
        type=int,
        default=_env_int('NUM_DYNAMICS', 20),
        help='Number of recent dynamics to check for interactions',
    )
    parser.add_argument(
        '--allow-list',
        type=Path,
        default=os.environ.get('ALLOW_LIST'),
        help='Path to allow list file (one UID per line)',
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=_env_float('DELAY', 0.3),
        help='Delay between API requests (seconds)',
    )

    # Filter options (all optional - only enabled if specified)
    filter_group = parser.add_argument_group(
        'filtering options',
        'Optional filters for the no-interaction list. Only enabled if specified.',
    )
    filter_group.add_argument(
        '--filter-max-following',
        type=int,
        default=os.environ.get('FILTER_MAX_FOLLOWING'),
        metavar='N',
        help='Filter users following more than N accounts (e.g., 3000)',
    )
    filter_group.add_argument(
        '--filter-inactive-days',
        type=int,
        default=os.environ.get('FILTER_INACTIVE_DAYS'),
        metavar='DAYS',
        help='Filter users who have not posted in DAYS (e.g., 365)',
    )
    filter_group.add_argument(
        '--filter-repost-ratio',
        type=float,
        default=os.environ.get('FILTER_REPOST_RATIO'),
        metavar='RATIO',
        help='Filter users whose repost ratio exceeds RATIO (0.0-1.0, e.g., 0.8)',
    )
    filter_group.add_argument(
        '--filter-dynamics-count',
        type=int,
        default=_env_int('FILTER_DYNAMICS_COUNT', 10),
        metavar='N',
        help='Number of recent dynamics to check for filtering (default: 10)',
    )

    return parser.parse_args()


def main() -> None:
    """
    Main entry point for the CLI.

    Loads environment variables, parses arguments, and runs the analysis.
    """
    load_dotenv()
    args = parse_args()

    if not args.mid:
        raise SystemExit('Error: --mid is required (or set MID in .env)')

    # Load allow list
    allow_list = load_allow_list(args.allow_list)
    if allow_list:
        print(f'Loaded {len(allow_list)} users in allow list')

    # Build filter config from args
    filter_config = FilterConfig(
        max_following=args.filter_max_following,
        inactive_days=args.filter_inactive_days,
        repost_ratio=args.filter_repost_ratio,
        dynamics_to_check=args.filter_dynamics_count,
    )

    # Initialize client with context manager for proper cleanup
    with BilibiliClient(sessdata=args.sessdata, delay=args.delay) as client:
        # Collect interacting users
        total_posts = args.num_videos + args.num_dynamics
        interacting_users: set[int]
        if total_posts > 0:
            interacting_users = collect_interacting_users(
                client,
                args.mid,
                args.num_videos,
                args.num_dynamics,
            )
            print(f'\nFound {len(interacting_users)} unique users who interacted')
        else:
            interacting_users = set()

        # Analyze followings
        not_following_back, no_interaction = analyze_followings(
            client,
            args.mid,
            allow_list,
            args.follower_threshold,
            interacting_users,
        )

        # Apply filters to no_interaction list if any filters are enabled
        filtered_users = None
        if filter_config.is_enabled():
            no_interaction, filtered_users = filter_inactive_users(
                client, no_interaction, filter_config
            )

    # Print results
    print_results(not_following_back, no_interaction, filtered_users)
