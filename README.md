# bilibili-following-analyzer

[![CI](https://github.com/hakula139/bilibili-following-analyzer/actions/workflows/ci.yml/badge.svg)](https://github.com/hakula139/bilibili-following-analyzer/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/hakula139/bilibili-following-analyzer/graph/badge.svg)](https://codecov.io/gh/hakula139/bilibili-following-analyzer)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Analyze your Bilibili following list with composable filters for missing follow-backs, inactivity, and interactions. An allow list preserves accounts you want to keep following.

## Install

Use Python 3.11 or later and [uv](https://docs.astral.sh/uv/) 0.13 or later. The [Nix](https://nixos.org/download/) development shell supplies the supported tools through `direnv allow` or `nix develop`.

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

## Configuration

Copy the example files in your checkout:

```bash
cp config.example.toml config.toml
cp .env.local.example .env.local
```

Set your UID and analysis preferences in `config.toml`:

```toml
mid = 12345
allow_list = [23456, 34567]
filters = ["not-following-back", "below-followers:5000"]
filter_mode = "and"
```

The default is `./config.toml` in the current working directory. A missing default file uses built-in defaults, while a missing explicit `--config PATH` file is an error. Relative output paths also use the current working directory. Unknown keys, malformed TOML, and invalid effective values are errors.

CLI options override their corresponding TOML settings before value validation. A nonempty `filter_expr` takes precedence over `filters`. Explicit `--filter` options disable the configured expression, and `--filter-expr ''` falls back to configured filters. The allow list is an array of positive integer UIDs, and matching accounts are skipped before filtering. Duplicate UIDs are harmless.

### Authentication

For authenticated requests, set `SESSDATA` in `.env.local`. The checked-in `.envrc` loads this file with `direnv allow`. If you run without direnv, provide `SESSDATA` through the launching environment. Credentials are not read from TOML, and the CLI does not load dotenv files itself.

To obtain the cookie:

1. Log in to Bilibili in your browser.
2. Open DevTools, then Application → Cookies.
3. Copy the `SESSDATA` value into `.env.local`.

Keep `config.toml`, `.env.local`, cached responses, and analysis results local. The old `.env` configuration and separate allow-list file are no longer read.

## Usage

```bash
uv run bilibili-analyzer
```

The module entry point is also available as `uv run python -m bilibili_following_analyzer`.

### Available filters

Use `--list-filters` to see all available filters:

| Filter                  | Description                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| `not-following-back`    | Users who don't follow you back                                          |
| `mutual`                | Users who follow you back (mutual follows)                               |
| `below-followers:N`     | Users with fewer than N followers                                        |
| `above-followers:N`     | Users with more than N followers                                         |
| `no-interaction`        | Users with no comments, dynamic likes or forwards on the sampled content |
| `too-many-followings:N` | Users following more than N accounts                                     |
| `inactive:DAYS`         | Users who haven't posted in DAYS                                         |
| `repost-ratio:RATIO`    | Users whose plain repost ratio is at least RATIO (0.0-1.0)               |
| `deactivated`           | Users with deactivated accounts                                          |
| `no-posts`              | Users who have no posts at all                                           |

### Options

| Option           | TOML key       | Default | Description                                         |
| ---------------- | -------------- | ------- | --------------------------------------------------- |
| `--config`       | -              | (auto)  | TOML configuration path                             |
| `-f, --filter`   | `filters`      | `[]`    | Add a filter (repeatable on the CLI)                |
| `--filter-mode`  | `filter_mode`  | `and`   | Combine filters with `and` or `or`                  |
| `--filter-expr`  | `filter_expr`  | -       | Filter expression with nested AND / OR logic        |
| `--mid`          | `mid`          | -       | Your Bilibili UID                                   |
| `--sessdata`     | -              | (env)   | Override the SESSDATA cookie from the environment   |
| `--num-videos`   | `num_videos`   | 10      | Videos sampled for interactions                     |
| `--num-dynamics` | `num_dynamics` | 20      | Dynamics sampled for interactions                   |
| -                | `allow_list`   | `[]`    | UIDs to skip before filtering                       |
| `--delay`        | `delay`        | 0.3     | Delay between API requests in seconds               |
| `--limit`        | -              | -       | Analyze only the first N non-allowlisted followings |
| `-o, --output`   | `output`       | -       | Export results as text, JSON, or CSV                |
| `--no-cache`     | -              | false   | Disable disk caching                                |
| `--clear-cache`  | -              | false   | Clear cached data before running                    |
| `--cache-dir`    | -              | (auto)  | Custom cache directory                              |

### Examples

Find users who don't follow back AND have few followers:

```bash
uv run bilibili-analyzer \
  -f not-following-back \
  -f below-followers:5000
```

Find inactive accounts or accounts with no posts (OR mode):

```bash
uv run bilibili-analyzer \
  -f inactive:365 \
  -f no-posts \
  --filter-mode or
```

Find users with excessive followings who don't interact:

```bash
uv run bilibili-analyzer \
  -f too-many-followings:3000 \
  -f no-interaction
```

Use another configuration file:

```bash
uv run bilibili-analyzer --config settings/analysis.toml
```

Complex filter expression with nested logic:

```bash
# Find users matching ANY of these conditions:
# 1. Non-followers with < 5000 fans
# 2. Mutual followers who don't interact AND are problematic
# 3. Deactivated accounts
uv run bilibili-analyzer \
  --filter-expr \
    '
    (
      not-following-back
      + below-followers:5000
    )
    | (
      mutual
      + no-interaction
      + (
        too-many-followings:2000
        | inactive:365
        | no-posts
      )
    )
    | deactivated
    ' \
  -o results.json
```

Expression syntax:

- `+` for AND (higher precedence)
- `|` for OR (lower precedence)
- `()` for grouping

## Output

The report lists matching accounts with their profile links and the contributing filter reasons. `--output` also exports the matches as `.txt`, `.json`, or `.csv`, according to the filename extension.

Activity fetch failures leave activity unknown. Affected users are skipped by activity-based filters, and the report includes a failure summary. A successful exit does not mean every user's activity was available.

## Development

See [AGENTS.md](AGENTS.md) for contributor instructions and verification commands.

## License

Copyright (c) 2026 [Hakula](https://hakula.xyz). Licensed under the [MIT License](LICENSE).
