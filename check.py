#!/usr/bin/env python3
"""
Bilibili Following Analyzer

Analyzes your Bilibili following list to find:
1. Users who don't follow you back (with < N followers)
2. Users who haven't interacted with your recent posts
"""

from __future__ import annotations

import argparse
import os
import time
import urllib.parse
from dataclasses import dataclass
from functools import reduce
from hashlib import md5
from http.cookiejar import Cookie, CookieJar
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from dotenv import load_dotenv


if TYPE_CHECKING:
    from collections.abc import Iterator


# fmt: off
# WBI signature encoding table
MIXIN_KEY_ENC_TAB = [
    46, 47, 18,  2, 53,  8, 23, 32, 15, 50, 10, 31, 58,  3, 45, 35,
    27, 43,  5, 49, 33,  9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48,  7, 16, 24, 55, 40, 61, 26, 17,  0,  1, 60, 51, 30,  4,
    22, 25, 54, 21, 56, 59,  6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
# fmt: on


@dataclass
class User:
    mid: int
    name: str
    follower_count: int | None = None

    @property
    def space_url(self) -> str:
        return f'https://space.bilibili.com/{self.mid}'


class BilibiliClient:
    """Client for Bilibili API with WBI signature support."""

    BASE_HEADERS = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
            'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.bilibili.com/',
    }

    def __init__(self, sessdata: str | None = None, delay: float = 0.3) -> None:
        self.session = requests.Session()
        self.session.headers.update(self.BASE_HEADERS)
        self.delay = delay

        if sessdata:
            cookie = Cookie(
                version=0,
                name='SESSDATA',
                value=sessdata,
                port=None,
                port_specified=False,
                domain='.bilibili.com',
                domain_specified=True,
                domain_initial_dot=True,
                path='/',
                path_specified=True,
                secure=True,
                expires=None,
                discard=True,
                comment=None,
                comment_url=None,
                rest={},
            )
            # Use CookieJar.set_cookie which has proper type stubs
            CookieJar.set_cookie(self.session.cookies, cookie)

        self._img_key: str | None = None
        self._sub_key: str | None = None

    def _rate_limit(self) -> None:
        time.sleep(self.delay)

    def _get_wbi_keys(self) -> tuple[str, str]:
        """Fetch WBI keys from nav API (cached)."""
        if self._img_key and self._sub_key:
            return self._img_key, self._sub_key

        resp = self.session.get('https://api.bilibili.com/x/web-interface/nav')
        resp.raise_for_status()
        data = resp.json()['data']

        img_url: str = data['wbi_img']['img_url']
        sub_url: str = data['wbi_img']['sub_url']

        self._img_key = img_url.rsplit('/', 1)[1].split('.')[0]
        self._sub_key = sub_url.rsplit('/', 1)[1].split('.')[0]

        return self._img_key, self._sub_key

    def _sign_wbi(self, params: dict[str, Any]) -> dict[str, str]:
        """Sign request parameters with WBI signature."""
        img_key, sub_key = self._get_wbi_keys()
        mixin_key = reduce(
            lambda s, i: s + (img_key + sub_key)[i], MIXIN_KEY_ENC_TAB, ''
        )[:32]

        signed: dict[str, str] = {str(k): str(v) for k, v in params.items()}
        signed['wts'] = str(round(time.time()))
        signed = dict(sorted(signed.items()))

        # Filter out special characters from values
        signed = {
            k: ''.join(c for c in v if c not in "!'()*") for k, v in signed.items()
        }

        query = urllib.parse.urlencode(signed)
        signed['w_rid'] = md5((query + mixin_key).encode()).hexdigest()

        return signed

    def _get(
        self, url: str, params: dict[str, Any] | None = None, *, wbi: bool = False
    ) -> dict[str, Any]:
        """Make a GET request with optional WBI signing."""
        self._rate_limit()

        if params is None:
            params = {}

        if wbi:
            params = self._sign_wbi(params)

        resp = self.session.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    # --------------------------------------------------------------------------
    # Following / Relationship APIs
    # --------------------------------------------------------------------------

    def get_followings(self, mid: int, page_size: int = 20) -> Iterator[dict[str, Any]]:
        """
        Iterate over all followings for a user.

        Uses the game platform API which has no pagination limit.
        Each item contains: mid, attribute, uname, face
        attribute: 2 = following only, 6 = mutual follow
        """
        url = 'https://line3-h5-mobile-api.biligame.com/game/center/h5/user/relationship/following_list'
        pn = 1

        while True:
            data = self._get(url, {'vmid': mid, 'ps': page_size, 'pn': pn})
            following_list = data.get('data', {}).get('list', [])

            if not following_list:
                break

            yield from following_list
            pn += 1

    def get_user_card(self, mid: int) -> dict[str, Any]:
        """Get user card info including follower count."""
        url = 'https://api.bilibili.com/x/web-interface/card'
        return self._get(url, {'mid': mid})['data']

    # --------------------------------------------------------------------------
    # Video APIs
    # --------------------------------------------------------------------------

    def get_user_videos(
        self, mid: int, page_size: int = 30, max_count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Iterate over a user's uploaded videos (newest first)."""
        url = 'https://api.bilibili.com/x/space/wbi/arc/search'
        pn = 1
        count = 0

        while True:
            params = {'mid': mid, 'ps': page_size, 'pn': pn, 'order': 'pubdate'}
            data = self._get(url, params, wbi=True)

            vlist = data.get('data', {}).get('list', {}).get('vlist', [])
            if not vlist:
                break

            for video in vlist:
                yield video
                count += 1
                if max_count and count >= max_count:
                    return

            pn += 1

    def get_video_comments(
        self, aid: int, page_size: int = 20, max_count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Iterate over comments on a video."""
        url = 'https://api.bilibili.com/x/v2/reply/wbi/main'
        next_offset = None
        count = 0

        while True:
            params: dict[str, Any] = {'oid': aid, 'type': 1, 'mode': 3, 'ps': page_size}
            if next_offset:
                params['next'] = next_offset

            data = self._get(url, params, wbi=True)
            cursor = data.get('data', {}).get('cursor', {})
            replies: list[dict[str, Any]] = data.get('data', {}).get('replies') or []

            for reply in replies:
                yield reply
                count += 1
                if max_count and count >= max_count:
                    return

            if not cursor.get('is_end', True):
                next_offset = cursor.get('next')
            else:
                break

    # --------------------------------------------------------------------------
    # Dynamic APIs
    # --------------------------------------------------------------------------

    def get_user_dynamics(
        self, mid: int, max_count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Iterate over a user's dynamics (newest first)."""
        url = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space'
        offset = None
        count = 0

        while True:
            params = {'host_mid': mid}
            if offset:
                params['offset'] = offset

            data = self._get(url, params)
            items = data.get('data', {}).get('items', [])

            if not items:
                break

            for item in items:
                yield item
                count += 1
                if max_count and count >= max_count:
                    return

            if data.get('data', {}).get('has_more'):
                offset = data['data'].get('offset')
            else:
                break

    def get_dynamic_reactions(self, dynamic_id: str) -> Iterator[dict[str, Any]]:
        """Get users who liked/forwarded a dynamic (requires auth)."""
        url = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/detail/reaction'
        offset = None

        while True:
            params = {'id': dynamic_id}
            if offset:
                params['offset'] = offset

            data = self._get(url, params)
            items: list[dict[str, Any]] = data.get('data', {}).get('items') or []

            if not items:
                break

            yield from items

            if data.get('data', {}).get('has_more'):
                offset = data['data'].get('offset')
            else:
                break

    def get_dynamic_comments(
        self, dynamic_id: str, page_size: int = 20, max_count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """Get comments on a dynamic."""
        url = 'https://api.bilibili.com/x/v2/reply/wbi/main'
        next_offset = None
        count = 0

        while True:
            params: dict[str, Any] = {
                'oid': dynamic_id,
                'type': 17,
                'mode': 3,
                'ps': page_size,
            }
            if next_offset:
                params['next'] = next_offset

            data = self._get(url, params, wbi=True)
            cursor = data.get('data', {}).get('cursor', {})
            replies: list[dict[str, Any]] = data.get('data', {}).get('replies') or []

            for reply in replies:
                yield reply
                count += 1
                if max_count and count >= max_count:
                    return

            if not cursor.get('is_end', True):
                next_offset = cursor.get('next')
            else:
                break


def load_allow_list(path: Path | None) -> set[int]:
    """Load allow list from a file (one UID per line, # for comments)."""
    if not path or not path.exists():
        return set()

    allow_list: set[int] = set()
    for line in path.read_text().splitlines():
        line = line.split('#')[0].strip()
        if line:
            allow_list.add(int(line))

    return allow_list


def collect_interacting_users(
    client: BilibiliClient,
    my_mid: int,
    num_videos: int,
    num_dynamics: int,
) -> set[int]:
    """
    Collect all user IDs who interacted with recent posts.

    Interactions include: likes, forwards, and comments on videos and dynamics.
    """
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
                interacting_users.add(comment['mid'])

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

            # Get comments
            for comment in client.get_dynamic_comments(dynamic_id, max_count=100):
                interacting_users.add(comment['mid'])

            dynamic_count += 1

        print(f'  Processed {dynamic_count} dynamics')

    return interacting_users


def analyze_followings(
    client: BilibiliClient,
    my_mid: int,
    allow_list: set[int],
    follower_threshold: int,
    interacting_users: set[int],
) -> tuple[list[User], list[User]]:
    """
    Analyze followings and categorize them.

    Returns:
        - not_following_back: Users who don't follow back and have < threshold followers
        - no_interaction: Users who haven't interacted with recent posts
    """
    not_following_back: list[User] = []
    no_interaction: list[User] = []

    print('Analyzing followings...')

    for following in client.get_followings(my_mid):
        mid = int(following['mid'])
        name = following['uname']
        is_mutual = following['attribute'] == 6

        if mid in allow_list:
            continue

        if is_mutual:
            # Mutual follow - check if they've interacted
            if mid not in interacting_users:
                no_interaction.append(User(mid=mid, name=name))
        else:
            # Not following back - check follower count
            card = client.get_user_card(mid)
            follower_count = card.get('follower', 0)

            if follower_count < follower_threshold:
                not_following_back.append(
                    User(mid=mid, name=name, follower_count=follower_count)
                )
            elif mid not in interacting_users:
                # Has many followers but no interaction
                no_interaction.append(
                    User(mid=mid, name=name, follower_count=follower_count)
                )

    return not_following_back, no_interaction


def print_results(
    not_following_back: list[User],
    no_interaction: list[User],
) -> None:
    """Print analysis results."""
    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)

    if not_following_back:
        print(f'\n📛 NOT FOLLOWING BACK ({len(not_following_back)} users):')
        print('-' * 40)
        for user in not_following_back:
            suffix = (
                f' ({user.follower_count} followers)' if user.follower_count else ''
            )  # noqa: E501
            print(f'  {user.name}{suffix}')
            print(f'    {user.space_url}')
    else:
        print('\n✅ Everyone is following you back (or above follower threshold)!')

    if no_interaction:
        print(f'\n😴 NO RECENT INTERACTION ({len(no_interaction)} users):')
        print('-' * 40)
        for user in no_interaction:
            suffix = ''
            if user.follower_count is not None:
                suffix = f' ({user.follower_count} followers)'
            print(f'  {user.name}{suffix}')
            print(f'    {user.space_url}')
    else:
        print('\n✅ All followings have interacted with your recent posts!')


def main() -> None:
    load_dotenv()

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

    args = parser.parse_args()

    if not args.mid:
        parser.error('--mid is required (or set MID in .env)')

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


if __name__ == '__main__':
    main()
