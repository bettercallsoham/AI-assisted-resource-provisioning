import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from app import DemoController
from fastapi import HTTPException


class DemoControllerTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_is_idempotent_duplicate_scenarios_are_blocked_and_stop_is_safe(self):
        async def waiting_run(url, phases, stop, on_event):
            on_event({"event": "phase_start", "phase": "normal"})
            on_event({"event": "progress", "phase": "normal", "requests": 1,
                      "successful": 1, "failed": 0})
            await stop.wait()
            on_event({"event": "phase_end", "phase": "normal", "requests": 2,
                      "successful": 2, "failed": 0})
            return {"requests": 2, "successful": 2, "failed": 0, "stopped": True}

        controller = DemoController()
        with patch("app.run_phases", side_effect=waiting_run):
            first = await controller.start("normal")
            self.assertEqual(first["state"], "RUNNING")
            await asyncio.sleep(0)
            self.assertEqual(controller.status()["successful"], 1)
            self.assertEqual((await controller.start("normal"))["started_at"], first["started_at"])
            with self.assertRaises(HTTPException) as error:
                await controller.start("high")
            self.assertEqual(error.exception.status_code, 409)
            self.assertEqual((await controller.stop())["state"], "STOPPED")
            self.assertEqual((await controller.stop())["state"], "STOPPED")
            self.assertEqual(controller.status()["successful"], 2)
            self.assertEqual((await controller.reset())["state"], "IDLE")

    async def test_scenario_failure_is_visible_and_reset_requires_stopped_workload(self):
        async def broken_run(url, phases, stop, on_event):
            raise RuntimeError("request transport failed")

        controller = DemoController()
        with patch("app.run_phases", side_effect=broken_run):
            await controller.start("high")
            await controller.task
        self.assertEqual(controller.status()["state"], "FAILED")
        self.assertIn("transport failed", controller.status()["error"])
        self.assertEqual((await controller.reset())["state"], "IDLE")


if __name__ == "__main__":
    unittest.main()
