"""Temperature graphs must stay pannable for a full session, not one hour."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


class GraphSampleHistoryTests(unittest.TestCase):
    def test_keeps_samples_older_than_one_hour(self) -> None:
        from graph_history import GraphSampleHistory

        history = GraphSampleHistory()
        history.add((0.0, 36.0))
        history.add((2 * 3600.0, 32.0))

        self.assertEqual(history[0], (0.0, 36.0))
        self.assertEqual(history[-1], (2 * 3600.0, 32.0))

    def test_drops_samples_older_than_the_session_window(self) -> None:
        from graph_history import GRAPH_HISTORY_SEC, GraphSampleHistory

        history = GraphSampleHistory()
        history.add((0.0, "old"))
        history.add((GRAPH_HISTORY_SEC + 3600.0, "new"))

        self.assertEqual(list(history), [(GRAPH_HISTORY_SEC + 3600.0, "new")])

    def test_thins_the_tail_and_keeps_the_recent_hour_dense(self) -> None:
        from graph_history import GraphSampleHistory

        history = GraphSampleHistory()
        for second in range(2 * 3600 + 1):
            history.add((float(second), second))

        self.assertEqual(history[0][0], 0.0)
        self.assertEqual(history[-1][0], 7200.0)
        self.assertEqual(len(history._fine), 3601)
        self.assertGreater(len(history._coarse), 700)
        self.assertLess(len(history._coarse), 800)
        self.assertLess(len(history), 7201)
        # Coarse points stay at least one coarse step apart.
        coarse_ts = [ts for ts, _value in history._coarse]
        gaps = [b - a for a, b in zip(coarse_ts, coarse_ts[1:])]
        self.assertTrue(all(gap >= history.coarse_sec for gap in gaps))


class TemperatureGraphHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc
        cls._app = QApplication.instance() or QApplication([])

    def test_expert_graph_pans_past_one_hour(self) -> None:
        from gui import MultiTemperatureGraphWidget

        widget = MultiTemperatureGraphWidget(["CSF"])
        widget.use_history_end_as_now = True
        widget.set_window_minutes(60)
        start = 1_000_000.0
        widget.add_sample({"CSF": 36.5}, timestamp=start)
        widget.add_sample({"CSF": 31.0}, timestamp=start + 3 * 3600.0)

        self.assertEqual(widget._history[0][0], start)
        self.assertGreaterEqual(widget.max_pan_windows(), 2)
        widget.pan_older()
        widget.pan_older()
        widget.pan_older()
        self.assertEqual(widget._x_pan_windows, 3)

    def test_main_graph_keeps_and_enables_back_navigation(self) -> None:
        from gui import MainScreenWidget

        widget = MainScreenWidget(
            show_cartridge=False,
            show_graph=True,
            show_temp_controls=True,
        )
        widget._x_window_minutes = 60
        now = time.monotonic()
        start = now - 2 * 3600.0
        widget.add_temperature_sample(36.5, 22.0, timestamp=start)
        widget.add_temperature_sample(32.0, 20.0, timestamp=now)

        self.assertEqual(widget._temp_history[0][0], start)
        self.assertEqual(widget._temp_history[-1][2], 32.0)
        self.assertTrue(widget.graph_nav_left_button.isEnabled())

    def test_time_window_menu_includes_multi_hour_spans(self) -> None:
        from gui import MultiTemperatureGraphWidget, _format_window_minutes

        widget = MultiTemperatureGraphWidget(["CSF"])
        self.assertIn(2880, widget._x_window_minutes_options)
        self.assertEqual(_format_window_minutes(60), "1 h")
        self.assertEqual(_format_window_minutes(2880), "48 h")
        self.assertEqual(_format_window_minutes(15), "15 min")


if __name__ == "__main__":
    unittest.main()
