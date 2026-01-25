"""Bilibili API client with WBI signature support."""

from __future__ import annotations

import time
import urllib.parse
from functools import reduce
from hashlib import md5
from http.cookiejar import Cookie, CookieJar
from typing import TYPE_CHECKING, Any

import requests


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


class BilibiliClient:
    """
    Client for Bilibili API with WBI signature support.

    Parameters
    ----------
    sessdata : str or None, optional
        SESSDATA cookie for authentication. Required for some APIs.
    delay : float, optional
        Delay between API requests in seconds. Default is 0.3.

    Attributes
    ----------
    session : requests.Session
        The underlying HTTP session.
    delay : float
        Rate limiting delay between requests.
    """

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

        # Fetch buvid3 cookie by visiting the homepage (required for some APIs)
        self.session.get('https://www.bilibili.com/')

    def _rate_limit(self) -> None:
        """Apply rate limiting delay between requests."""
        time.sleep(self.delay)

    def _get_wbi_keys(self) -> tuple[str, str]:
        """
        Fetch WBI keys from nav API.

        Keys are cached after the first call.

        Returns
        -------
        tuple[str, str]
            The (img_key, sub_key) pair used for WBI signing.
        """
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
        """
        Sign request parameters with WBI signature.

        Parameters
        ----------
        params : dict[str, Any]
            The request parameters to sign.

        Returns
        -------
        dict[str, str]
            Signed parameters including wts and w_rid fields.
        """
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
        """
        Make a GET request with optional WBI signing.

        Parameters
        ----------
        url : str
            The API endpoint URL.
        params : dict[str, Any] or None, optional
            Query parameters for the request.
        wbi : bool, optional
            Whether to apply WBI signing. Default is False.

        Returns
        -------
        dict[str, Any]
            The JSON response from the API.

        Raises
        ------
        requests.HTTPError
            If the request fails.
        """
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

        Parameters
        ----------
        mid : int
            The user's member ID.
        page_size : int, optional
            Number of results per page. Default is 20.

        Yields
        ------
        dict[str, Any]
            Following info with keys: mid, attribute, uname, face.
            attribute: 2 = following only, 6 = mutual follow.
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

    def get_user_stat(self, mid: int) -> dict[str, Any]:
        """
        Get user relationship stats including follower count.

        Parameters
        ----------
        mid : int
            The user's member ID.

        Returns
        -------
        dict[str, Any]
            Stats dict with keys: mid, following, whisper, black, follower.
        """
        url = 'https://api.bilibili.com/x/relation/stat'
        return self._get(url, {'vmid': mid})['data']

    # --------------------------------------------------------------------------
    # Video APIs
    # --------------------------------------------------------------------------

    def get_user_videos(
        self, mid: int, page_size: int = 30, max_count: int | None = None
    ) -> Iterator[dict[str, Any]]:
        """
        Iterate over a user's uploaded videos (newest first).

        Parameters
        ----------
        mid : int
            The user's member ID.
        page_size : int, optional
            Number of results per page. Default is 30.
        max_count : int or None, optional
            Maximum number of videos to return. None for unlimited.

        Yields
        ------
        dict[str, Any]
            Video info including aid, title, created, etc.
        """
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
        """
        Iterate over comments on a video.

        Parameters
        ----------
        aid : int
            The video's archive ID (aid).
        page_size : int, optional
            Number of results per page. Default is 20.
        max_count : int or None, optional
            Maximum number of comments to return. None for unlimited.

        Yields
        ------
        dict[str, Any]
            Comment info including mid, content, ctime, etc.
        """
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
        """
        Iterate over a user's dynamics (newest first).

        Parameters
        ----------
        mid : int
            The user's member ID.
        max_count : int or None, optional
            Maximum number of dynamics to return. None for unlimited.

        Yields
        ------
        dict[str, Any]
            Dynamic info including id_str, type, modules, etc.
        """
        url = 'https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space'
        offset = None
        count = 0

        while True:
            params = {'host_mid': mid}
            if offset:
                params['offset'] = offset

            data = self._get(url, params, wbi=True)
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
        """
        Get users who liked/forwarded a dynamic.

        Requires authentication (SESSDATA).

        Parameters
        ----------
        dynamic_id : str
            The dynamic's ID string.

        Yields
        ------
        dict[str, Any]
            Reaction info including mid, type, etc.
        """
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
        """
        Get comments on a dynamic.

        Parameters
        ----------
        dynamic_id : str
            The dynamic's ID string.
        page_size : int, optional
            Number of results per page. Default is 20.
        max_count : int or None, optional
            Maximum number of comments to return. None for unlimited.

        Yields
        ------
        dict[str, Any]
            Comment info including mid, content, ctime, etc.
        """
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
