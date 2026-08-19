"""Tests for the event-based status / error / warning CSV logger."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import FaultCode  # noqa: E402
from state_machine import State, StateMachine  # noqa: E402
from status_event_logger import StatusEventLogger  # noqa: E402


class StatusEventLoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = {"logging": {"directory": self._tmpdir.name}}
        self.session_start = datetime(2026, 8, 19, 12, 58, 0)
        self.logger = StatusEventLogger(self.config, session_start=self.session_start)

    def tearDown(self) -> None:
        self.logger.stop_logging()
        self._tmpdir.cleanup()

    def _rows(self) -> list[dict[str, str]]:
        path = Path(self.logger.get_log_file_path() or "")
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def test_start_writes_header_and_session_start(self) -> None:
        self.assertTrue(self.logger.start_logging())
        path = Path(self.logger.get_log_file_path() or "")
        self.assertEqual(path.name, "20260819_125800_status_and_errors.csv")
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event"], "session_start")
        self.assertEqual(rows[0]["severity"], "info")

    def test_state_change_and_error_and_warning_rows(self) -> None:
        self.assertTrue(self.logger.start_logging())
        self.logger.log_state_change(State.INIT, State.READY, "Initialization complete")
        self.logger.log_state_change(
            State.COOLING,
            State.ERROR,
            "Leak detected",
            fault_code=FaultCode.LEAK_DETECTED,
        )
        self.logger.log_warning(FaultCode.BATTERY_LOW, "Battery low", state=State.COOLING)
        self.logger.log_warning(
            FaultCode.BATTERY_LOW,
            "Battery low",
            state=State.COOLING,
            cleared=True,
        )
        self.logger.log_session_stop(state=State.READY)
        self.logger.stop_logging()

        by_event = {row["event"]: row for row in self._rows()}
        self.assertEqual(by_event["state_change"]["previous_state"], "Init")
        self.assertEqual(by_event["state_change"]["state"], "Ready")
        self.assertEqual(by_event["state_change"]["message"], "Initialization complete")

        self.assertEqual(by_event["error"]["severity"], "stop")
        self.assertEqual(by_event["error"]["previous_state"], "Cooling")
        self.assertEqual(by_event["error"]["state"], "Error")
        self.assertEqual(by_event["error"]["fault_code"], "LEAK_DETECTED")

        self.assertEqual(by_event["warning"]["fault_code"], "BATTERY_LOW")
        self.assertEqual(by_event["warning"]["severity"], "message")
        self.assertEqual(by_event["warning_cleared"]["fault_code"], "BATTERY_LOW")
        self.assertEqual(by_event["session_stop"]["state"], "Ready")

    def test_state_machine_callback_writes_reason(self) -> None:
        self.assertTrue(self.logger.start_logging())
        sm = StateMachine(ready_hold_after_startup_s=0)
        sm.on_state_change = (
            lambda old, new, reason: self.logger.log_state_change(old, new, reason)
        )
        sm.handle_init_complete(True)
        sm.update(
            {
                "Cartridge In Place": True,
                "Level Low": True,
                "Level Critical": True,
            }
        )
        sm.apply_fault(FaultCode.CARTRIDGE_REMOVED)
        self.logger.stop_logging()

        events = [(row["event"], row["state"], row["message"]) for row in self._rows()]
        self.assertIn(("state_change", "Ready", "Initialization complete"), events)
        self.assertIn(("state_change", "Cooling", "All conditions met"), events)
        self.assertTrue(
            any(
                event == "error"
                and state == "Error"
                and "Cartridge removed" in message
                for event, state, message in events
            )
        )


if __name__ == "__main__":
    unittest.main()
