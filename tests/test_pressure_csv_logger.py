"""Tests for always-on high-rate pressure CSV capture."""

from __future__ import annotations

import csv
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pressure_csv_logger import PressureCSVLogger, PressureCaptureLoop  # noqa: E402


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
        "capture_rate_hz": 100,
        "channels": [0, 1, 2, 3],
        "labels": {
            0: "Cartridge Input",
            1: "Cartridge Output",
            2: "Pump Input",
            3: "Pump Output",
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

    def test_header_includes_pump_set_speed(self) -> None:
        self.assertEqual(
            self.logger.header,
            [
                "timestamp",
                "peristaltic_pump_set_speed_rpm",
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
            },
            peristaltic_pump_set_speed_rpm=60,
        )
        self.logger.stop_logging()

        with path.open(newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0], self.logger.header)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            rows[1][1:],
            ["60.00", "-11.50", "75.00", "12.34", "45.67"],
        )

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

    def test_capture_rate_hz_defaults_to_100(self) -> None:
        self.assertEqual(self.logger.capture_rate_hz, 100.0)

    def test_runs_are_numbered_within_one_session(self) -> None:
        names = []
        for _ in range(3):
            self.assertTrue(self.logger.start_logging())
            names.append(Path(self.logger.get_log_file_path() or "").name)
            self.logger.stop_logging()

        stamp = self.logger.session_start.strftime("%Y%m%d_%H%M%S")
        self.assertEqual(
            names,
            [
                f"pressure_log_{stamp}_run01.csv",
                f"pressure_log_{stamp}_run02.csv",
                f"pressure_log_{stamp}_run03.csv",
            ],
        )

    def test_filename_uses_session_start(self) -> None:
        session_start = datetime(2026, 8, 17, 16, 30, 45)
        logger = PressureCSVLogger(self.config, session_start=session_start)
        self.assertTrue(logger.start_logging())
        name = Path(logger.get_log_file_path() or "").name
        logger.stop_logging()
        self.assertEqual(name, "pressure_log_20260817_163045_run01.csv")

    def test_session_and_pressure_files_share_one_stamp(self) -> None:
        from csv_logger import CSVLogger

        session_start = datetime(2026, 8, 17, 16, 30, 45)
        config = {
            **self.config,
            "logging": {
                **self.config["logging"],
                "csv_directory": self._tmpdir.name,
                "filename_format": "sensor_log_%Y%m%d_%H%M%S.csv",
            },
        }
        session_logger = CSVLogger(config, session_start=session_start)
        pressure_logger = PressureCSVLogger(config, session_start=session_start)
        self.assertTrue(session_logger.start_logging())
        self.assertTrue(pressure_logger.start_logging())
        session_name = Path(session_logger.get_log_file_path() or "").name
        pressure_name = Path(pressure_logger.get_log_file_path() or "").name
        session_logger.stop_logging()
        pressure_logger.stop_logging()

        stamp = "20260817_163045"
        self.assertEqual(session_name, f"sensor_log_{stamp}.csv")
        self.assertEqual(pressure_name, f"pressure_log_{stamp}_run01.csv")


class PressureCaptureLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = dict(_CONFIG)
        self.config["logging"] = {
            **_CONFIG["logging"],
            "pressure_csv_directory": self._tmpdir.name,
        }
        self.logger = PressureCSVLogger(self.config)
        self.reads = 0

        def _read_pressures() -> dict:
            self.reads += 1
            return {
                "Cartridge Input": float(self.reads),
                "Cartridge Output": 0.0,
                "Pump Input": 0.0,
                "Pump Output": 0.0,
            }

        self.reader = SimpleNamespace(read_pressures=_read_pressures)

    def tearDown(self) -> None:
        if self.logger.is_logging:
            self.logger.stop_logging()
        self._tmpdir.cleanup()

    def test_loop_runs_near_configured_rate(self) -> None:
        self.assertTrue(self.logger.start_logging())
        loop = PressureCaptureLoop(
            self.reader,
            self.logger,
            rate_hz=100.0,
            pump_set_speed_rpm_getter=lambda: 45,
        )
        loop.start()
        time.sleep(0.25)
        loop.stop()
        self.logger.stop_logging()

        # Allow some scheduling jitter; expect roughly 100 Hz over 0.25 s.
        self.assertGreaterEqual(self.reads, 15)
        self.assertLessEqual(self.reads, 40)

        path = Path(self.logger.get_log_file_path() or "")
        with path.open(newline="") as handle:
            rows = list(csv.reader(handle))
        self.assertEqual(rows[0][1], "peristaltic_pump_set_speed_rpm")
        self.assertGreaterEqual(len(rows), 2)
        self.assertEqual(rows[1][1], "45.00")


if __name__ == "__main__":
    unittest.main()
