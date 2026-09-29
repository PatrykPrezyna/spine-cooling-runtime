"""Unit tests for compressor plate-average control temperature."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compressor_control import (  # noqa: E402
    CompressorRestartDelay,
    average_temperature_c,
    commanded_compressor_on,
    compressor_overlay_spans,
    heat_ex_labels_from_config,
)


class CompressorControlTests(unittest.TestCase):
    def test_labels_prefer_heat_ex_labels_list(self) -> None:
        labels = heat_ex_labels_from_config(
            {
                "heat_ex_label": "Heat Ex",
                "heat_ex_labels": ["Plate 1", "Plate 2"],
            }
        )
        self.assertEqual(labels, ["Plate 1", "Plate 2"])

    def test_labels_fall_back_to_single_heat_ex_label(self) -> None:
        self.assertEqual(
            heat_ex_labels_from_config({"heat_ex_label": "Plate 1"}),
            ["Plate 1"],
        )

    def test_labels_default_when_missing(self) -> None:
        self.assertEqual(heat_ex_labels_from_config({}), ["Heat Ex"])
        self.assertEqual(heat_ex_labels_from_config(None), ["Heat Ex"])

    def test_average_of_plate_1_and_plate_2(self) -> None:
        temps = {"Plate 1": -8.0, "Plate 2": -10.0, "Tip": 36.0}
        self.assertEqual(
            average_temperature_c(temps, ["Plate 1", "Plate 2"]),
            -9.0,
        )

    def test_average_requires_every_probe(self) -> None:
        self.assertIsNone(
            average_temperature_c({"Plate 1": -8.0}, ["Plate 1", "Plate 2"])
        )
        self.assertIsNone(
            average_temperature_c({"Plate 1": -8.0, "Plate 2": None}, ["Plate 1", "Plate 2"])
        )

    def test_average_rejects_non_numeric(self) -> None:
        self.assertIsNone(
            average_temperature_c(
                {"Plate 1": -8.0, "Plate 2": "fault"},
                ["Plate 1", "Plate 2"],
            )
        )


class CompressorRestartDelayTests(unittest.TestCase):
    def test_first_on_is_immediate(self) -> None:
        delay = CompressorRestartDelay(60.0)
        self.assertEqual(delay.push(0.0, True), [(0.0, 1.0)])

    def test_on_after_off_waits_60s(self) -> None:
        delay = CompressorRestartDelay(60.0)
        delay.push(0.0, True)
        self.assertEqual(delay.push(10.0, False), [(10.0, 0.0)])
        self.assertEqual(delay.push(20.0, True), [(20.0, 0.0)])
        # Still commanded on at 80 s: the real start is 60 s after the off.
        self.assertEqual(delay.push(80.0, True), [(70.0, 1.0), (80.0, 1.0)])

    def test_command_that_drops_during_the_wait_does_not_start(self) -> None:
        delay = CompressorRestartDelay(60.0)
        delay.push(0.0, True)
        delay.push(10.0, False)
        delay.push(20.0, True)
        self.assertEqual(delay.push(40.0, False), [(40.0, 0.0)])
        self.assertFalse(delay.physical)
        # The wait already elapsed while the command was off, so the next on is immediate.
        self.assertEqual(delay.push(80.0, True), [(80.0, 1.0)])

    def test_missing_reading_is_ignored(self) -> None:
        self.assertIsNone(commanded_compressor_on(None))
        self.assertIsNone(commanded_compressor_on(float("nan")))
        delay = CompressorRestartDelay(60.0)
        self.assertEqual(delay.push(0.0, None), [])

    def test_overlay_spans_clip_to_the_window(self) -> None:
        trace = [(0.0, 0.0), (10.0, 1.0), (40.0, 0.0), (70.0, 1.0)]
        spans, switches = compressor_overlay_spans(trace, 5.0, 80.0)
        self.assertEqual(spans, [(10.0, 40.0), (70.0, 80.0)])
        self.assertEqual(switches, [(10.0, True), (40.0, False), (70.0, True)])


if __name__ == "__main__":
    unittest.main()
