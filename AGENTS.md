# AGENTS.md: bilibili-following-analyzer

Follow the user's global instructions. Keep this file focused on constraints that are not apparent from the source or tooling.

## Analysis contracts

- Use the configured `.env` filters and allow list for analysis runs. Override them only when the user asks.
- Keep login cookies, allow lists, cached API responses, and analysis results local.
- Activity fetch failures leave the user's activity unknown. Preserve `UNAVAILABLE` status and never interpret it as an empty feed or an inactive account.
- Report skipped users and API failures with the results. A successful process exit does not establish that every user's data was available.
- Keep live API calls out of tests. Use fixtures or mocks for external responses.

## Development

Enter the development environment with `direnv allow` or `nix develop`, then synchronize dependencies with `uv sync --locked`. The shell installs repository hooks. Python hooks use the locked project tools and require the synchronized environment.

Run `nix flake check` for repository checks and the locked Python checks declared in CI. Use NumPy-style docstrings for non-obvious API contracts.

Use topic branches and squash-merged PRs. Obtain approval for each PR before merging. Keep local plans under ignored `.agents/plans/`.

## API reference

Consult [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) when changing API requests. Confirm request behavior against live responses before attributing a risk-control failure to a particular parameter.
