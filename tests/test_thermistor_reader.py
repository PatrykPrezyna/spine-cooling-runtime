"""Unit tests for ADS1115 thermistor voltage → °C conversion."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ads1115_thermistor_reader import ADS1115ThermistorReader  # noqa: E402
from hardware_factory import build_hardware  # noqa: E402
from sensor_injection import (  # noqa: E402
    temperature_labels_from_config,
    thermocouple_labels_from_config,
    thermistor_labels_from_config,
)
from thermistor_conversion import (  # noqa: E402
    DEFAULT_TABLE_CSV,
    millivolts_to_celsius,
    voltage_to_celsius,
    voltage_to_r,
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
            "vref_v": 2.5,
            "rs_ohm": 100000,
            "resistance_column": "10k_Ohm",
            "table_csv": "data/calibration/Thermistor_MA300TA103C.csv",
        },
    },
    "pressure_sensors": {
        "enabled": True,
        "i2c_addresses": [74, 75],
        "channels": [0, 1, 2, 3],
        "channel_configs": {
            0: {"label": "Cartridge Input"},
            1: {"label": "Cartridge Output"},
            2: {"label": "Pump Input"},
            3: {"label": "Pump Output"},
        },
    },
    "stepper_motor": {"max_speed_rpm": 120},
    "simulation": {
        "csf_label": "CSF",
        "csf_initial_c": 37.0,
        "thermistors": {"CSF": 36.5, "Heat Ex": 22.0},
        "pressures": {
            "Cartridge Input": 20.0,
            "Cartridge Output": 15.0,
            "Pump Input": 25.0,
            "Pump Output": 30.0,
        },
        "sensors": {"Level Low": True},
    },
}


class ThermistorConversionTests(unittest.TestCase):
    def test_table_file_exists(self) -> None:
        self.assertTrue(DEFAULT_TABLE_CSV.is_file(), str(DEFAULT_TABLE_CSV))

    def test_calibration_points(self) -> None:
        # Divider voltages implied by the 10kΩ column at 0 / 37 / 50 °C.
        for r_ohm, expected_c in ((32739.8, 0.0), (6014.23, 37.0), (3603.46, 50.0)):
            mv = 1000.0 * 2.5 * r_ohm / (100000.0 + r_ohm)
            self.assertAlmostEqual(millivolts_to_celsius(mv), expected_c, places=5)

    def test_25c_nominal(self) -> None:
        # At 25 °C, R = 10 kΩ → V = 2.5 * 10k / 110k.
        v = 2.5 * 10000.0 / 110000.0
        self.assertAlmostEqual(voltage_to_celsius(v), 25.0, places=5)

    def test_adjacent_interpolation(self) -> None:
        r_24 = 10450.1
        r_25 = 10000.0
        r_mid = (r_24 + r_25) / 2.0
        v = 2.5 * r_mid / (100000.0 + r_mid)
        self.assertAlmostEqual(voltage_to_celsius(v), 24.5, places=3)

    def test_voltage_to_r_roundtrip(self) -> None:
        r = 10000.0
        v = 2.5 * r / (100000.0 + r)
        self.assertAlmostEqual(voltage_to_r(v), r, places=6)

    def test_reader_loads_table_from_config(self) -> None:
        reader = ADS1115ThermistorReader(
            {
                "thermistor_sensors": {
                    "enabled": False,
                    "conversion": _CONFIG["thermistor_sensors"]["conversion"],
                }
            }
        )
        self.assertGreaterEqual(len(reader.rt_table), 2)
        self.assertAlmostEqual(reader.rt_table[0][1], 0.0)  # coldest first (highest R)
        self.assertAlmostEqual(reader.rt_table[-1][1], 50.0)


class ThermistorHardwareTests(unittest.TestCase):
    def test_labels_split_by_family_with_shared_names(self) -> None:
        self.assertEqual(temperature_labels_from_config(_CONFIG), ["CSF"])
        self.assertEqual(thermocouple_labels_from_config(_CONFIG), ["CSF"])
        self.assertEqual(thermistor_labels_from_config(_CONFIG), ["CSF", "Heat Ex"])

    def test_temperature_sources_select_backend(self) -> None:
        from sensor_injection import select_temperatures

        cfg = {
            **_CONFIG,
            "temperature_sources": {
                "CSF": "thermocouple",
                "Cart In": "thermistor",
                "Heat Ex": "thermistor",
                "Room Temp": "thermistor",
            },
            "thermocouples": {
                "enabled": True,
                "channels": [1, 5],
                "labels": {1: "CSF", 5: "Heat Ex"},
            },
        }
        self.assertEqual(
            temperature_labels_from_config(cfg),
            ["CSF", "Cart In", "Heat Ex", "Room Temp"],
        )
        selected = select_temperatures(
            {"CSF": 30.0, "Heat Ex": 10.0, "Cart In": 99.0},
            {"Cart In": 22.0, "Heat Ex": 18.0, "Room Temp": 21.5},
            cfg,
        )
        # Same label name, value taken from the board named in temperature_sources.
        self.assertAlmostEqual(selected["CSF"], 30.0)  # thermocouple
        self.assertAlmostEqual(selected["Cart In"], 22.0)  # thermistor (not 99)
        self.assertAlmostEqual(selected["Heat Ex"], 18.0)  # thermistor (not 10)
        self.assertAlmostEqual(selected["Room Temp"], 21.5)
        self.assertEqual(list(selected.keys()), ["CSF", "Cart In", "Heat Ex", "Room Temp"])

    def test_temperature_sources_missing_board_value_is_nan(self) -> None:
        from sensor_injection import select_temperatures
        import math

        cfg = {
            "temperature_sources": {"CSF": "thermocouple", "Room Temp": "thermistor"},
        }
        selected = select_temperatures({"CSF": 37.0}, {}, cfg)
        self.assertAlmostEqual(selected["CSF"], 37.0)
        self.assertTrue(math.isnan(selected["Room Temp"]))

    def test_sim_reads_thermistors_and_pressure_separately(self) -> None:
        bundle = build_hardware(_CONFIG, simulation=True)
        temps = bundle.thermocouple_reader.read_temperatures()
        self.assertAlmostEqual(temps["CSF"], 37.0)

        therms = bundle.thermistor_reader.read_temperatures()
        self.assertAlmostEqual(therms["CSF"], 36.5)
        self.assertAlmostEqual(therms["Heat Ex"], 22.0)

        pressures = bundle.pressure_reader.read_pressures()
        self.assertAlmostEqual(pressures["Cartridge Input"], 20.0)
        self.assertEqual(len(pressures), 4)

        bundle.thermocouple_reader.cleanup()
        bundle.thermistor_reader.cleanup()
        bundle.pressure_reader.cleanup()


if __name__ == "__main__":
    unittest.main()
