"""
Thermocouple Reader Module
Reads Sequent SMtc thermocouple channels via I2C.
"""

from __future__ import annotations

from typing import Dict, Optional

try:
    import sm_tc  # type: ignore
    SMTC_AVAILABLE = True
except ImportError:
    SMTC_AVAILABLE = False


class ThermocoupleReader:
    """Read thermocouple channels from Sequent SMtc board."""

    def __init__(self, config: dict, simulation_mode: bool = False):
        tc_cfg = config.get("thermocouples", {})
        self.enabled = bool(tc_cfg.get("enabled", True))
        self.simulation_mode = bool(simulation_mode)
        self.stack = int(tc_cfg.get("stack", 0))
        self.i2c_bus = int(tc_cfg.get("i2c_bus", 1))
        self.channels = tc_cfg.get("channels", [1, 2, 3, 4])
        self.channel_labels = tc_cfg.get(
            "labels",
            {
                1: "Body Temp",
                2: "Plate Temp",
                3: "Temp 3",
                4: "Temp 4",
            },
        )

        self.is_initialized = False
        self.last_error: Optional[str] = None
        self._device = None

        if not self.enabled:
            self.last_error = "Thermocouple reader disabled by config"
            return
        if self.simulation_mode:
            # In simulation mode we keep the module available but inactive.
            self.last_error = "Simulation mode active"
            return
        if not SMTC_AVAILABLE:
            self.last_error = "sm_tc package is not installed"
            return

        try:
            self._device = sm_tc.SMtc(self.stack, self.i2c_bus)
            self.is_initialized = True
        except Exception as exc:
            self.last_error = f"SMtc initialization failed: {exc}"

    def read_temperatures(self) -> Dict[str, float]:
        """
        Read configured thermocouple channels.

        Returns:
            dict[str, float]: mapping from label to temperature in Celsius.
            Returns empty dict when not initialized.
        """
        if not self.is_initialized or not self._device:
            return {}

        values: Dict[str, float] = {}
        for channel in self.channels:
            try:
                raw_value = self._device.get_temp(int(channel))
                label = self.channel_labels.get(channel, f"Temp {channel}")
                values[label] = float(raw_value)
            except Exception as exc:
                self.last_error = f"Failed reading thermocouple channel {channel}: {exc}"
        return values

