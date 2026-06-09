"""Unit tests for the spine cooling state machine."""

import sys
import unittest
from pathlib import Path


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
        sm = StateMachine()

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


if __name__ == "__main__":
    unittest.main()
