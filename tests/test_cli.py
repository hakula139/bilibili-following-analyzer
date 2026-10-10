"""Tests for filter selection from CLI arguments and environment variables."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from bilibili_following_analyzer.cli import _collect_filter_specs, parse_args


class FilterSelectionTests(unittest.TestCase):
    def parse(self, *arguments: str):
        with (
            patch.dict(
                os.environ,
                {'FILTERS': 'inactive:365', 'FILTER_EXPR': 'mutual + no-interaction'},
                clear=True,
            ),
            patch('sys.argv', ['bilibili-analyzer', *arguments]),
        ):
            args = parse_args()
            specs = _collect_filter_specs(args) if not args.filter_expr else None
        return args, specs

    def test_cli_filters_override_both_environment_selectors(self):
        args, specs = self.parse(
            '-f', 'not-following-back', '-f', 'below-followers:5000'
        )
        self.assertIsNone(args.filter_expr)
        self.assertEqual(specs, ['not-following-back', 'below-followers:5000'])

    def test_cli_expression_overrides_environment_expression(self):
        args, _ = self.parse('--filter-expr', 'not-following-back | mutual')
        self.assertEqual(args.filter_expr, 'not-following-back | mutual')

    def test_environment_expression_is_used_without_cli_selection(self):
        args, _ = self.parse()
        self.assertEqual(args.filter_expr, 'mutual + no-interaction')

    def test_empty_cli_expression_selects_environment_filters(self):
        args, specs = self.parse('--filter-expr', '')
        self.assertEqual(args.filter_expr, '')
        self.assertEqual(specs, ['inactive:365'])

    def test_cli_filters_and_expression_conflict(self):
        with patch('sys.stderr'), self.assertRaises(SystemExit) as error:
            self.parse('-f', 'mutual', '--filter-expr', 'not-following-back')
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
