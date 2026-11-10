# AGENTS.md: bilibili-following-analyzer

## Analysis contracts

- Use the configured `.env` filters and allow list for analysis runs. Override them only when the user asks.
- Keep login cookies, allow lists, cached API responses, and analysis results local.
- Activity fetch failures leave the user's activity unknown. Preserve `UNAVAILABLE` status and never interpret it as an empty feed or an inactive account.
- Report skipped users and API failures with the results. A successful process exit does not establish that every user's data was available.
- Keep live API calls out of tests. Use fixtures or mocks for external responses.

## Development

Enter the dev shell with `direnv allow` or `nix develop`, and verify a change with:

```bash
nix develop -c run-hooks
nix develop -c uv run --locked pytest -q
```

Use NumPy-style docstrings for non-obvious API contracts.

## API reference

Consult [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) when changing API requests. Confirm request behavior against live responses before attributing a risk-control failure to a particular parameter.
