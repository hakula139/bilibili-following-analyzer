"""Tests for interaction collection across content and comment types."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, call

import pytest

from bilibili_following_analyzer.cli import collect_interacting_users
from bilibili_following_analyzer.client import BilibiliAPIError, BilibiliClient
from bilibili_following_analyzer.filters import (
    FilterContext,
    Following,
    NoInteractionFilter,
)


@pytest.mark.parametrize('comment_type', [1, 11, 17, 33])
def test_collection_uses_comment_metadata_and_merges_authors(
    comment_type: int,
) -> None:
    client = Mock(spec=BilibiliClient)
    dynamic = {
        'id_str': '100',
        'basic': {'comment_id_str': '900', 'comment_type': comment_type},
    }
    client.get_user_videos.return_value = iter([{'aid': 200}])
    client.get_user_dynamics.return_value = iter([dynamic])
    client.get_dynamic_reactions.return_value = iter([{'mid': '42'}])
    client.get_comments.side_effect = [
        iter([{'member': {'mid': '42'}, 'replies': None}]),
        iter(
            [
                {
                    'member': {'mid': '43'},
                    'replies': [
                        {
                            'member': {'mid': '42'},
                            'replies': [{'member': {'mid': '44'}, 'replies': []}],
                        }
                    ],
                }
            ]
        ),
    ]

    users = collect_interacting_users(client, 1, 3, 5)
    assert users == {42, 43, 44}
    ctx = FilterContext(client, 1, interacting_users=users)
    filter_ = NoInteractionFilter()
    assert not filter_.matches(Following(44, 'Reply author', 6), ctx).matched
    assert filter_.matches(Following(45, 'Other user', 6), ctx).matched
    client.get_user_videos.assert_called_once_with(1, max_count=3)
    client.get_user_dynamics.assert_called_once_with(1, max_count=5)
    client.get_dynamic_reactions.assert_called_once_with('100')
    assert client.get_comments.call_args_list == [
        call(200, type_=1),
        call('900', type_=comment_type),
    ]


def test_disabled_sources_are_not_requested() -> None:
    client = Mock(spec=BilibiliClient)

    assert collect_interacting_users(client, 1, 0, 0) == set()
    assert client.mock_calls == []


@pytest.mark.parametrize('code', [-404, -352])
def test_dynamic_comment_failures_do_not_become_absent_interactions(code: int) -> None:
    client = Mock(spec=BilibiliClient)
    dynamic: dict[str, Any] = {
        'id_str': '100',
        'basic': {'comment_id_str': '900', 'comment_type': 11},
    }
    client.get_user_dynamics.return_value = iter([dynamic])
    client.get_dynamic_reactions.return_value = iter([{'mid': '42'}])
    error = BilibiliAPIError(code, 'Comment request failed')

    client.get_comments.side_effect = error

    with pytest.raises(BilibiliAPIError) as caught:
        collect_interacting_users(client, 1, 0, 5)
    assert caught.value is error


def test_dynamic_without_a_comment_section_still_collects_reactions() -> None:
    client = Mock(spec=BilibiliClient)
    client.get_user_dynamics.return_value = iter(
        [{'id_str': '100', 'basic': {'comment_id_str': '', 'comment_type': 0}}]
    )
    client.get_dynamic_reactions.return_value = iter([{'mid': '42'}])

    assert collect_interacting_users(client, 1, 0, 5) == {42}
    client.get_comments.assert_not_called()
