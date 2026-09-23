# Contributing

Thanks for considering a contribution! This document covers the practical workflow; the
[README](README.md#development) describes the toolchain. By participating you agree to the
[Code of Conduct](CODE_OF_CONDUCT.md).

## Getting started

```sh
git clone https://github.com/lmgarret/wox-stopwatch-plugin
cd wox-stopwatch-plugin
uv sync --group dev
uvx pre-commit install --hook-type pre-commit --hook-type commit-msg
```

`pre-commit install` registers two hooks:

- **pre-commit** — `ruff check --fix` and `ruff format` on staged files, plus whitespace/JSON/YAML checks.
- **commit-msg** — [conventional-pre-commit](https://github.com/compilerla/conventional-pre-commit) validates the message against Conventional Commits.

## Commit messages

We use [Conventional Commits](https://www.conventionalcommits.org); release-please derives versions and the changelog from them:

- `feat: ...` → minor bump
- `fix: ...` → patch bump
- `feat!: ...` or a `BREAKING CHANGE:` footer → major bump
- `chore:`, `docs:`, `ci:`, `refactor:`, `test:` → no release, still linted

## Before opening a PR

```sh
make lint && make test
```

CI runs the same checks on Linux, macOS and Windows against Python 3.10 and 3.13, plus a packaging
step, on every PR. New behavior should come with unit tests — the Wox API is faked in
`tests/test_plugin.py`, so tests are fast and deterministic.

## Testing against a real Wox

In Wox settings, add this repository folder as a local plugin directory, then reload the plugin to
try your changes end-to-end.

## Releasing (maintainers)

Merge the release-please PR. That publishes a GitHub release, and CI attaches the `.wox` package
built from the tagged commit as `wox.plugin.stopwatch.wox`.

The Wox plugin store entry points at `releases/latest/download/wox.plugin.stopwatch.wox`, so the
asset name must stay unversioned — don't rename it in the `Makefile`.

release-please bumps `$.Version` in `plugin.json` by reserializing the whole file with
`JSON.stringify(obj, null, 2)`. `plugin.json` is committed in exactly that shape so the release
PR's diff stays limited to the version line. Don't reflow it by hand.
