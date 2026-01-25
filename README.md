# Bilibili Following Analyzer

Analyze your Bilibili following list using composable filters to find:

- **Non-followers** who don't follow you back
- **Inactive accounts** who haven't posted recently
- **Silent followers** who don't interact with your content
- **Mass-following accounts** with too many followings
- And more...

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Configuration

Create a `.env` file in the project root:

```bash
MID=12345
SESSDATA="your_sessdata_here"
```

All options can be set via `.env` or CLI arguments. CLI arguments override `.env` values.

## Usage

```bash
# Using the CLI entry point
uv run bilibili-analyzer -f <filter> [OPTIONS]

# Or as a Python module
uv run python -m bilibili_following_analyzer -f <filter> [OPTIONS]
```

### Available Filters

Use `--list-filters` to see all available filters:

| Filter                  | Description                                           |
| ----------------------- | ----------------------------------------------------- |
| `not-following-back`    | Users who don't follow you back                       |
| `mutual`                | Users who follow you back (mutual follows)            |
| `below-followers:N`     | Users with fewer than N followers                     |
| `above-followers:N`     | Users with more than N followers                      |
| `no-interaction`        | Users who haven't interacted with your recent content |
| `too-many-followings:N` | Users following more than N accounts                  |
| `inactive:DAYS`         | Users who haven't posted in DAYS                      |
| `repost-ratio:RATIO`    | Users whose repost ratio exceeds RATIO (0.0-1.0)      |
| `deactivated`           | Users with deactivated or inaccessible accounts       |
| `no-posts`              | Users who have no posts at all                        |

### Options

| Option           | Env Variable   | Default | Description                                             |
| ---------------- | -------------- | ------- | ------------------------------------------------------- |
| `-f, --filter`   | `FILTERS`      | -       | Add a filter (repeatable, comma-separated in env)       |
| `--filter-mode`  | `FILTER_MODE`  | `and`   | Combine filters with `and` (all match) or `or` (any)    |
| `--mid`          | `MID`          | -       | Your Bilibili UID                                       |
| `--sessdata`     | `SESSDATA`     | -       | SESSDATA cookie for authenticated API calls             |
| `--num-videos`   | `NUM_VIDEOS`   | 10      | Videos to check for interactions (for `no-interaction`) |
| `--num-dynamics` | `NUM_DYNAMICS` | 20      | Dynamics to check for interactions                      |
| `--allow-list`   | `ALLOW_LIST`   | -       | Path to file with UIDs to skip (one per line)           |
| `--delay`        | `DELAY`        | 0.3     | Delay between API requests (seconds)                    |
| `--limit`        | -              | -       | Analyze only first N followings (for testing)           |
| `--no-cache`     | -              | -       | Disable disk caching (in-memory only)                   |
| `--clear-cache`  | -              | -       | Clear cached data before running                        |
| `--cache-dir`    | -              | (auto)  | Custom cache directory                                  |

### Examples

Find users who don't follow back AND have few followers:

```bash
uv run bilibili-analyzer -f not-following-back -f below-followers:5000
```

Find inactive mutual followers (OR mode - any filter matches):

```bash
uv run bilibili-analyzer -f inactive:365 -f no-posts --filter-mode or
```

Find users with excessive followings who don't interact:

```bash
uv run bilibili-analyzer -f too-many-followings:3000 -f no-interaction
```

Using env variables:

```bash
# In .env
FILTERS=not-following-back,below-followers:5000
FILTER_MODE=and
```

### Allow List Format

```text
34795       # comment (optional)
1831567     # another user
```

## Getting Your SESSDATA

1. Log in to Bilibili in your browser
2. Open DevTools (F12) → Application → Cookies
3. Find `SESSDATA` and copy its value
