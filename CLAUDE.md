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

This is a CLI tool for analyzing Bilibili following lists using composable filters. Users can combine multiple filter criteria with AND/OR logic to identify followings that match specific patterns.

### Module Structure

- **`cli.py`** - Entry point, argument parsing, orchestrates the analysis workflow
- **`client.py`** - `BilibiliClient` class with WBI signature support for authenticated API requests
- **`filters.py`** - Composable filter system with `Filter` base class and concrete implementations
- **`cache.py`** - Disk-based caching using `diskcache` for cross-run persistence
- **`utils.py`** - Allow list loading and result formatting

### Filter System

The filter system uses a composable design pattern:

- **`Filter`** - Abstract base class defining the filter interface
- **`AndFilter`** / **`OrFilter`** - Composite filters for nested logic
- **`FilterContext`** - Shared context with cached API data (user stats, activity)
- **`Following`** - Data class representing a followed user
- **`FilterResult`** - Result containing matched filters and details
- **`FilterExpressionParser`** - Recursive descent parser for filter expressions

Available filters (use `--list-filters` to see all):

- `not-following-back` - Users who don't follow you back
- `mutual` - Users who follow you back
- `below-followers:N` - Users with < N followers
- `no-interaction` - Users who haven't interacted with recent content
- `inactive:DAYS` - Users who haven't posted in DAYS
- `repost-ratio:RATIO` - Users whose posts are mostly reposts

**Filter Expressions**: Use `--filter-expr` for complex nested logic:

- Syntax: `+` (AND), `|` (OR), `()` (grouping)
- Precedence: `+` binds tighter than `|`
- Example: `(a + b) | (c + d + (e | f)) | g`

### Key Patterns

**WBI Signing**: Bilibili APIs require request signing with WBI keys. The client fetches keys from `/x/web-interface/nav` and signs requests using `MIXIN_KEY_ENC_TAB` encoding table.

**Relationship Attributes**: Following status uses attribute codes (2 = one-way follow, 6 = mutual follow).

**Rate Limiting**: All API calls go through `_rate_limit()` with configurable delay to avoid throttling.

**Progress Bars**: Uses `tqdm` for progress indication during video/dynamic collection and filter evaluation. Use `--limit N` to test with only the first N followings.

**Caching**: Two-level caching system:

- In-memory cache (per-session): `FilterContext` keeps a hot cache for the current run
- Disk cache (cross-run): `diskcache` persists data with TTLs (24h for user stats, 6h for activity)
- Use `--no-cache` to disable disk caching, `--clear-cache` to invalidate

## Code Style

- NumPy-style docstrings
- Ruff for linting (see `pyproject.toml` for config)
- Single quotes for strings
- Python 3.10+ type annotations

## External References

- **Bilibili API Documentation**: [SocialSisterYi/bilibili-API-collect - GitHub](https://github.com/SocialSisterYi/bilibili-API-collect)
