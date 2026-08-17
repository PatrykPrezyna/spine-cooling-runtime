"""Tests for catheter / cartridge cooling-power calculation and the Power tab."""

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

from cooling_power import (  # noqa: E402
    CoolingPowerConfig,
    cartridge_cooling_power_w,
    catheter_cooling_power_w,
    heat_rate_w,
    mass_flow_kg_per_s,
)


class CoolingPowerFormulaTests(unittest.TestCase):
    def test_mass_flow_from_ml_per_min(self) -> None:
        # 60 ml/min of water at 1 kg/L → 0.001 kg/s
        self.assertAlmostEqual(mass_flow_kg_per_s(60.0), 0.001, places=9)

    def test_heat_rate_at_60_ml_min_and_5k(self) -> None:
        # P = 0.001 kg/s * 4184 J/(kg·K) * 5 K = 20.92 W
        power = heat_rate_w(20.0, 25.0, 60.0)
        self.assertAlmostEqual(power, 20.92, places=4)

    def test_zero_flow_is_zero_power(self) -> None:
        self.assertEqual(catheter_cooling_power_w(20.0, 25.0, 0.0), 0.0)

    def test_missing_temperature_is_nan(self) -> None:
        self.assertTrue(math.isnan(catheter_cooling_power_w(None, 25.0, 60.0)))
        self.assertTrue(math.isnan(cartridge_cooling_power_w(22.0, None, 60.0)))

    def test_catheter_positive_when_water_warms(self) -> None:
        power = catheter_cooling_power_w(18.0, 22.0, 60.0)
        self.assertGreater(power, 0.0)
        self.assertAlmostEqual(power, 16.736, places=3)

    def test_cartridge_positive_when_water_cools(self) -> None:
        # In 24 °C, out 18 °C at 60 ml/min → same 25.104 W extracted
        power = cartridge_cooling_power_w(24.0, 18.0, 60.0)
        self.assertGreater(power, 0.0)
        self.assertAlmostEqual(power, 25.104, places=3)

    def test_config_defaults_match_temperature_source_labels(self) -> None:
        cfg = CoolingPowerConfig.from_config_dict(None)
        self.assertEqual(cfg.catheter_in_label, "Catheter In")
        self.assertEqual(cfg.catheter_out_label, "Catheter Out")
        self.assertEqual(cfg.cartridge_in_label, "Cartrige In")
        self.assertEqual(cfg.cartridge_out_label, "Cartrige Out")


class PowerGraphTabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        try:
            from PyQt6.QtWidgets import QApplication
        except Exception as exc:
            raise unittest.SkipTest(f"PyQt6 unavailable on this host: {exc}") from exc

        cls._app = QApplication.instance() or QApplication([])

    def test_tab_plots_catheter_and_cartridge_watts(self) -> None:
        from gui import PowerGraphTab

        tab = PowerGraphTab(
            {
                "cooling_power": {
                    "catheter_in_label": "Catheter In",
                    "catheter_out_label": "Catheter Out",
                    "cartridge_in_label": "Cartrige In",
                    "cartridge_out_label": "Cartrige Out",
                }
            }
        )
        tab.update_temperatures(
            {
                "Catheter In": 18.0,
                "Catheter Out": 22.0,
                "Cartrige In": 24.0,
                "Cartrige Out": 18.0,
            }
        )
        tab.update_pump_speed(flow_ml_per_min=60.0)
        tab.push_latest_sample()

        self.assertEqual(tab.checkboxes["Catheter"].text(), "Catheter  16.7 W")
        self.assertEqual(tab.checkboxes["Cartridge"].text(), "Cartridge  25.1 W")
        latest = tab.graph_widget._history[-1][1]
        self.assertAlmostEqual(latest["Catheter"], 16.736, places=3)
        self.assertAlmostEqual(latest["Cartridge"], 25.104, places=3)
        self.assertEqual(tab.graph_widget._y_unit, "W")


if __name__ == "__main__":
    unittest.main()
