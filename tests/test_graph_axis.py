"""Graph axis scaling must survive non-finite thermistor readings."""

from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class SnapAxisRangeTests(unittest.TestCase):
    def test_infinite_limits_stay_finite(self) -> None:
        from gui import _axis_tick_values, _snap_axis_range

        y_min, y_max = _snap_axis_range(float("-inf"), float("inf"), 1)
        self.assertTrue(math.isfinite(y_min))
        self.assertTrue(math.isfinite(y_max))
        self.assertLess(y_min, y_max)
        ticks = _axis_tick_values(y_min, y_max, 1)
        self.assertTrue(all(math.isfinite(tick) for tick in ticks))

    def test_finite_limits_still_cover_the_data(self) -> None:
        from gui import _snap_axis_range

        y_min, y_max = _snap_axis_range(20.0, 40.0, 1)
        self.assertLessEqual(y_min, 20.0)
        self.assertGreaterEqual(y_max, 40.0)


class MultiTemperatureGraphRangeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def test_open_probe_does_not_abort_paint(self) -> None:
        from gui import MultiTemperatureGraphWidget

        widget = MultiTemperatureGraphWidget(["CSF 2", "Heat Ex"])
        widget.resize(480, 320)
        widget.use_history_end_as_now = True
        # Bypass normalization: this is the sample shape that used to reach paint.
        widget._history.append(
            (1000.0, {"CSF 2": float("-inf"), "Heat Ex": 22.5})
        )

        y_min, y_max = widget._compute_visible_y_range(
            list(widget._history),
            widget._left_axis_names(),
            widget._default_y_range,
            decimals=1,
        )
        self.assertTrue(math.isfinite(y_min))
        self.assertTrue(math.isfinite(y_max))
        self.assertLessEqual(y_min, 22.5)
        self.assertGreaterEqual(y_max, 22.5)
        widget.grab()

    def test_only_infinite_sample_uses_the_default_range(self) -> None:
        from gui import MultiTemperatureGraphWidget, _snap_axis_range

        widget = MultiTemperatureGraphWidget(["CSF 2"])
        y_min, y_max = widget._compute_visible_y_range(
            [(1000.0, {"CSF 2": float("-inf")})],
            ["CSF 2"],
            widget._default_y_range,
            decimals=1,
        )
        expected = _snap_axis_range(*widget._default_y_range, 1)
        self.assertEqual((y_min, y_max), expected)

    def test_add_sample_stores_infinity_as_missing(self) -> None:
        from gui import MultiTemperatureGraphWidget

        widget = MultiTemperatureGraphWidget(["CSF 2"])
        widget.add_sample({"CSF 2": float("-inf")}, timestamp=1000.0)
        stored = widget._history[-1][1]["CSF 2"]
        self.assertTrue(math.isnan(stored))


if __name__ == "__main__":
    unittest.main()
