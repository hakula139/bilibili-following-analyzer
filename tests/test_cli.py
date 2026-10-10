"""Tests for filter selection from CLI arguments and environment variables."""

from __future__ import annotations

import os

import pytest

from bilibili_following_analyzer.cli import _collect_filter_specs, parse_args


@pytest.fixture(autouse=True)
def filter_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        monkeypatch.delenv(name)
    monkeypatch.setenv('FILTERS', 'inactive:365')
    monkeypatch.setenv('FILTER_EXPR', 'mutual + no-interaction')
    monkeypatch.setattr('sys.argv', ['bilibili-analyzer'])


def test_cli_filters_override_both_environment_selectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'sys.argv',
        ['bilibili-analyzer', '-f', 'not-following-back', '-f', 'below-followers:5000'],
    )

    args = parse_args()

    assert args.filter_expr is None
    assert _collect_filter_specs(args) == ['not-following-back', 'below-followers:5000']


def test_cli_expression_overrides_environment_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        'sys.argv',
        ['bilibili-analyzer', '--filter-expr', 'not-following-back | mutual'],
    )

    args = parse_args()

    assert args.filter_expr == 'not-following-back | mutual'


def test_environment_expression_is_used_without_cli_selection() -> None:
    args = parse_args()

    assert args.filter_expr == 'mutual + no-interaction'


def test_empty_cli_expression_selects_environment_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr('sys.argv', ['bilibili-analyzer', '--filter-expr', ''])

    args = parse_args()

    assert args.filter_expr == ''
    assert _collect_filter_specs(args) == ['inactive:365']


def test_cli_filters_and_expression_conflict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        'sys.argv',
        ['bilibili-analyzer', '-f', 'mutual', '--filter-expr', 'not-following-back'],
    )

    with pytest.raises(SystemExit) as error:
        parse_args()

    assert error.value.code == 2
    assert 'not allowed with argument' in capsys.readouterr().err
