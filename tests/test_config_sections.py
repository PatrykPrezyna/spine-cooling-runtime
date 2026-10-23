"""Grouped config.yaml sections still drive the runtime."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config_sections import (  # noqa: E402
    actuator_device,
    control_temp_label,
    digital_sample_rate_hz,
    ensure_actuator_device,
    flow_cfg,
    digital_sensor_entries,
    pressure_cfg,
    thermistor_cfg,
)
from hardware_factory import build_hardware  # noqa: E402
from sensor_injection import (  # noqa: E402
    digital_sensor_names,
    temperature_labels_from_config,
)


class ConfigLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with (PROJECT_ROOT / "config.yaml").open(encoding="utf-8") as handle:
            cls.config = yaml.safe_load(handle)

    def test_top_level_groups(self) -> None:
        self.assertEqual(
            list(self.config),
            ["ui", "actuators", "sensors", "logging", "alarms", "simulation"],
        )

    def test_grouped_file_resolves_devices(self) -> None:
        self.assertEqual(control_temp_label(self.config), "Tip")
        self.assertEqual(self.config["ui"]["main_view"], "spine")
        self.assertEqual(actuator_device(self.config, "compressor")["relay_pin"], 16)
        self.assertEqual(
            actuator_device(self.config, "stepper_motor")["pins"]["step"],
            5,
        )
        self.assertEqual(
            actuator_device(self.config, "pump_control")["max_flow_ml_per_min"],
            60.0,
        )
        self.assertEqual(
            actuator_device(self.config, "cooling_power")["catheter_in_label"],
            "Catheter In",
        )
        digital = self.config["sensors"]["digital_sensors"]
        self.assertEqual(digital["sample_rate_hz"], 1.0)
        self.assertNotIn("sample_rate_hz", self.config["sensors"])
        self.assertNotIn("gpio", self.config["sensors"])
        self.assertEqual(digital_sample_rate_hz(self.config), 1.0)
        self.assertEqual(digital_sensor_entries(self.config)[0]["name"], "Level Low")
        self.assertEqual(thermistor_cfg(self.config)["labels"][0], "Tip")
        self.assertEqual(flow_cfg(self.config)["i2c_bus"], 6)
        self.assertEqual(pressure_cfg(self.config)["labels"][0], "Pump In")
        self.assertEqual(
            temperature_labels_from_config(self.config)[0],
            "Tip",
        )
        self.assertEqual(digital_sensor_names(self.config)[0], "Level Low")
        self.assertEqual(self.config["logging"]["directory"], "logs")
        self.assertEqual(self.config["alarms"]["csf_label"], "Body Temp")
        self.assertEqual(self.config["simulation"]["csf_label"], "Tip")

    def test_legacy_flat_keys_still_resolve(self) -> None:
        flat = {
            "control_temp_label": "CSF",
            "sample_rate_hz": 2.0,
            "sensors": [{"name": "Leak Sensor", "gpio_pin": 26}],
            "thermistor_sensors": {"labels": {0: "CSF"}},
            "flow_sensor": {"enabled": True, "i2c_bus": 1},
            "pressure_sensors": {"labels": {0: "Pump In"}},
            "compressor": {"relay_pin": 4},
            "stepper_motor": {"max_speed_rpm": 120},
        }
        self.assertEqual(control_temp_label(flat), "CSF")
        self.assertEqual(digital_sample_rate_hz(flat), 2.0)
        self.assertEqual(digital_sensor_entries(flat)[0]["gpio_pin"], 26)
        self.assertEqual(thermistor_cfg(flat)["labels"][0], "CSF")
        self.assertTrue(flow_cfg(flat)["enabled"])
        self.assertEqual(pressure_cfg(flat)["labels"][0], "Pump In")
        self.assertEqual(actuator_device(flat, "compressor")["relay_pin"], 4)
        self.assertEqual(actuator_device(flat, "stepper_motor")["max_speed_rpm"], 120)

    def test_threshold_edit_stays_inside_actuators(self) -> None:
        config = {"actuators": {"compressor": {"off_below_temp_c": -0.5}}}
        block = ensure_actuator_device(config, "compressor")
        block["off_below_temp_c"] = -1.0
        self.assertEqual(config["actuators"]["compressor"]["off_below_temp_c"], -1.0)
        self.assertNotIn("compressor", config)

    def test_real_config_builds_simulated_hardware(self) -> None:
        bundle = build_hardware(self.config, simulation=True)
        temps = bundle.thermistor_reader.read_temperatures()
        self.assertAlmostEqual(temps["Tip"], 36.5)
        self.assertAlmostEqual(temps["Plate 1"], 22.0)
        pressures = bundle.pressure_reader.read_pressures()
        self.assertAlmostEqual(pressures["Pump In"], 1.72)
        self.assertEqual(bundle.flow_reader.read_flow_ml_per_min(), 30.0)
        self.assertIn("Leak Sensor", bundle.sensor_reader.read_all())
        self.assertEqual(bundle.stepper_driver.max_speed_rpm, 390.0)
        bundle.thermistor_reader.cleanup()
        bundle.pressure_reader.cleanup()


if __name__ == "__main__":
    unittest.main()
