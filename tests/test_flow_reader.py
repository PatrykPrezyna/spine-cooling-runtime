"""Unit tests for 4–20 mA flow conversion through a 220 Ω shunt."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ads1115_flow_reader import (  # noqa: E402
    ADS1115FlowReader,
    ma_to_flow_ml_per_min,
    voltage_to_flow_ml_per_min,
    voltage_to_ma,
)
from hardware_factory import build_hardware  # noqa: E402


class FlowConversionTests(unittest.TestCase):
    def test_4ma_is_zero_flow_at_220_ohm(self) -> None:
        voltage_v = 0.004 * 220.0
        self.assertAlmostEqual(voltage_to_ma(voltage_v, 220.0), 4.0, places=6)
        self.assertAlmostEqual(voltage_to_flow_ml_per_min(voltage_v), 0.0, places=6)

    def test_20ma_is_full_scale_at_220_ohm(self) -> None:
        voltage_v = 0.020 * 220.0
        self.assertAlmostEqual(voltage_v, 4.40, places=6)
        self.assertAlmostEqual(voltage_to_flow_ml_per_min(voltage_v), 100.0, places=6)

    def test_midscale_12ma(self) -> None:
        self.assertAlmostEqual(ma_to_flow_ml_per_min(12.0), 50.0, places=6)


class FlowConfigTests(unittest.TestCase):
    def test_disabled_reader_parses_0x49_ain0(self) -> None:
        reader = ADS1115FlowReader(
            {
                "flow_sensor": {
                    "enabled": False,
                    "i2c_bus": 6,
                    "i2c_address": 73,
                    "analog_input": 0,
                    "shunt_ohm": 220,
                }
            }
        )
        self.assertEqual(reader.i2c_address, 0x49)
        self.assertEqual(reader.i2c_bus, 6)
        self.assertEqual(reader.analog_input, 0)
        self.assertAlmostEqual(reader.shunt_ohm, 220.0)

    def test_config_yaml_flow_sensor_on_bus6_0x49_ain0(self) -> None:
        import yaml

        with (PROJECT_ROOT / "config.yaml").open(encoding="utf-8") as fh:
            config = yaml.safe_load(fh)
        fs = config["flow_sensor"]
        self.assertTrue(fs["enabled"])
        self.assertEqual(int(fs["i2c_bus"]), 6)
        self.assertEqual(int(fs["i2c_address"]), 0x49)
        self.assertEqual(int(fs["analog_input"]), 0)
        self.assertAlmostEqual(float(fs["shunt_ohm"]), 220.0)
        self.assertIn(4, config["thermistor_sensors"]["channels"])
        self.assertEqual(config["thermistor_sensors"]["labels"][4], "Cartrige In")
        self.assertEqual(config["pressure_sensors"]["i2c_addresses"], [74, 75])

    def test_sim_reads_configured_flow(self) -> None:
        bundle = build_hardware(
            {
                "sensors": [{"name": "Level Low"}],
                "flow_sensor": {"enabled": True},
                "simulation": {"flow_ml_per_min": 42.5},
                "stepper_motor": {"max_speed_rpm": 120},
            },
            simulation=True,
        )
        self.assertTrue(bundle.flow_reader.is_initialized)
        self.assertAlmostEqual(bundle.flow_reader.read_flow_ml_per_min(), 42.5)
        bundle.flow_reader.cleanup()


if __name__ == "__main__":
    unittest.main()
