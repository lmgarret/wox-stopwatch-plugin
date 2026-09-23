# Security Policy

## Supported versions

Only the latest release receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities privately via
[GitHub's private vulnerability reporting](https://github.com/lmgarret/wox-stopwatch-plugin/security/advisories/new)
rather than opening a public issue. You should get a response within a week.

## Scope notes

- The plugin makes no network calls at all.
- The only data it stores is the stopwatch state (start time, accumulated elapsed time and laps),
  written to a JSON file in the plugin's cache folder on your machine.
- Releases are built by GitHub Actions from the tagged commit and carry a
  [build provenance attestation](https://docs.github.com/actions/security-for-github-actions/using-artifact-attestations),
  verifiable with `gh attestation verify wox.plugin.stopwatch.wox -R lmgarret/wox-stopwatch-plugin`.
