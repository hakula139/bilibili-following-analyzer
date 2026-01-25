# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and Development Commands

```bash
# Install dependencies
uv sync

# Run the analyzer
uv run bilibili-analyzer [OPTIONS]
uv run python -m bilibili_following_analyzer [OPTIONS]

# Lint and format
uv run ruff check .
uv run ruff format .
```

## Architecture

This is a CLI tool for analyzing Bilibili following lists. It identifies users who don't follow back (below a follower threshold) and mutual followers who haven't interacted with recent content.

### Module Structure

- **`cli.py`** - Entry point, argument parsing, orchestrates the analysis workflow
- **`client.py`** - `BilibiliClient` class with WBI signature support for authenticated API requests
- **`analyzer.py`** - Core analysis logic: `collect_interacting_users()`, `analyze_followings()`, and `filter_inactive_users()`
- **`models.py`** - `User`, `FilterConfig`, and `FilteredUser` dataclasses
- **`utils.py`** - Allow list loading and result formatting

### Key Patterns

**WBI Signing**: Bilibili APIs require request signing with WBI keys. The client fetches keys from `/x/web-interface/nav` and signs requests using `MIXIN_KEY_ENC_TAB` encoding table.

**Relationship Attributes**: Following status uses attribute codes (2 = one-way follow, 6 = mutual follow).

**Rate Limiting**: All API calls go through `_rate_limit()` with configurable delay to avoid throttling.

## Code Style

- NumPy-style docstrings
- Ruff for linting (see `pyproject.toml` for config)
- Single quotes for strings
- Python 3.10+ type annotations

## External References

- **Bilibili API Documentation**: [SocialSisterYi/bilibili-API-collect - GitHub](https://github.com/SocialSisterYi/bilibili-API-collect)
