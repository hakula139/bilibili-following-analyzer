"""Tests for argument precedence and analysis configuration."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
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
def isolated_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
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


def configure(contents: str) -> None:
    Path('config.toml').write_text(dedent(contents), encoding='utf-8')


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
    argv: list[str],
    expression: str | None,
    specs: list[str] | None,
) -> None:
    configure('filters = ["inactive:365"]\nfilter_expr = "mutual + no-interaction"\n')

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
    ('key', 'option', 'value', 'attribute', 'expected'),
    [
        ('mid', '--mid', '123', 'mid', 123),
        ('delay', '--delay', '0.5', 'delay', 0.5),
        ('num_videos', '--num-videos', '3', 'num_videos', 3),
        ('num_dynamics', '--num-dynamics', '4', 'num_dynamics', 4),
        ('filter_mode', '--filter-mode', 'or', 'filter_mode', 'or'),
    ],
)
def test_explicit_arguments_override_invalid_config_defaults(
    key: str,
    option: str,
    value: str,
    attribute: str,
    expected: int | float | str,
) -> None:
    configure(f'{key} = "invalid"\n')

    args = parse_args([option, value])

    assert getattr(args, attribute) == expected
    with pytest.raises(SystemExit) as error:
        parse_args([])
    assert error.value.code == 2


@pytest.mark.parametrize('option', ['--help', '--list-filters'])
def test_help_does_not_load_configuration(
    option: str, capsys: pytest.CaptureFixture[str]
) -> None:
    configure('invalid = [\n')

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


def test_toml_settings_and_cookie_environment_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(
        """
        mid = 123
        allow_list = [456, 789, 456]
        delay = 0.5
        output = "report.json"
        filters = ["mutual"]
        filter_mode = "or"
        num_videos = 3
        num_dynamics = 4
        """
    )
    monkeypatch.setenv('MID', '999')
    monkeypatch.setenv('SESSDATA', 'example-cookie')

    args = parse_args([])
    override = parse_args(['--sessdata', 'other-cookie'])

    assert (
        args.mid,
        args.allow_list,
        args.delay,
        args.output,
        args.filters,
        args.filter_mode,
        args.num_videos,
        args.num_dynamics,
        args.sessdata,
    ) == (
        123,
        [456, 789, 456],
        0.5,
        Path('report.json'),
        ['mutual'],
        'or',
        3,
        4,
        'example-cookie',
    )
    assert override.sessdata == 'other-cookie'


def test_default_config_is_optional_but_explicit_config_is_required(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = parse_args([])

    assert args.mid is None
    assert args.allow_list == []
    with pytest.raises(SystemExit) as error:
        parse_args(['--config', 'missing.toml'])
    assert error.value.code == 2
    assert 'missing.toml' in capsys.readouterr().err


def test_explicit_config_and_relative_output_keep_cwd_semantics() -> None:
    configure('not valid TOML')
    directory = Path('settings')
    directory.mkdir()
    path = directory / 'analysis.toml'
    path.write_text('mid = 123\noutput = "report.json"\n', encoding='utf-8')

    args = parse_args(['--config', str(path)])

    assert args.mid == 123
    assert args.output == Path('report.json')


@pytest.mark.parametrize(
    'contents',
    [
        'mid = true',
        'mid = 0',
        'allow_list = "123"',
        'allow_list = [true]',
        'allow_list = [0]',
        'allow_list = [1.5]',
        'delay = true',
        'delay = -0.1',
        'delay = nan',
        'delay = inf',
        'output = 123',
        'output = ""',
        'filters = "mutual"',
        'filters = [123]',
        'filter_expr = []',
        'filter_mode = "xor"',
        'num_videos = true',
        'num_videos = -1',
        'num_dynamics = 1.5',
        'num_dynamics = -1',
    ],
)
def test_invalid_effective_toml_values_are_errors(contents: str) -> None:
    configure(contents + '\n')

    with pytest.raises(SystemExit) as error:
        parse_args([])

    assert error.value.code == 2


@pytest.mark.parametrize(
    ('contents', 'message'),
    [
        ('mid = ["private-value"', 'Invalid TOML'),
        ('unknown = "private-value"', 'Unknown configuration keys'),
        ('[analysis]\nmid = 123', 'Unknown configuration keys'),
        ('sessdata = "private-value"', 'Unknown configuration keys'),
    ],
)
def test_bad_config_diagnostics_do_not_reveal_values(
    contents: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    configure(contents)

    with pytest.raises(SystemExit) as error:
        parse_args([])

    assert error.value.code == 2
    diagnostic = capsys.readouterr().err
    assert message in diagnostic
    assert 'private-value' not in diagnostic


def test_cli_filters_disable_invalid_config_expression() -> None:
    configure('filter_expr = 123\nfilters = ["inactive:365"]\n')

    args = parse_args(['--filter', 'mutual'])

    assert args.filter_expr is None
    assert args.filters == ['mutual']


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


def test_main_applies_config_and_inline_allow_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(
        """
        mid = 123
        filters = ["mutual"]
        allow_list = [456, 789, 456]
        """
    )
    analysis = Mock(return_value=[])
    monkeypatch.setattr('bilibili_following_analyzer.cli._run_analysis', analysis)
    monkeypatch.setattr('sys.argv', ['bilibili-analyzer', '--no-cache'])

    main()

    args, filter_obj, _, allow_list = analysis.call_args.args
    ctx = FilterContext(client=Mock(), my_mid=123)
    assert args.mid == 123
    assert filter_obj.matches(Following(456, 'mutual user', 6), ctx).matched
    assert not filter_obj.matches(Following(789, 'one-way user', 2), ctx).matched
    assert allow_list == {456, 789}


def test_main_reports_missing_mid_before_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = Mock()
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
    monkeypatch.setattr('bilibili_following_analyzer.cli._run_analysis', analysis)
    monkeypatch.setattr(
        'sys.argv', ['bilibili-analyzer', '--mid', '123', '--no-cache', *selection]
    )

    main()

    _, filter_obj, _, _ = analysis.call_args.args
    ctx = FilterContext(client=Mock(), my_mid=123)
    assert filter_obj.matches(Following(456, 'mutual user', 6), ctx).matched is matched
    assert filter_obj.matches(Following(789, 'one-way user', 2), ctx).matched is matched
