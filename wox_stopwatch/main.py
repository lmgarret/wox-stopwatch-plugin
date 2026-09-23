"""Wox stopwatch plugin.

The launcher shows the live elapsed time plus start/pause, lap, reset and
"open window" results. The dedicated window (window.py) is a separate process
because Wox only offers built-in windows (like Notes) to system plugins; both
sides share state through StateStore.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from typing import Awaitable, Callable, List, Optional

from wox_plugin import (
    ActionContext,
    Context,
    CopyParams,
    Plugin,
    PluginInitParams,
    PublicAPI,
    Query,
    QueryResponse,
    RefreshQueryParam,
    Result,
    ResultAction,
    ResultTail,
    UpdatableResult,
    WoxImage,
    WoxPreview,
    WoxPreviewType,
)

from .state import StateStore, Stopwatch, format_duration

STATUS_RESULT_ID = "wox-stopwatch-status"
TICK_SECONDS = 0.1
WINDOW_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "window.py")

ICON_STOPWATCH = WoxImage.new_emoji("⏱️")
ICON_START = WoxImage.new_emoji("▶️")
ICON_PAUSE = WoxImage.new_emoji("⏸️")
ICON_LAP = WoxImage.new_emoji("🏁")
ICON_RESET = WoxImage.new_emoji("🔄")
ICON_WINDOW = WoxImage.new_emoji("🪟")
ICON_COPY = WoxImage.new_emoji("📋")

STATUS_TEXT = {"running": "Running", "paused": "Paused", "idle": "Ready"}


def _window_python() -> str:
    """Interpreter for the window; prefer pythonw on Windows to avoid a console."""
    executable = sys.executable
    if os.name == "nt":
        candidate = os.path.join(os.path.dirname(executable), "pythonw.exe")
        if os.path.exists(candidate):
            return candidate
    return executable


class StopwatchPlugin(Plugin):
    api: PublicAPI
    store: StateStore
    tick_task: Optional[asyncio.Task] = None

    async def init(self, ctx: Context, init_params: PluginInitParams) -> None:
        self.api = init_params.api
        self.store = StateStore(await self.api.get_cache_folder(ctx))
        self.tick_task = None

    # Query

    async def query(self, ctx: Context, query: Query) -> QueryResponse:
        stopwatch = self.store.load()
        results = self._build_results(stopwatch)

        search = query.search.strip().lower()
        if search:
            results = [r for r in results if r.id == STATUS_RESULT_ID or search in r.title.lower()]

        self._start_ticking(ctx)
        return QueryResponse(results=results)

    def _build_results(self, stopwatch: Stopwatch) -> List[Result]:
        running = stopwatch.running
        elapsed = stopwatch.elapsed()
        results: List[Result] = [
            Result(
                id=STATUS_RESULT_ID,
                title=format_duration(elapsed, 1),
                sub_title=self._status_subtitle(stopwatch),
                icon=ICON_STOPWATCH,
                score=1000,
                tails=self._status_tails(stopwatch),
                preview=self._laps_preview(stopwatch),
                actions=[
                    self._action("Pause" if running else ("Resume" if elapsed > 0 else "Start"), self._toggle, ICON_PAUSE if running else ICON_START, is_default=True),
                    self._action("Lap", self._lap, ICON_LAP),
                    self._action("Reset", self._reset, ICON_RESET),
                    self._window_action(),
                    ResultAction(name="Copy time", icon=ICON_COPY, action=self._copy),
                ],
            )
        ]

        if running:
            results.append(self._simple_result("Pause", "Pause the stopwatch", ICON_PAUSE, 900, self._toggle))
            results.append(self._simple_result("Lap", "Record a lap at the current time", ICON_LAP, 850, self._lap))
        else:
            title = "Resume" if elapsed > 0 else "Start"
            results.append(self._simple_result(title, f"{title} the stopwatch", ICON_START, 900, self._toggle))
        if elapsed > 0:
            results.append(self._simple_result("Reset", "Stop and clear the stopwatch and its laps", ICON_RESET, 800, self._reset))

        window_open = self.store.is_window_open()
        results.append(
            Result(
                title="Show stopwatch window" if window_open else "Open stopwatch window",
                sub_title="Floating window that stays on top of other apps",
                icon=ICON_WINDOW,
                score=700,
                actions=[self._window_action(is_default=True)],
            )
        )
        return results

    def _simple_result(self, title: str, subtitle: str, icon: WoxImage, score: float, handler) -> Result:
        return Result(title=title, sub_title=subtitle, icon=icon, score=score, actions=[self._action(title, handler, icon, is_default=True)])

    @staticmethod
    def _status_subtitle(stopwatch: Stopwatch) -> str:
        text = STATUS_TEXT[stopwatch.status]
        if stopwatch.laps:
            text += f" · {len(stopwatch.laps)} lap{'s' if len(stopwatch.laps) != 1 else ''}"
        return text

    @staticmethod
    def _status_tails(stopwatch: Stopwatch) -> List[ResultTail]:
        if not stopwatch.laps:
            return []
        current_lap = stopwatch.elapsed() - stopwatch.laps[-1]
        return [ResultTail(text=f"Lap {len(stopwatch.laps) + 1}: {format_duration(current_lap, 1)}")]

    @staticmethod
    def _laps_preview(stopwatch: Stopwatch) -> WoxPreview:
        if not stopwatch.laps:
            return WoxPreview()
        rows = ["| Lap | Split | Total |", "| ---: | ---: | ---: |"]
        splits = stopwatch.lap_splits()
        for index in range(len(splits) - 1, -1, -1):
            rows.append(f"| {index + 1} | {format_duration(splits[index])} | {format_duration(stopwatch.laps[index])} |")
        return WoxPreview(preview_type=WoxPreviewType.MARKDOWN, preview_data="\n".join(rows))

    # Live update of the status row

    def _start_ticking(self, ctx: Context) -> None:
        if self.tick_task and not self.tick_task.done():
            self.tick_task.cancel()
        self.tick_task = asyncio.create_task(self._tick(ctx))

    async def _tick(self, ctx: Context) -> None:
        """Keep the status row live while the results are on screen.

        Also watches the state file so changes made from the window show up in
        the launcher. Stops once Wox reports the status row is no longer visible.
        """
        # Give Wox a moment to render the results before the first update.
        await asyncio.sleep(TICK_SECONDS)
        last_state_mtime = self.store.state_mtime()
        idle_polls = 0
        while True:
            if self.store.state_mtime() != last_state_mtime:
                # Rebuild results so action labels (Start/Pause, Reset...) match the new state.
                await self.api.refresh_query(ctx, RefreshQueryParam(preserve_selected_index=True))
                return
            stopwatch = self.store.load()
            if stopwatch.running:
                still_visible = await self.api.update_result(
                    ctx,
                    UpdatableResult(
                        id=STATUS_RESULT_ID,
                        title=format_duration(stopwatch.elapsed(), 1),
                        tails=self._status_tails(stopwatch),
                    ),
                )
            else:
                # Nothing to redraw; only check visibility every few polls to keep RPCs low.
                idle_polls += 1
                still_visible = idle_polls % 5 != 0 or await self.api.get_updatable_result(ctx, STATUS_RESULT_ID) is not None
            if not still_visible:
                return
            await asyncio.sleep(TICK_SECONDS)

    # Actions

    def _action(
        self,
        name: str,
        handler: Callable[[Context, ActionContext], Awaitable[None]],
        icon: WoxImage,
        is_default: bool = False,
    ) -> ResultAction:
        return ResultAction(name=name, icon=icon, action=handler, is_default=is_default, prevent_hide_after_action=True)

    def _window_action(self, is_default: bool = False) -> ResultAction:
        return ResultAction(name="Open window", icon=ICON_WINDOW, action=self._open_window, is_default=is_default)

    async def _change(self, ctx: Context, change: Callable[[Stopwatch], None]) -> None:
        self.store.update(change)
        await self.api.refresh_query(ctx, RefreshQueryParam(preserve_selected_index=True))

    async def _toggle(self, ctx: Context, _action_ctx: ActionContext) -> None:
        await self._change(ctx, lambda sw: sw.toggle())

    async def _lap(self, ctx: Context, _action_ctx: ActionContext) -> None:
        await self._change(ctx, lambda sw: sw.lap())

    async def _reset(self, ctx: Context, _action_ctx: ActionContext) -> None:
        await self._change(ctx, lambda sw: sw.reset())

    async def _copy(self, ctx: Context, _action_ctx: ActionContext) -> None:
        await self.api.copy(ctx, CopyParams(text=format_duration(self.store.load().elapsed())))

    async def _open_window(self, ctx: Context, _action_ctx: ActionContext) -> None:
        if self.store.is_window_open():
            self.store.send_window_command("raise")
            return

        if importlib.util.find_spec("tkinter") is None:
            await self.api.notify(
                ctx,
                "The stopwatch window needs Tkinter for the Python used by Wox (e.g. `sudo apt install python3-tk` or `brew install python-tk`).",
            )
            return

        args = [_window_python(), WINDOW_SCRIPT, "--folder", self.store.folder, "--theme", await self._theme_json(ctx)]
        log = open(os.path.join(self.store.folder, "window.log"), "ab")
        kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": log, "stderr": log, "close_fds": True}
        # Detach so the window keeps running if the plugin host restarts.
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            subprocess.Popen(args, **kwargs)
        except OSError as e:
            await self.api.notify(ctx, f"Failed to open stopwatch window: {e}")
        finally:
            log.close()

    async def _theme_json(self, ctx: Context) -> str:
        try:
            colors = await self.api.get_theme_colors(ctx)
        except Exception:
            # Older Wox versions don't expose theme colors; the window has defaults.
            return ""
        return json.dumps(
            {
                "background": colors.background,
                "text": colors.text,
                "secondary_text": colors.secondary_text,
                "border": colors.border,
                "accent": colors.accent,
                "accent_text": colors.accent_text,
                "selection": colors.selection,
            }
        )


plugin = StopwatchPlugin()
