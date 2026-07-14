"""Smoke tests for simulated hardware (no Raspberry Pi required)."""

import sys
import time
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hardware_factory import build_hardware  # noqa: E402


_MINIMAL_CONFIG = {
    "sensors": [
        {"name": "Level Low"},
        {"name": "Level Critical"},
        {"name": "Cartridge In Place"},
    ],
    "thermocouples": {
        "enabled": True,
        "channels": [2, 3, 4, 5],
        "labels": {2: "CSF", 3: "Cart In", 4: "Cart Out", 5: "Heat Ex"},
    },
    "thermistor_sensors": {
        "enabled": True,
        "channels": [0, 1],
        "labels": {0: "CSF", 1: "Heat Ex"},
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
        "csf_max_c": 37.0,
        "csf_min_c": 25.0,
        "csf_rate_c_per_s": 0.1,
        "csf_cart_out_scale": 0.05,
        "heat_ex_label": "Heat Ex",
        "heat_ex_initial_c": 22.0,
        "heat_ex_cool_rate_c_per_s": 0.5,
        "heat_ex_warm_rate_c_per_s": 0.02,
        "heat_ex_max_c": 23.0,
        "cart_in_label": "Cart In",
        "cart_out_label": "Cart Out",
        "cart_initial_c": 22.0,
        "cart_in_rise_rate_c_per_s": 0.2,
        "sensors": {
            "Cartridge In Place": True,
            "Level Low": True,
            "Level Critical": True,
        },
        "pressures": {
            "Pressure 1": 120.0,
            "Pressure 2": 95.0,
            "Pressure 3": 110.0,
            "Pressure 4": 100.0,
        },
        "thermistors": {"CSF": 36.0, "Heat Ex": 21.0},
    },
}


class SimHardwareTests(unittest.TestCase):
    def test_build_hardware_sim_mode(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)

        self.assertTrue(bundle.sensor_reader.is_initialized)
        sensor_states = bundle.sensor_reader.read_all()
        self.assertTrue(sensor_states["Cartridge In Place"])
        self.assertTrue(sensor_states["Level Low"])
        self.assertTrue(sensor_states["Level Critical"])

        self.assertTrue(bundle.thermocouple_reader.is_initialized)
        temps = bundle.thermocouple_reader.read_temperatures()
        self.assertAlmostEqual(temps["CSF"], 37.0)
        self.assertAlmostEqual(temps["Heat Ex"], 22.0)

        self.assertTrue(bundle.thermistor_reader.is_initialized)
        therms = bundle.thermistor_reader.read_temperatures()
        self.assertAlmostEqual(therms["CSF"], 36.0)
        self.assertAlmostEqual(therms["Heat Ex"], 21.0)

        self.assertTrue(bundle.pressure_reader.is_initialized)
        pressures = bundle.pressure_reader.read_pressures()
        self.assertAlmostEqual(pressures["Pressure 1"], 120.0)
        self.assertAlmostEqual(pressures["Pressure 4"], 100.0)

        self.assertTrue(bundle.stepper_driver.is_initialized)
        bundle.stepper_driver.enable()
        bundle.stepper_driver.start_continuous(direction=1, speed_rpm=30.0)
        bundle.stepper_driver.stop_continuous()
        bundle.stepper_driver.cleanup()
        bundle.sensor_reader.cleanup()
        bundle.thermocouple_reader.cleanup()
        bundle.thermistor_reader.cleanup()
        bundle.pressure_reader.cleanup()

    def test_csf_follows_pump_state(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)
        reader = bundle.thermocouple_reader

        self.assertAlmostEqual(reader.read_temperatures()["CSF"], 37.0)

        reader._last_raw_temperatures["CSF"] = 27.5
        reader._last_raw_temperatures["Cart In"] = 22.0
        reader._last_raw_temperatures["Heat Ex"] = 20.0
        for label in ("CSF", "Cart In", "Heat Ex"):
            reader._apply_calibration_for_label(label)
        reader.notify_setpoint(32.0, pump_running=True, pump_speed_rpm=120)
        time.sleep(10.05)
        reader.notify_setpoint(32.0, pump_running=True, pump_speed_rpm=120)
        # Cart Out = Cart In - (Cart In - Heat Ex) * 0.75
        self.assertAlmostEqual(reader.read_temperatures()["CSF"], 27.4, places=1)

        reader._last_raw_temperatures["CSF"] = 30.0
        reader._apply_calibration_for_label("CSF")
        reader.notify_setpoint(32.0, pump_running=False, pump_speed_rpm=0)
        time.sleep(1.05)
        reader.notify_setpoint(32.0, pump_running=False, pump_speed_rpm=0)
        self.assertAlmostEqual(reader.read_temperatures()["CSF"], 30.1, places=1)
        reader.cleanup()

    def test_csf_warms_when_pump_speed_below_threshold(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)
        reader = bundle.thermocouple_reader

        reader._last_raw_temperatures["CSF"] = 30.0
        reader._last_raw_temperatures["Cart In"] = 22.0
        reader._last_raw_temperatures["Heat Ex"] = 20.0
        for label in ("CSF", "Cart In", "Heat Ex"):
            reader._apply_calibration_for_label(label)

        reader.notify_setpoint(32.0, pump_running=True, pump_speed_rpm=20)
        time.sleep(1.05)
        reader.notify_setpoint(32.0, pump_running=True, pump_speed_rpm=20)
        self.assertAlmostEqual(reader.read_temperatures()["CSF"], 30.1, places=1)
        reader.cleanup()

    def test_heat_ex_responds_to_compressor(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)
        reader = bundle.thermocouple_reader

        self.assertAlmostEqual(reader.read_temperatures()["Heat Ex"], 22.0)

        reader.notify_setpoint(32.0, compressor_cooling=1)
        time.sleep(1.05)
        reader.notify_setpoint(32.0, compressor_cooling=1)
        self.assertAlmostEqual(reader.read_temperatures()["Heat Ex"], 21.5, places=1)

        reader.notify_setpoint(32.0, compressor_cooling=0)
        time.sleep(1.05)
        reader.notify_setpoint(32.0, compressor_cooling=0)
        self.assertAlmostEqual(reader.read_temperatures()["Heat Ex"], 21.52, places=1)
        reader.cleanup()

    def test_heat_ex_never_exceeds_max(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)
        reader = bundle.thermocouple_reader

        reader._last_raw_temperatures["Heat Ex"] = 22.9
        reader._apply_calibration_for_label("Heat Ex")
        reader.notify_setpoint(32.0, compressor_cooling=0)
        time.sleep(5.0)
        reader.notify_setpoint(32.0, compressor_cooling=0)

        self.assertLessEqual(reader.read_temperatures()["Heat Ex"], 23.0)
        reader.cleanup()

    def test_cart_temps_follow_pump_and_heat_ex(self) -> None:
        bundle = build_hardware(_MINIMAL_CONFIG, simulation=True)
        reader = bundle.thermocouple_reader
        temps = reader.read_temperatures()

        self.assertAlmostEqual(temps["Cart In"], 22.0)
        self.assertAlmostEqual(temps["Cart Out"], 22.0)

        reader._last_raw_temperatures["CSF"] = 50.0
        reader._apply_calibration_for_label("CSF")
        reader.notify_setpoint(32.0, compressor_cooling=0, pump_running=True, pump_speed_rpm=120)
        time.sleep(10.05)
        reader.notify_setpoint(32.0, compressor_cooling=0, pump_running=True, pump_speed_rpm=120)
        temps = reader.read_temperatures()

        self.assertAlmostEqual(temps["Cart In"], 24.0, places=1)
        expected_cart_out = temps["Cart In"] - (temps["Cart In"] - temps["Heat Ex"]) * 0.75
        self.assertAlmostEqual(temps["Cart Out"], expected_cart_out, places=1)

        reader.notify_setpoint(32.0, compressor_cooling=0, pump_running=False, pump_speed_rpm=0)
        temps = reader.read_temperatures()
        self.assertAlmostEqual(temps["Cart Out"], temps["Cart In"], places=2)
        reader.cleanup()


if __name__ == "__main__":
    unittest.main()
