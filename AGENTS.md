# AGENTS.md: bilibili-following-analyzer

`bilibili-following-analyzer` is a Python CLI that evaluates composable filters against a Bilibili following list.

## Read before you edit

| When the change touches       | Read                                                                           |
| ----------------------------- | ------------------------------------------------------------------------------ |
| Configuration or CLI behavior | [Configuration](README.md#configuration)                                       |
| API requests                  | [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect) |
| CI or a workflow              | [devkit's CI guide](https://github.com/hakula139/devkit/blob/v3/docs/ci.md)    |

## Analysis contracts

- Use the configured TOML filters and allow list for analysis runs. Override them only when the user asks.
- Keep login cookies, allow lists, cached API responses, and analysis results local.
- Activity fetch failures leave the user's activity unknown. Preserve `UNAVAILABLE` status and never interpret it as an empty feed or an inactive account.
- Report skipped users and API failures with the results. A successful process exit does not establish that every user's data was available.
- Keep live API calls out of tests. Use fixtures or mocks for external responses.
- Confirm request behavior against live responses before attributing a risk-control failure to a particular parameter.

## Code

Use NumPy-style docstrings for non-obvious API contracts.

## Verification

In each new checkout or worktree, run `nix develop -c true` once to install the pre-commit hooks and link their configuration.

```bash
nix flake check --all-systems
nix develop -c run-hooks
nix develop -c uv run --locked pytest
nix develop -c uv run --locked bilibili-analyzer --help
```
