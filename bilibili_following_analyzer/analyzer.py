"""Analysis functions for Bilibili following data."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from .client import BilibiliAPIError
from .models import FilterConfig, FilteredUser, User


if TYPE_CHECKING:
    from .client import BilibiliClient


# Bilibili relationship attribute values
ATTRIBUTE_FOLLOWING = 2  # Following only (not mutual)
ATTRIBUTE_MUTUAL = 6  # Mutual follow


def collect_interacting_users(
    client: BilibiliClient,
    my_mid: int,
    num_videos: int,
    num_dynamics: int,
) -> set[int]:
    """
    Collect all user IDs who interacted with recent posts.

    Interactions include: likes, forwards, and comments on videos and dynamics.

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


def analyze_followings(
    client: BilibiliClient,
    my_mid: int,
    allow_list: set[int],
    follower_threshold: int,
    interacting_users: set[int],
) -> tuple[list[User], list[User]]:
    """
    Analyze followings and categorize them.

    Parameters
    ----------
    client : BilibiliClient
        The authenticated API client.
    my_mid : int
        The user's own member ID.
    allow_list : set[int]
        Set of user IDs to skip.
    follower_threshold : int
        Only report non-followers with fewer than this many followers.
    interacting_users : set[int]
        Set of user IDs who have interacted.

    Returns
    -------
    tuple[list[User], list[User]]
        A tuple of (not_following_back, no_interaction) user lists.
        - not_following_back: Users who don't follow back and have < threshold followers
        - no_interaction: Users who haven't interacted with recent posts
    """
    not_following_back: list[User] = []
    no_interaction: list[User] = []

    print('Analyzing followings...')

    for following in client.get_followings(my_mid):
        mid = int(following['mid'])
        name = following['uname']
        is_mutual = following['attribute'] == ATTRIBUTE_MUTUAL

        if mid in allow_list:
            continue

        if is_mutual:
            # Mutual follow - check if they've interacted
            if mid not in interacting_users:
                no_interaction.append(User(mid=mid, name=name))
        else:
            # Not following back - check follower count
            stat = client.get_user_stat(mid)
            follower_count = stat.get('follower', 0)

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


def filter_inactive_users(
    client: BilibiliClient,
    users: list[User],
    config: FilterConfig,
) -> tuple[list[User], list[FilteredUser]]:
    """
    Filter users based on activity criteria.

    Parameters
    ----------
    client : BilibiliClient
        The authenticated API client.
    users : list[User]
        List of users to filter.
    config : FilterConfig
        Filter configuration with enabled criteria.

    Returns
    -------
    tuple[list[User], list[FilteredUser]]
        A tuple of (kept_users, filtered_users).
        - kept_users: Users who passed all filters
        - filtered_users: Users who matched at least one filter criterion
    """
    if not config.is_enabled():
        return users, []

    kept: list[User] = []
    filtered: list[FilteredUser] = []

    now_ts = int(time.time())

    print(f'Filtering {len(users)} users for activity...')

    for user in users:
        max_dynamics = config.dynamics_to_check
        activity = client.get_user_activity(user.mid, max_dynamics=max_dynamics)
        reasons: list[str] = []

        # Check: deactivated account
        if activity['is_deactivated']:
            reasons.append('账号已注销或空间不可访问')

        # Check: too many followings
        if config.max_following is not None:
            following_count = activity['following_count']
            if following_count > config.max_following:
                reasons.append(f'关注数过多 ({following_count})')

        # Check: no posts at all
        if activity['total_dynamics'] == 0 and not activity['is_deactivated']:
            reasons.append('无任何动态')

        # Check: inactive for too long
        if config.inactive_days is not None and activity['last_post_ts'] is not None:
            days_since_post = (now_ts - activity['last_post_ts']) // 86400
            if days_since_post > config.inactive_days:
                reasons.append(f'超过 {days_since_post} 天未发布动态')

        # Check: mostly reposts
        if config.repost_ratio is not None and activity['total_dynamics'] > 0:
            ratio = activity['repost_count'] / activity['total_dynamics']
            if ratio >= config.repost_ratio:
                pct = int(ratio * 100)
                reasons.append(f'近期动态 {pct}% 为转发')

        if reasons:
            filtered.append(FilteredUser(user=user, reasons=reasons))
        else:
            kept.append(user)

    print(f'  Kept {len(kept)}, filtered {len(filtered)} users')

    return kept, filtered
