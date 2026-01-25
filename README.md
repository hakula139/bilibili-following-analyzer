# Bilibili Following Analyzer

Analyze your Bilibili following list to find:

- **Non-followers** with fewer followers than a threshold (potential spam / inactive accounts)
- **Silent followers** who don't interact with your recent content

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
uv run bilibili-analyzer [OPTIONS]

# Or as a Python module
uv run python -m bilibili_following_analyzer [OPTIONS]
```

Or if installed with pip:

```bash
bilibili-analyzer [OPTIONS]
```

### Options

| Option                 | Env Variable         | Default | Description                                         |
| ---------------------- | -------------------- | ------- | --------------------------------------------------- |
| `--mid`                | `MID`                | -       | Your Bilibili UID                                   |
| `--sessdata`           | `SESSDATA`           | -       | SESSDATA cookie for authenticated API calls         |
| `--follower-threshold` | `FOLLOWER_THRESHOLD` | 5000    | Report non-followers below this follower count      |
| `--num-videos`         | `NUM_VIDEOS`         | 10      | Number of recent videos to check for interactions   |
| `--num-dynamics`       | `NUM_DYNAMICS`       | 10      | Number of recent dynamics to check for interactions |
| `--allow-list`         | `ALLOW_LIST`         | -       | Path to file with UIDs to skip (one per line)       |
| `--delay`              | `DELAY`              | 0.3     | Delay between API requests (seconds)                |

### Examples

Basic check (with `.env` configured):

```bash
uv run bilibili-analyzer
```

Override threshold via CLI:

```bash
uv run bilibili-analyzer --follower-threshold 10000
```

With allow list to skip certain users:

```bash
uv run bilibili-analyzer --allow-list allow_list.txt
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
