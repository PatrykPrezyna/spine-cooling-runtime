"""Simulated sensor readers (GPIO, thermistor, pressure)."""

from __future__ import annotations

import time
from typing import Dict, Optional

from ads1115_thermistor_reader import labels_from_config
from compressor_control import heat_ex_labels_from_config


def _sim_cfg(config: dict) -> dict:
    return config.get("simulation", {}) or {}


class _SimThermalLoop:
    """Shared pump/compressor temperature dynamics for simulated readers."""

    def __init__(self, config: dict):
        sim_cfg = _sim_cfg(config)
        compressor_cfg = config.get("compressor", {}) or {}
        stepper_cfg = config.get("stepper_motor", {}) or {}
        self.csf_label = str(sim_cfg.get("csf_label", "CSF"))
        self.csf_max_c = float(sim_cfg.get("csf_max_c", 37.0))
        self.csf_min_c = float(sim_cfg.get("csf_min_c", 25.0))
        self.csf_rate_c_per_s = float(sim_cfg.get("csf_rate_c_per_s", 0.1))
        self.csf_cart_out_scale = float(
            sim_cfg.get(
                "csf_cart_out_scale",
                sim_cfg.get("csf_heat_ex_scale", 0.05),
            )
        )
        self.csf_min_effective_pump_speed_rpm = float(
            sim_cfg.get("csf_min_effective_pump_speed_rpm", 30.0)
        )
        self.csf_pump_speed_ref_rpm = float(
            sim_cfg.get(
                "csf_pump_speed_ref_rpm",
                stepper_cfg.get("pumping_speed_rpm", 120),
            )
        )
        self.heat_ex_labels = heat_ex_labels_from_config(compressor_cfg)
        sim_heat_ex = sim_cfg.get("heat_ex_label")
        if sim_heat_ex is not None and str(sim_heat_ex).strip():
            self.heat_ex_label = str(sim_heat_ex).strip()
            if self.heat_ex_label not in self.heat_ex_labels:
                self.heat_ex_labels = [self.heat_ex_label, *self.heat_ex_labels]
        else:
            self.heat_ex_label = self.heat_ex_labels[0]
        self.heat_ex_max_c = float(sim_cfg.get("heat_ex_max_c", 23.0))
        self.heat_ex_cool_rate_c_per_s = float(
            sim_cfg.get("heat_ex_cool_rate_c_per_s", 0.5)
        )
        self.heat_ex_warm_rate_c_per_s = float(
            sim_cfg.get("heat_ex_warm_rate_c_per_s", 0.02)
        )
        self.cart_in_label = str(sim_cfg.get("cart_in_label", "Cart In"))
        self.cart_out_label = str(sim_cfg.get("cart_out_label", "Cart Out"))
        self.cart_initial_c = float(sim_cfg.get("cart_initial_c", 22.0))
        self.cart_in_rise_rate_c_per_s = float(
            sim_cfg.get("cart_in_rise_rate_c_per_s", 0.2)
        )

    def advance(
        self,
        temps: Dict[str, float],
        *,
        compressor_on: bool,
        pump_running: bool,
        pump_speed_rpm: int,
        elapsed: float,
        frozen: Optional[set[str]] = None,
    ) -> list[str]:
        """Mutate ``temps`` and return labels that were written."""
        frozen = frozen or set()
        changed: list[str] = []
        changed.extend(self._advance_heat_ex(temps, compressor_on, elapsed, frozen))
        if pump_running and self._advance_cart_in(temps, elapsed, frozen):
            changed.append(self.cart_in_label)
        if self._update_cart_out(temps, pump_running, frozen):
            changed.append(self.cart_out_label)
        if self._advance_csf(temps, pump_speed_rpm, elapsed, frozen):
            changed.append(self.csf_label)
        return changed

    def _advance_csf(
        self,
        temps: Dict[str, float],
        pump_speed_rpm: int,
        elapsed: float,
        frozen: set[str],
    ) -> bool:
        if self.csf_label in frozen or self.csf_label not in temps:
            return False
        current = temps[self.csf_label]
        if pump_speed_rpm <= 0 or pump_speed_rpm < self.csf_min_effective_pump_speed_rpm:
            temps[self.csf_label] = min(current + self.csf_rate_c_per_s * elapsed, self.csf_max_c)
        else:
            cart_out = temps.get(self.cart_out_label, self.cart_initial_c)
            speed_factor = pump_speed_rpm / max(self.csf_pump_speed_ref_rpm, 1.0)
            rate = (
                self.csf_rate_c_per_s
                * self.csf_cart_out_scale
                * (self.cart_initial_c - cart_out)
                * speed_factor
            )
            new_raw = current - rate * elapsed
            temps[self.csf_label] = max(min(new_raw, self.csf_max_c), self.csf_min_c)
        return True

    def _advance_heat_ex(
        self,
        temps: Dict[str, float],
        compressor_on: bool,
        elapsed: float,
        frozen: set[str],
    ) -> list[str]:
        changed: list[str] = []
        for label in self.heat_ex_labels:
            if label in frozen or label not in temps:
                continue
            current = temps[label]
            if compressor_on:
                new_raw = current - self.heat_ex_cool_rate_c_per_s * elapsed
            else:
                new_raw = current + self.heat_ex_warm_rate_c_per_s * elapsed
            temps[label] = min(new_raw, self.heat_ex_max_c)
            changed.append(label)
        return changed

    def _advance_cart_in(
        self,
        temps: Dict[str, float],
        elapsed: float,
        frozen: set[str],
    ) -> bool:
        if self.cart_in_label in frozen or self.cart_in_label not in temps:
            return False
        if self.csf_label not in temps:
            return False
        target = temps[self.csf_label] * 0.8
        current = temps[self.cart_in_label]
        if current >= target:
            return False
        temps[self.cart_in_label] = min(
            current + self.cart_in_rise_rate_c_per_s * elapsed, target
        )
        return True

    def _update_cart_out(
        self,
        temps: Dict[str, float],
        pump_running: bool,
        frozen: set[str],
    ) -> bool:
        if self.cart_out_label in frozen or self.cart_out_label not in temps:
            return False
        if self.cart_in_label not in temps:
            return False
        cart_in = temps[self.cart_in_label]
        if not pump_running:
            temps[self.cart_out_label] = cart_in
            return True
        if self.heat_ex_label not in temps:
            return False
        heat_ex = temps[self.heat_ex_label]
        temps[self.cart_out_label] = cart_in - (cart_in - heat_ex) * 0.75
        return True


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


class SimThermistorReader:
    """Thermistor temperatures from config defaults (ADS1115 simulation).

    Uses ``_SimThermalLoop`` for labels listed under ``simulation``
    (Tip / CSF, plates, catheter). Call ``notify_setpoint()`` each tick
    before ``read_temperatures()``.
    """

    def __init__(self, config: dict):
        self.channel_labels = labels_from_config(config)
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._temperatures: Dict[str, float] = {}
        self._thermal = _SimThermalLoop(config)
        self._last_advance_time = time.monotonic()
        self.physics_enabled = True
        self._frozen_labels: set[str] = set()

        if not self.channel_labels:
            self.last_error = "No thermistor labels in config"
            return

        overrides = _sim_cfg(config).get("thermistors", {}) or {}
        for _channel, label in sorted(self.channel_labels.items()):
            self._temperatures[label] = float(overrides.get(label, 25.0))

        self.is_initialized = bool(self._temperatures)
        if self.is_initialized:
            print(
                f"SimThermistorReader: {len(self._temperatures)} channels "
                "(simulation mode)"
            )
        else:
            self.last_error = "No valid thermistor channels configured"

    def notify_setpoint(
        self,
        set_temperature_c: float,
        compressor_cooling: int = 0,
        pump_running: bool = False,
        pump_speed_rpm: int = 0,
    ) -> None:
        """Advance simulated thermistor temperatures since the last tick."""
        if not self.physics_enabled or not self.is_initialized:
            return
        del set_temperature_c
        now = time.monotonic()
        elapsed = max(0.0, now - self._last_advance_time)
        self._last_advance_time = now
        effective_speed = int(pump_speed_rpm) if pump_running else 0
        self._thermal.advance(
            self._temperatures,
            compressor_on=bool(compressor_cooling),
            pump_running=bool(pump_running),
            pump_speed_rpm=effective_speed,
            elapsed=elapsed,
            frozen=self._frozen_labels,
        )

    def read_temperatures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        return dict(self._temperatures)

    def get_last_raw_temperatures(self) -> Dict[str, float]:
        return dict(self._temperatures)

    def set_raw_temperature(self, label: str, raw_c: float) -> None:
        if label not in self._temperatures:
            return
        self._temperatures[label] = float(raw_c)
        self._frozen_labels.add(label)

    def release_temperature(self, label: str) -> None:
        self._frozen_labels.discard(label)

    def cleanup(self) -> None:
        self.is_initialized = False


class SimPressureReader:
    """Pressure readings from config defaults (differential ADS1115 simulation)."""

    def __init__(self, config: dict):
        ps_cfg = config.get("pressure_sensors", {})
        self.enabled = bool(ps_cfg.get("enabled", False))
        self.channels = ps_cfg.get("channels", [0, 1, 2, 3])
        self.channel_labels = self._parse_labels(ps_cfg)
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

    @staticmethod
    def _parse_labels(ps_cfg: dict) -> Dict[int, str]:
        raw = ps_cfg.get("labels", {}) or {}
        labels: Dict[int, str] = {}
        for key, value in raw.items():
            try:
                labels[int(key)] = str(value)
            except (TypeError, ValueError):
                continue
        channel_configs = ps_cfg.get("channel_configs", {}) or {}
        for key, cfg in channel_configs.items():
            if not isinstance(cfg, dict) or not cfg.get("label"):
                continue
            try:
                labels[int(key)] = str(cfg["label"])
            except (TypeError, ValueError):
                continue
        return labels

    def _channel_label(self, channel: int) -> str:
        return self.channel_labels.get(channel, f"Pressure {channel + 1}")

    def read_pressures(self) -> Dict[str, float]:
        if not self.is_initialized:
            return {}
        return dict(self._pressures)

    def set_pressure(self, label: str, value: float) -> None:
        if label in self._pressures:
            self._pressures[label] = float(value)

    def cleanup(self) -> None:
        self.is_initialized = False


class SimFlowReader:
    """Flow in ml/min from ``simulation.flow_ml_per_min``."""

    def __init__(self, config: dict):
        fs_cfg = config.get("flow_sensor", {}) or {}
        self.enabled = bool(fs_cfg.get("enabled", False))
        self.last_error: Optional[str] = None
        self.is_initialized = False
        self._flow_ml_per_min = 0.0

        if not self.enabled:
            self.last_error = "Flow sensor disabled by config"
            return

        sim = config.get("simulation", {}) or {}
        self._flow_ml_per_min = float(sim.get("flow_ml_per_min", 30.0))
        self.is_initialized = True
        print(f"SimFlowReader: {self._flow_ml_per_min:.1f} ml/min (simulation mode)")

    def read_flow_ml_per_min(self) -> Optional[float]:
        if not self.is_initialized:
            return None
        return float(self._flow_ml_per_min)

    def set_flow_ml_per_min(self, value: float) -> None:
        self._flow_ml_per_min = float(value)

    def cleanup(self) -> None:
        self.is_initialized = False
