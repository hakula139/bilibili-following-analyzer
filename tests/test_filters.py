"""Behavioral contracts for filter evaluation and expressions."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import Mock

import pytest

from bilibili_following_analyzer.client import (
    ActivityStatus,
    BilibiliClient,
    UserActivity,
)
from bilibili_following_analyzer.filters import (
    AndFilter,
    DeactivatedFilter,
    Filter,
    FilterContext,
    FilterMatch,
    Following,
    InactiveFilter,
    MatchInfo,
    NoInteractionFilter,
    NoPostsFilter,
    OrFilter,
    RepostRatioFilter,
    parse_filter_expression,
    parse_filter_spec,
)


@pytest.fixture
def following() -> Following:
    return Following(42, 'Example user', 6)


@pytest.fixture
def client() -> Mock:
    return Mock(spec=BilibiliClient)


@pytest.fixture
def context(client: Mock) -> FilterContext:
    return FilterContext(client, 1)


@pytest.mark.parametrize('parse', [parse_filter_spec, parse_filter_expression])
@pytest.mark.parametrize(
    'spec',
    [
        'inactive:-1',
        'inactive:1.5',
        'below-followers:-1',
        'above-followers:-1',
        'too-many-followings:-1',
        'repost-ratio:-0.1',
        'repost-ratio:1.1',
        'repost-ratio:nan',
        'repost-ratio:inf',
        'repost-ratio:-inf',
        'inactive',
        'repost-ratio:',
        'mutual:1',
        'unknown-filter',
    ],
)
def test_parsers_reject_invalid_parameters(
    parse: Callable[[str], Filter], spec: str
) -> None:
    with pytest.raises(ValueError):
        parse(spec)


@pytest.mark.parametrize('parse', [parse_filter_spec, parse_filter_expression])
@pytest.mark.parametrize(
    ('spec', 'attribute', 'expected'),
    [
        ('inactive:0', 'days', 0),
        ('inactive:365', 'days', 365),
        ('below-followers:0', 'threshold', 0),
        ('above-followers:100', 'threshold', 100),
        ('too-many-followings:0', 'threshold', 0),
        ('repost-ratio:0', 'ratio', 0.0),
        ('repost-ratio:0.75', 'ratio', 0.75),
        ('repost-ratio:1', 'ratio', 1.0),
    ],
)
def test_parsers_preserve_valid_parameters(
    parse: Callable[[str], Filter], spec: str, attribute: str, expected: float
) -> None:
    assert getattr(parse(spec), attribute) == expected


@pytest.mark.parametrize(
    ('spec', 'below', 'equal', 'above'),
    [
        ('below-followers:10', True, False, False),
        ('above-followers:10', False, False, True),
        ('too-many-followings:10', False, False, True),
    ],
)
def test_stat_filters_use_their_field_and_strict_threshold(
    client: Mock,
    following: Following,
    context: FilterContext,
    spec: str,
    below: bool,
    equal: bool,
    above: bool,
) -> None:
    filter_ = parse_filter_spec(spec)
    for value, expected in [(9, below), (10, equal), (11, above)]:
        context.user_stats.clear()
        stat = (
            {'follower': 100, 'following': value}
            if spec.startswith('too-many-followings')
            else {'follower': value, 'following': 100}
        )
        client.get_user_stat.return_value = stat

        assert filter_.matches(following, context).matched is expected


@pytest.mark.parametrize(
    ('elapsed', 'expected'),
    [(3 * 86400 - 1, False), (3 * 86400, True), (3 * 86400 + 1, True)],
)
def test_inactivity_uses_exact_elapsed_threshold(
    monkeypatch: pytest.MonkeyPatch,
    client: Mock,
    following: Following,
    context: FilterContext,
    elapsed: int,
    expected: bool,
) -> None:
    now = 2_000_000
    monkeypatch.setattr('bilibili_following_analyzer.filters.time.time', lambda: now)
    client.get_user_activity.return_value = UserActivity(
        ActivityStatus.OK, total_dynamics=5, last_post_ts=now - elapsed
    )

    assert InactiveFilter(3).matches(following, context).matched is expected


@pytest.mark.parametrize(
    ('activity', 'inactive', 'no_posts', 'deactivated', 'reposts'),
    [
        (UserActivity(ActivityStatus.UNAVAILABLE), False, False, False, False),
        (UserActivity(ActivityStatus.DEACTIVATED), True, False, True, False),
        (UserActivity(ActivityStatus.OK), True, True, False, False),
        (
            UserActivity(ActivityStatus.OK, total_dynamics=4, repost_count=3),
            False,
            False,
            False,
            True,
        ),
    ],
)
def test_activity_status_controls_derived_filters(
    client: Mock,
    following: Following,
    context: FilterContext,
    activity: UserActivity,
    inactive: bool,
    no_posts: bool,
    deactivated: bool,
    reposts: bool,
) -> None:
    client.get_user_activity.return_value = activity

    assert InactiveFilter(10).matches(following, context).matched is inactive
    assert NoPostsFilter().matches(following, context).matched is no_posts
    assert DeactivatedFilter().matches(following, context).matched is deactivated
    assert RepostRatioFilter(0.75).matches(following, context).matched is reposts


@pytest.mark.parametrize(
    ('threshold', 'expected'), [(0.49, True), (0.5, True), (0.51, False)]
)
def test_repost_ratio_includes_equal_threshold(
    client: Mock,
    following: Following,
    context: FilterContext,
    threshold: float,
    expected: bool,
) -> None:
    client.get_user_activity.return_value = UserActivity(
        ActivityStatus.OK, total_dynamics=6, repost_count=3
    )

    assert RepostRatioFilter(threshold).matches(following, context).matched is expected


@pytest.mark.parametrize(
    ('users', 'expected'), [(None, False), (set(), True), ({42}, False), ({43}, True)]
)
def test_no_interaction_requires_collected_data(
    following: Following,
    context: FilterContext,
    users: set[int] | None,
    expected: bool,
) -> None:
    context.interacting_users = users

    assert NoInteractionFilter().matches(following, context).matched is expected


def test_and_short_circuits_and_discards_partial_matches(
    following: Following, context: FilterContext
) -> None:
    first = Mock(spec=Filter)
    second = Mock(spec=Filter)
    third = Mock(spec=Filter)
    first.matches.return_value = MatchInfo.match('first', 'First detail')
    second.matches.return_value = MatchInfo.no_match()

    result = AndFilter([first, second, third]).matches(following, context)

    assert result == MatchInfo.no_match()
    first.matches.assert_called_once_with(following, context)
    second.matches.assert_called_once_with(following, context)
    third.matches.assert_not_called()


def test_nested_composites_preserve_order_and_repeated_match_details(
    following: Following, context: FilterContext
) -> None:
    first = Mock(spec=Filter)
    second = Mock(spec=Filter)
    missing = Mock(spec=Filter)
    first.matches.return_value = MatchInfo.match('repeated', 'First detail; extra')
    second.matches.return_value = MatchInfo.match('repeated', 'Second detail')
    missing.matches.return_value = MatchInfo.no_match()

    result = OrFilter([AndFilter([first, second]), missing, first]).matches(
        following, context
    )

    assert result.matched
    assert result.matches == [
        FilterMatch('repeated', 'First detail; extra'),
        FilterMatch('repeated', 'Second detail'),
        FilterMatch('repeated', 'First detail; extra'),
    ]
    assert first.matches.call_count == 2
    missing.matches.assert_called_once_with(following, context)


@pytest.mark.parametrize(
    ('expression', 'expected'),
    [
        ('mutual | not-following-back + no-interaction', True),
        ('(mutual | not-following-back) + no-interaction', False),
    ],
)
def test_expression_grouping_changes_evaluation(
    following: Following, context: FilterContext, expression: str, expected: bool
) -> None:
    context.interacting_users = {following.mid}

    assert (
        parse_filter_expression(expression).matches(following, context).matched
        is expected
    )
