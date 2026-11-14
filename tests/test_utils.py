"""Tests for local allow lists and result exports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from bilibili_following_analyzer.filters import FilterMatch, FilterResult, Following
from bilibili_following_analyzer.utils import output_results_to_file


@pytest.fixture
def result() -> FilterResult:
    return FilterResult(
        following=Following(mid=123, name='用户, "名字"', attribute=6),
        matches=[
            FilterMatch('below-followers', '粉丝 < 100; 条件甲'),
            FilterMatch('below-followers', '粉丝 < 500; 条件乙'),
        ],
    )


def test_json_export_preserves_repeated_matches_and_unsplit_details(
    tmp_path: Path, result: FilterResult
) -> None:
    path = tmp_path / 'results.json'

    output_results_to_file([result], path)

    assert json.loads(path.read_text(encoding='utf-8')) == [
        {
            'mid': 123,
            'name': '用户, "名字"',
            'space_url': 'https://space.bilibili.com/123',
            'is_mutual': True,
            'matched_filters': ['below-followers', 'below-followers'],
            'details': ['粉丝 < 100; 条件甲', '粉丝 < 500; 条件乙'],
        }
    ]
    assert '用户' in path.read_text(encoding='utf-8')


def test_csv_export_quotes_user_names_and_preserves_all_details(
    tmp_path: Path, result: FilterResult
) -> None:
    path = tmp_path / 'results.csv'

    output_results_to_file([result], path)

    with path.open(encoding='utf-8', newline='') as handle:
        assert list(csv.DictReader(handle)) == [
            {
                'mid': '123',
                'name': '用户, "名字"',
                'space_url': 'https://space.bilibili.com/123',
                'is_mutual': 'True',
                'matched_filters': 'below-followers, below-followers',
                'details': '粉丝 < 100; 条件甲; 粉丝 < 500; 条件乙',
            }
        ]


def test_text_export_preserves_unicode_and_ordered_details(
    tmp_path: Path, result: FilterResult
) -> None:
    path = tmp_path / 'results.txt'

    output_results_to_file([result], path)

    assert path.read_text(encoding='utf-8') == (
        '用户, "名字"\thttps://space.bilibili.com/123\t'
        '粉丝 < 100; 条件甲; 粉丝 < 500; 条件乙'
    )
