# Wox Stopwatch

A stopwatch plugin for [Wox](https://github.com/Wox-launcher/Wox) v2 that shows laps. You can use it from the launcher or from its own floating window.

## Usage

Type `sw` in Wox:

| Result | Action |
| --- | --- |
| `00:12.3` (status row) | Shows the live elapsed time, the lap count and the current lap. Enter starts or pauses it, and the Action Panel has Lap, Reset, Open window and Copy time. The preview lists your laps. |
| Start / Pause / Resume | Toggles the stopwatch |
| Lap | Records a lap (only while running) |
| Reset | Stops the stopwatch and clears its laps |
| Open stopwatch window | Opens the floating window, or brings it to the front if it's already open |

Anything you type after `sw` filters the results, for example `sw lap` or `sw win`.

### Stopwatch window

The window stays on top of other apps and uses the colors of your Wox theme. It shares the same stopwatch as the launcher, so you can start it in one and pause it in the other.

Keyboard shortcuts: `Space`/`Enter` start/pause · `L` lap · `R` reset · `P` pin/unpin (always on top) · `Esc` close.

The stopwatch uses wall-clock time and is saved in the plugin's cache folder, so it keeps running across Wox restarts.

## Why a separate process for the window?

Wox's built-in Notes and Timer windows are available only to system (Go) plugins. The public plugin API has no window API for third-party plugins. So the plugin starts `wox_stopwatch/window.py` as a small Tkinter app with the same Python interpreter Wox uses. The window and the plugin share state through JSON files: the stopwatch itself, a heartbeat from the window, and a command file used to bring the window to the front.

Tkinter comes with the python.org installers for Windows and macOS. On other setups, install it yourself:

- Debian/Ubuntu: `sudo apt install python3-tk`
- Fedora: `sudo dnf install python3-tkinter`
- Homebrew: `brew install python-tk`

If Tkinter is missing, the plugin shows a notification. Everything in the launcher still works without it.

## Install

- **Development**: in Wox settings, add this repository folder as a local plugin directory.
- **Package**: run `make package` and install the resulting `wox.plugin.stopwatch.wox`.

Requires Wox ≥ 2.0.4 with Python ≥ 3.10.

## Development

```sh
uv venv && uv pip install wox-plugin
.venv/bin/python -m unittest discover -s tests
make lint
```
