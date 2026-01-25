"""
Bilibili Following Analyzer.

A tool to analyze your Bilibili following list and find:
1. Users who don't follow you back (with < N followers)
2. Users who haven't interacted with your recent posts
"""

from .cli import main
from .client import BilibiliClient
from .models import User


__version__ = '0.1.0'
__all__ = ['BilibiliClient', 'User', 'main', '__version__']
