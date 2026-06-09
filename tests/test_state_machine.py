"""Unit tests for the spine cooling state machine."""

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import FaultCode  # noqa: E402
from state_machine import State, StateMachine  # noqa: E402


_ALL_SENSORS_OK = {
    "Cartridge In Place": True,
    "Level Low": True,
    "Level Critical": True,
}


class StateMachineTests(unittest.TestCase):
    def test_normal_session(self) -> None:
        sm = StateMachine(ready_hold_after_startup_s=0)

        sm.handle_init_complete(True)
        self.assertEqual(sm.get_current_state(), State.READY)

        sm.update(_ALL_SENSORS_OK)
        self.assertEqual(sm.get_current_state(), State.COOLING)

        sm.start_pumping()
        self.assertEqual(sm.get_current_state(), State.PUMPING)

        sm.stop_pumping()
        self.assertEqual(sm.get_current_state(), State.COOLING)

        sm.apply_fault(FaultCode.CARTRIDGE_REMOVED)
        self.assertEqual(sm.get_current_state(), State.ERROR)
        self.assertEqual(sm.get_error_message(), "Cartridge removed during operation")
        sm.acknowledge_error()
        self.assertEqual(sm.get_current_state(), State.READY)

        sm.update(_ALL_SENSORS_OK)
        self.assertEqual(sm.get_current_state(), State.COOLING)
        sm.apply_fault(FaultCode.CSF_LOW_TEMP)
        self.assertEqual(sm.get_current_state(), State.ERROR)
        self.assertEqual(sm.get_error_message(), "CSF low temp")
        self.assertEqual(sm.get_latched_fault_code(), FaultCode.CSF_LOW_TEMP)
        self.assertEqual(sm.get_fault_context_state(), State.COOLING)
        sm.acknowledge_error()
        self.assertEqual(sm.get_current_state(), State.READY)
        self.assertIsNone(sm.get_error_message())
        self.assertIsNone(sm.get_latched_fault_code())

        sm.update(_ALL_SENSORS_OK)
        sm.handle_sensor_error("Test error")
        self.assertEqual(sm.get_current_state(), State.ERROR)
        self.assertEqual(sm.get_error_message(), "Test error")

        sm.acknowledge_error()
        self.assertEqual(sm.get_current_state(), State.READY)
        self.assertIsNone(sm.get_error_message())

    def test_ready_hold_after_startup(self) -> None:
        sm = StateMachine(ready_hold_after_startup_s=10.0)
        start = datetime(2026, 6, 9, 12, 0, 0)

        with patch("state_machine.datetime") as mock_dt:
            mock_dt.now.return_value = start
            sm.handle_init_complete(True)
            self.assertEqual(sm.get_current_state(), State.READY)

            mock_dt.now.return_value = start + timedelta(seconds=5)
            sm.update(_ALL_SENSORS_OK)
            self.assertEqual(sm.get_current_state(), State.READY)

            mock_dt.now.return_value = start + timedelta(seconds=10)
            sm.update(_ALL_SENSORS_OK)
            self.assertEqual(sm.get_current_state(), State.COOLING)

    def test_ready_hold_skipped_after_error_ack(self) -> None:
        sm = StateMachine(ready_hold_after_startup_s=10.0)
        start = datetime(2026, 6, 9, 12, 0, 0)

        with patch("state_machine.datetime") as mock_dt:
            mock_dt.now.return_value = start
            sm.handle_init_complete(True)
            sm.update(_ALL_SENSORS_OK)
            self.assertEqual(sm.get_current_state(), State.READY)

            mock_dt.now.return_value = start + timedelta(seconds=15)
            sm.update(_ALL_SENSORS_OK)
            self.assertEqual(sm.get_current_state(), State.COOLING)

            sm.apply_fault(FaultCode.CARTRIDGE_REMOVED)
            sm.acknowledge_error()
            self.assertEqual(sm.get_current_state(), State.READY)

            mock_dt.now.return_value = start + timedelta(seconds=16)
            sm.update(_ALL_SENSORS_OK)
            self.assertEqual(sm.get_current_state(), State.COOLING)


if __name__ == "__main__":
    unittest.main()
