"""Unit tests for compressor plate-average control temperature."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compressor_control import (  # noqa: E402
    average_temperature_c,
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


if __name__ == "__main__":
    unittest.main()
