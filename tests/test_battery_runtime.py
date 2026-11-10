"""Battery-mode countdown and the UPS Remote command."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from battery_runtime import (  # noqa: E402
    BatteryRuntimeTracker,
    format_countdown,
    running_on_battery_text,
)


class BatteryRuntimeTests(unittest.TestCase):
    def test_idle_until_battery_mode(self) -> None:
        tracker = BatteryRuntimeTracker(runtime_s=1800)
        tracker.update(on_battery=False, now=10.0)
        self.assertFalse(tracker.remote_on)
        self.assertIsNone(tracker.remaining_s)
        self.assertEqual(running_on_battery_text(None), "Running on battery")

    def test_countdown_starts_at_thirty_minutes(self) -> None:
        tracker = BatteryRuntimeTracker(runtime_s=1800)
        tracker.update(on_battery=True, now=100.0)
        self.assertEqual(tracker.remaining_s, 1800)
        self.assertEqual(format_countdown(tracker.remaining_s), "30:00")
        self.assertEqual(
            running_on_battery_text(tracker.remaining_s),
            "Running on battery 30:00",
        )
        self.assertFalse(tracker.remote_on)

    def test_counts_down_and_clears_if_mains_returns(self) -> None:
        tracker = BatteryRuntimeTracker(runtime_s=1800)
        tracker.update(on_battery=True, now=0.0)
        tracker.update(on_battery=True, now=61.0)
        self.assertEqual(format_countdown(tracker.remaining_s), "28:59")
        tracker.update(on_battery=False, now=62.0)
        self.assertIsNone(tracker.remaining_s)
        self.assertFalse(tracker.shutdown_started)
        tracker.update(on_battery=True, now=70.0)
        self.assertEqual(tracker.remaining_s, 1800)

    def test_zero_starts_shutdown_and_latches_remote(self) -> None:
        tracker = BatteryRuntimeTracker(runtime_s=1800)
        tracker.update(on_battery=True, now=0.0)
        tracker.update(on_battery=True, now=1800.0)
        self.assertTrue(tracker.shutdown_started)
        self.assertTrue(tracker.remote_on)
        self.assertEqual(tracker.remaining_s, 0.0)
        tracker.update(on_battery=False, now=1900.0)
        self.assertTrue(tracker.remote_on)


if __name__ == "__main__":
    unittest.main()
