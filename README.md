<p align="center">
  <img src="images/stopwatch.svg" width="96" alt="Stopwatch icon">
</p>

<h1 align="center">Wox Stopwatch</h1>

<p align="center">
  <a href="https://github.com/lmgarret/wox-stopwatch-plugin/actions/workflows/ci.yml"><img src="https://github.com/lmgarret/wox-stopwatch-plugin/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/lmgarret/wox-stopwatch-plugin/releases/latest"><img src="https://img.shields.io/github/v/release/lmgarret/wox-stopwatch-plugin" alt="Latest release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="License: GPL-3.0"></a>
</p>

A stopwatch plugin for [Wox](https://github.com/Wox-launcher/Wox) v2 that runs in the launcher and records laps.

## Usage

Type `sw` in Wox:

| Result | Action |
| --- | --- |
| `00:12.3` (status row) | Shows the live elapsed time, the lap count and the current lap. Enter starts or pauses it, and the Action Panel has Lap, Reset and Copy time. The preview lists your laps. |
| Start / Pause / Resume | Toggles the stopwatch |
| Lap | Records a lap (only while running) |
| Reset | Stops the stopwatch and clears its laps |

Anything you type after `sw` filters the results, for example `sw lap`.

The stopwatch uses wall-clock time and is saved in the plugin's cache folder, so it keeps running across Wox restarts.

## Screenshots

| | |
| :-- | :-- |
| Ready to start | <img src="screenshots/idle.png" width="420" alt="Stopwatch ready to start"> |
| Running, with Lap and Reset | <img src="screenshots/running.png" width="420" alt="Stopwatch running with Lap, Pause and Reset actions"> |
| Laps in the preview panel | <img src="screenshots/laps.png" width="420" alt="Lap table in the preview panel"> |

## Install

- **Store**: search for *Stopwatch* in Wox's plugin store.
- **Release**: download `wox.plugin.stopwatch.wox` from the
  [latest release](https://github.com/lmgarret/wox-stopwatch-plugin/releases/latest) and open it.
- **Development**: in Wox settings, add this repository folder as a local plugin directory.

Requires Wox ≥ 2.0.4 with Python ≥ 3.10.

## Development

```sh
uv sync --group dev
make test
make lint
make package
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the git hooks, commit conventions and release process.

## License

[GPL-3.0](LICENSE)
