"""Unit tests for two-point temperature calibration helpers."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from temperature_calibration import (  # noqa: E402
    IDENTITY_CALIBRATION,
    apply_linear_calibration,
    build_two_point_calibration,
)


class TwoPointCalibrationTests(unittest.TestCase):
    def test_identity_when_points_are_perfect(self) -> None:
        (gain, offset), error = build_two_point_calibration(0.0, 100.0)
        self.assertIsNone(error)
        self.assertAlmostEqual(gain, 1.0)
        self.assertAlmostEqual(offset, 0.0)
        self.assertAlmostEqual(apply_linear_calibration(37.5, gain, offset), 37.5)

    def test_corrects_offset_and_gain(self) -> None:
        # Sensor reads low by -2C at ice point and +1C at boiling point.
        (gain, offset), error = build_two_point_calibration(-2.0, 101.0)
        self.assertIsNone(error)
        self.assertAlmostEqual(apply_linear_calibration(-2.0, gain, offset), 0.0, places=6)
        self.assertAlmostEqual(apply_linear_calibration(101.0, gain, offset), 100.0, places=6)

    def test_rejects_missing_points(self) -> None:
        calibration, error = build_two_point_calibration(None, 100.0)
        self.assertEqual(calibration, IDENTITY_CALIBRATION)
        self.assertIn("missing", error or "")

    def test_rejects_non_numeric_points(self) -> None:
        calibration, error = build_two_point_calibration("bad", 100.0)
        self.assertEqual(calibration, IDENTITY_CALIBRATION)
        self.assertIn("numeric", error or "")

    def test_rejects_zero_span(self) -> None:
        calibration, error = build_two_point_calibration(10.0, 10.0)
        self.assertEqual(calibration, IDENTITY_CALIBRATION)
        self.assertIn("must differ", error or "")


if __name__ == "__main__":
    unittest.main()
