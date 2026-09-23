"""Plugin tests against a fake Wox API. Skipped when wox-plugin is not installed."""

import asyncio
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from wox_plugin import ActionContext, Context, PluginInitParams, Query, QueryEnv, QueryType, Selection
except ImportError:  # pragma: no cover
    raise unittest.SkipTest("wox-plugin not installed")

from wox_stopwatch.main import STATUS_RESULT_ID, StopwatchPlugin  # noqa: E402


class FakeAPI:
    def __init__(self, folder):
        self.folder = folder
        self.refreshes = 0
        self.updates = []
        self.visible = True

    async def get_cache_folder(self, ctx):
        return self.folder

    async def refresh_query(self, ctx, param):
        self.refreshes += 1

    async def update_result(self, ctx, result):
        self.updates.append(result)
        return self.visible

    async def notify(self, ctx, message):
        pass


def make_query(search=""):
    return Query(
        id="q",
        type=QueryType.INPUT,
        raw_query=f"sw {search}",
        selection=Selection(),
        env=QueryEnv(),
        trigger_keyword="sw",
        search=search,
    )


class PluginTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = FakeAPI(self.tmp.name)
        self.plugin = StopwatchPlugin()
        self.ctx = Context.new()
        await self.plugin.init(self.ctx, PluginInitParams(api=self.api, plugin_directory=self.tmp.name))

    async def asyncTearDown(self):
        if self.plugin.tick_task:
            self.plugin.tick_task.cancel()
        self.tmp.cleanup()

    def default_action(self, result):
        return next(a for a in result.actions if a.is_default)

    async def test_idle_results(self):
        response = await self.plugin.query(self.ctx, make_query())
        titles = [r.title for r in response.results]
        self.assertEqual(titles[0], "00:00.0")
        self.assertIn("Start", titles)
        self.assertNotIn("Reset", titles)

    async def test_start_then_tick_updates_status_row(self):
        response = await self.plugin.query(self.ctx, make_query())
        start = next(r for r in response.results if r.title == "Start")
        await self.default_action(start).action(self.ctx, ActionContext())
        self.assertTrue(self.plugin.store.load().running)
        self.assertEqual(self.api.refreshes, 1)

        response = await self.plugin.query(self.ctx, make_query())
        titles = [r.title for r in response.results]
        self.assertIn("Pause", titles)
        self.assertIn("Lap", titles)
        await asyncio.sleep(0.35)
        self.assertTrue(self.api.updates)
        self.assertEqual(self.api.updates[-1].id, STATUS_RESULT_ID)

        # Once Wox reports the row is gone, the loop stops.
        self.api.visible = False
        await asyncio.sleep(0.25)
        self.assertTrue(self.plugin.tick_task.done())

    async def test_search_filters_but_keeps_status(self):
        response = await self.plugin.query(self.ctx, make_query("sta"))
        titles = [r.title for r in response.results]
        self.assertEqual(titles, ["00:00.0", "Start"])


if __name__ == "__main__":
    unittest.main()
