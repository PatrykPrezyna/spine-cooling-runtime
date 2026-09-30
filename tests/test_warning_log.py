"""USB-missing warnings are written once per session, not on every flicker."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fault_catalog import FaultCode  # noqa: E402
from status_event_logger import warning_log_edges  # noqa: E402


class UsbMissingWarningTests(unittest.TestCase):
    def _edges(self, logged, incoming, once_logged):
        return warning_log_edges(
            logged,
            incoming,
            once_codes={FaultCode.USB_NOT_PRESENT},
            once_logged=once_logged,
        )

    def test_usb_missing_is_logged_once_across_flicker(self) -> None:
        logged: set[FaultCode] = set()
        once: set[FaultCode] = set()
        missing = {FaultCode.USB_NOT_PRESENT}
        rows: list[tuple[str, bool]] = []

        for incoming in (missing, set(), missing, missing):
            cleared, raised, logged, once = self._edges(logged, incoming, once)
            rows.extend((code.value, True) for code in cleared)
            rows.extend((code.value, False) for code in raised)

        self.assertEqual(rows, [("USB_NOT_PRESENT", False)])

    def test_other_warnings_still_follow_edges(self) -> None:
        logged: set[FaultCode] = set()
        once: set[FaultCode] = set()
        rows: list[tuple[str, bool]] = []
        steps = (
            {FaultCode.USB_NOT_PRESENT, FaultCode.BATTERY_LOW},
            {FaultCode.USB_NOT_PRESENT},
            {FaultCode.BATTERY_LOW},
        )
        for incoming in steps:
            cleared, raised, logged, once = self._edges(logged, incoming, once)
            rows.extend((code.value, True) for code in cleared)
            rows.extend((code.value, False) for code in raised)

        self.assertEqual(
            rows,
            [
                ("USB_NOT_PRESENT", False),
                ("BATTERY_LOW", False),
                ("BATTERY_LOW", True),
                ("BATTERY_LOW", False),
            ],
        )


if __name__ == "__main__":
    unittest.main()
