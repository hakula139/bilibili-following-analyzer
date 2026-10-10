"""Cache reuse and invalidation contracts for external data."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import Mock, call

import pytest
from diskcache import Cache

from bilibili_following_analyzer.cache import CachedDataFetcher
from bilibili_following_analyzer.client import (
    ActivityStatus,
    BilibiliClient,
    UserActivity,
)
from bilibili_following_analyzer.filters import FilterContext


@pytest.fixture
def fetcher(tmp_path: Path) -> Iterator[CachedDataFetcher]:
    with Cache(str(tmp_path / 'cache')) as cache:
        yield CachedDataFetcher(cache)


def test_cache_predicate_retries_rejected_values_and_reuses_accepted_value(
    fetcher: CachedDataFetcher,
) -> None:
    source = Mock(side_effect=[-1, 42])

    assert (
        fetcher.get_or_fetch('value', source, 60, cache_if=lambda value: value >= 0)
        == -1
    )
    assert (
        fetcher.get_or_fetch('value', source, 60, cache_if=lambda value: value >= 0)
        == 42
    )
    assert (
        fetcher.get_or_fetch('value', source, 60, cache_if=lambda value: value >= 0)
        == 42
    )
    assert source.call_count == 2


def test_disabled_cache_fetches_every_time() -> None:
    source = Mock(side_effect=[11, 22])
    fetcher = CachedDataFetcher()

    assert fetcher.get_or_fetch('value', source, 60) == 11
    assert fetcher.get_or_fetch('value', source, 60) == 22


@pytest.mark.parametrize('value', [0, False, '', []])
def test_default_cache_reuses_falsy_values(
    fetcher: CachedDataFetcher, value: object
) -> None:
    source = Mock(return_value=value)

    assert fetcher.get_or_fetch('value', source, 60) == value
    assert fetcher.get_or_fetch('value', source, 60) == value
    source.assert_called_once_with()


def test_fetch_errors_propagate_and_allow_retry(fetcher: CachedDataFetcher) -> None:
    error = RuntimeError('External request failed')
    source = Mock(side_effect=[error, 42])

    with pytest.raises(RuntimeError) as caught:
        fetcher.get_or_fetch('value', source, 60)
    assert caught.value is error
    assert fetcher.get_or_fetch('value', source, 60) == 42


@pytest.mark.parametrize('status', [ActivityStatus.OK, ActivityStatus.DEACTIVATED])
def test_activity_reuses_only_matching_observer_and_sample(
    fetcher: CachedDataFetcher, status: ActivityStatus
) -> None:
    client = Mock(spec=BilibiliClient)
    activities = [
        UserActivity(status, total_dynamics=3),
        UserActivity(status, total_dynamics=7),
        UserActivity(status, total_dynamics=9),
    ]
    client.get_user_activity.side_effect = activities
    first = FilterContext(client, 1, cache=fetcher)

    assert first.get_user_activity(42, max_dynamics=3) == activities[0]
    assert first.get_user_activity(42, max_dynamics=7) == activities[1]
    assert first.get_user_activity(42, max_dynamics=3) == activities[0]
    same_observer = FilterContext(client, 1, cache=fetcher)
    assert same_observer.get_user_activity(42, max_dynamics=7) == activities[1]
    other_observer = FilterContext(client, 2, cache=fetcher)
    assert other_observer.get_user_activity(42, max_dynamics=3) == activities[2]
    assert client.get_user_activity.call_args_list == [
        call(42, max_dynamics=3),
        call(42, max_dynamics=7),
        call(42, max_dynamics=3),
    ]


def test_unavailable_activity_is_shared_in_session_and_retried_next_session(
    fetcher: CachedDataFetcher,
) -> None:
    client = Mock(spec=BilibiliClient)
    unavailable = UserActivity(ActivityStatus.UNAVAILABLE, error_code=-352)
    available = UserActivity(ActivityStatus.OK, total_dynamics=5)
    client.get_user_activity.side_effect = [unavailable, available]
    first = FilterContext(client, 1, cache=fetcher)

    assert first.get_user_activity(42) == unavailable
    assert first.get_user_activity(42) == unavailable
    second = FilterContext(client, 1, cache=fetcher)
    assert second.get_user_activity(42) == available
    assert second.get_user_activity(42) == available
    third = FilterContext(client, 1, cache=fetcher)
    assert third.get_user_activity(42) == available
    assert client.get_user_activity.call_count == 2


def test_user_stats_remain_shared_across_observers(fetcher: CachedDataFetcher) -> None:
    client = Mock(spec=BilibiliClient)
    client.get_user_stat.return_value = {'follower': 10, 'following': 20}
    first = FilterContext(client, 1, cache=fetcher)
    second = FilterContext(client, 2, cache=fetcher)

    assert first.get_user_stat(42) == {'follower': 10, 'following': 20}
    assert first.get_user_stat(42) == {'follower': 10, 'following': 20}
    assert second.get_user_stat(42) == {'follower': 10, 'following': 20}
    client.get_user_stat.assert_called_once_with(42)
