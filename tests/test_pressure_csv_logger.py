"""Tests for toggleable pressure-only CSV capture."""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pressure_csv_logger import PressureCSVLogger  # noqa: E402


_CONFIG = {
    "logging": {
        "csv_directory": "unused",
        "filename_format": "unused_%Y%m%d_%H%M%S.csv",
        "pressure_csv_directory": "unused",
        "pressure_filename_format": "pressure_log_%Y%m%d_%H%M%S.csv",
    },
    "pressure_sensors": {
        "enabled": True,
        "sample_rate_hz": 10,
        "channels": [0, 1, 2, 3],
        "channel_configs": {
            0: {"label": "Cartridge Input"},
            1: {"label": "Cartridge Output"},
            2: {"label": "Pump Input"},
            3: {"label": "Pump Output"},
        },
    },
}


class PressureCsvLoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = dict(_CONFIG)
        self.config["logging"] = {
            **_CONFIG["logging"],
            "pressure_csv_directory": self._tmpdir.name,
        }
        self.logger = PressureCSVLogger(self.config)

    def tearDown(self) -> None:
        if self.logger.is_logging:
            self.logger.stop_logging()
        self._tmpdir.cleanup()

    def test_header_is_pressure_only(self) -> None:
        self.assertEqual(
            self.logger.header,
            [
                "timestamp",
                "cartridge_input_psi",
                "cartridge_output_psi",
                "pump_input_psi",
                "pump_output_psi",
            ],
        )

    def test_log_is_noop_until_started(self) -> None:
        self.logger.log({"Cartridge Input": 1.0})
        self.assertEqual(list(Path(self._tmpdir.name).iterdir()), [])

    def test_start_creates_file_and_writes_rows(self) -> None:
        self.assertTrue(self.logger.start_logging())
        path = Path(self.logger.get_log_file_path() or "")
        self.assertTrue(path.exists())
        self.assertTrue(path.name.startswith("pressure_log_"))

        self.logger.log(
            {
                "Cartridge Input": -11.5,
                "Cartridge Output": 75.0,
                "Pump Input": 12.34,
                "Pump Output": 45.67,
            }
        )
        self.logger.stop_logging()

        with path.open(newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], self.logger.header)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][1:], ["-11.50", "75.00", "12.34", "45.67"])

    def test_each_start_creates_a_new_file(self) -> None:
        self.assertTrue(self.logger.start_logging())
        first = Path(self.logger.get_log_file_path() or "")
        self.logger.log({"Cartridge Input": 1.0})
        self.logger.stop_logging()

        self.assertTrue(self.logger.start_logging())
        second = Path(self.logger.get_log_file_path() or "")
        self.logger.log({"Cartridge Input": 2.0})
        self.logger.stop_logging()

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        files = sorted(Path(self._tmpdir.name).glob("pressure_log_*.csv"))
        self.assertEqual(len(files), 2)

    def test_start_while_active_closes_previous_and_opens_new(self) -> None:
        self.assertTrue(self.logger.start_logging())
        first = Path(self.logger.get_log_file_path() or "")
        self.logger.log({"Cartridge Input": 1.0})

        self.assertTrue(self.logger.start_logging())
        second = Path(self.logger.get_log_file_path() or "")
        self.assertNotEqual(first, second)
        self.logger.stop_logging()

        with first.open(newline="") as handle:
            first_rows = list(csv.reader(handle))
        self.assertEqual(len(first_rows), 2)


try:
    from PyQt6.QtWidgets import QApplication  # noqa: F401
except Exception:  # pragma: no cover - depends on host Qt install
    QApplication = None  # type: ignore[misc, assignment]


@unittest.skipIf(QApplication is None, "PyQt6 unavailable on this host")
class PressureServiceTabLoggingToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_toggle_flips_state_and_invokes_callback(self) -> None:
        from gui import PressureServiceTab

        tab = PressureServiceTab()
        calls: list[bool] = []
        tab.on_pressure_csv_logging_toggle_callback = calls.append

        self.assertFalse(tab.pressure_csv_logging_enabled)
        self.assertEqual(tab.pressure_csv_logging_button.text(), "Logging OFF")

        tab.pressure_csv_logging_button.click()
        self.assertTrue(tab.pressure_csv_logging_enabled)
        self.assertEqual(tab.pressure_csv_logging_button.text(), "Logging ON")
        self.assertEqual(calls, [True])

        tab.pressure_csv_logging_button.click()
        self.assertFalse(tab.pressure_csv_logging_enabled)
        self.assertEqual(tab.pressure_csv_logging_button.text(), "Logging OFF")
        self.assertEqual(calls, [True, False])

    def test_set_pressure_csv_logging_does_not_emit_callback(self) -> None:
        from gui import PressureServiceTab

        tab = PressureServiceTab()
        calls: list[bool] = []
        tab.on_pressure_csv_logging_toggle_callback = calls.append

        tab.set_pressure_csv_logging(True)
        self.assertTrue(tab.pressure_csv_logging_enabled)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
