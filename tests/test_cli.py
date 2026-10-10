"""Tests for argument precedence and analysis configuration."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from bilibili_following_analyzer.cache import CachedDataFetcher
from bilibili_following_analyzer.cli import (
    _collect_filter_specs,
    _run_analysis,
    main,
    parse_args,
)
from bilibili_following_analyzer.filters import (
    FilterContext,
    Following,
    parse_filter_expression,
    parse_filter_spec,
)


@pytest.fixture(autouse=True)
def configuration_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        'MID',
        'SESSDATA',
        'ALLOW_LIST',
        'DELAY',
        'OUTPUT',
        'FILTERS',
        'FILTER_EXPR',
        'FILTER_MODE',
        'NUM_VIDEOS',
        'NUM_DYNAMICS',
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ('argv', 'expression', 'specs'),
    [
        (
            ['-f', 'not-following-back', '-f', 'below-followers:5000'],
            None,
            ['not-following-back', 'below-followers:5000'],
        ),
        (
            ['--filter-expr', 'not-following-back | mutual'],
            'not-following-back | mutual',
            None,
        ),
        ([], 'mutual + no-interaction', None),
        (['--filter-expr', ''], '', ['inactive:365']),
    ],
)
def test_filter_selection_precedence(
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    expression: str | None,
    specs: list[str] | None,
) -> None:
    monkeypatch.setenv('FILTERS', 'inactive:365')
    monkeypatch.setenv('FILTER_EXPR', 'mutual + no-interaction')

    args = parse_args(argv)

    assert args.filter_expr == expression
    if specs is not None:
        assert _collect_filter_specs(args) == specs


def test_cli_filters_and_expression_conflict(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        parse_args(['-f', 'mutual', '--filter-expr', 'not-following-back'])

    assert error.value.code == 2
    assert 'not allowed with argument' in capsys.readouterr().err


@pytest.mark.parametrize(
    ('environment', 'option', 'value', 'attribute', 'expected'),
    [
        ('MID', '--mid', '123', 'mid', 123),
        ('DELAY', '--delay', '0.5', 'delay', 0.5),
        ('NUM_VIDEOS', '--num-videos', '3', 'num_videos', 3),
        ('NUM_DYNAMICS', '--num-dynamics', '4', 'num_dynamics', 4),
        ('FILTER_MODE', '--filter-mode', 'or', 'filter_mode', 'or'),
    ],
)
def test_explicit_arguments_override_invalid_environment_defaults(
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
    option: str,
    value: str,
    attribute: str,
    expected: int | float | str,
) -> None:
    monkeypatch.setenv(environment, 'invalid')

    assert getattr(parse_args([option, value]), attribute) == expected

    with pytest.raises(SystemExit) as error:
        parse_args([])
    assert error.value.code == 2


@pytest.mark.parametrize('option', ['--help', '--list-filters'])
def test_help_does_not_validate_unused_environment_defaults(
    monkeypatch: pytest.MonkeyPatch, option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in ('MID', 'DELAY', 'NUM_VIDEOS', 'NUM_DYNAMICS', 'FILTER_MODE'):
        monkeypatch.setenv(name, 'invalid')

    with pytest.raises(SystemExit) as error:
        parse_args([option])

    assert error.value.code == 0
    assert capsys.readouterr().out


@pytest.mark.parametrize(
    ('option', 'value'),
    [
        ('--mid', '0'),
        ('--mid', '-1'),
        ('--delay', '-0.1'),
        ('--delay', 'nan'),
        ('--delay', 'inf'),
        ('--num-videos', '-1'),
        ('--num-dynamics', '-1'),
        ('--limit', '-1'),
    ],
)
def test_invalid_numeric_argument_ranges(option: str, value: str) -> None:
    with pytest.raises(SystemExit) as error:
        parse_args([option, value])
    assert error.value.code == 2


def test_zero_limits_and_delay_are_valid() -> None:
    args = parse_args(
        [
            '--delay',
            '0',
            '--num-videos',
            '0',
            '--num-dynamics',
            '0',
            '--limit',
            '0',
        ]
    )

    assert (args.delay, args.num_videos, args.num_dynamics, args.limit) == (0, 0, 0, 0)


@pytest.mark.parametrize('expression', [None, 'mutual + no-interaction'])
def test_no_interaction_requires_a_content_sample_before_opening_client(
    monkeypatch: pytest.MonkeyPatch, expression: str | None
) -> None:
    client = Mock()
    monkeypatch.setattr('bilibili_following_analyzer.cli.BilibiliClient', client)
    args = parse_args(['--mid', '123', '--num-videos', '0', '--num-dynamics', '0'])
    filter_obj = (
        parse_filter_expression(expression)
        if expression
        else parse_filter_spec('no-interaction')
    )

    with pytest.raises(ValueError):
        _run_analysis(args, filter_obj, CachedDataFetcher(), set())

    client.assert_not_called()


def test_main_loads_environment_before_resolving_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def load_configuration() -> None:
        monkeypatch.setenv('MID', '123')
        monkeypatch.setenv('FILTERS', 'mutual')

    analysis = Mock(return_value=[])
    monkeypatch.setattr(
        'bilibili_following_analyzer.cli.load_dotenv', load_configuration
    )
    monkeypatch.setattr('bilibili_following_analyzer.cli._run_analysis', analysis)
    monkeypatch.setattr('sys.argv', ['bilibili-analyzer', '--no-cache'])

    main()

    args, filter_obj, _, allow_list = analysis.call_args.args
    ctx = FilterContext(client=Mock(), my_mid=123)
    assert args.mid == 123
    assert filter_obj.matches(Following(456, 'mutual user', 6), ctx).matched
    assert not filter_obj.matches(Following(789, 'one-way user', 2), ctx).matched
    assert allow_list == set()


def test_main_reports_missing_mid_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = Mock()
    monkeypatch.setattr('bilibili_following_analyzer.cli.load_dotenv', lambda: None)
    monkeypatch.setattr('bilibili_following_analyzer.cli._run_analysis', analysis)
    monkeypatch.setattr('sys.argv', ['bilibili-analyzer'])

    with pytest.raises(SystemExit, match='mid is required'):
        main()

    analysis.assert_not_called()


@pytest.mark.parametrize(
    ('selection', 'matched'),
    [
        (['-f', 'mutual', '-f', 'not-following-back'], False),
        (['-f', 'mutual', '-f', 'not-following-back', '--filter-mode', 'or'], True),
        (['--filter-expr', 'mutual + not-following-back'], False),
        (['--filter-expr', 'mutual | not-following-back'], True),
    ],
)
def test_main_filter_modes_and_expressions_agree_on_matching_behavior(
    monkeypatch: pytest.MonkeyPatch, selection: list[str], matched: bool
) -> None:
    analysis = Mock(return_value=[])
    monkeypatch.setattr('bilibili_following_analyzer.cli.load_dotenv', lambda: None)
    monkeypatch.setattr('bilibili_following_analyzer.cli._run_analysis', analysis)
    monkeypatch.setattr(
        'sys.argv', ['bilibili-analyzer', '--mid', '123', '--no-cache', *selection]
    )

    main()

    _, filter_obj, _, _ = analysis.call_args.args
    ctx = FilterContext(client=Mock(), my_mid=123)
    assert filter_obj.matches(Following(456, 'mutual user', 6), ctx).matched is matched
    assert filter_obj.matches(Following(789, 'one-way user', 2), ctx).matched is matched
