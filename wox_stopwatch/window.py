"""Standalone stopwatch window.

Launched by the plugin as a separate process (Wox does not expose a window API
to third-party plugins), so it only uses the standard library. It shares the
stopwatch with the launcher through StateStore: every change made here is
written to disk and picked up by the plugin, and vice versa.

Usage: python window.py --folder <state folder> [--theme <json>]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tkinter as tk
import tkinter.font as tkfont

# Allow running this file directly as a script from the plugin package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wox_stopwatch.state import StateStore, Stopwatch, format_duration  # noqa: E402

TICK_MS = 30
SYNC_MS = 200
HEARTBEAT_MS = 1000

DEFAULT_THEME = {
    "background": "#1f1f24",
    "text": "#f2f2f5",
    "secondary_text": "#9a9aa5",
    "border": "#34343c",
    "accent": "#4c8dff",
    "accent_text": "#ffffff",
    "selection": "#2c2c34",
}

_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def parse_theme(raw: str) -> dict:
    """Merge Wox theme colors over the defaults, ignoring anything Tk can't render."""
    theme = dict(DEFAULT_THEME)
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        data = {}
    for key in theme:
        value = str(data.get(key, "")).strip()
        # Wox may return #RRGGBBAA; Tk only understands #RRGGBB.
        if re.match(r"^#[0-9a-fA-F]{8}$", value):
            value = value[:7]
        if _HEX_COLOR.match(value):
            theme[key] = value
    return theme


def pick_font(root: tk.Tk, size: int, weight: str = "normal") -> tkfont.Font:
    families = set(tkfont.families(root))
    for family in ("SF Mono", "Menlo", "Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono", "Liberation Mono"):
        if family in families:
            return tkfont.Font(root=root, family=family, size=size, weight=weight)
    font = tkfont.nametofont("TkFixedFont").copy()
    font.configure(size=size, weight=weight)
    return font


class FlatButton(tk.Label):
    """Label-based button: tk.Button ignores background colors on macOS."""

    def __init__(self, master: tk.Misc, text: str, command, bg: str, fg: str, hover: str, **kwargs) -> None:
        super().__init__(master, text=text, bg=bg, fg=fg, cursor="hand2", padx=14, pady=8, **kwargs)
        self._bg = bg
        self._hover = hover
        self._command = command
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", lambda _e: self.configure(bg=self._hover))
        self.bind("<Leave>", lambda _e: self.configure(bg=self._bg))

    def set_colors(self, bg: str, fg: str, hover: str) -> None:
        self._bg = bg
        self._hover = hover
        self.configure(bg=bg, fg=fg)


class StopwatchWindow:
    def __init__(self, store: StateStore, theme: dict) -> None:
        self.store = store
        self.theme = theme
        self.stopwatch: Stopwatch = store.load()
        self.state_mtime = store.state_mtime()
        # Ignore commands that were written before this window started.
        self.last_command_at = float(store.read_window_command().get("at", 0.0))
        self.rendered_laps: list = []

        self.root = tk.Tk()
        self.root.title("Stopwatch")
        self.root.configure(bg=theme["background"])
        self.root.minsize(260, 220)
        self.root.geometry("300x360")
        self.pinned = True
        self.root.attributes("-topmost", True)

        self._build()
        self._bind_keys()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._render_controls()
        self._render_laps()
        self._tick()
        self._sync()
        self._heartbeat()

    # UI construction

    def _build(self) -> None:
        t = self.theme
        root = self.root

        header = tk.Frame(root, bg=t["background"])
        header.pack(fill="x", padx=14, pady=(10, 0))
        self.status_label = tk.Label(header, text="", bg=t["background"], fg=t["secondary_text"], anchor="w")
        self.status_label.pack(side="left")
        self.pin_button = FlatButton(header, "", self.toggle_pin, t["background"], t["secondary_text"], t["selection"])
        self.pin_button.configure(padx=6, pady=2)
        self.pin_button.pack(side="right")

        self.time_font = pick_font(root, 34, "bold")
        self.time_label = tk.Label(root, text="00:00.00", font=self.time_font, bg=t["background"], fg=t["text"])
        self.time_label.pack(fill="x", padx=14, pady=(4, 10))

        controls = tk.Frame(root, bg=t["background"])
        controls.pack(fill="x", padx=14)
        for column in range(3):
            controls.columnconfigure(column, weight=1, uniform="controls")
        self.toggle_button = FlatButton(controls, "Start", self.toggle, t["accent"], t["accent_text"], t["accent"])
        self.lap_button = FlatButton(controls, "Lap", self.lap, t["selection"], t["text"], t["border"])
        self.reset_button = FlatButton(controls, "Reset", self.reset, t["selection"], t["text"], t["border"])
        self.toggle_button.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.lap_button.grid(row=0, column=1, sticky="ew", padx=4)
        self.reset_button.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        hint = tk.Label(
            root,
            text="Space start/pause · L lap · R reset · P pin",
            bg=t["background"],
            fg=t["secondary_text"],
            font=tkfont.nametofont("TkSmallCaptionFont"),
        )
        # Packed before the laps list so the expanding list cannot squeeze it out.
        hint.pack(side="bottom", pady=(0, 8))

        list_frame = tk.Frame(root, bg=t["border"], padx=1, pady=1)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(12, 6))
        self.laps_list = tk.Listbox(
            list_frame,
            font=pick_font(root, 11),
            bg=t["background"],
            fg=t["text"],
            selectbackground=t["selection"],
            selectforeground=t["text"],
            highlightthickness=0,
            borderwidth=0,
            activestyle="none",
        )
        self.laps_list.pack(fill="both", expand=True)

    def _bind_keys(self) -> None:
        self.root.bind("<space>", lambda _e: self.toggle())
        self.root.bind("<Return>", lambda _e: self.toggle())
        for key in ("l", "L"):
            self.root.bind(key, lambda _e: self.lap())
        for key in ("r", "R"):
            self.root.bind(key, lambda _e: self.reset())
        for key in ("p", "P"):
            self.root.bind(key, lambda _e: self.toggle_pin())
        self.root.bind("<Escape>", lambda _e: self.close())

    # Actions

    def _apply(self, change) -> None:
        # Re-read before writing so a change made from the launcher is not lost.
        self.stopwatch = self.store.update(change)
        self.state_mtime = self.store.state_mtime()
        self._render_controls()
        self._render_laps()

    def toggle(self) -> None:
        self._apply(lambda sw: sw.toggle())

    def lap(self) -> None:
        self._apply(lambda sw: sw.lap())

    def reset(self) -> None:
        self._apply(lambda sw: sw.reset())

    def toggle_pin(self) -> None:
        self.pinned = not self.pinned
        self.root.attributes("-topmost", self.pinned)
        self._render_controls()

    def bring_to_front(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        if not self.pinned:
            self.root.after(200, lambda: self.root.attributes("-topmost", False))
        self.root.focus_force()

    def close(self) -> None:
        self.store.clear_heartbeat()
        self.root.destroy()

    # Rendering

    def _render_controls(self) -> None:
        t = self.theme
        sw = self.stopwatch
        if sw.running:
            self.toggle_button.configure(text="Pause")
        else:
            self.toggle_button.configure(text="Resume" if sw.accumulated > 0 else "Start")
        lap_fg = t["text"] if sw.running else t["secondary_text"]
        self.lap_button.set_colors(t["selection"], lap_fg, t["border"])
        self.status_label.configure(text={"running": "Running", "paused": "Paused", "idle": "Ready"}[sw.status])
        self.pin_button.configure(text="Pinned" if self.pinned else "Pin", fg=t["accent"] if self.pinned else t["secondary_text"])

    def _render_laps(self) -> None:
        if self.stopwatch.laps == self.rendered_laps:
            return
        self.rendered_laps = list(self.stopwatch.laps)
        self.laps_list.delete(0, "end")
        splits = self.stopwatch.lap_splits()
        for index in range(len(splits) - 1, -1, -1):
            line = f" #{index + 1:<3} {format_duration(splits[index]):>10}  {format_duration(self.stopwatch.laps[index]):>10}"
            self.laps_list.insert("end", line)

    # Loops

    def _tick(self) -> None:
        self.time_label.configure(text=format_duration(self.stopwatch.elapsed()))
        self.root.after(TICK_MS, self._tick)

    def _sync(self) -> None:
        mtime = self.store.state_mtime()
        if mtime != self.state_mtime:
            self.state_mtime = mtime
            self.stopwatch = self.store.load()
            self._render_controls()
            self._render_laps()

        command = self.store.read_window_command()
        command_at = float(command.get("at", 0.0))
        if command_at > self.last_command_at:
            self.last_command_at = command_at
            if command.get("command") == "raise":
                self.bring_to_front()
            elif command.get("command") == "close":
                self.close()
                return

        self.root.after(SYNC_MS, self._sync)

    def _heartbeat(self) -> None:
        self.store.write_heartbeat(os.getpid())
        self.root.after(HEARTBEAT_MS, self._heartbeat)

    def run(self) -> None:
        self.bring_to_front()
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Wox stopwatch window")
    parser.add_argument("--folder", required=True, help="folder holding the shared stopwatch state")
    parser.add_argument("--theme", default="", help="JSON object with Wox theme colors")
    args = parser.parse_args()

    store = StateStore(args.folder)
    if store.is_window_open():
        # Another window is alive; ask it to come forward instead of opening a duplicate.
        store.send_window_command("raise")
        return 0

    store.write_heartbeat(os.getpid())
    try:
        StopwatchWindow(store, parse_theme(args.theme)).run()
    finally:
        store.clear_heartbeat()
    return 0


if __name__ == "__main__":
    sys.exit(main())
