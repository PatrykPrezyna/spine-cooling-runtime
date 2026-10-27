"""SessionRecorder opens the three session CSVs under one stamp."""

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

from session_recorder import SessionRecorder  # noqa: E402


class _PressureReader:
    is_initialized = True

    def read_pressures(self) -> dict:
        return {}


class SessionRecorderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = {
            "logging": {
                "directory": self._tmpdir.name,
                "usb": {"enabled": False},
            },
            "thermistor_sensors": {"labels": {0: "CSF"}},
            "pressure_sensors": {
                "enabled": True,
                "channels": [0],
                "labels": {0: "Cartridge Input"},
            },
        }
        self.session_start = datetime(2026, 8, 19, 12, 58, 0)
        self.recorder = SessionRecorder(
            self.config,
            self.session_start,
            simulation=True,
        )

    def tearDown(self) -> None:
        self.recorder.stop()
        self._tmpdir.cleanup()

    def test_one_stamp_and_one_sensor_row(self) -> None:
        self.recorder.start_status_log()
        self.assertTrue(self.recorder.start_sensor_log())
        self.recorder.record_sensors(
            {},
            {"CSF": 36.5},
            peristaltic_pump_set_speed_rpm=10,
            set_temperature_c=32.0,
            compressor_cooling=1,
            pressures={"Cartridge Input": 1.25},
            flow_sensor_ml_per_min=None,
        )
        self.recorder.start_pressure_capture(_PressureReader(), lambda: 0)
        self.recorder.start_usb_mirror()
        self.recorder.stop()

        folder = Path(self._tmpdir.name)
        names = sorted(path.name for path in folder.glob("*.csv"))
        self.assertEqual(
            names,
            [
                "20260819_125800_pressure_100Hz.csv",
                "20260819_125800_sensors.csv",
                "20260819_125800_status_and_errors.csv",
            ],
        )

        with (folder / "20260819_125800_sensors.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["csf_c"], "36.500")
        self.assertEqual(rows[0]["set_temperature_c"], "32.000")
        self.assertEqual(rows[0]["cartridge_input_bar"], "1.25")
