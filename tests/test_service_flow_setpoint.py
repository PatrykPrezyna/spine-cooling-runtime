"""Service-tab exact flow setpoint entry."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class ServiceFlowSetpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def _tab(self):
        from gui import ServiceTab

        return ServiceTab(
            {
                "default_speed_rpm": 92,
                "min_speed_rpm": 1,
                "max_speed_rpm": 390,
            }
        )

    def test_typing_exact_flow_sets_commanded_ml_and_nearest_rpm(self) -> None:
        tab = self._tab()
        speeds = []
        tab.on_stepper_speed_change_callback = speeds.append

        tab._apply_typed_flow_ml_per_min(80)

        self.assertEqual(tab._commanded_flow_ml_per_min, 80)
        self.assertEqual(tab.stepper_flow_spin.value(), 80)
        self.assertEqual(tab.stepper_speed_rpm, tab._flow_setpoint_to_rpm(80))
        self.assertEqual(tab.stepper_speed_label.text(), f"{tab.stepper_speed_rpm} RPM")
        self.assertEqual(speeds, [tab.stepper_speed_rpm])

    def test_typed_flow_is_clamped_to_pump_range(self) -> None:
        tab = self._tab()
        lo, hi = tab._flow_entry_bounds()

        tab._apply_typed_flow_ml_per_min(hi + 50)
        self.assertEqual(tab._commanded_flow_ml_per_min, hi)
        self.assertEqual(tab.stepper_flow_spin.value(), hi)

        tab._apply_typed_flow_ml_per_min(0)
        self.assertEqual(tab._commanded_flow_ml_per_min, lo)
        self.assertEqual(tab.stepper_flow_spin.value(), lo)

    def test_spin_box_value_change_applies_non_slider_step(self) -> None:
        tab = self._tab()
        tab.stepper_flow_spin.setValue(75)

        self.assertEqual(tab._commanded_flow_ml_per_min, 75)
        self.assertEqual(tab.stepper_speed_rpm, tab._flow_setpoint_to_rpm(75))
        self.assertNotEqual(75 % 10, 0)

    def test_pid_run_disables_flow_entry(self) -> None:
        tab = self._tab()
        self.assertTrue(tab.stepper_flow_spin.isEnabled())
        tab.pid_run_active = True
        tab._update_stepper_control_enabled_state()
        self.assertFalse(tab.stepper_flow_spin.isEnabled())


if __name__ == "__main__":
    unittest.main()
