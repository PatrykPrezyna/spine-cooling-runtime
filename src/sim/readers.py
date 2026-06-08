"""Simulated sensor readers (GPIO, thermocouple, pressure)."""

from __future__ import annotations

import time
from typing import Dict, Optional

from temperature_calibration import (
    IDENTITY_CALIBRATION,
    apply_linear_calibration,
    build_two_point_calibration,
)


def _sim_cfg(config: dict) -> dict:
    return config.get("simulation", {}) or {}


class SimSensorReader:
    """Digital GPIO sensors backed by in-memory booleans."""

    def __init__(self, config: dict):
        self.sensors = config["sensors"]
        overrides = _sim_cfg(config).get("sensors", {}) or {}
        self.sensor_states: Dict[str, bool] = {}
        for sensor in self.sensors:
            name = sensor["name"]
            self.sensor_states[name] = bool(overrides.get(name, False))
        self.is_initialized = True
        print(f"SimSensorReader: {len(self.sensors)} sensors (simulation mode)")

    def read_all(self) -> Dict[str, bool]:
        return dict(self.sensor_states)

    def cleanup(self) -> None:
        self.is_initialized = False


class SimThermocoupleReader:
    """Thermocouple readings from config defaults.

    - CSF starts at 37.0 C. Pump off: rises at ``csf_rate_c_per_s`` until
      ``csf_max_c`` (37). Pump on: change rate is
      ``csf_rate_c_per_s * csf_cart_out_scale * (22 - Cart Out)`` until
      ``csf_min_c`` (25).
    - Heat Ex starts at 22.0 C, cools at ``heat_ex_cool_rate_c_per_s`` when the
      compressor is on, warms at ``heat_ex_warm_rate_c_per_s`` when off.
    - Cart In / Cart Out start at 22.0 C. When the pump is on, Cart In rises at
      ``cart_in_rise_rate_c_per_s`` until it reaches CSF / 2 and
      ``Cart Out = Cart In - (cart_initial_c - Heat Ex)``. When the pump is off,
      ``Cart Out = Cart In``.

    Call ``notify_setpoint()`` each tick before ``read_temperatures()``.
    """

    def __init__(self, config: dict):
        tc_cfg = config.get("thermocouples", {})
        sim_cfg = _sim_cfg(config)
        compressor_cfg = config.get("compressor", {}) or {}
        self.enabled = bool(tc_cfg.get("enabled", True))
        self.channels = tc_cfg.get("channels", [2, 3, 4, 5, 6, 7])
        self.channel_labels: Dict[int, str] = {}
        for key, value in (tc_cfg.get("labels", {}) or {}).items():
            try:
                self.channel_labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue

        self.is_initialized = False
        self.last_error: Optional[str] = None
        self._channel_calibration: Dict[int, tuple[float, float]] = {}
        self._last_raw_temperatures: Dict[str, float] = {}
        self._temperatures: Dict[str, float] = {}
        self._csf_label = str(sim_cfg.get("csf_label", "CSF"))
        self._csf_initial_c = float(sim_cfg.get("csf_initial_c", 37.0))
        self._csf_max_c = float(sim_cfg.get("csf_max_c", 37.0))
        self._csf_min_c = float(sim_cfg.get("csf_min_c", 25.0))
        self._csf_rate_c_per_s = float(sim_cfg.get("csf_rate_c_per_s", 0.1))
        self._csf_cart_out_scale = float(
            sim_cfg.get(
                "csf_cart_out_scale",
                sim_cfg.get("csf_heat_ex_scale", 0.05),
            )
        )
        self._heat_ex_label = str(
            sim_cfg.get("heat_ex_label", compressor_cfg.get("heat_ex_label", "Heat Ex"))
        )
        self._heat_ex_initial_c = float(sim_cfg.get("heat_ex_initial_c", 22.0))
        self._heat_ex_max_c = float(sim_cfg.get("heat_ex_max_c", 23.0))
        self._heat_ex_cool_rate_c_per_s = float(sim_cfg.get("heat_ex_cool_rate_c_per_s", 0.5))
        self._heat_ex_warm_rate_c_per_s = float(sim_cfg.get("heat_ex_warm_rate_c_per_s", 0.02))
        self._cart_in_label = str(sim_cfg.get("cart_in_label", "Cart In"))
        self._cart_out_label = str(sim_cfg.get("cart_out_label", "Cart Out"))
        self._cart_initial_c = float(sim_cfg.get("cart_initial_c", 22.0))
        self._cart_in_rise_rate_c_per_s = float(sim_cfg.get("cart_in_rise_rate_c_per_s", 0.2))
        self._last_advance_time = time.monotonic()

        if not self.enabled:
            self.last_error = "Thermocouple reader disabled by config"
            return

        temp_overrides = sim_cfg.get("temperatures", {}) or {}
        for channel in self.channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            label = self.channel_labels.get(ch, f"Temp {ch}")
            if label == self._csf_label:
                default_c = self._csf_initial_c
            elif label == self._heat_ex_label:
                default_c = self._heat_ex_initial_c
            elif label in (self._cart_in_label, self._cart_out_label):
                default_c = self._cart_initial_c
            else:
                default_c = float(temp_overrides.get(label, 25.0))
            self._last_raw_temperatures[label] = default_c
            self._temperatures[label] = default_c

        self._channel_calibration = self._build_calibration(tc_cfg)
        self._apply_all_calibrations()
        self.is_initialized = True
        print(f"SimThermocoupleReader: {len(self._temperatures)} channels (simulation mode)")

    def notify_setpoint(
        self,
        set_temperature_c: float,
        compressor_cooling: int = 0,
        pump_running: bool = False,
    ) -> None:
        """Advance simulated temperatures since the last tick."""
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_advance_time)
        self._last_advance_time = now

        del set_temperature_c  # CSF no longer follows the UI setpoint in sim mode
        self._advance_heat_ex(bool(compressor_cooling), elapsed)
        self._advance_cart_temps(bool(pump_running), elapsed)
        self._advance_csf(bool(pump_running), elapsed)

    def _advance_csf(self, pump_running: bool, elapsed: float) -> None:
        if self._csf_label not in self._last_raw_temperatures:
            return

        current = self._last_raw_temperatures[self._csf_label]
        if pump_running:
            cart_out = self._last_raw_temperatures.get(
                self._cart_out_label, self._cart_initial_c
            )
            rate = (
                self._csf_rate_c_per_s
                * self._csf_cart_out_scale
                * (self._cart_initial_c - cart_out)
            )
            new_raw = current - rate * elapsed
            new_raw = max(min(new_raw, self._csf_max_c), self._csf_min_c)
        else:
            step = self._csf_rate_c_per_s * elapsed
            new_raw = min(current + step, self._csf_max_c)

        self._last_raw_temperatures[self._csf_label] = new_raw
        self._apply_calibration_for_label(self._csf_label)

    def _advance_heat_ex(self, compressor_on: bool, elapsed: float) -> None:
        if self._heat_ex_label not in self._last_raw_temperatures:
            return

        current = self._last_raw_temperatures[self._heat_ex_label]
        if compressor_on:
            new_raw = current - self._heat_ex_cool_rate_c_per_s * elapsed
        else:
            new_raw = current + self._heat_ex_warm_rate_c_per_s * elapsed

        new_raw = min(new_raw, self._heat_ex_max_c)
        self._last_raw_temperatures[self._heat_ex_label] = new_raw
        self._apply_calibration_for_label(self._heat_ex_label)

    def _advance_cart_temps(self, pump_running: bool, elapsed: float) -> None:
        if pump_running:
            self._advance_cart_in(elapsed)
        self._update_cart_out(pump_running)

    def _advance_cart_in(self, elapsed: float) -> None:
        if self._cart_in_label not in self._last_raw_temperatures:
            return
        if self._csf_label not in self._last_raw_temperatures:
            return

        target = self._last_raw_temperatures[self._csf_label] * 0.8
        current = self._last_raw_temperatures[self._cart_in_label]
        if current >= target:
            return

        step = self._cart_in_rise_rate_c_per_s * elapsed
        new_raw = min(current + step, target)
        self._last_raw_temperatures[self._cart_in_label] = new_raw
        self._apply_calibration_for_label(self._cart_in_label)

    def _update_cart_out(self, pump_running: bool) -> None:
        if self._cart_out_label not in self._last_raw_temperatures:
            return
        if self._cart_in_label not in self._last_raw_temperatures:
            return

        cart_in = self._last_raw_temperatures[self._cart_in_label]
        if not pump_running:
            new_raw = cart_in
        else:
            if self._heat_ex_label not in self._last_raw_temperatures:
                return
            heat_ex = self._last_raw_temperatures[self._heat_ex_label]
            new_raw = cart_in - (self._cart_initial_c - heat_ex*0.8)

        self._last_raw_temperatures[self._cart_out_label] = new_raw
        self._apply_calibration_for_label(self._cart_out_label)

    def _label_to_channel(self, label: str) -> Optional[int]:
        for ch, ch_label in self.channel_labels.items():
            if ch_label == label:
                return ch
        return None

    def _apply_calibration_for_label(self, label: str) -> None:
        ch = self._label_to_channel(label)
        if ch is None:
            return
        raw = self._last_raw_temperatures.get(label)
        if raw is None:
            return
        gain, offset = self._channel_calibration.get(ch, IDENTITY_CALIBRATION)
        self._temperatures[label] = apply_linear_calibration(raw, gain, offset)

    def _build_calibration(self, tc_cfg: dict) -> Dict[int, tuple[float, float]]:
        calibration_cfg = tc_cfg.get("calibration", {}) or {}
        default_pts = calibration_cfg.get("default", {}) or {}
        default_cal, _ = build_two_point_calibration(
            default_pts.get("measured_at_0c", 0.0),
            default_pts.get("measured_at_100c", 100.0),
        )
        per_channel = calibration_cfg.get("channels", {}) or {}
        result: Dict[int, tuple[float, float]] = {}
        for channel in self.channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            pts = per_channel.get(str(ch), per_channel.get(ch, default_pts))
            if isinstance(pts, dict):
                cal, err = build_two_point_calibration(
                    pts.get("measured_at_0c", 0.0),
                    pts.get("measured_at_100c", 100.0),
                )
                result[ch] = cal if err is None else default_cal
            else:
                result[ch] = default_cal
        return result

    def _apply_all_calibrations(self) -> None:
        for channel in self.channels:
            try:
                ch = int(channel)
            except (TypeError, ValueError):
                continue
            label = self.channel_labels.get(ch, f"Temp {ch}")
            raw = self._last_raw_temperatures.get(label)
            if raw is None:
                continue
            gain, offset = self._channel_calibration.get(ch, IDENTITY_CALIBRATION)
            self._temperatures[label] = apply_linear_calibration(raw, gain, offset)

    def read_temperatures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        return dict(self._temperatures)

    def get_last_raw_temperatures(self) -> Dict[str, float]:
        return dict(self._last_raw_temperatures)

    def set_channel_two_point_calibration(
        self,
        channel: int,
        measured_at_0c: float,
        measured_at_100c: float,
    ) -> tuple[bool, str]:
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            return False, f"Invalid channel: {channel}"

        calibration, error = build_two_point_calibration(measured_at_0c, measured_at_100c)
        if error:
            msg = f"Invalid calibration for channel {ch}: {error}"
            self.last_error = msg
            return False, msg

        self._channel_calibration[ch] = calibration
        label = self.channel_labels.get(ch, f"Temp {ch}")
        raw = self._last_raw_temperatures.get(label)
        if raw is not None:
            gain, offset = calibration
            self._temperatures[label] = apply_linear_calibration(raw, gain, offset)
        self.last_error = None
        return True, f"Calibration updated for channel {ch}"

    def cleanup(self) -> None:
        self.is_initialized = False


class SimPressureReader:
    """Pressure readings from config defaults."""

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        self.channels = ps_cfg.get("channels", [0, 1])
        self.channel_configs = ps_cfg.get("channel_configs", {})
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._pressures: Dict[str, float] = {}

        if not self.enabled:
            self.last_error = "ADS1115 pressure reader disabled by config"
            return

        overrides = _sim_cfg(config).get("pressures", {}) or {}
        for channel in self.channels:
            ch = int(channel)
            label = self._channel_label(ch)
            self._pressures[label] = float(overrides.get(label, 0.0))

        self.is_initialized = bool(self._pressures)
        if self.is_initialized:
            print(f"SimPressureReader: {len(self._pressures)} channels (simulation mode)")
        else:
            self.last_error = "No valid pressure channels configured"

    def _channel_label(self, channel: int) -> str:
        cfg = self.channel_configs.get(str(channel), self.channel_configs.get(channel, {}))
        if isinstance(cfg, dict):
            label = cfg.get("label")
            if label:
                return str(label)
        return f"Pressure {channel + 1}"

    def read_pressures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        return dict(self._pressures)

    def cleanup(self) -> None:
        self.is_initialized = False
