"""Unit tests for ADS1115 thermistor mV → °C conversion."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ads1115_thermistor_reader import millivolts_to_celsius  # noqa: E402
from hardware_factory import build_hardware  # noqa: E402
from sensor_injection import (  # noqa: E402
    temperature_labels_from_config,
    thermocouple_labels_from_config,
    thermistor_labels_from_config,
)


_CONFIG = {
    "sensors": [{"name": "Level Low"}],
    "thermocouples": {
        "enabled": True,
        "channels": [1],
        "labels": {1: "CSF"},
    },
    "thermistor_sensors": {
        "enabled": True,
        "i2c_addresses": [72, 73],
        "channels": [0, 1],
        "labels": {0: "CSF", 1: "Heat Ex"},
        "conversion": {
            "points_mv_c": [[616.0, 0.0], [142.0, 37.0], [87.0, 50.0]],
        },
    },
    "pressure_sensors": {
        "enabled": True,
        "i2c_addresses": [50, 51],
        "channels": [0, 1, 2, 3],
        "channel_configs": {
            0: {"label": "Pressure 1"},
            1: {"label": "Pressure 2"},
            2: {"label": "Pressure 3"},
            3: {"label": "Pressure 4"},
        },
    },
    "stepper_motor": {"max_speed_rpm": 120},
    "simulation": {
        "csf_label": "CSF",
        "csf_initial_c": 37.0,
        "thermistors": {"CSF": 36.5, "Heat Ex": 22.0},
        "pressures": {
            "Pressure 1": 120.0,
            "Pressure 2": 95.0,
            "Pressure 3": 110.0,
            "Pressure 4": 100.0,
        },
        "sensors": {"Level Low": True},
    },
}


class ThermistorConversionTests(unittest.TestCase):
    def test_calibration_points(self) -> None:
        self.assertAlmostEqual(millivolts_to_celsius(616.0), 0.0)
        self.assertAlmostEqual(millivolts_to_celsius(142.0), 37.0)
        self.assertAlmostEqual(millivolts_to_celsius(87.0), 50.0)

    def test_midpoint_0_to_37(self) -> None:
        # Halfway in mV between 616 and 142 should be halfway in °C.
        mid_mv = (616.0 + 142.0) / 2.0
        self.assertAlmostEqual(millivolts_to_celsius(mid_mv), 18.5, places=5)

    def test_midpoint_37_to_50(self) -> None:
        mid_mv = (142.0 + 87.0) / 2.0
        self.assertAlmostEqual(millivolts_to_celsius(mid_mv), 43.5, places=5)


class ThermistorHardwareTests(unittest.TestCase):
    def test_labels_split_by_family_with_shared_names(self) -> None:
        self.assertEqual(temperature_labels_from_config(_CONFIG), ["CSF"])
        self.assertEqual(thermocouple_labels_from_config(_CONFIG), ["CSF"])
        self.assertEqual(thermistor_labels_from_config(_CONFIG), ["CSF", "Heat Ex"])

    def test_sim_reads_thermistors_and_pressure_separately(self) -> None:
        bundle = build_hardware(_CONFIG, simulation=True)
        temps = bundle.thermocouple_reader.read_temperatures()
        self.assertAlmostEqual(temps["CSF"], 37.0)

        therms = bundle.thermistor_reader.read_temperatures()
        self.assertAlmostEqual(therms["CSF"], 36.5)
        self.assertAlmostEqual(therms["Heat Ex"], 22.0)

        pressures = bundle.pressure_reader.read_pressures()
        self.assertAlmostEqual(pressures["Pressure 1"], 120.0)
        self.assertEqual(len(pressures), 4)

        bundle.thermocouple_reader.cleanup()
        bundle.thermistor_reader.cleanup()
        bundle.pressure_reader.cleanup()


if __name__ == "__main__":
    unittest.main()
