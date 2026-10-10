"""Tests for the shared comment API iterator."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock, call

import pytest

from bilibili_following_analyzer.client import BilibiliAPIError, BilibiliClient


@pytest.fixture
def client() -> Iterator[BilibiliClient]:
    with BilibiliClient() as instance:
        yield instance


def comment(mid: int) -> dict[str, Any]:
    return {'rpid': mid, 'member': {'mid': str(mid)}}


def page(replies: list[dict[str, Any]] | None, **cursor: Any) -> dict[str, Any]:
    return {'data': {'replies': replies, 'cursor': cursor}}


@pytest.mark.parametrize(('oid', 'type_'), [(123, 1), ('456', 11), ('789', 33)])
def test_comments_forward_object_and_type_and_follow_cursor(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient, oid: int | str, type_: int
) -> None:
    get = Mock(
        side_effect=[
            page([comment(42)], is_end=False, next=2),
            page([comment(43)], is_end=True),
        ]
    )
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(oid, type_, page_size=7)) == [
        comment(42),
        comment(43),
    ]
    params = {'oid': oid, 'type': type_, 'mode': 3, 'ps': 7}
    url = 'https://api.bilibili.com/x/v2/reply/wbi/main'
    assert get.call_args_list == [
        call(url, params, wbi=True),
        call(url, {**params, 'next': 2}, wbi=True),
    ]


@pytest.mark.parametrize(
    ('limit', 'expected'),
    [(0, []), (1, [42]), (2, [42, 43]), (3, [42, 43, 44])],
)
def test_comment_limit_stops_without_fetching_another_page(
    monkeypatch: pytest.MonkeyPatch,
    client: BilibiliClient,
    limit: int,
    expected: list[int],
) -> None:
    get = Mock(
        side_effect=[
            page([comment(42), comment(43)], is_end=False, next=2),
            page([comment(44), comment(45)], is_end=True),
        ]
    )
    monkeypatch.setattr(client, '_get', get)

    assert [
        int(c['member']['mid']) for c in client.get_comments(123, 1, max_count=limit)
    ] == expected
    assert get.call_count == (limit + 1) // 2


def test_empty_page_with_a_cursor_does_not_end_iteration(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    get = Mock(
        side_effect=[
            page([], is_end=False, next=2),
            page([comment(42)], is_end=True),
        ]
    )
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(123, 1)) == [comment(42)]
    assert get.call_args.kwargs['wbi'] is True
    assert get.call_args.args[1]['next'] == 2


@pytest.mark.parametrize('replies', [None, []])
def test_empty_comment_section(
    monkeypatch: pytest.MonkeyPatch,
    client: BilibiliClient,
    replies: list[dict[str, Any]] | None,
) -> None:
    get = Mock(return_value=page(replies, is_end=True))
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(123, 1)) == []
    get.assert_called_once()


def test_comment_api_error_propagates(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    error = BilibiliAPIError(-352, 'Request rejected')
    monkeypatch.setattr(client, '_get', Mock(side_effect=error))

    with pytest.raises(BilibiliAPIError) as caught:
        list(client.get_comments(123, 1))

    assert caught.value is error


def test_stalled_comment_cursor_raises_before_filling_a_limit_with_duplicates(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    get = Mock(return_value=page([comment(42)], is_end=False, next=2))
    monkeypatch.setattr(client, '_get', get)

    with pytest.raises(BilibiliAPIError, match='cursor did not advance'):
        list(client.get_comments(123, 1, max_count=2))
    assert get.call_count == 2


def test_truncated_reply_preview_is_replaced_with_all_reply_pages(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    root = {**comment(42), 'rpid': 7, 'rcount': 3, 'replies': [comment(43)]}
    get = Mock(
        side_effect=[
            page([root], is_end=True),
            {'data': {'page': {'count': 3}, 'replies': [comment(43), comment(44)]}},
            {'data': {'page': {'count': 3}, 'replies': [comment(45)]}},
        ]
    )
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(123, 11)) == [
        {**root, 'replies': [comment(43), comment(44), comment(45)]}
    ]
    assert get.call_args_list[1:] == [
        call(
            'https://api.bilibili.com/x/v2/reply/reply',
            {'oid': 123, 'type': 11, 'root': 7, 'pn': 1, 'ps': 20},
        ),
        call(
            'https://api.bilibili.com/x/v2/reply/reply',
            {'oid': 123, 'type': 11, 'root': 7, 'pn': 2, 'ps': 20},
        ),
    ]


def test_complete_reply_preview_requires_no_extra_request(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    root = {**comment(42), 'rpid': 7, 'rcount': 1, 'replies': [comment(43)]}
    get = Mock(return_value=page([root], is_end=True))
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(123, 1)) == [root]
    get.assert_called_once()


def test_pinned_comments_and_replies_are_collected_once_across_pages(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    pinned = {**comment(42), 'rcount': 1, 'replies': [comment(43)]}
    same_author = {
        **comment(42),
        'rpid': 142,
        'rcount': 1,
        'replies': [comment(46)],
    }
    first = page([comment(44)], is_end=False, next=2)
    first['data']['top_replies'] = [pinned]
    second = page([pinned, same_author], is_end=True)
    second['data']['top_replies'] = [pinned]
    get = Mock(side_effect=[first, second])
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_comments(123, 1)) == [pinned, comment(44), same_author]


def test_incomplete_reply_page_is_an_error(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    get = Mock(return_value={'data': {'page': {'count': 1}, 'replies': []}})
    monkeypatch.setattr(client, '_get', get)

    with pytest.raises(BilibiliAPIError, match='before the reported total'):
        list(client.get_comment_replies(123, 1, 7))
