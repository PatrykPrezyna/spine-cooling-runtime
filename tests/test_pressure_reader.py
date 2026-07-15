"""End-to-end tests for the pressure measuring chain.

Chain under test:
  ADS1115 differential voltage (V)
    → millivolts (V * 1000)
    → linear mV → psi calibration
    → labeled dict from reader
    → UI text \"{name}: {value:.2f} psi\"
"""

from __future__ import annotations

import math
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
    mv_to_psi,
    _MV_HI,
    _MV_LO,
    _PSI_HI,
    _PSI_LO,
)


# Calibration anchors (must match example + config.yaml).
MV_LO, PSI_LO = -14.858, -11.5
MV_HI, PSI_HI = 96.9, 75.0

_PRESSURE_CONFIG = {
    "pressure_sensors": {
        "enabled": True,
        "i2c_addresses": [74, 75],
        "gain": 16,
        "channels": [0, 1, 2, 3],
        "calibration": {
            "mv_lo": MV_LO,
            "psi_lo": PSI_LO,
            "mv_hi": MV_HI,
            "psi_hi": PSI_HI,
        },
        "channel_configs": {
            0: {"label": "Cartridge Input"},
            1: {"label": "Cartridge Output"},
            2: {"label": "Pump Input"},
            3: {"label": "Pump Output"},
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


class MvToPsiConversionTests(unittest.TestCase):
    def test_module_defaults_match_calibration_anchors(self) -> None:
        self.assertEqual(_MV_LO, MV_LO)
        self.assertEqual(_PSI_LO, PSI_LO)
        self.assertEqual(_MV_HI, MV_HI)
        self.assertEqual(_PSI_HI, PSI_HI)

    def test_low_calibration_point(self) -> None:
        self.assertAlmostEqual(mv_to_psi(MV_LO), PSI_LO, places=6)

    def test_high_calibration_point(self) -> None:
        self.assertAlmostEqual(mv_to_psi(MV_HI), PSI_HI, places=6)

    def test_midpoint_is_linear(self) -> None:
        mid_mv = (MV_LO + MV_HI) / 2.0
        mid_psi = (PSI_LO + PSI_HI) / 2.0
        self.assertAlmostEqual(mv_to_psi(mid_mv), mid_psi, places=6)

    def test_zero_mv(self) -> None:
        # Known point on the line through the two anchors.
        expected = PSI_LO + (0.0 - MV_LO) * (PSI_HI - PSI_LO) / (MV_HI - MV_LO)
        self.assertAlmostEqual(mv_to_psi(0.0), expected, places=6)

    def test_example_script_formula_matches(self) -> None:
        # Replicate simple_examples/ads1115_pressure.py inline.
        for mv in (MV_LO, 0.0, 41.021, MV_HI, 50.0):
            example = PSI_LO + (mv - MV_LO) * (PSI_HI - PSI_LO) / (MV_HI - MV_LO)
            self.assertAlmostEqual(mv_to_psi(mv), example, places=9)


class ConfigCalibrationTests(unittest.TestCase):
    def test_config_yaml_matches_conversion_defaults(self) -> None:
        import yaml

        config_path = PROJECT_ROOT / "config.yaml"
        with config_path.open(encoding="utf-8") as fh:
            config = yaml.safe_load(fh)

        cal = config["pressure_sensors"]["calibration"]
        self.assertAlmostEqual(float(cal["mv_lo"]), MV_LO)
        self.assertAlmostEqual(float(cal["psi_lo"]), PSI_LO)
        self.assertAlmostEqual(float(cal["mv_hi"]), MV_HI)
        self.assertAlmostEqual(float(cal["psi_hi"]), PSI_HI)

        labels = [
            config["pressure_sensors"]["channel_configs"][i]["label"] for i in range(4)
        ]
        self.assertEqual(
            labels,
            [
                "Cartridge Input",
                "Cartridge Output",
                "Pump Input",
                "Pump Output",
            ],
        )


class ReaderMeasuringChainTests(unittest.TestCase):
    def test_voltage_to_psi_at_calibration_anchors(self) -> None:
        # AnalogIn.voltage is volts; reader multiplies by 1000 → mV.
        reader = _reader_with_voltages(
            {
                0: MV_LO / 1000.0,  # Cartridge Input → -11.5 psi
                1: MV_HI / 1000.0,  # Cartridge Output → 75.0 psi
                2: 0.0,  # Pump Input
                3: ((MV_LO + MV_HI) / 2.0) / 1000.0,  # Pump Output midpoint
            }
        )

        pressures = reader.read_pressures()
        self.assertAlmostEqual(pressures["Cartridge Input"], PSI_LO, places=5)
        self.assertAlmostEqual(pressures["Cartridge Output"], PSI_HI, places=5)
        expected_zero = mv_to_psi(0.0)
        self.assertAlmostEqual(pressures["Pump Input"], expected_zero, places=5)
        self.assertAlmostEqual(
            pressures["Pump Output"], (PSI_LO + PSI_HI) / 2.0, places=5
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
                    "psi_lo": 0.0,
                    "mv_hi": 100.0,
                    "psi_hi": 50.0,
                },
                "channel_configs": {0: {"label": "Cartridge Input"}},
            }
        }
        reader = ADS1115PressureReader(config)
        reader._analog_inputs = {0: _fake_analog(0.05)}  # 50 mV → 25 psi
        reader.is_initialized = True

        pressures = reader.read_pressures()
        self.assertAlmostEqual(pressures["Cartridge Input"], 25.0, places=6)

    def test_display_roundtrip_two_decimals(self) -> None:
        """Values the UI will show must match conversion to 2 decimal places."""
        cases = [
            (MV_LO / 1000.0, -11.50),
            (MV_HI / 1000.0, 75.00),
            (0.0, round(mv_to_psi(0.0), 2)),
            (0.05, round(mv_to_psi(50.0), 2)),  # 50 mV
        ]
        for voltage_v, expected_display in cases:
            with self.subTest(voltage_v=voltage_v):
                reader = _reader_with_voltages({0: voltage_v})
                psi = reader.read_pressures()["Cartridge Input"]
                self.assertAlmostEqual(round(psi, 2), expected_display, places=2)


class UiPressureFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication

        cls._app = QApplication.instance() or QApplication([])

    def test_service2_tab_shows_psi_with_two_decimals(self) -> None:
        from gui import Service2Tab

        tab = Service2Tab(
            sensor_names=["CSF"],
            pressure_sensor_names=[
                "Cartridge Input",
                "Cartridge Output",
                "Pump Input",
                "Pump Output",
            ],
        )

        # Drive the same path main.py uses after a reader poll.
        voltages = {
            0: MV_LO / 1000.0,
            1: MV_HI / 1000.0,
            2: 0.0,
            3: ((MV_LO + MV_HI) / 2.0) / 1000.0,
        }
        reader = _reader_with_voltages(voltages)
        pressures = reader.read_pressures()
        tab.update_pressures(pressures)

        self.assertEqual(
            tab.pressure_labels["Cartridge Input"].text(),
            "Cartridge Input: -11.50 psi",
        )
        self.assertEqual(
            tab.pressure_labels["Cartridge Output"].text(),
            "Cartridge Output: 75.00 psi",
        )
        mid = (PSI_LO + PSI_HI) / 2.0
        self.assertEqual(
            tab.pressure_labels["Pump Output"].text(),
            f"Pump Output: {mid:.2f} psi",
        )
        zero_psi = mv_to_psi(0.0)
        self.assertEqual(
            tab.pressure_labels["Pump Input"].text(),
            f"Pump Input: {zero_psi:.2f} psi",
        )

    def test_nan_shows_placeholder_with_unit(self) -> None:
        from gui import Service2Tab

        tab = Service2Tab(
            sensor_names=["CSF"],
            pressure_sensor_names=["Cartridge Input"],
        )
        tab.update_pressures({"Cartridge Input": float("nan")})
        self.assertEqual(
            tab.pressure_labels["Cartridge Input"].text(),
            "Cartridge Input: --.-- psi",
        )
        self.assertTrue(math.isnan(tab.pressure_values["Cartridge Input"]))

    def test_pressure_service_tab_shows_psi_and_pump_speed(self) -> None:
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

        self.assertEqual(
            tab.pressure_labels["Cartridge Input"].text(),
            "Cartridge Input: -11.50 psi",
        )
        self.assertEqual(
            tab.pressure_labels["Cartridge Output"].text(),
            "Cartridge Output: 75.00 psi",
        )
        self.assertIn("Pump: 30 RPM", tab.pump_speed_label.text())
        self.assertIn("ml/min", tab.pump_speed_label.text())


if __name__ == "__main__":
    unittest.main()
