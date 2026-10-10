"""Tests for bounded transport, API pagination, and activity classification."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import Mock

import pytest
import requests

from bilibili_following_analyzer.client import (
    ActivityStatus,
    BilibiliAPIError,
    BilibiliClient,
    _latest_post_ts,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[BilibiliClient]:
    with BilibiliClient() as instance:
        monkeypatch.setattr(instance, '_rate_limit', Mock())
        yield instance


def test_bootstrap_and_signing_use_the_same_bounded_transport(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    rate_limit = Mock()
    monkeypatch.setattr(client, '_rate_limit', rate_limit)
    nav = Mock()
    nav.json.return_value = {
        'code': 0,
        'data': {
            'wbi_img': {
                'img_url': 'https://example.test/' + 'a' * 32 + '.png',
                'sub_url': 'https://example.test/' + 'b' * 32 + '.png',
            }
        },
    }
    api = Mock()
    api.json.return_value = {'code': 0, 'data': {'value': 42}}
    transport = Mock(side_effect=[Mock(), nav, api, api])
    monkeypatch.setattr(client.session, 'get', transport)
    original = {'mid': 123}

    assert client._get('https://example.test/api', original, wbi=True)['data'] == {
        'value': 42
    }
    assert client._get('https://example.test/api', original, wbi=True)['data'] == {
        'value': 42
    }
    assert original == {'mid': 123}
    assert [c.args[0] for c in transport.call_args_list] == [
        'https://www.bilibili.com/',
        'https://api.bilibili.com/x/web-interface/nav',
        'https://example.test/api',
        'https://example.test/api',
    ]
    assert all(c.kwargs['timeout'] == 30 for c in transport.call_args_list)
    signed = transport.call_args.kwargs['params']
    assert signed['mid'] == '123'
    assert 'wts' in signed and 'w_rid' in signed
    assert rate_limit.call_count == 4


@pytest.mark.parametrize('code', [-404, -352])
def test_api_envelope_errors_propagate(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient, code: int
) -> None:
    api = Mock()
    api.json.return_value = {'code': code, 'message': 'Request failed'}
    monkeypatch.setattr(client.session, 'get', Mock(side_effect=[Mock(), api]))

    with pytest.raises(BilibiliAPIError) as caught:
        client._get('https://example.test/api')
    assert caught.value.code == code


@pytest.mark.parametrize(
    ('error', 'status', 'code'),
    [
        (BilibiliAPIError(-404, 'Gone'), ActivityStatus.DEACTIVATED, -404),
        (BilibiliAPIError(-352, 'Rejected'), ActivityStatus.UNAVAILABLE, -352),
        (requests.Timeout('Timed out'), ActivityStatus.UNAVAILABLE, None),
        (requests.ConnectionError('Disconnected'), ActivityStatus.UNAVAILABLE, None),
    ],
)
def test_activity_classifies_api_and_transport_failures(
    monkeypatch: pytest.MonkeyPatch,
    client: BilibiliClient,
    error: Exception,
    status: ActivityStatus,
    code: int | None,
) -> None:
    monkeypatch.setattr(client, 'get_user_dynamics', Mock(side_effect=error))
    stats = Mock(
        side_effect=AssertionError('Activity must not request relationship stats')
    )
    monkeypatch.setattr(client, 'get_user_stat', stats)

    activity = client.get_user_activity(42)
    assert activity.status == status
    assert activity.error_code == code
    stats.assert_not_called()


def test_http_activity_failure_retains_status_code(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    response = requests.Response()
    response.status_code = 412
    error = requests.HTTPError('Rejected', response=response)
    monkeypatch.setattr(client, 'get_user_dynamics', Mock(side_effect=error))

    activity = client.get_user_activity(42)
    assert activity.status == ActivityStatus.UNAVAILABLE
    assert activity.error_code == 412


def test_successful_activity_needs_no_relationship_stat_request(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    monkeypatch.setattr(client, 'get_user_dynamics', Mock(return_value=iter([])))
    stats = Mock(side_effect=AssertionError('Unexpected stat request'))
    monkeypatch.setattr(client, 'get_user_stat', stats)

    activity = client.get_user_activity(42)
    assert activity.status == ActivityStatus.OK
    assert activity.total_dynamics == 0
    stats.assert_not_called()


@pytest.mark.parametrize(
    'method', ['get_user_videos', 'get_user_dynamics', 'get_dynamic_reactions']
)
def test_zero_content_limits_make_no_requests(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient, method: str
) -> None:
    get = Mock(side_effect=AssertionError('Zero limit must not request data'))
    monkeypatch.setattr(client, '_get', get)

    assert list(getattr(client, method)(42, max_count=0)) == []
    get.assert_not_called()


def test_offset_pagination_continues_after_empty_pages(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient
) -> None:
    get = Mock(
        side_effect=[
            {'data': {'items': [], 'has_more': True, 'offset': 'next-page'}},
            {'data': {'items': [{'id_str': '42'}], 'has_more': False}},
        ]
    )
    monkeypatch.setattr(client, '_get', get)

    assert list(client.get_user_dynamics(123)) == [{'id_str': '42'}]
    assert get.call_args.args[1]['offset'] == 'next-page'


@pytest.mark.parametrize('limit', [None, 2])
def test_stalled_offset_is_incomplete_activity_not_a_duplicate_sample(
    monkeypatch: pytest.MonkeyPatch, client: BilibiliClient, limit: int | None
) -> None:
    get = Mock(
        return_value={
            'data': {
                'items': [{'id_str': '42'}],
                'has_more': True,
                'offset': 'same-page',
            }
        }
    )
    monkeypatch.setattr(client, '_get', get)

    with pytest.raises(BilibiliAPIError, match='cursor did not advance'):
        list(client.get_user_dynamics(123, max_count=limit))
    assert get.call_count == 2


def test_publish_timestamp_uses_latest_sample_even_with_pinned_or_missing_entries() -> (
    None
):
    dynamics: list[dict[str, Any]] = [
        {'modules': {'module_tag': {'text': '置顶'}, 'module_author': {'pub_ts': 100}}},
        {'modules': {}},
        {'modules': {'module_author': {'pub_ts': 50}}},
        {'modules': {'module_author': {'pub_ts': '80'}}},
    ]
    assert _latest_post_ts(dynamics) == 100
    assert _latest_post_ts([{'modules': {}}]) is None
