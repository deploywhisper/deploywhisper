"""Application lifecycle owns only configured engine coordinators."""

from __future__ import annotations

import asyncio
import runpy
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import app
from infra_automation.local_workers import HandlerRegistry


async def idle_scheduler(stop):
    await stop.wait()


class EngineLifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_spawn_bootstrap_does_not_restart_uvicorn(self):
        with patch("uvicorn.run") as start_server:
            runpy.run_path(str(Path(app.__file__)), run_name="__mp_main__")
        start_server.assert_not_called()

    async def test_empty_registry_creates_no_workers_or_coordinator(self):
        with (
            patch("app.init_db"),
            patch("infra_automation.storage.configure_engine_sqlite") as profile,
            patch("app._topology_drift_scheduler_loop", new=idle_scheduler),
            patch("infra_automation.local_workers.DEFAULT_REGISTRY", HandlerRegistry()),
            patch("infra_automation.local_workers.SpawnProcessWorkers") as workers,
            patch("infra_automation.coordinator.Coordinator") as coordinator,
        ):
            async with app.lifespan(app.fastapi_app):
                await asyncio.sleep(0)
            profile.assert_not_called()
            workers.assert_not_called()
            coordinator.assert_not_called()

    async def test_configured_coordinator_starts_and_stops_with_lifespan(self):
        owned = MagicMock(start=AsyncMock(), stop=AsyncMock())
        with (
            patch("app.init_db"),
            patch("infra_automation.storage.configure_engine_sqlite") as profile,
            patch("app._topology_drift_scheduler_loop", new=idle_scheduler),
            patch("infra_automation.local_workers.DEFAULT_REGISTRY", object()),
            patch("infra_automation.local_workers.SpawnProcessWorkers") as workers,
            patch("infra_automation.coordinator.Coordinator", return_value=owned),
        ):
            async with app.lifespan(app.fastapi_app):
                owned.start.assert_awaited_once()
                owned.stop.assert_not_awaited()
            owned.stop.assert_awaited_once()
            profile.assert_called_once()
            workers.assert_called_once()

    async def test_start_failure_closes_owned_coordinator_and_existing_scheduler(self):
        async def fail_start():
            await asyncio.sleep(0)
            raise RuntimeError("synthetic-start-fault")

        owned = MagicMock(start=AsyncMock(side_effect=fail_start), stop=AsyncMock())
        stopped = asyncio.Event()

        async def scheduler(stop):
            try:
                await stop.wait()
            finally:
                stopped.set()

        with (
            patch("app.init_db"),
            patch("infra_automation.storage.configure_engine_sqlite"),
            patch("app._topology_drift_scheduler_loop", new=scheduler),
            patch("infra_automation.local_workers.DEFAULT_REGISTRY", object()),
            patch("infra_automation.local_workers.SpawnProcessWorkers"),
            patch("infra_automation.coordinator.Coordinator", return_value=owned),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic-start-fault"):
                async with app.lifespan(app.fastapi_app):
                    self.fail("A failed startup cannot yield a running application.")
            owned.stop.assert_awaited_once()
            await asyncio.sleep(0)
            self.assertTrue(stopped.is_set())
