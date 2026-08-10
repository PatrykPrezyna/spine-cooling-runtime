"""Unit tests for closed-loop pump flow control."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pump_flow_control import (  # noqa: E402
    PumpFlowControlConfig,
    PumpFlowController,
    flow_ml_per_min_to_rpm,
)


class PumpFlowControlTests(unittest.TestCase):
    def test_full_speed_above_band(self) -> None:
        ctrl = PumpFlowController()
        flow = ctrl.compute(33.0, 32.0, now_s=1.0)  # error = 1.0 > 0.5
        self.assertEqual(flow, 100.0)

    def test_min_flow_at_or_below_setpoint(self) -> None:
        ctrl = PumpFlowController()
        self.assertEqual(ctrl.compute(32.0, 32.0, now_s=1.0), 10.0)
        self.assertEqual(ctrl.compute(31.5, 32.0, now_s=2.0), 10.0)

    def test_pid_band_between_zero_and_half(self) -> None:
        ctrl = PumpFlowController(
            PumpFlowControlConfig(kp=180.0, ki=0.0, kd=0.0)
        )
        # error = 0.25 → min(10) + 180*0.25 = 55
        flow = ctrl.compute(32.25, 32.0, now_s=1.0)
        self.assertAlmostEqual(flow, 55.0, places=3)

    def test_pid_clamped_to_max_inside_band(self) -> None:
        ctrl = PumpFlowController(
            PumpFlowControlConfig(kp=180.0, ki=0.0, kd=0.0)
        )
        # error = 0.5 → min(10) + 180*0.5 = 100
        flow = ctrl.compute(32.5, 32.0, now_s=1.0)
        self.assertEqual(flow, 100.0)

    def test_flow_to_rpm_conversion(self) -> None:
        self.assertEqual(flow_ml_per_min_to_rpm(100.0, 0.5862), 171)
        self.assertEqual(flow_ml_per_min_to_rpm(10.0, 0.5862), 17)

    def test_from_config_dict(self) -> None:
        ctrl = PumpFlowController.from_config_dict(
            {
                "max_flow_ml_per_min": 80,
                "min_flow_ml_per_min": 12,
                "full_speed_error_c": 0.4,
            }
        )
        self.assertEqual(ctrl.compute(33.0, 32.0, now_s=1.0), 80.0)
        self.assertEqual(ctrl.compute(31.0, 32.0, now_s=2.0), 12.0)


if __name__ == "__main__":
    unittest.main()
