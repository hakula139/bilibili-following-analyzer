"""Tests for collecting interactions from dynamic comment sections."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock

import pytest

from bilibili_following_analyzer.cli import _collect_dynamic_interactions
from bilibili_following_analyzer.client import BilibiliAPIError, BilibiliClient


@pytest.mark.parametrize(
    ('comment_id', 'comment_type'),
    [('200', 11), ('100', 17), ('300', 1)],
)
def test_dynamic_comments_use_the_declared_comment_section(
    monkeypatch: pytest.MonkeyPatch, comment_id: str, comment_type: int
) -> None:
    dynamic = {
        'id_str': '100',
        'basic': {'comment_id_str': comment_id, 'comment_type': comment_type},
    }

    def get_comments(
        url: str, params: dict[str, Any], *, wbi: bool = False
    ) -> dict[str, Any]:
        assert url == 'https://api.bilibili.com/x/v2/reply/wbi/main'
        assert wbi
        if params['oid'] != comment_id or params['type'] != comment_type:
            raise BilibiliAPIError(-404, 'Comment section not found')
        return {
            'data': {
                'cursor': {'is_end': True},
                'replies': [{'member': {'mid': '42'}}],
            }
        }

    with BilibiliClient() as client:
        monkeypatch.setattr(
            client, 'get_user_dynamics', Mock(return_value=iter([dynamic]))
        )
        monkeypatch.setattr(
            client, 'get_dynamic_reactions', Mock(return_value=iter([]))
        )
        monkeypatch.setattr(client, '_get', get_comments)
        users: set[int] = set()

        _collect_dynamic_interactions(client, 1, 20, users)

    assert 42 in users
