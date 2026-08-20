"""Tests for session CSV discovery and loading."""

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

from session_logs import (  # noqa: E402
    csv_slug_to_label,
    discover_session_files,
    load_session,
    parse_timestamp,
    series_stats,
)


def _write_csv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


class SessionLogsTests(unittest.TestCase):
    def test_slug_to_label_keeps_known_typos(self) -> None:
        self.assertEqual(csv_slug_to_label("cartrige_out"), "Cartrige Out")
        self.assertEqual(csv_slug_to_label("pump_in"), "Pump In")
        self.assertEqual(csv_slug_to_label("tip"), "Tip")

    def test_parse_iso_timestamp(self) -> None:
        ts = parse_timestamp("2026-08-19T15:08:03.426090")
        self.assertIsNotNone(ts)
        self.assertEqual(
            datetime.fromtimestamp(ts).isoformat(timespec="seconds"),
            datetime.fromisoformat("2026-08-19T15:08:03").isoformat(timespec="seconds"),
        )

    def test_discover_and_load_session_folder(self) -> None:
        stamp = "20260819_150802"
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            start = datetime(2026, 8, 19, 15, 8, 3)
            sensors_header = [
                "timestamp",
                "tip_c",
                "cartrige_out_c",
                "catheter_in_c",
                "catheter_out_c",
                "cartrige_in_c",
                "set_temperature_c",
                "peristaltic_pump_set_speed_rpm",
                "pump_flow_ml_per_s",
                "compressor_cooling",
                "pump_in_bar",
            ]
            _write_csv(
                folder / f"{stamp}_sensors.csv",
                sensors_header,
                [
                    [
                        start.isoformat(),
                        36.1,
                        18.0,
                        21.0,
                        24.0,
                        25.0,
                        32.0,
                        102.0,
                        1.0,
                        1,
                        0.20,
                    ],
                    [
                        datetime(2026, 8, 19, 15, 10, 3).isoformat(),
                        35.0,
                        10.0,
                        20.0,
                        23.0,
                        22.0,
                        32.0,
                        102.0,
                        1.0,
                        1,
                        0.25,
                    ],
                ],
            )
            _write_csv(
                folder / f"{stamp}_pressure_100Hz.csv",
                [
                    "timestamp",
                    "peristaltic_pump_set_speed_rpm",
                    "pump_in_bar",
                    "pump_out_bar",
                ],
                [
                    [start.isoformat(), 102.0, 0.20, 0.30],
                    [datetime(2026, 8, 19, 15, 8, 4).isoformat(), 102.0, 0.21, 0.31],
                ],
            )
            _write_csv(
                folder / f"{stamp}_status_and_errors.csv",
                [
                    "timestamp",
                    "event",
                    "severity",
                    "previous_state",
                    "state",
                    "fault_code",
                    "message",
                ],
                [
                    [start.isoformat(), "session_start", "info", "", "", "", "Logging started"],
                    [
                        datetime(2026, 8, 19, 15, 8, 12).isoformat(),
                        "state_change",
                        "info",
                        "Ready",
                        "Cooling",
                        "",
                        "All conditions met",
                    ],
                ],
            )

            discovered = discover_session_files(folder / f"{stamp}_sensors.csv")
            self.assertEqual(discovered[0], stamp)
            session = load_session(folder)
            self.assertEqual(session.stamp, stamp)
            self.assertEqual(session.last_state, "Cooling")
            self.assertIn("Tip", session.temperature_names)
            self.assertIn("Cartrige Out", session.temperature_names)
            self.assertEqual(session.pressure_names, ["Pump In", "Pump Out"])
            self.assertEqual(len(session.temperature_samples), 2)
            self.assertEqual(len(session.pressure_samples), 2)
            self.assertAlmostEqual(session.duration_s, 120.0, places=0)
            self.assertAlmostEqual(session.set_temperature_c, 32.0)
            self.assertEqual(len(session.events), 2)
            self.assertIn("Catheter", session.power_samples[0][1])
            self.assertIn("Flow", session.pressure_samples[0][1])
            self.assertAlmostEqual(session.pressure_samples[0][1]["Flow"], 102.0 * 0.5862, places=2)
            tip = series_stats(session.temperature_samples, "Tip")
            self.assertAlmostEqual(tip["min"], 35.0)
            self.assertAlmostEqual(tip["max"], 36.1)

    def test_load_evaluation_sample_when_present(self) -> None:
        sample = PROJECT_ROOT / "evaluation tool" / "20260819_150802_sensors.csv"
        if not sample.is_file():
            self.skipTest("evaluation sample CSVs are not in the workspace")
        session = load_session(sample)
        self.assertEqual(session.stamp, "20260819_150802")
        self.assertGreater(len(session.temperature_samples), 100)
        self.assertGreater(len(session.pressure_samples), 100)
        self.assertEqual(session.last_state, "Cooling")
        self.assertIn("Probe 2", session.temperature_names)


if __name__ == "__main__":
    unittest.main()
