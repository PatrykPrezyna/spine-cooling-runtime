"""Unit tests for cooling effectiveness tracking."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from cooling_tracker import CoolingEffectivenessTracker  # noqa: E402
from fault_catalog import FaultCode  # noqa: E402
from safety_rules import RuleContext, TelemetrySnapshot, evaluate  # noqa: E402
from state_machine import State  # noqa: E402


class CoolingTrackerTests(unittest.TestCase):
    def test_cooling_ineffective_after_timeout(self) -> None:
        tracker = CoolingEffectivenessTracker()
        tracker.tick(pump=True, compressor=True, csf_temp=30.0, now=0.0)
        tracker.tick(pump=True, compressor=True, csf_temp=30.0, now=100.0)
        ctx = RuleContext(
            current_state=State.PUMPING,
            seconds_in_state=0.0,
            sensor_states={},
            temperatures={"CSF": 29.95},
            pressures={},
            pump_running=True,
            compressor_on=True,
            telemetry=TelemetrySnapshot(),
            config={
                "alarms": {
                    "csf_label": "CSF",
                    "cooling_ineffective_timeout_s": 60,
                    "cooling_ineffective_csf_delta_c": 0.2,
                }
            },
            cooling_tracker=tracker,
            now=100.0,
        )
        active = evaluate(ctx)
        self.assertIn(FaultCode.COOLING_INEFFECTIVE, active)

    def test_tracker_resets_when_pump_stops(self) -> None:
        tracker = CoolingEffectivenessTracker()
        tracker.tick(pump=True, compressor=True, csf_temp=30.0, now=0.0)
        tracker.tick(pump=False, compressor=True, csf_temp=30.0, now=50.0)
        self.assertFalse(
            tracker.is_ineffective(
                now=200.0,
                csf_temp=29.0,
                timeout_s=60,
                min_delta_c=0.2,
            )
        )


if __name__ == "__main__":
    unittest.main()
