"""Unit tests for runtime sensor injection."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hardware_factory import build_hardware  # noqa: E402
from sensor_injection import SensorInjectionController  # noqa: E402


_TEST_CONFIG = {
    "alarms": {
        "csf_label": "CSF 2",
        "csf_low_temp_c": 28.0,
        "heat_ex_label": "Heat Ex",
        "heat_ex_min_c": -10.0,
        "leak_pressure_delta_min": 5.0,
    },
    "sensors": [
        {"name": "Level Low"},
        {"name": "Level Critical"},
        {"name": "Cartridge In Place"},
    ],
    "thermocouples": {
        "enabled": True,
        "channels": [1, 2, 5],
        "labels": {1: "CSF 2", 2: "CSF", 5: "Heat Ex"},
    },
    "thermistor_sensors": {
        "enabled": True,
        "channels": [0],
        "labels": {0: "Therm 1"},
    },
    "pressure_sensors": {
        "enabled": True,
        "i2c_address": 73,
        "channels": [0, 1],
        "channel_configs": {
            0: {"label": "Pressure 1"},
            1: {"label": "Pressure 2"},
        },
    },
    "simulation": {
        "csf_label": "CSF 2",
        "csf_initial_c": 37.0,
        "heat_ex_label": "Heat Ex",
        "heat_ex_initial_c": 22.0,
        "sensors": {
            "Cartridge In Place": True,
            "Level Low": True,
            "Level Critical": True,
        },
        "pressures": {"Pressure 1": 120.0, "Pressure 2": 95.0},
        "thermistors": {"Therm 1": 25.0},
    },
}


class SensorInjectionTests(unittest.TestCase):
    def test_passthrough_when_not_simulated(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)

        states = wrapped.sensor_reader.read_all()
        self.assertTrue(states["Level Low"])

    def test_digital_override_when_simulated(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)

        controller.set_digital("Level Low", False)
        states = wrapped.sensor_reader.read_all()
        self.assertFalse(states["Level Low"])

    def test_temperature_override_when_simulated(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)

        controller.set_temperature_raw("CSF 2", 30.0)
        controller._sync_thermocouple_inner()
        temps = wrapped.thermocouple_reader.read_temperatures()
        self.assertAlmostEqual(temps["CSF 2"], 30.0)

    def test_pressure_override_when_simulated(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)

        controller.set_pressure("Pressure 1", 50.0)
        pressures = wrapped.pressure_reader.read_pressures()
        self.assertAlmostEqual(pressures["Pressure 1"], 50.0)

    def test_clear_override_restores_passthrough(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)

        controller.set_digital("Level Low", False)
        controller.clear_override("digital", "Level Low")
        states = wrapped.sensor_reader.read_all()
        self.assertTrue(states["Level Low"])

    def test_simulated_temp_stays_frozen_during_physics(self) -> None:
        controller = SensorInjectionController(_TEST_CONFIG)
        bundle = build_hardware(_TEST_CONFIG, simulation=True)
        wrapped = controller.wrap_bundle(bundle)
        controller.set_temperature_raw("CSF 2", 30.0)
        controller._sync_thermocouple_inner()

        notify = getattr(wrapped.thermocouple_reader, "notify_setpoint", None)
        self.assertIsNotNone(notify)
        notify(32.0, 1, True)
        temps = wrapped.thermocouple_reader.read_temperatures()
        self.assertAlmostEqual(temps["CSF 2"], 30.0)


if __name__ == "__main__":
    unittest.main()
