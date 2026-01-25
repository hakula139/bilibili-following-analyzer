# Bilibili Following Analyzer

Analyze your Bilibili following list to find:

- **Non-followers** with fewer followers than a threshold (potential spam / inactive accounts)
- **Silent followers** who don't interact with your recent content

## Requirements

```bash
pip install requests
```

## Usage

```bash
python check.py --mid <YOUR_UID> [OPTIONS]
```

### Options

| Option                 | Default    | Description                                         |
| ---------------------- | ---------- | --------------------------------------------------- |
| `--mid`                | (required) | Your Bilibili UID                                   |
| `--sessdata`           | None       | SESSDATA cookie for authenticated API calls         |
| `--follower-threshold` | 5000       | Report non-followers below this follower count      |
| `--num-videos`         | 10         | Number of recent videos to check for interactions   |
| `--num-dynamics`       | 10         | Number of recent dynamics to check for interactions |
| `--allow-list`         | None       | Path to file with UIDs to skip (one per line)       |
| `--delay`              | 0.3        | Delay between API requests (seconds)                |

### Examples

Basic check (non-followers only):

```bash
python check.py --mid 12345
```

Full analysis with interaction checking:

```bash
python check.py --mid 12345 --sessdata "your_sessdata_here"
```

With allow list to skip certain users:

```bash
python check.py --mid 12345 --sessdata "..." --allow-list allow_list.txt
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
