"""End-to-end tests for the pressure measuring chain.

Chain under test:
  ADS1115 differential voltage (V)
    → millivolts (V * 1000)
    → linear mV → bar calibration
    → labeled dict from reader
    → UI text \"{name}: {value:.2f} bar\"
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ads1115_pressure_reader import (  # noqa: E402
    ADS1115PressureReader,
    mv_to_bar,
    PSI_TO_BAR,
    _BAR_HI,
    _BAR_LO,
    _MV_HI,
    _MV_LO,
)


# Calibration anchors (must match example + config.yaml).
MV_LO, PSI_LO = -14.858, -11.5
MV_HI, PSI_HI = 96.9, 75.0
BAR_LO, BAR_HI = PSI_LO * PSI_TO_BAR, PSI_HI * PSI_TO_BAR

_PRESSURE_CONFIG = {
    "pressure_sensors": {
        "enabled": True,
        "i2c_addresses": [74, 75],
        "gain": 16,
        "channels": [0, 1, 2, 3],
        "calibration": {
            "mv_lo": MV_LO,
            "bar_lo": BAR_LO,
            "mv_hi": MV_HI,
            "bar_hi": BAR_HI,
        },
        "labels": {
            0: "Cartridge Input",
            1: "Cartridge Output",
            2: "Pump Input",
            3: "Pump Output",
        },
    }
}


def _fake_analog(voltage_v: float) -> SimpleNamespace:
    """Stub for Adafruit AnalogIn (exposes .voltage in volts)."""
    return SimpleNamespace(voltage=voltage_v)


def _reader_with_voltages(voltages_by_channel: dict[int, float]) -> ADS1115PressureReader:
    """Build a reader that skips real I2C and injects known voltages."""
    reader = ADS1115PressureReader(_PRESSURE_CONFIG)
    # Hardware init fails off-Pi; wire the post-conversion path ourselves.
    reader._analog_inputs = {
        ch: _fake_analog(v) for ch, v in voltages_by_channel.items()
    }
    reader.is_initialized = True
    reader.last_error = None
    return reader


class MvToBarConversionTests(unittest.TestCase):
    def test_module_defaults_match_calibration_anchors(self) -> None:
        self.assertEqual(_MV_LO, MV_LO)
        self.assertAlmostEqual(_BAR_LO, BAR_LO, places=9)
        self.assertEqual(_MV_HI, MV_HI)
        self.assertAlmostEqual(_BAR_HI, BAR_HI, places=9)

    def test_low_calibration_point(self) -> None:
        self.assertAlmostEqual(mv_to_bar(MV_LO), BAR_LO, places=6)

    def test_high_calibration_point(self) -> None:
        self.assertAlmostEqual(mv_to_bar(MV_HI), BAR_HI, places=6)

    def test_midpoint_is_linear(self) -> None:
        mid_mv = (MV_LO + MV_HI) / 2.0
        mid_bar = (BAR_LO + BAR_HI) / 2.0
        self.assertAlmostEqual(mv_to_bar(mid_mv), mid_bar, places=6)

    def test_zero_mv(self) -> None:
        # Known point on the line through the two anchors.
        expected = BAR_LO + (0.0 - MV_LO) * (BAR_HI - BAR_LO) / (MV_HI - MV_LO)
        self.assertAlmostEqual(mv_to_bar(0.0), expected, places=6)

    def test_example_script_formula_matches(self) -> None:
        # Replicate simple_examples/ads1115_pressure.py inline.
        for mv in (MV_LO, 0.0, 41.021, MV_HI, 50.0):
            example = BAR_LO + (mv - MV_LO) * (BAR_HI - BAR_LO) / (MV_HI - MV_LO)
            self.assertAlmostEqual(mv_to_bar(mv), example, places=9)


class ConfigCalibrationTests(unittest.TestCase):
    def test_config_yaml_matches_conversion_defaults(self) -> None:
        import yaml

        config_path = PROJECT_ROOT / "config.yaml"
        with config_path.open(encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        cal = config["pressure_sensors"]["calibration"]
        self.assertAlmostEqual(float(cal["mv_lo"]), MV_LO)
        self.assertAlmostEqual(float(cal["bar_lo"]), BAR_LO, places=6)
        self.assertAlmostEqual(float(cal["mv_hi"]), MV_HI)
        self.assertAlmostEqual(float(cal["bar_hi"]), BAR_HI, places=6)

        labels_map = config["pressure_sensors"]["labels"]
        labels = [labels_map[i] for i in range(4)]
        self.assertEqual(
            labels,
            [
                "Pump In",
                "Pump Out",
                "Catheter In",
                "Catheter Out",
            ],
        )


class ReaderMeasuringChainTests(unittest.TestCase):
    def test_voltage_to_bar_at_calibration_anchors(self) -> None:
        # AnalogIn.voltage is volts; reader multiplies by 1000 → mV.
        reader = _reader_with_voltages(
            {
                0: MV_LO / 1000.0,  # Cartridge Input → -11.5 psi → bar
                1: MV_HI / 1000.0,  # Cartridge Output → 75.0 psi → bar
                2: 0.0,  # Pump Input
                3: ((MV_LO + MV_HI) / 2.0) / 1000.0,  # Pump Output midpoint
            }
        )

        pressures = reader.read_pressures()
        self.assertAlmostEqual(pressures["Cartridge Input"], BAR_LO, places=5)
        self.assertAlmostEqual(pressures["Cartridge Output"], BAR_HI, places=5)
        expected_zero = mv_to_bar(0.0)
        self.assertAlmostEqual(pressures["Pump Input"], expected_zero, places=5)
        self.assertAlmostEqual(
            pressures["Pump Output"], (BAR_LO + BAR_HI) / 2.0, places=5
        )

    def test_all_four_sensor_labels_present(self) -> None:
        reader = _reader_with_voltages(
            {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.04}
        )
        pressures = reader.read_pressures()
        self.assertEqual(
            set(pressures),
            {
                "Cartridge Input",
                "Cartridge Output",
                "Pump Input",
                "Pump Output",
            },
        )

    def test_uses_config_calibration_not_hardcoded_only(self) -> None:
        config = {
            "pressure_sensors": {
                "enabled": True,
                "channels": [0],
                "calibration": {
                    "mv_lo": 0.0,
                    "bar_lo": 0.0,
                    "mv_hi": 100.0,
                    "bar_hi": 50.0,
                },
                "labels": {0: "Cartridge Input"},
            }
        }
        reader = ADS1115PressureReader(config)
        reader._analog_inputs = {0: _fake_analog(0.05)}  # 50 mV → 25 bar
        reader.is_initialized = True

        pressures = reader.read_pressures()
        self.assertAlmostEqual(pressures["Cartridge Input"], 25.0, places=6)

    def test_flat_labels_and_channel_configs_override(self) -> None:
        config = {
            "pressure_sensors": {
                "enabled": True,
                "channels": [0, 1],
                "labels": {0: "From Labels", 1: "Also Labels"},
                "channel_configs": {1: {"label": "From Channel Config"}},
            }
        }
        reader = ADS1115PressureReader(config)
        reader._analog_inputs = {0: _fake_analog(0.0), 1: _fake_analog(0.0)}
        reader.is_initialized = True

        pressures = reader.read_pressures()
        self.assertIn("From Labels", pressures)
        self.assertIn("From Channel Config", pressures)
        self.assertNotIn("Also Labels", pressures)

    def test_display_roundtrip_two_decimals(self) -> None:
        """Values the UI will show must match conversion to 2 decimal places."""
        cases = [
            (MV_LO / 1000.0, round(BAR_LO, 2)),
            (MV_HI / 1000.0, round(BAR_HI, 2)),
            (0.0, round(mv_to_bar(0.0), 2)),
            (0.05, round(mv_to_bar(50.0), 2)),  # 50 mV
        ]
        for voltage_v, expected_display in cases:
            with self.subTest(voltage_v=voltage_v):
                reader = _reader_with_voltages({0: voltage_v})
                bar = reader.read_pressures()["Cartridge Input"]
                self.assertAlmostEqual(round(bar, 2), expected_display, places=2)


class UiPressureFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc

        cls._app = QApplication.instance() or QApplication([])

    def test_pressure_service_tab_shows_bar_and_pump_speed(self) -> None:
        from gui import PressureServiceTab

        tab = PressureServiceTab(
            pressure_sensor_names=[
                "Cartridge Input",
                "Cartridge Output",
                "Pump Input",
                "Pump Output",
            ],
        )
        reader = _reader_with_voltages(
            {
                0: MV_LO / 1000.0,
                1: MV_HI / 1000.0,
                2: 0.0,
                3: ((MV_LO + MV_HI) / 2.0) / 1000.0,
            }
        )
        tab.update_pressures(reader.read_pressures())
        tab.update_pump_speed(pump_speed_rpm=30)
        tab.push_latest_sample()

        self.assertEqual(
            tab.checkboxes["Cartridge Input"].text(),
            f"Cartridge Input  {BAR_LO:.2f} bar",
        )
        self.assertEqual(
            tab.checkboxes["Cartridge Output"].text(),
            f"Cartridge Output  {BAR_HI:.2f} bar",
        )
        flow_series = PressureServiceTab.PUMP_FLOW_SERIES
        self.assertIn(flow_series, tab.checkboxes)
        self.assertIn("ml/min", tab.checkboxes[flow_series].text())
        self.assertGreater(tab._flow_ml_per_min, 0.0)
        self.assertEqual(len(tab.graph_widget._history), 1)
        latest = tab.graph_widget._history[-1][1]
        self.assertAlmostEqual(latest["Cartridge Input"], BAR_LO, places=2)
        self.assertAlmostEqual(latest[flow_series], tab._flow_ml_per_min, places=2)

    def test_pressure_tab_one_second_average_and_raw_toggle(self) -> None:
        from gui import PressureServiceTab

        tab = PressureServiceTab(pressure_sensor_names=["Pump Out"])
        flow_series = PressureServiceTab.PUMP_FLOW_SERIES
        tab.update_pump_speed(flow_ml_per_min=10.0)
        tab.update_pressures({"Pump Out": 10.0})
        tab.push_latest_sample(timestamp=1.0)
        tab.update_pump_speed(flow_ml_per_min=50.0)
        tab.update_pressures({"Pump Out": 20.0})
        tab.push_latest_sample(timestamp=1.5)

        self.assertEqual(tab._display_mode, PressureServiceTab.MODE_AVG)
        self.assertTrue(tab._avg_button.isChecked())
        latest = tab.graph_widget._history[-1][1]
        self.assertAlmostEqual(latest["Pump Out"], 15.0, places=4)
        self.assertAlmostEqual(latest[flow_series], 50.0, places=4)
        self.assertEqual(tab.checkboxes["Pump Out"].text(), "Pump Out  15.00 bar")

        tab._on_smoothing_clicked(PressureServiceTab.MODE_MAX)
        self.assertEqual(tab._display_mode, PressureServiceTab.MODE_MAX)
        self.assertTrue(tab._max_button.isChecked())
        self.assertFalse(tab._avg_button.isChecked())
        max_history = list(tab.graph_widget._history)
        self.assertEqual(len(max_history), 2)
        self.assertAlmostEqual(max_history[0][1]["Pump Out"], 10.0, places=4)
        self.assertAlmostEqual(max_history[1][1]["Pump Out"], 20.0, places=4)
        self.assertEqual(tab.checkboxes["Pump Out"].text(), "Pump Out  20.00 bar")

        tab._on_smoothing_clicked(PressureServiceTab.MODE_RAW)
        self.assertEqual(tab._display_mode, PressureServiceTab.MODE_RAW)
        self.assertTrue(tab._raw_button.isChecked())
        self.assertFalse(tab._avg_button.isChecked())
        self.assertFalse(tab._max_button.isChecked())
        raw_history = list(tab.graph_widget._history)
        self.assertEqual(len(raw_history), 2)
        self.assertAlmostEqual(raw_history[0][1]["Pump Out"], 10.0, places=4)
        self.assertAlmostEqual(raw_history[1][1]["Pump Out"], 20.0, places=4)
        self.assertEqual(tab.checkboxes["Pump Out"].text(), "Pump Out  20.00 bar")

        tab._on_smoothing_clicked(PressureServiceTab.MODE_AVG)
        tab.update_pressures({"Pump Out": 40.0})
        tab.push_latest_sample(timestamp=3.0)
        latest = tab.graph_widget._history[-1][1]
        # 1.0 and 1.5 are older than the 1 s window ending at 3.0.
        self.assertAlmostEqual(latest["Pump Out"], 40.0, places=4)

    def test_pressure_tab_one_second_max_holds_peak_in_window(self) -> None:
        from gui import PressureServiceTab

        tab = PressureServiceTab(pressure_sensor_names=["Pump Out"])
        tab._on_smoothing_clicked(PressureServiceTab.MODE_MAX)
        tab.update_pressures({"Pump Out": 10.0})
        tab.push_latest_sample(timestamp=1.0)
        tab.update_pressures({"Pump Out": 30.0})
        tab.push_latest_sample(timestamp=1.4)
        tab.update_pressures({"Pump Out": 12.0})
        tab.push_latest_sample(timestamp=1.8)

        latest = tab.graph_widget._history[-1][1]
        self.assertAlmostEqual(latest["Pump Out"], 30.0, places=4)
        self.assertEqual(tab.checkboxes["Pump Out"].text(), "Pump Out  30.00 bar")

        tab.update_pressures({"Pump Out": 8.0})
        tab.push_latest_sample(timestamp=2.5)
        latest = tab.graph_widget._history[-1][1]
        # Peak at 1.4 has aged out of the 1 s window ending at 2.5.
        self.assertAlmostEqual(latest["Pump Out"], 12.0, places=4)


if __name__ == "__main__":
    unittest.main()
