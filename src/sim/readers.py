"""Simulated sensor readers (GPIO, thermocouple, thermistor, pressure)."""

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

    def set_state(self, name: str, active: bool) -> None:
        if name in self.sensor_states:
            self.sensor_states[name] = bool(active)

    def cleanup(self) -> None:
        self.is_initialized = False


class SimThermocoupleReader:
    """Thermocouple readings from config defaults.

    - CSF starts at 37.0 C. Pump off or speed below
      ``csf_min_effective_pump_speed_rpm`` (30): rises at ``csf_rate_c_per_s``
      until ``csf_max_c`` (37). Pump on at effective speed: change rate is
      ``csf_rate_c_per_s * csf_cart_out_scale * (Cart Initial - Cart Out)
      * (pump_speed / csf_pump_speed_ref_rpm)`` until ``csf_min_c`` (25).
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
        stepper_cfg = config.get("stepper_motor", {}) or {}
        self._csf_min_effective_pump_speed_rpm = float(
            sim_cfg.get("csf_min_effective_pump_speed_rpm", 30.0)
        )
        self._csf_pump_speed_ref_rpm = float(
            sim_cfg.get(
                "csf_pump_speed_ref_rpm",
                stepper_cfg.get("pumping_speed_rpm", 120),
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
        self.physics_enabled = True
        self._frozen_labels: set[str] = set()

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
        pump_speed_rpm: int = 0,
    ) -> None:
        """Advance simulated temperatures since the last tick."""
        if not self.physics_enabled:
            return

        now = time.monotonic()
        elapsed = max(0.0, now - self._last_advance_time)
        self._last_advance_time = now

        del set_temperature_c  # CSF no longer follows the UI setpoint in sim mode
        effective_speed = int(pump_speed_rpm) if pump_running else 0
        self._advance_heat_ex(bool(compressor_cooling), elapsed)
        self._advance_cart_temps(bool(pump_running), elapsed)
        self._advance_csf(effective_speed, elapsed)

    def _advance_csf(self, pump_speed_rpm: int, elapsed: float) -> None:
        if self._csf_label in self._frozen_labels:
            return
        if self._csf_label not in self._last_raw_temperatures:
            return

        current = self._last_raw_temperatures[self._csf_label]
        if (
            pump_speed_rpm <= 0
            or pump_speed_rpm < self._csf_min_effective_pump_speed_rpm
        ):
            step = self._csf_rate_c_per_s * elapsed
            new_raw = min(current + step, self._csf_max_c)
        else:
            cart_out = self._last_raw_temperatures.get(
                self._cart_out_label, self._cart_initial_c
            )
            speed_factor = pump_speed_rpm / max(self._csf_pump_speed_ref_rpm, 1.0)
            rate = (
                self._csf_rate_c_per_s
                * self._csf_cart_out_scale
                * (self._cart_initial_c - cart_out)
                * speed_factor
            )
            new_raw = current - rate * elapsed
            new_raw = max(min(new_raw, self._csf_max_c), self._csf_min_c)

        self._last_raw_temperatures[self._csf_label] = new_raw
        self._apply_calibration_for_label(self._csf_label)

    def _advance_heat_ex(self, compressor_on: bool, elapsed: float) -> None:
        if self._heat_ex_label in self._frozen_labels:
            return
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
        if self._cart_in_label in self._frozen_labels:
            return
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
        if self._cart_out_label in self._frozen_labels:
            return
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
            new_raw = cart_in - (cart_in - heat_ex)*0.75

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

    def set_raw_temperature(self, label: str, raw_c: float) -> None:
        if label not in self._last_raw_temperatures:
            return
        self._last_raw_temperatures[label] = float(raw_c)
        self._frozen_labels.add(label)
        self._apply_calibration_for_label(label)

    def release_temperature(self, label: str) -> None:
        self._frozen_labels.discard(label)

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


class SimThermistorReader:
    """Thermistor temperatures from config defaults (ADS1115 simulation)."""

    def __init__(self, config: dict):
        ts_cfg = config.get("thermistor_sensors", {})
        self.enabled = bool(ts_cfg.get("enabled", False))
        self.channels = [int(ch) for ch in ts_cfg.get("channels", [])]
        self.channel_labels = self._parse_labels(ts_cfg)
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._temperatures: Dict[str, float] = {}

        if not self.enabled:
            self.last_error = "ADS1115 thermistor reader disabled by config"
            return

        overrides = _sim_cfg(config).get("thermistors", {}) or {}
        for channel in self.channels:
            label = self.channel_labels.get(channel, f"Therm {channel + 1}")
            self._temperatures[label] = float(overrides.get(label, 25.0))

        self.is_initialized = bool(self._temperatures)
        if self.is_initialized:
            print(
                f"SimThermistorReader: {len(self._temperatures)} channels "
                "(simulation mode)"
            )
        else:
            self.last_error = "No valid thermistor channels configured"

    @staticmethod
    def _parse_labels(ts_cfg: dict) -> Dict[int, str]:
        raw = ts_cfg.get("labels", {}) or {}
        labels: Dict[int, str] = {}
        for key, value in raw.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        channel_configs = ts_cfg.get("channel_configs", {}) or {}
        for key, cfg in channel_configs.items():
            if not isinstance(cfg, dict) or not cfg.get("label"):
                continue
            try:
                labels[int(key)] = str(cfg["label"])
            except (TypeError, ValueError):
                continue
        return labels

    def read_temperatures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        return dict(self._temperatures)

    def set_raw_temperature(self, label: str, raw_c: float) -> None:
        if label in self._temperatures:
            self._temperatures[label] = float(raw_c)

    def cleanup(self) -> None:
        self.is_initialized = False


class SimPressureReader:
    """Pressure readings from config defaults (third ADS1115)."""

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        self.channels = ps_cfg.get("channels", [0, 1, 2, 3])
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

    def set_pressure(self, label: str, value: float) -> None:
        if label in self._pressures:
            self._pressures[label] = float(value)

    def cleanup(self) -> None:
        self.is_initialized = False
