"""Wox stopwatch plugin.

The launcher shows the live elapsed time plus start/pause, lap and reset
results. State is persisted by StateStore so a running stopwatch survives
Wox restarts.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable

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
IMAGES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "images")


def _icon(name: str) -> WoxImage:
    with open(os.path.join(IMAGES_DIR, f"{name}.svg"), encoding="utf-8") as f:
        return WoxImage.new_svg(f.read())


ICON_STOPWATCH = _icon("stopwatch")
ICON_START = _icon("stopwatch-start")
ICON_PAUSE = _icon("stopwatch-pause")
ICON_LAP = _icon("stopwatch-lap")
ICON_RESET = _icon("stopwatch-reset")
ICON_COPY = _icon("stopwatch-copy")

STATUS_TEXT = {"running": "Running", "paused": "Paused", "idle": "Ready"}


class StopwatchPlugin(Plugin):
    api: PublicAPI
    store: StateStore
    tick_task: asyncio.Task | None = None

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

        self._start_ticking(ctx, stopwatch)
        return QueryResponse(results=results)

    def _build_results(self, stopwatch: Stopwatch) -> list[Result]:
        running = stopwatch.running
        elapsed = stopwatch.elapsed()
        toggle_title = "Pause" if running else ("Resume" if elapsed > 0 else "Start")
        toggle_icon = ICON_PAUSE if running else ICON_START
        results: list[Result] = [
            Result(
                id=STATUS_RESULT_ID,
                title=format_duration(elapsed, 1),
                sub_title=self._status_subtitle(stopwatch),
                icon=ICON_PAUSE if stopwatch.status == "paused" else ICON_STOPWATCH,
                score=1000,
                tails=self._status_tails(stopwatch),
                preview=self._laps_preview(stopwatch),
                actions=[
                    self._action(toggle_title, self._toggle, toggle_icon, is_default=True),
                    self._action("Lap", self._lap, ICON_LAP),
                    self._action("Reset", self._reset, ICON_RESET),
                    ResultAction(name="Copy time", icon=ICON_COPY, action=self._copy),
                ],
            )
        ]

        results.append(self._simple_result(toggle_title, f"{toggle_title} the stopwatch", toggle_icon, 900, self._toggle))
        if running:
            results.append(self._simple_result("Lap", "Record a lap at the current time", ICON_LAP, 850, self._lap))
        if elapsed > 0:
            results.append(self._simple_result("Reset", "Stop and clear the stopwatch and its laps", ICON_RESET, 800, self._reset))
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
    def _status_tails(stopwatch: Stopwatch) -> list[ResultTail]:
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

    def _start_ticking(self, ctx: Context, stopwatch: Stopwatch) -> None:
        if self.tick_task and not self.tick_task.done():
            self.tick_task.cancel()
        self.tick_task = asyncio.create_task(self._tick(ctx)) if stopwatch.running else None

    async def _tick(self, ctx: Context) -> None:
        """Keep the status row live until Wox reports it is no longer visible."""
        # Give Wox a moment to render the results before the first update.
        await asyncio.sleep(TICK_SECONDS)
        while True:
            stopwatch = self.store.load()
            if not stopwatch.running:
                return
            still_visible = await self.api.update_result(
                ctx,
                UpdatableResult(
                    id=STATUS_RESULT_ID,
                    title=format_duration(stopwatch.elapsed(), 1),
                    tails=self._status_tails(stopwatch),
                ),
            )
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


plugin = StopwatchPlugin()
