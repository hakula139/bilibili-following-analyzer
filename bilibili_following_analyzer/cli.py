"""Command-line interface for Bilibili Following Analyzer."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import analyze_followings, collect_interacting_users
from .client import BilibiliClient
from .utils import load_allow_list, print_results


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
        default=int(os.environ.get('FOLLOWER_THRESHOLD', 5000)),
        help='Only report non-followers with fewer than this many followers',
    )
    parser.add_argument(
        '--num-videos',
        type=int,
        default=int(os.environ.get('NUM_VIDEOS', 10)),
        help='Number of recent videos to check for interactions',
    )
    parser.add_argument(
        '--num-dynamics',
        type=int,
        default=int(os.environ.get('NUM_DYNAMICS', 10)),
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
        default=float(os.environ.get('DELAY', 0.3)),
        help='Delay between API requests (seconds)',
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

    # Initialize client
    client = BilibiliClient(sessdata=args.sessdata, delay=args.delay)

    # Collect interacting users
    total_posts = args.num_videos + args.num_dynamics
    if total_posts > 0:
        interacting_users = collect_interacting_users(
            client,
            args.mid,
            args.num_videos,
            args.num_dynamics,
        )
        print(f'\nFound {len(interacting_users)} unique users who interacted')
    else:
        interacting_users: set[int] = set()

    # Analyze followings
    not_following_back, no_interaction = analyze_followings(
        client,
        args.mid,
        allow_list,
        args.follower_threshold,
        interacting_users,
    )

    # Print results
    print_results(not_following_back, no_interaction)
