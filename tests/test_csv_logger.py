"""Tests for CSV logging including pressure columns at the 10 Hz tick rate."""

from __future__ import annotations

import csv
import sys
import tempfile
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from csv_logger import CSVLogger  # noqa: E402


_CONFIG = {
    "logging": {
        "directory": "unused",
        "sensors_filename_format": "%Y%m%d_%H%M%S_sensors.csv",
    },
    "pump_flow_ml_per_min_per_rpm": 0.5862,
    "thermocouples": {
        "enabled": True,
        "channels": [1, 2],
        "labels": {1: "CSF", 2: "Heat Ex"},
    },
    "pressure_sensors": {
        "enabled": True,
        "sample_rate_hz": 10,
        "channels": [0, 1, 2, 3],
        "labels": {
            0: "Cartridge Input",
            1: "Cartridge Output",
            2: "Pump Input",
            3: "Pump Output",
        },
    },
}


class CsvPressureLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.config = dict(_CONFIG)
        self.config["logging"] = {
            **_CONFIG["logging"],
            "directory": self._tmpdir.name,
        }
        self.logger = CSVLogger(self.config)

    def tearDown(self) -> None:
        if self.logger.is_logging:
            self.logger.stop_logging()
        self._tmpdir.cleanup()

    def test_header_includes_pressure_bar_columns(self) -> None:
        self.assertIn("cartridge_input_bar", self.logger.header)
        self.assertIn("cartridge_output_bar", self.logger.header)
        self.assertIn("pump_input_bar", self.logger.header)
        self.assertIn("pump_output_bar", self.logger.header)
        # Existing columns still present.
        self.assertIn("csf_c", self.logger.header)
        self.assertIn("compressor_cooling", self.logger.header)

    def test_filename_uses_session_stamp_suffix(self) -> None:
        from datetime import datetime

        logger = CSVLogger(self.config, session_start=datetime(2026, 8, 19, 12, 58, 0))
        self.assertTrue(logger.start_logging())
        name = Path(logger.get_log_file_path() or "").name
        logger.stop_logging()
        self.assertEqual(name, "20260819_125800_sensors.csv")

    def test_log_writes_pressure_values_two_decimals(self) -> None:
        self.assertTrue(self.logger.start_logging())
        self.logger.log(
            sensor_states={},
            temperatures={"CSF": 37.0, "Heat Ex": 22.5},
            peristaltic_pump_set_speed_rpm=60,
            set_temperature_c=33.0,
            compressor_cooling=1,
            pressures={
                "Cartridge Input": -11.5,
                "Cartridge Output": 75.0,
                "Pump Input": 12.345,
                "Pump Output": float("nan"),
            },
        )
        self.logger.stop_logging()

        path = Path(self.logger.get_log_file_path())
        self.assertTrue(path.exists())
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 2)  # header + one sample
        header, row = rows[0], rows[1]
        by_name = dict(zip(header, row))
        self.assertEqual(by_name["cartridge_input_bar"], "-11.50")
        self.assertEqual(by_name["cartridge_output_bar"], "75.00")
        self.assertEqual(by_name["pump_input_bar"], "12.35")
        self.assertEqual(by_name["pump_output_bar"], "")  # nan → blank
        self.assertEqual(by_name["csf_c"], "37.000")

    def test_ten_hz_burst_writes_expected_row_count(self) -> None:
        """Simulate ~10 Hz logging for 0.5 s → about 5 rows (+ header)."""
        self.assertTrue(self.logger.start_logging())
        interval_s = 0.1  # 10 Hz
        samples = 5
        t0 = time.perf_counter()
        for i in range(samples):
            self.logger.log(
                sensor_states={},
                temperatures={"CSF": 37.0 + i * 0.01, "Heat Ex": 22.0},
                peristaltic_pump_set_speed_rpm=30,
                set_temperature_c=33.0,
                compressor_cooling=0,
                pressures={
                    "Cartridge Input": 10.0 + i,
                    "Cartridge Output": 11.0 + i,
                    "Pump Input": 12.0 + i,
                    "Pump Output": 13.0 + i,
                },
            )
            time.sleep(interval_s)
        elapsed = time.perf_counter() - t0
        self.logger.stop_logging()

        path = Path(self.logger.get_log_file_path())
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), samples + 1)
        # Timing sanity: 5 × 100 ms should be near 0.5 s (allow slack).
        self.assertGreaterEqual(elapsed, 0.45)
        self.assertLess(elapsed, 1.5)

        header = rows[0]
        last = dict(zip(header, rows[-1]))
        self.assertEqual(last["cartridge_input_bar"], "14.00")
        self.assertEqual(last["pump_output_bar"], "17.00")

    def test_log_without_pressures_still_writes_temp_row(self) -> None:
        self.assertTrue(self.logger.start_logging())
        self.logger.log(
            sensor_states={},
            temperatures={"CSF": 36.5, "Heat Ex": 21.0},
            peristaltic_pump_set_speed_rpm=0,
            set_temperature_c=33.0,
            compressor_cooling=0,
        )
        self.logger.stop_logging()

        path = Path(self.logger.get_log_file_path())
        with path.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        by_name = dict(zip(rows[0], rows[1]))
        self.assertEqual(by_name["csf_c"], "36.500")
        self.assertEqual(by_name["cartridge_input_bar"], "")


if __name__ == "__main__":
    unittest.main()
