"""Stopwatch state, persisted as JSON in the plugin cache folder.

Times are wall-clock (time.time()) so a running stopwatch keeps counting
across Wox restarts.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, List, Optional


@dataclass
class Stopwatch:
    running: bool = False
    # Wall-clock timestamp of the last start/resume; only meaningful while running.
    started_at: float = 0.0
    # Elapsed seconds accumulated before the current run segment.
    accumulated: float = 0.0
    # Total elapsed seconds at the moment each lap was recorded.
    laps: List[float] = field(default_factory=list)

    def elapsed(self, now: Optional[float] = None) -> float:
        if not self.running:
            return self.accumulated
        now = time.time() if now is None else now
        return self.accumulated + max(0.0, now - self.started_at)

    def start(self, now: Optional[float] = None) -> None:
        if self.running:
            return
        self.started_at = time.time() if now is None else now
        self.running = True

    def pause(self, now: Optional[float] = None) -> None:
        if not self.running:
            return
        self.accumulated = self.elapsed(now)
        self.running = False
        self.started_at = 0.0

    def toggle(self, now: Optional[float] = None) -> None:
        if self.running:
            self.pause(now)
        else:
            self.start(now)

    def lap(self, now: Optional[float] = None) -> None:
        if self.running:
            self.laps.append(self.elapsed(now))

    def reset(self) -> None:
        self.running = False
        self.started_at = 0.0
        self.accumulated = 0.0
        self.laps = []

    def lap_splits(self) -> List[float]:
        """Duration of each individual lap (laps store cumulative totals)."""
        splits = []
        previous = 0.0
        for total in self.laps:
            splits.append(total - previous)
            previous = total
        return splits

    @property
    def status(self) -> str:
        if self.running:
            return "running"
        return "paused" if self.accumulated > 0 else "idle"

    @classmethod
    def from_dict(cls, data: dict) -> "Stopwatch":
        return cls(
            running=bool(data.get("running", False)),
            started_at=float(data.get("started_at", 0.0)),
            accumulated=float(data.get("accumulated", 0.0)),
            laps=[float(v) for v in data.get("laps", [])],
        )


def format_duration(seconds: float, precision: int = 2) -> str:
    """Format as MM:SS.cc, or H:MM:SS.cc once past an hour."""
    seconds = max(0.0, seconds)
    scale = 10**precision
    total = int(seconds * scale)
    fraction = total % scale
    whole = total // scale
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    text = f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes:02d}:{secs:02d}"
    if precision > 0:
        text += f".{fraction:0{precision}d}"
    return text


def _write_json_atomic(path: str, data: dict) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class StateStore:
    """Loads and saves the Stopwatch in `folder`/stopwatch.json."""

    def __init__(self, folder: str) -> None:
        self.folder = folder
        self.state_path = os.path.join(folder, "stopwatch.json")

    def load(self) -> Stopwatch:
        return Stopwatch.from_dict(_read_json(self.state_path))

    def save(self, stopwatch: Stopwatch) -> None:
        _write_json_atomic(self.state_path, asdict(stopwatch))

    def update(self, change: Callable[[Stopwatch], None]) -> Stopwatch:
        stopwatch = self.load()
        change(stopwatch)
        self.save(stopwatch)
        return stopwatch
