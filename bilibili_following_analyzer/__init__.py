"""
Bilibili Following Analyzer.

A tool to analyze your Bilibili following list using composable filters.
"""

from importlib.metadata import version

from .cli import main
from .client import BilibiliAPIError, BilibiliClient
from .filters import Filter, FilterContext, FilterResult, Following


__version__ = version('bilibili-following-analyzer')
__all__ = [
    'BilibiliAPIError',
    'BilibiliClient',
    'Filter',
    'FilterContext',
    'FilterResult',
    'Following',
    'main',
    '__version__',
]
