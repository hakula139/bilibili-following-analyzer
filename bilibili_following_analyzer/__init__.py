"""
Bilibili Following Analyzer.

A tool to analyze your Bilibili following list and find:
1. Users who don't follow you back (with < N followers)
2. Users who haven't interacted with your recent posts
"""

from importlib.metadata import version

from .cli import main
from .client import BilibiliAPIError, BilibiliClient
from .models import User


__version__ = version('bilibili-following-analyzer')
__all__ = ['BilibiliAPIError', 'BilibiliClient', 'User', 'main', '__version__']
